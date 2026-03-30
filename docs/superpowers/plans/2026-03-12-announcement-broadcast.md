# Announcement Broadcast Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable admins to broadcast announcements to all users through their personalized assistants via a Slack DM command.

**Architecture:** Two components — (1) new `announce:` route + pending-action confirmation in the Slack Events Handler workflow, (2) new "Announcement Broadcast" sub-workflow for fan-out delivery with Claude personalization per assistant voice.

**Tech Stack:** n8n workflows (modified via Python scripts + n8n REST API), Supabase (PostgreSQL), Slack API, Anthropic Claude API

**Spec:** `docs/superpowers/specs/2026-03-12-announcement-broadcast-design.md`

---

## Chunk 1: Database Seed + Sub-workflow

### Task 1: Seed `announcement` feature_catalog row

**Files:**
- Create: `supabase/migrations/009_announcement_feature.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Migration 009: Announcement feature catalog entry
-- Required by the Announcement Broadcast workflow for education_log FK.

INSERT INTO feature_catalog (id, display_name, description, how_to_use, category)
VALUES (
    'announcement',
    'Announcements',
    'Broadcast messages from admins through personalized assistants.',
    'Admin-only: DM "announce: <message>" to broadcast.',
    'core'
)
ON CONFLICT (id) DO NOTHING;
```

- [ ] **Step 2: Run in Supabase SQL Editor**

Copy the SQL above and execute in the Supabase SQL Editor at `https://rhrlnkbphxntxxxcrgvv.supabase.co`. Verify with:

```sql
SELECT * FROM feature_catalog WHERE id = 'announcement';
```

Expected: one row returned.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/009_announcement_feature.sql
git commit -m "feat: add announcement feature_catalog seed row"
```

---

### Task 2: Create the Announcement Broadcast sub-workflow script

**Files:**
- Create: `scripts/create_announcement_broadcast.py`
- Uses: `scripts/n8n_helpers.py` (all helpers, node factories, credentials)

This script creates the "Announcement Broadcast" sub-workflow with 10 nodes.

- [ ] **Step 1: Write the script — imports and node definitions**

```python
"""
Create the Announcement Broadcast sub-workflow.

Fan-out workflow: receives an announcement message + admin channel ID,
personalizes it per user's assistant voice via Claude, delivers via Slack DM,
logs to education_log, and notifies admin on completion.

Usage:
    N8N_API_KEY=... python scripts/create_announcement_broadcast.py
"""

from n8n_helpers import (
    uid, create_or_update_workflow,
    make_code_node, make_slack_http_node, make_supabase_http_node,
    SUPABASE_CRED, ANTHROPIC_CRED, SLACK_CRED, SUPABASE_URL,
    SLACK_CONVERSATIONS_OPEN, SLACK_CHAT_POST,
    NODE_SPLIT_IN_BATCHES, NODE_AGENT, NODE_ANTHROPIC_CHAT,
    MODEL_SONNET,
)


def build_workflow():
    nodes = []
    connections = {}

    # ── Node 1: Execute Workflow Trigger ──────────────────────────────
    trigger = {
        "parameters": {"inputSource": "passthrough"},
        "id": uid(),
        "name": "Execute Workflow Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
    }
    nodes.append(trigger)

    # ── Node 2: Fetch Users (Supabase getAll) ─────────────────────────
    fetch_users = {
        "parameters": {
            "operation": "getAll",
            "tableId": "users",
            "returnAll": True,
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Users",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [220, 0],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(fetch_users)

    # ── Node 3: Filter Active + Opted-in ──────────────────────────────
    filter_code = """
const users = $input.all();
const message = $('Execute Workflow Trigger').first().json.message;
const adminChannelId = $('Execute Workflow Trigger').first().json.admin_channel_id;

const active = users.filter(u =>
  u.json.onboarding_state === 'complete' &&
  u.json.announcements_enabled !== false
);

return active.map(u => ({
  json: {
    ...u.json,
    announcementMessage: message,
    adminChannelId: adminChannelId,
    totalUsers: active.length,
  }
}));
"""
    filter_node = make_code_node("Filter Active Users", filter_code, [440, 0])
    nodes.append(filter_node)

    # ── Node 4: SplitInBatches ────────────────────────────────────────
    split = {
        "parameters": {"batchSize": 1, "options": {}},
        "id": uid(),
        "name": "SplitInBatches",
        "type": NODE_SPLIT_IN_BATCHES,
        "typeVersion": 3,
        "position": [660, 0],
    }
    nodes.append(split)

    # ── Node 5: Resolve Identity ──────────────────────────────────────
    resolve_code = """
const user = $json;

const assistantName = user.assistant_name || 'Aria';
const assistantEmoji = user.assistant_emoji || ':robot_face:';
const persona = user.assistant_persona || 'friendly and helpful';

const prompt = `You are ${assistantName}. Rephrase this announcement in your voice (personality: ${persona}). Keep it concise — 2-3 sentences max. Don't change the core information, just wrap it in your style. Use Slack formatting (*bold*, _italic_, bullet points). Do NOT use markdown headers.

Announcement: ${user.announcementMessage}`;

return [{
  json: {
    ...user,
    assistantName,
    assistantEmoji,
    persona,
    personalizePrompt: prompt,
  }
}];
"""
    resolve_node = make_code_node("Resolve Identity", resolve_code, [880, 100])
    nodes.append(resolve_node)

    # ── Node 6: Personalize via Claude (Agent node, no MCP needed) ────
    personalize_agent = {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.personalizePrompt }}",
            "options": {
                "maxIterations": 1,
            },
        },
        "id": uid(),
        "name": "Personalize Message",
        "type": NODE_AGENT,
        "typeVersion": 1.7,
        "position": [1100, 100],
        "continueOnFail": True,
    }
    nodes.append(personalize_agent)

    personalize_model = {
        "parameters": {
            "model": {
                "__rl": True, "mode": "list",
                "value": MODEL_SONNET,
                "cachedResultName": "Claude Sonnet 4.5",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Anthropic Chat Model (Announce)",
        "type": NODE_ANTHROPIC_CHAT,
        "typeVersion": 1.3,
        "position": [1050, 300],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }
    nodes.append(personalize_model)

    # Wire model → agent
    connections["Anthropic Chat Model (Announce)"] = {
        "ai_languageModel": [[{
            "node": "Personalize Message",
            "type": "ai_languageModel",
            "index": 0,
        }]]
    }

    # ── Node 7: Open Bot DM ───────────────────────────────────────────
    open_dm = make_slack_http_node(
        "Open Bot DM",
        SLACK_CONVERSATIONS_OPEN,
        '={{ JSON.stringify({ users: $json.slack_user_id }) }}',
        [1320, 100],
    )
    open_dm["continueOnFail"] = True
    nodes.append(open_dm)

    # ── Node 8: Send Announcement ─────────────────────────────────────
    send_body = """={{
JSON.stringify({
  channel: $json.channel.id,
  text: $('Personalize Message').first().json.output || $('Resolve Identity').first().json.announcementMessage,
  username: $('Resolve Identity').first().json.assistantName,
  icon_emoji: $('Resolve Identity').first().json.assistantEmoji,
})
}}"""
    send_msg = make_slack_http_node(
        "Send Announcement",
        SLACK_CHAT_POST,
        send_body,
        [1540, 100],
    )
    send_msg["continueOnFail"] = True
    nodes.append(send_msg)

    # ── Node 9: Log to education_log ──────────────────────────────────
    log_code = """
const user = $('Resolve Identity').first().json;
const personalizedText = $('Personalize Message').first().json.output || '';
const sendResult = $json;

return [{
  json: {
    user_id: user.id,
    feature_id: 'announcement',
    trigger_type: 'announcement',
    message_text: personalizedText,
    slack_message_ts: sendResult.ts || null,
    slack_channel_id: sendResult.channel || null,
  }
}];
"""
    log_prepare = make_code_node("Prepare Log Entry", log_code, [1760, 100])
    nodes.append(log_prepare)

    log_insert = make_supabase_http_node(
        "Log to education_log",
        "POST",
        "education_log",
        [1980, 100],
        json_body='={{ JSON.stringify($json) }}',
    )
    log_insert["continueOnFail"] = True
    nodes.append(log_insert)

    # ── Node 10: Notify Admin (after loop done) ───────────────────────
    notify_code = """
const trigger = $('Execute Workflow Trigger').first().json;
const adminChannelId = trigger.admin_channel_id;
// Count is from the first item that went through the filter
const totalUsers = $('Filter Active Users').first().json.totalUsers || 0;

return [{
  json: {
    channel: adminChannelId,
    text: `Announcement delivered to *${totalUsers}* users.`,
  }
}];
"""
    notify_prepare = make_code_node("Prepare Admin Notification", notify_code, [880, -200])
    nodes.append(notify_prepare)

    notify_send = make_slack_http_node(
        "Notify Admin",
        SLACK_CHAT_POST,
        '={{ JSON.stringify({ channel: $json.channel, text: $json.text }) }}',
        [1100, -200],
    )
    nodes.append(notify_send)

    # ── Connections ───────────────────────────────────────────────────
    connections["Execute Workflow Trigger"] = {
        "main": [[{"node": "Fetch Users", "type": "main", "index": 0}]]
    }
    connections["Fetch Users"] = {
        "main": [[{"node": "Filter Active Users", "type": "main", "index": 0}]]
    }
    connections["Filter Active Users"] = {
        "main": [[{"node": "SplitInBatches", "type": "main", "index": 0}]]
    }
    # SplitInBatches: output 0 = done, output 1 = loop
    connections["SplitInBatches"] = {
        "main": [
            [{"node": "Prepare Admin Notification", "type": "main", "index": 0}],
            [{"node": "Resolve Identity", "type": "main", "index": 0}],
        ]
    }
    connections["Resolve Identity"] = {
        "main": [[{"node": "Personalize Message", "type": "main", "index": 0}]]
    }
    connections["Personalize Message"] = {
        "main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]
    }
    connections["Open Bot DM"] = {
        "main": [[{"node": "Send Announcement", "type": "main", "index": 0}]]
    }
    connections["Send Announcement"] = {
        "main": [[{"node": "Prepare Log Entry", "type": "main", "index": 0}]]
    }
    connections["Prepare Log Entry"] = {
        "main": [[{"node": "Log to education_log", "type": "main", "index": 0}]]
    }
    connections["Log to education_log"] = {
        "main": [[{"node": "SplitInBatches", "type": "main", "index": 0}]]
    }
    connections["Prepare Admin Notification"] = {
        "main": [[{"node": "Notify Admin", "type": "main", "index": 0}]]
    }

    return {
        "name": "Announcement Broadcast",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


if __name__ == "__main__":
    wf = build_workflow()
    result = create_or_update_workflow(wf, "Announcement Broadcast.json")
    print(f"\nDone! Workflow ID: {result['id']}")
```

- [ ] **Step 2: Run the script to create the workflow**

```bash
cd /Users/scottmetcalf/projects/oppassistant
N8N_API_KEY=<key> python scripts/create_announcement_broadcast.py
```

Expected output:
```
Looking for existing 'Announcement Broadcast' workflow...
  Not found — creating new workflow
  Created: <workflow-id>
=== Activating workflow <id> ===
  Activated
=== Syncing ===
  Synced .../n8n/workflows/Announcement Broadcast.json
Done! Workflow ID: <id>
```

- [ ] **Step 3: Verify in n8n UI**

Open `https://scottai.trackslife.com` → Workflows → "Announcement Broadcast". Confirm:
- 13 nodes visible (trigger, fetch, filter, split, resolve, agent, model, open DM, send, prepare log, log insert, prepare notify, notify send)
- Execute Workflow Trigger → Fetch Users → Filter → SplitInBatches (two outputs) → loop path + done path
- Workflow is active

- [ ] **Step 4: Commit**

```bash
git add scripts/create_announcement_broadcast.py n8n/workflows/Announcement\ Broadcast.json
git commit -m "feat: create Announcement Broadcast sub-workflow"
```

---

## Chunk 2: Slack Events Handler Modifications

### Task 3: Add `announce:` route + pending action routing to Slack Events Handler

**Files:**
- Create: `scripts/add_announce_route.py`
- Modifies: Slack Events Handler workflow (ID `QuQbIaWetunUOFUW`) via n8n API

This script modifies the live Slack Events Handler to add:
1. `announce:` command detection in Route by State
2. Pending action check (`send`/`cancel` confirmation)
3. Three new Switch outputs (announce, confirm, cancel)
4. Six new nodes for the announce flow

- [ ] **Step 1: Write the script — Route by State modification**

The Route by State Code node needs two additions:
- Add `announce:` to Pass 1 exact matching
- Add pending action routing for `send`/`cancel` (reads from a new upstream node)

Updated Route by State JavaScript — add these lines to the `state === 'complete'` block, Pass 1, **before** the existing `if (lower.startsWith('rename '))` line:

```javascript
  // --- Pending action routing (announcement confirmation) ---
  const pendingAction = $('Check Pending Action').first().json;
  const hasPending = Array.isArray(pendingAction) ? pendingAction.length > 0
    : (pendingAction && pendingAction.id);

  if (hasPending) {
    if (lower === 'send') { route = 'confirm_announce'; }
    else if (lower === 'cancel') { route = 'cancel_announce'; }
    // Any other text: ignore pending action, route normally
  }

  // --- Pass 1: Exact command matching ---
  if (route === 'unknown' && lower.startsWith('announce:')) route = 'cmd_announce';
  else if (route === 'unknown' && lower.startsWith('announce ')) route = 'cmd_announce';
```

The full script (`scripts/add_announce_route.py`):

```python
"""
Add announcement broadcast route to the Slack Events Handler.

Adds:
1. 'Check Pending Action' HTTP Request node (before Route by State)
2. 'announce:' detection in Route by State code
3. Three new Switch outputs: cmd_announce, confirm_announce, cancel_announce
4. Admin Gate code node
5. Fetch Eligible Users node
6. Preview + Store Pending Action code node
7. Send Preview node
8. Store Pending Action HTTP Request node
9. Confirm Announce code node + Execute Sub-workflow node
10. Cancel Announce code node + Update Pending Action node + Send Cancel Confirmation

Usage:
    N8N_API_KEY=... python scripts/add_announce_route.py
"""

import json
from n8n_helpers import (
    uid, find_node, modify_workflow,
    make_code_node, make_slack_http_node, make_supabase_http_node,
    make_switch_condition, make_switch_rule,
    SUPABASE_CRED, SLACK_CRED, SUPABASE_URL,
    SLACK_CHAT_POST,
    WF_EVENTS_HANDLER,
)


def modifier(nodes, connections):
    changes = 0

    # ── 1. Add "Check Pending Action" node ────────────────────────────
    # HTTP GET to Supabase REST API to check for pending announcement actions
    # Placed between "Lookup User" and "Route by State"
    lookup_node = find_node(nodes, "Lookup User")
    route_node = find_node(nodes, "Route by State")

    if not lookup_node or not route_node:
        print("ERROR: Could not find 'Lookup User' or 'Route by State' nodes")
        return 0

    # Position between Lookup User and Route by State
    lu_pos = lookup_node["position"]
    rs_pos = route_node["position"]
    mid_x = (lu_pos[0] + rs_pos[0]) // 2
    mid_y = lu_pos[1]

    check_pending = make_supabase_http_node(
        "Check Pending Action",
        "GET",
        "pending_actions?action_type=eq.announcement_broadcast&status=eq.pending&user_id=eq.{{ $('Lookup User').first().json.id }}",
        [mid_x, mid_y],
        extra_headers=[
            {"name": "Prefer", "value": "return=representation"},
            {"name": "Accept", "value": "application/json"},
        ],
    )
    check_pending["continueOnFail"] = True
    nodes.append(check_pending)
    changes += 1

    # Rewire: Lookup User → Check Pending Action → Route by State
    # Find and update the Lookup User → Route by State connection
    if "Lookup User" in connections:
        for output in connections["Lookup User"].get("main", []):
            for conn in output:
                if conn["node"] == "Route by State":
                    conn["node"] = "Check Pending Action"
                    break

    connections["Check Pending Action"] = {
        "main": [[{"node": "Route by State", "type": "main", "index": 0}]]
    }
    changes += 1

    # ── 2. Update Route by State code ─────────────────────────────────
    old_code = route_node["parameters"]["jsCode"]

    # Insert pending action check + announce command detection
    pending_block = """
  // --- Pending action routing (announcement confirmation) ---
  const pendingRaw = $('Check Pending Action').first().json;
  const hasPending = Array.isArray(pendingRaw)
    ? pendingRaw.length > 0 && pendingRaw[0].id
    : (pendingRaw && pendingRaw.id);

  if (hasPending) {
    if (lower === 'send') route = 'confirm_announce';
    else if (lower === 'cancel') route = 'cancel_announce';
    else route = 'expire_pending'; // clear stale pending, then route normally
  }

  // Announce command
  if (route === 'unknown' && (lower.startsWith('announce:') || lower.startsWith('announce '))) {
    route = 'cmd_announce';
  }

"""

    # Insert right after: const lower = text.toLowerCase();
    # and the blank line that follows it
    marker = "// --- Pass 1: Exact command matching (keyword at start of text) ---"
    if marker in old_code:
        new_code = old_code.replace(marker, pending_block + "  " + marker)
        route_node["parameters"]["jsCode"] = new_code
        changes += 1
    else:
        print("WARNING: Could not find Pass 1 marker in Route by State code")

    # ── 3. Add three new Switch outputs ───────────────────────────────
    switch_node = find_node(nodes, "Switch Route")
    if not switch_node:
        print("ERROR: Could not find 'Switch Route' node")
        return changes

    rules = switch_node["parameters"]["rules"]["values"]

    rules.append(make_switch_rule(
        "cmd_announce", "={{ $json.route }}", "cmd_announce"
    ))
    rules.append(make_switch_rule(
        "confirm_announce", "={{ $json.route }}", "confirm_announce"
    ))
    rules.append(make_switch_rule(
        "cancel_announce", "={{ $json.route }}", "cancel_announce"
    ))
    rules.append(make_switch_rule(
        "expire_pending", "={{ $json.route }}", "expire_pending"
    ))
    changes += 4

    # Get switch position for placing new nodes
    sw_pos = switch_node["position"]
    base_x = sw_pos[0] + 400
    base_y = sw_pos[1] + 1200  # Below existing routes

    # ── 4. Admin Gate node ────────────────────────────────────────────
    admin_gate_code = """
const ADMIN_IDS = ['U061WJ6RMJS']; // Scott

const route = $json;
const slackUserId = route.userId;
const isAdmin = ADMIN_IDS.includes(slackUserId);

// Extract message text after "announce:" or "announce "
let messageText = route.text;
if (messageText.toLowerCase().startsWith('announce:')) {
  messageText = messageText.slice(9).trim();
} else if (messageText.toLowerCase().startsWith('announce ')) {
  messageText = messageText.slice(9).trim();
}

return [{
  json: {
    ...route,
    isAdmin,
    announcementText: messageText,
  }
}];
"""
    admin_gate = make_code_node("Admin Gate", admin_gate_code, [base_x, base_y])
    nodes.append(admin_gate)
    changes += 1

    # ── 5. Is Admin? (If node) ────────────────────────────────────────
    is_admin = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                    "leftValue": "={{ $json.isAdmin }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Is Admin?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [base_x + 250, base_y],
    }
    nodes.append(is_admin)
    changes += 1

    # ── 6. Not Admin Reply ────────────────────────────────────────────
    not_admin_body = """={{
JSON.stringify({
  channel: $json.channelId,
  text: "Sorry, only admins can send announcements.",
  username: $json.assistantName,
  icon_emoji: $json.assistantEmoji,
})
}}"""
    not_admin = make_slack_http_node(
        "Not Admin Reply",
        SLACK_CHAT_POST,
        not_admin_body,
        [base_x + 500, base_y + 150],
    )
    nodes.append(not_admin)
    changes += 1

    # ── 7. Check Existing Pending ─────────────────────────────────────
    check_existing = make_supabase_http_node(
        "Check Existing Announce",
        "GET",
        "pending_actions?action_type=eq.announcement_broadcast&status=eq.pending&user_id=eq.{{ $json.dbUserId }}",
        [base_x + 500, base_y - 150],
        extra_headers=[
            {"name": "Prefer", "value": "return=representation"},
            {"name": "Accept", "value": "application/json"},
        ],
    )
    nodes.append(check_existing)
    changes += 1

    # ── 8. Fetch Eligible Users (count) ───────────────────────────────
    fetch_eligible = {
        "parameters": {
            "operation": "getAll",
            "tableId": "users",
            "returnAll": True,
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Eligible Users",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [base_x + 750, base_y - 150],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(fetch_eligible)
    changes += 1

    # ── 9. Build Preview ──────────────────────────────────────────────
    preview_code = """
const route = $('Admin Gate').first().json;
const allUsers = $input.all();
const existingPending = $('Check Existing Announce').first().json;

// Check for existing pending announcement
const hasDuplicate = Array.isArray(existingPending)
  ? existingPending.length > 0
  : (existingPending && existingPending.id);

if (hasDuplicate) {
  return [{
    json: {
      channel: route.channelId,
      text: "You already have a pending announcement — reply *send* or *cancel* first.",
      username: route.assistantName,
      icon_emoji: route.assistantEmoji,
      shouldStore: false,
    }
  }];
}

// Count eligible users
const eligible = allUsers.filter(u =>
  u.json.onboarding_state === 'complete' &&
  u.json.announcements_enabled !== false
);

if (eligible.length === 0) {
  return [{
    json: {
      channel: route.channelId,
      text: "No users have announcements enabled — nothing to send.",
      username: route.assistantName,
      icon_emoji: route.assistantEmoji,
      shouldStore: false,
    }
  }];
}

return [{
  json: {
    channel: route.channelId,
    text: `Will send this announcement to *${eligible.length}* users through their assistants:\\n\\n_Your message:_ ${route.announcementText}\\n\\nReply *send* to confirm or *cancel* to abort.`,
    username: route.assistantName,
    icon_emoji: route.assistantEmoji,
    shouldStore: true,
    userId: route.dbUserId,
    announcementText: route.announcementText,
    userCount: eligible.length,
    adminSlackId: route.userId,
  }
}];
"""
    preview_node = make_code_node("Build Preview", preview_code, [base_x + 1000, base_y - 150])
    nodes.append(preview_node)
    changes += 1

    # ── 10. Send Preview ──────────────────────────────────────────────
    send_preview = make_slack_http_node(
        "Send Preview",
        SLACK_CHAT_POST,
        '={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji }) }}',
        [base_x + 1250, base_y - 150],
    )
    nodes.append(send_preview)
    changes += 1

    # ── 11. Should Store? (If node) ───────────────────────────────────
    should_store = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                    "leftValue": "={{ $('Build Preview').first().json.shouldStore }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Should Store?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [base_x + 1500, base_y - 150],
    }
    nodes.append(should_store)
    changes += 1

    # ── 12. Store Pending Action ──────────────────────────────────────
    store_code = """
const data = $('Build Preview').first().json;
return [{
  json: {
    user_id: data.userId,
    action_type: 'announcement_broadcast',
    draft_content: data.announcementText,
    context: { user_count: data.userCount, admin_slack_id: data.adminSlackId },
    status: 'pending',
  }
}];
"""
    store_prepare = make_code_node("Prepare Pending Action", store_code, [base_x + 1750, base_y - 250])
    nodes.append(store_prepare)
    changes += 1

    store_insert = make_supabase_http_node(
        "Store Pending Action",
        "POST",
        "pending_actions",
        [base_x + 2000, base_y - 250],
        json_body='={{ JSON.stringify($json) }}',
    )
    nodes.append(store_insert)
    changes += 1

    # ── 13. Confirm Announce path ─────────────────────────────────────
    confirm_code = """
const route = $json;
// Get pending action from the pre-route check
const pendingRaw = $('Check Pending Action').first().json;
const pending = Array.isArray(pendingRaw) ? pendingRaw[0] : pendingRaw;

return [{
  json: {
    ...route,
    pendingActionId: pending.id,
    announcementText: pending.draft_content,
    userCount: JSON.parse(pending.context || '{}').user_count || 0,
    adminChannelId: route.channelId,
  }
}];
"""
    confirm_node = make_code_node(
        "Prepare Confirm", confirm_code, [base_x, base_y + 300]
    )
    nodes.append(confirm_node)
    changes += 1

    # Update pending action status to 'approved'
    update_approved = make_supabase_http_node(
        "Mark Approved",
        "PATCH",
        "pending_actions?id=eq.{{ $json.pendingActionId }}",
        [base_x + 250, base_y + 300],
        json_body='={{ JSON.stringify({ status: "approved" }) }}',
    )
    nodes.append(update_approved)
    changes += 1

    # Send "Sending now" confirmation
    sending_body = """={{
JSON.stringify({
  channel: $('Prepare Confirm').first().json.adminChannelId,
  text: `Sending announcement to *${$('Prepare Confirm').first().json.userCount}* users now.`,
  username: $('Prepare Confirm').first().json.assistantName,
  icon_emoji: $('Prepare Confirm').first().json.assistantEmoji,
})
}}"""
    send_confirm = make_slack_http_node(
        "Send Confirm Reply", SLACK_CHAT_POST, sending_body,
        [base_x + 500, base_y + 300],
    )
    nodes.append(send_confirm)
    changes += 1

    # Execute Announcement Broadcast sub-workflow
    execute_broadcast = {
        "parameters": {
            "source": "database",
            "workflowId": {
                "__rl": True,
                "mode": "list",
                "value": "",  # Will be set after sub-workflow is created
            },
            "options": {},
        },
        "id": uid(),
        "name": "Execute Broadcast",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [base_x + 750, base_y + 300],
    }
    nodes.append(execute_broadcast)
    changes += 1

    # Prepare broadcast input
    broadcast_input_code = """
const data = $('Prepare Confirm').first().json;
return [{
  json: {
    message: data.announcementText,
    admin_channel_id: data.adminChannelId,
  }
}];
"""
    broadcast_input = make_code_node(
        "Prepare Broadcast Input", broadcast_input_code,
        [base_x + 500, base_y + 450],
    )
    nodes.append(broadcast_input)
    changes += 1

    # ── 14. Cancel Announce path ──────────────────────────────────────
    cancel_code = """
const route = $json;
const pendingRaw = $('Check Pending Action').first().json;
const pending = Array.isArray(pendingRaw) ? pendingRaw[0] : pendingRaw;

return [{
  json: {
    ...route,
    pendingActionId: pending.id,
  }
}];
"""
    cancel_node = make_code_node(
        "Prepare Cancel", cancel_code, [base_x, base_y + 600]
    )
    nodes.append(cancel_node)
    changes += 1

    # Update pending action status to 'rejected'
    update_rejected = make_supabase_http_node(
        "Mark Rejected",
        "PATCH",
        "pending_actions?id=eq.{{ $json.pendingActionId }}",
        [base_x + 250, base_y + 600],
        json_body='={{ JSON.stringify({ status: "rejected" }) }}',
    )
    nodes.append(update_rejected)
    changes += 1

    # Send cancel confirmation
    cancel_body = """={{
JSON.stringify({
  channel: $('Prepare Cancel').first().json.channelId,
  text: "Announcement cancelled.",
  username: $('Prepare Cancel').first().json.assistantName,
  icon_emoji: $('Prepare Cancel').first().json.assistantEmoji,
})
}}"""
    send_cancel = make_slack_http_node(
        "Send Cancel Reply", SLACK_CHAT_POST, cancel_body,
        [base_x + 500, base_y + 600],
    )
    nodes.append(send_cancel)
    changes += 1

    # ── 15. Expire Pending path ──────────────────────────────────────
    # When user has pending action but types something other than send/cancel,
    # expire the pending action and re-route through normal command matching.
    expire_code = """
const route = $json;
const pendingRaw = $('Check Pending Action').first().json;
const pending = Array.isArray(pendingRaw) ? pendingRaw[0] : pendingRaw;

return [{
  json: {
    pendingActionId: pending.id,
  }
}];
"""
    expire_node = make_code_node(
        "Prepare Expire", expire_code, [base_x, base_y + 900]
    )
    nodes.append(expire_node)
    changes += 1

    expire_update = make_supabase_http_node(
        "Mark Expired",
        "PATCH",
        "pending_actions?id=eq.{{ $json.pendingActionId }}",
        [base_x + 250, base_y + 900],
        json_body='={{ JSON.stringify({ status: "expired" }) }}',
    )
    nodes.append(expire_update)
    changes += 1

    # Note: After expiring, the message is NOT re-routed to normal commands
    # in this execution. The user's text was already consumed. They'll need
    # to type their actual command again. This is acceptable for v1.

    # ── Wire new connections ──────────────────────────────────────────
    # Find the current number of Switch outputs (the new ones are at the end)
    num_existing = len(switch_node["parameters"]["rules"]["values"]) - 4
    announce_idx = num_existing
    confirm_idx = num_existing + 1
    cancel_idx = num_existing + 2
    expire_idx = num_existing + 3

    # Ensure Switch Route has enough main outputs in connections
    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}

    switch_main = connections["Switch Route"]["main"]
    # Pad with empty arrays up to the new indices
    while len(switch_main) <= expire_idx:
        switch_main.append([])

    switch_main[announce_idx] = [{"node": "Admin Gate", "type": "main", "index": 0}]
    switch_main[confirm_idx] = [{"node": "Prepare Confirm", "type": "main", "index": 0}]
    switch_main[cancel_idx] = [{"node": "Prepare Cancel", "type": "main", "index": 0}]
    switch_main[expire_idx] = [{"node": "Prepare Expire", "type": "main", "index": 0}]

    # Admin Gate → Is Admin?
    connections["Admin Gate"] = {
        "main": [[{"node": "Is Admin?", "type": "main", "index": 0}]]
    }
    # Is Admin? output 0 (true) → Check Existing Announce, output 1 (false) → Not Admin Reply
    connections["Is Admin?"] = {
        "main": [
            [{"node": "Check Existing Announce", "type": "main", "index": 0}],
            [{"node": "Not Admin Reply", "type": "main", "index": 0}],
        ]
    }
    connections["Check Existing Announce"] = {
        "main": [[{"node": "Fetch Eligible Users", "type": "main", "index": 0}]]
    }
    connections["Fetch Eligible Users"] = {
        "main": [[{"node": "Build Preview", "type": "main", "index": 0}]]
    }
    connections["Build Preview"] = {
        "main": [[{"node": "Send Preview", "type": "main", "index": 0}]]
    }
    connections["Send Preview"] = {
        "main": [[{"node": "Should Store?", "type": "main", "index": 0}]]
    }
    # Should Store? true → Prepare Pending Action, false → (end)
    connections["Should Store?"] = {
        "main": [
            [{"node": "Prepare Pending Action", "type": "main", "index": 0}],
            [],  # false: no further action
        ]
    }
    connections["Prepare Pending Action"] = {
        "main": [[{"node": "Store Pending Action", "type": "main", "index": 0}]]
    }

    # Confirm path
    connections["Prepare Confirm"] = {
        "main": [[{"node": "Mark Approved", "type": "main", "index": 0}]]
    }
    connections["Mark Approved"] = {
        "main": [[{"node": "Send Confirm Reply", "type": "main", "index": 0}]]
    }
    connections["Send Confirm Reply"] = {
        "main": [[{"node": "Prepare Broadcast Input", "type": "main", "index": 0}]]
    }
    connections["Prepare Broadcast Input"] = {
        "main": [[{"node": "Execute Broadcast", "type": "main", "index": 0}]]
    }

    # Cancel path
    connections["Prepare Cancel"] = {
        "main": [[{"node": "Mark Rejected", "type": "main", "index": 0}]]
    }
    connections["Mark Rejected"] = {
        "main": [[{"node": "Send Cancel Reply", "type": "main", "index": 0}]]
    }

    # Expire path
    connections["Prepare Expire"] = {
        "main": [[{"node": "Mark Expired", "type": "main", "index": 0}]]
    }
    # Mark Expired is a terminal node — the user's text was consumed.
    # They'll need to retype their actual command.

    return changes


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
```

- [ ] **Step 2: Run the script**

```bash
cd /Users/scottmetcalf/projects/oppassistant
N8N_API_KEY=<key> python scripts/add_announce_route.py
```

Expected: `Pushing workflow (N changes)` followed by sync confirmation.

- [ ] **Step 3: Set the sub-workflow ID in Execute Broadcast node**

After both scripts have run, update the Execute Broadcast node's `workflowId` to point to the Announcement Broadcast workflow. You can do this in the n8n UI:

1. Open "Slack Events Handler" workflow
2. Find "Execute Broadcast" node
3. Set the workflow to "Announcement Broadcast"
4. Save

Alternatively, write a small script:

```python
from n8n_helpers import fetch_workflow, push_workflow, find_node, WF_EVENTS_HANDLER
import requests, os

# Find the Announcement Broadcast workflow ID
headers = {"X-N8N-API-KEY": os.getenv("N8N_API_KEY"), "Content-Type": "application/json"}
resp = requests.get("https://scottai.trackslife.com/api/v1/workflows", headers=headers)
broadcast_id = None
for w in resp.json().get("data", []):
    if w["name"] == "Announcement Broadcast":
        broadcast_id = w["id"]
        break

if broadcast_id:
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    node = find_node(wf["nodes"], "Execute Broadcast")
    node["parameters"]["workflowId"]["value"] = broadcast_id
    push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"Set Execute Broadcast → {broadcast_id}")
```

- [ ] **Step 4: Verify in n8n UI**

Open Slack Events Handler workflow and verify:
- "Check Pending Action" node sits between "Lookup User" and "Route by State"
- Switch Route has 3 new outputs at the end: cmd_announce, confirm_announce, cancel_announce
- cmd_announce → Admin Gate → Is Admin? → (true) Check Existing → Fetch Eligible → Build Preview → Send Preview → Should Store? → Store
- confirm_announce → Prepare Confirm → Mark Approved → Send Confirm Reply → Prepare Broadcast Input → Execute Broadcast
- cancel_announce → Prepare Cancel → Mark Rejected → Send Cancel Reply

- [ ] **Step 5: Commit**

```bash
git add scripts/add_announce_route.py n8n/workflows/Slack\ Events\ Handler.json
git commit -m "feat: add announce command route to Slack Events Handler"
```

---

## Chunk 3: End-to-End Testing

### Task 4: Test the full announcement flow

- [ ] **Step 1: Test admin gate — non-admin rejection**

Temporarily remove your Slack ID from the `ADMIN_IDS` array (or test from a different Slack account). DM the bot:
```
announce: Test announcement
```
Expected: Bot replies "Sorry, only admins can send announcements."

Restore your Slack ID in `ADMIN_IDS` after testing.

- [ ] **Step 2: Test preview + confirmation flow**

DM the bot:
```
announce: We just launched a new Backstory Presentation skill! Type "presentation" followed by an account name to generate a slide deck.
```

Expected: Bot replies with preview showing user count and your message, asking to reply `send` or `cancel`.

- [ ] **Step 3: Test cancel**

Reply:
```
cancel
```

Expected: Bot replies "Announcement cancelled." Check Supabase `pending_actions` — the row should have `status = 'rejected'`.

- [ ] **Step 4: Test send**

DM the bot again with the same announce command. This time reply:
```
send
```

Expected:
1. Bot replies "Sending announcement to N users now."
2. Each active user receives a personalized version of the announcement in their assistant's voice
3. Admin receives "Announcement delivered to N users."
4. Check `education_log` for rows with `trigger_type = 'announcement'`

- [ ] **Step 5: Test duplicate prevention**

DM the bot with an announce command. Before replying `send` or `cancel`, try sending another announce command.

Expected: Bot replies "You already have a pending announcement — reply *send* or *cancel* first."

- [ ] **Step 6: Test opt-out**

Set `announcements_enabled = false` for a test user in Supabase. Run another announcement. Verify that user does NOT receive the message but others do.

- [ ] **Step 7: Commit any fixes**

If any fixes were needed during testing, commit them:
```bash
git add -A
git commit -m "fix: announcement broadcast testing fixes"
```

---

### Task 5: Update CLAUDE.md and memory

- [ ] **Step 1: Add Announcement Broadcast workflow ID to CLAUDE.md**

Add the new workflow to the workflow listing in CLAUDE.md under the `n8n/workflows/` section and update the Slack Events Handler description to mention the announce route.

- [ ] **Step 2: Update memory with new workflow ID**

Add the Announcement Broadcast workflow ID to the n8n memory file.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Announcement Broadcast workflow to CLAUDE.md"
```
