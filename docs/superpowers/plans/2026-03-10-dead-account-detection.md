# Dead Account Detection & Mute System — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop silence alerts from firing indefinitely on dead accounts by adding a `dead` severity tier (60+ days), interactive overflow menus (Snooze 7d/30d, Mark as Lost) on every alert, and a `muted_alerts` table for persistent mute state.

**Architecture:** Single Python script (`scripts/add_silence_mute.py`) modifies three live n8n workflows via the n8n REST API, following the established `n8n_helpers` pattern. A small Supabase migration adds the CHECK constraint update. All Supabase inserts use HTTP Request nodes (never the Supabase node).

**Tech Stack:** Python + n8n REST API, Supabase PostgreSQL, Slack Block Kit (overflow menus), n8n Code nodes (JavaScript)

**Spec:** `docs/superpowers/specs/2026-03-10-dead-account-detection-design.md`

---

## Chunk 1: Database Migration + Script Skeleton

### Task 1: Apply Additional Schema Changes

The `muted_alerts` table already exists (user ran migration). Two additional changes are needed: the `alert_history.severity` CHECK constraint must include `dead`, and the `alert_types` seed data must be updated.

**Files:**
- Modify: `supabase/migrations/009_muted_alerts.sql` (append constraint + seed update)

- [ ] **Step 1: Add CHECK constraint and seed update to migration file**

```sql
-- Add to 009_muted_alerts.sql:

-- Expand severity CHECK to include 'dead'
ALTER TABLE alert_history DROP CONSTRAINT alert_history_severity_check;
ALTER TABLE alert_history ADD CONSTRAINT alert_history_severity_check
  CHECK (severity IN ('info', 'warning', 'critical', 'dead'));

-- Add partial index for active mute lookups
CREATE INDEX idx_muted_alerts_active
  ON muted_alerts(user_id, alert_type_id, entity_name)
  WHERE unmuted_at IS NULL;

-- Update silence_contract severity levels
UPDATE alert_types
SET severity_levels = '[
  {"level": "info", "threshold": 5, "label": "Getting quiet"},
  {"level": "warning", "threshold": 10, "label": "Gone silent"},
  {"level": "critical", "threshold": 21, "label": "Relationship at risk"},
  {"level": "dead", "threshold": 60, "label": "Likely lost"}
]'::jsonb
WHERE id = 'silence_contract';
```

- [ ] **Step 2: Run the migration in Supabase SQL editor**

Copy the SQL above and execute in the Supabase SQL editor. Verify:
- `SELECT conname, consrc FROM pg_constraint WHERE conname = 'alert_history_severity_check';` — should show `dead` in the check
- `SELECT severity_levels FROM alert_types WHERE id = 'silence_contract';` — should show 4 levels

- [ ] **Step 3: Commit migration file**

```bash
git add supabase/migrations/009_muted_alerts.sql
git commit -m "feat: add dead severity + muted_alerts index + seed update"
```

### Task 2: Create Script Skeleton

**Files:**
- Create: `scripts/add_silence_mute.py`

- [ ] **Step 1: Create the script with imports and structure**

```python
#!/usr/bin/env python3
"""
Add dead account detection + interactive mute buttons to silence alerts.

Changes three workflows:
1. Silence Contract Monitor (cron) — Parse & Dedup, Build Alert Message, Send Alert DM
2. On-Demand Silence Check — Parse Silence Results, Build Alert Message
3. Interactive Events Handler — Route Action + new mute handler nodes

Design spec: docs/superpowers/specs/2026-03-10-dead-account-detection-design.md
"""

import json
from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    uid, make_code_node, make_supabase_http_node, make_slack_http_node,
    make_switch_condition,
    WF_SILENCE_MONITOR, WF_INTERACTIVE_HANDLER,
    SUPABASE_URL, SUPABASE_CRED, SLACK_CRED, SLACK_CHAT_UPDATE,
)


def update_silence_monitor():
    """Update Silence Contract Monitor cron with dead detection + Block Kit + mute filtering."""
    print("=== Updating Silence Contract Monitor ===\n")
    wf = fetch_workflow(WF_SILENCE_MONITOR)
    nodes = wf["nodes"]
    connections = wf["connections"]
    # ... (Tasks 3-5 fill this in)
    return wf


def update_on_demand_silence():
    """Update On-Demand Silence Check with dead detection + overflow menus + mute filtering."""
    print("\n=== Updating On-Demand Silence Check ===\n")
    wf = fetch_workflow("7QaWpTuTp6oNVFjM")
    nodes = wf["nodes"]
    connections = wf["connections"]
    # ... (Task 6 fills this in)
    return wf


def update_interactive_handler():
    """Add silence mute button handlers to Interactive Events Handler."""
    print("\n=== Updating Interactive Events Handler ===\n")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]
    # ... (Task 7 fills this in)
    return wf


def main():
    print("=== Dead Account Detection + Mute Buttons ===\n")

    # 1. Silence Contract Monitor
    wf1 = update_silence_monitor()
    result1 = push_workflow(WF_SILENCE_MONITOR, wf1)
    print(f"  Pushed cron: {len(result1['nodes'])} nodes")
    sync_local(fetch_workflow(WF_SILENCE_MONITOR), "Silence Contract Monitor.json")

    # 2. On-Demand Silence Check
    wf2 = update_on_demand_silence()
    result2 = push_workflow("7QaWpTuTp6oNVFjM", wf2)
    print(f"  Pushed on-demand: {len(result2['nodes'])} nodes")
    sync_local(fetch_workflow("7QaWpTuTp6oNVFjM"), "On-Demand Silence Check.json")

    # 3. Interactive Events Handler
    wf3 = update_interactive_handler()
    result3 = push_workflow(WF_INTERACTIVE_HANDLER, wf3)
    print(f"  Pushed interactive: {len(result3['nodes'])} nodes")
    sync_local(fetch_workflow(WF_INTERACTIVE_HANDLER), "Interactive Events Handler.json")

    print("\n=== Done! ===")
    print("  - Dead accounts (60+ days) alert once then auto-mute")
    print("  - Every alert has [...] overflow menu: Snooze 7d / Snooze 30d / Mark as Lost")
    print("  - Muted accounts filtered from future alerts")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script runs without errors (functions are stubs)**

```bash
cd /Users/scottmetcalf/projects/oppassistant/scripts
python3 -c "import add_silence_mute; print('Import OK')"
```

- [ ] **Step 3: Commit skeleton**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: add silence mute script skeleton"
```

---

## Chunk 2: Silence Contract Monitor — Parse & Dedup + Build Alert Message

### Task 3: Update Parse & Dedup Node

This node currently: extracts JSON from agent output, dedupes against recent alerts. New behavior: also fetch active mutes from Supabase, filter them out, reclassify 60+ day accounts as `dead`, and prepare auto-mute inserts for `dead` accounts.

**Important**: The muted accounts fetch happens in this Code node via a helper approach — we pass the muted accounts data from a new upstream node. n8n Code nodes cannot make HTTP requests directly. So we need a **new node** before Parse & Dedup that fetches muted accounts.

**Files:**
- Modify: `scripts/add_silence_mute.py` — `update_silence_monitor()` function

- [ ] **Step 1: Add "Fetch Muted Accounts" node**

Add to `update_silence_monitor()`:

```python
    # ── Add "Fetch Muted Accounts" node (runs after Open Bot DM, before Parse & Dedup) ──
    # Actually, this needs to run once before the loop, not per-user.
    # But Parse & Dedup is inside the loop and needs per-user muted accounts.
    # Solution: fetch ALL muted accounts before the loop, then filter per-user in Parse & Dedup.

    fetch_mutes_name = "Fetch Muted Accounts"
    if not find_node(nodes, fetch_mutes_name):
        # Position it after Prepare User Batch, before Split In Batches
        prep_node = find_node(nodes, "Prepare User Batch")
        prep_pos = prep_node["position"]

        fetch_mutes = make_supabase_http_node(
            name=fetch_mutes_name,
            method="GET",
            url_path="muted_alerts?alert_type_id=eq.silence_contract&unmuted_at=is.null&select=user_id,entity_name,muted_until",
            position=[prep_pos[0] + 224, prep_pos[1] + 100],
        )
        nodes.append(fetch_mutes)

        # Connect Prepare User Batch → Fetch Muted Accounts IN PARALLEL with Split In Batches
        # IMPORTANT: Do NOT wire in series (Fetch Muted → Split In Batches) because
        # SplitInBatches would iterate over muted alert rows instead of user rows.
        # Instead, add Fetch Muted Accounts as an additional parallel target.
        # Parse & Dedup accesses it via $('Fetch Muted Accounts').all() cross-node ref.
        prep_conns = connections.get("Prepare User Batch", {}).get("main", [[]])
        already_connected = any(c["node"] == fetch_mutes_name for c in prep_conns[0])
        if not already_connected:
            prep_conns[0].append({"node": fetch_mutes_name, "type": "main", "index": 0})
            connections["Prepare User Batch"]["main"] = prep_conns
        # Fetch Muted Accounts has no downstream connection — it just needs to execute
        connections[fetch_mutes_name] = {"main": [[]]}

        print(f"  Added '{fetch_mutes_name}'")
    else:
        print(f"  '{fetch_mutes_name}' already exists")
```

- [ ] **Step 2: Update Parse & Dedup code**

```python
    # ── Update Parse & Dedup ──
    parse_node = find_node(nodes, "Parse & Dedup")

    PARSE_DEDUP_CODE = r"""const agentOutput = $('Silence Monitor Agent').first().json.output || '';
const userData = $('Build Monitor Prompt').first().json;
const recentAlerts = userData.recentAlerts || [];

// Get all muted accounts (fetched before the loop)
let allMutedAccounts = [];
try {
  allMutedAccounts = $('Fetch Muted Accounts').all().map(i => i.json);
} catch (e) { /* node didn't run */ }

// Build per-user muted set (check muted_until expiry)
const now = new Date();
const mutedSet = new Set();
for (const m of allMutedAccounts) {
  if (m.user_id !== userData.userId) continue;
  if (m.muted_until && new Date(m.muted_until) < now) continue; // snooze expired
  mutedSet.add((m.entity_name || '').toLowerCase());
}

// Extract JSON from agent response
let silentAccounts = [];
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try {
    const parsed = JSON.parse(jsonMatch[1]);
    silentAccounts = parsed.silent_accounts || [];
  } catch (e) {
    try {
      silentAccounts = JSON.parse(agentOutput).silent_accounts || [];
    } catch (e2) {}
  }
}

// Build set of recently alerted entities for cooldown check
const alertedSet = new Set();
for (const alert of recentAlerts) {
  alertedSet.add(alert.entity_name.toLowerCase());
}

// Reclassify 60+ day accounts as 'dead'
for (const a of silentAccounts) {
  if ((a.days_silent || 0) >= 60) {
    a.severity = 'dead';
  }
}

// Filter out muted and recently alerted accounts
const newAlerts = silentAccounts.filter(a => {
  const name = (a.account_name || '').toLowerCase();
  if (mutedSet.has(name)) return false;
  if (alertedSet.has(name)) return false;
  return true;
});

// Identify dead accounts to auto-mute after this alert
const autoMuteAccounts = newAlerts
  .filter(a => a.severity === 'dead')
  .map(a => ({
    user_id: userData.userId,
    organization_id: userData.organizationId,
    alert_type_id: 'silence_contract',
    entity_name: a.account_name,
    mute_reason: 'auto_dead',
    muted_at: now.toISOString()
  }));

return [{
  json: {
    ...userData,
    allDetected: silentAccounts,
    newAlerts,
    autoMuteAccounts,
    detectedCount: silentAccounts.length,
    newAlertCount: newAlerts.length
  }
}];"""

    parse_node["parameters"]["jsCode"] = PARSE_DEDUP_CODE
    print("  Updated 'Parse & Dedup'")
```

- [ ] **Step 3: Add "Auto-Mute Dead Accounts" node after Log Alerts to DB**

```python
    # ── Add "Auto-Mute Dead Accounts" node ──
    auto_mute_name = "Auto-Mute Dead Accounts"
    if not find_node(nodes, auto_mute_name):
        log_node = find_node(nodes, "Log Alerts to DB")
        log_pos = log_node["position"]

        auto_mute_code = r"""// Insert muted_alerts rows for dead accounts
const data = $input.first().json;
const autoMute = data.autoMuteAccounts || [];

if (autoMute.length === 0) {
  return [{ json: { ...data, autoMuted: 0 } }];
}

return [{ json: { ...data, autoMutePayload: autoMute, autoMuted: autoMute.length } }];"""

        auto_mute_prep = make_code_node(auto_mute_name, auto_mute_code, [log_pos[0] + 224, log_pos[1]])
        nodes.append(auto_mute_prep)

        # Connect Log Alerts to DB → Auto-Mute Dead Accounts
        if "Log Alerts to DB" not in connections:
            connections["Log Alerts to DB"] = {"main": [[]]}
        # Check what Log Alerts currently connects to (likely loops back to Split In Batches)
        log_targets = connections["Log Alerts to DB"]["main"][0]
        loop_back = [t for t in log_targets if t["node"] == "Split In Batches"]
        connections["Log Alerts to DB"]["main"][0] = [{"node": auto_mute_name, "type": "main", "index": 0}]

        # Insert Dead Mutes node (HTTP POST to Supabase)
        insert_mutes_name = "Insert Dead Mutes"
        if not find_node(nodes, insert_mutes_name):
            insert_mutes = make_supabase_http_node(
                name=insert_mutes_name,
                method="POST",
                url_path="muted_alerts",
                position=[log_pos[0] + 448, log_pos[1]],
                json_body='={{ JSON.stringify($json.autoMutePayload || []) }}',
                extra_headers=[
                    {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                    {"name": "Content-Type", "value": "application/json"}
                ],
            )
            nodes.append(insert_mutes)

            # Connect Auto-Mute Dead → Insert Dead Mutes → loop back to Split In Batches
            connections[auto_mute_name] = {"main": [[{"node": insert_mutes_name, "type": "main", "index": 0}]]}
            connections[insert_mutes_name] = {"main": [loop_back if loop_back else [{"node": "Split In Batches", "type": "main", "index": 0}]]}

            print(f"  Added '{auto_mute_name}' + '{insert_mutes_name}'")
    else:
        print(f"  '{auto_mute_name}' already exists")
```

- [ ] **Step 4: Commit progress**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: Parse & Dedup mute filtering + dead severity + auto-mute nodes"
```

### Task 4: Update Build Alert Message — Block Kit with Overflow Menus

**Files:**
- Modify: `scripts/add_silence_mute.py` — inside `update_silence_monitor()`

- [ ] **Step 1: Replace Build Alert Message code**

```python
    # ── Update Build Alert Message — Block Kit with overflow menus ──
    alert_msg_node = find_node(nodes, "Build Alert Message")

    BUILD_ALERT_MSG_CODE = r"""const data = $input.first().json;
const alerts = data.newAlerts || [];

if (alerts.length === 0) {
  return [{ json: { ...data, hasAlerts: false, alertBlocks: '[]', alertText: '' } }];
}

const severityEmoji = {
  dead: ':skull:',
  critical: ':red_circle:',
  warning: ':large_orange_circle:',
  info: ':large_blue_circle:'
};

// Sort: dead first, then critical, warning, info
const order = { dead: 0, critical: 1, warning: 2, info: 3 };
alerts.sort((a, b) => (order[a.severity] || 9) - (order[b.severity] || 9));

const blocks = [
  {
    type: "section",
    text: {
      type: "mrkdwn",
      text: `:mag: *Silence Contract Alert*\n${alerts.length} account${alerts.length === 1 ? '' : 's'} need${alerts.length === 1 ? 's' : ''} attention:`
    }
  }
];

for (const a of alerts) {
  const emoji = severityEmoji[a.severity] || ':white_circle:';
  const lastType = a.last_activity_type || 'activity';
  const lastDate = a.last_activity_date || 'unknown';
  let line = `${emoji} *${a.account_name}* — ${a.days_silent} days silent`;
  if (lastDate !== 'unknown') {
    line += ` (last: ${lastType} on ${lastDate})`;
  }

  // Slack overflow value has 75-char max. Use compact format: "action|accountName"
  // userId and organizationId are derived from Lookup User (Action) in the handler.
  const acctName = a.account_name;

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: line },
    accessory: {
      type: "overflow",
      action_id: "silence_overflow_" + blocks.length,
      options: [
        {
          text: { type: "plain_text", text: "Snooze 7d" },
          value: ("s7|" + acctName).slice(0, 75)
        },
        {
          text: { type: "plain_text", text: "Snooze 30d" },
          value: ("s30|" + acctName).slice(0, 75)
        },
        {
          text: { type: "plain_text", text: "Mark as Lost" },
          value: ("ml|" + acctName).slice(0, 75)
        }
      ]
    }
  });
}

blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: "Use the menu on each account to snooze or mute alerts." }]
});

// Enforce Slack limits
if (blocks.length > 50) blocks.length = 50;
for (const b of blocks) {
  if (b.text && b.text.text && b.text.text.length > 3000) {
    b.text.text = b.text.text.slice(0, 2997) + '...';
  }
}

// Also build plain text fallback for notification
let plainText = alerts.length + ' account' + (alerts.length === 1 ? '' : 's') + ' need attention in silence check';

return [{ json: { ...data, hasAlerts: true, alertBlocks: JSON.stringify(blocks), alertText: plainText } }];"""

    alert_msg_node["parameters"]["jsCode"] = BUILD_ALERT_MSG_CODE
    print("  Updated 'Build Alert Message' — Block Kit with overflow menus")
```

- [ ] **Step 2: Commit**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: Build Alert Message with Block Kit overflow menus"
```

### Task 5: Update Send Alert DM — Use Blocks Instead of Text

**Files:**
- Modify: `scripts/add_silence_mute.py` — inside `update_silence_monitor()`

- [ ] **Step 1: Update Send Alert DM to use blocks**

The current node sends `text`. We need to change it to send `blocks` + `text` (fallback). The node is an HTTP Request node — update its `jsonBody`.

```python
    # ── Update Send Alert DM to use blocks ──
    send_node = find_node(nodes, "Send Alert DM")
    send_node["parameters"]["jsonBody"] = json.dumps({
        "channel": "={{ $json.slackChannelId }}",
        "blocks": "={{ $json.alertBlocks }}",
        "text": "={{ $json.alertText }}",
        "username": "={{ $json.assistantName }}",
        "icon_emoji": "={{ $json.assistantEmoji }}"
    })
    print("  Updated 'Send Alert DM' — sends blocks")
```

Note: The `jsonBody` value uses n8n expression syntax (`={{ }}`). The `blocks` field must be a JSON array (string), which `alertBlocks` already is from Build Alert Message. However, n8n's `jsonBody` with `specifyBody: "json"` expects valid JSON — the expressions get evaluated at runtime. We need to ensure `blocks` receives the parsed array, not a string. Update to use string body:

```python
    # Use cross-node refs — $json here points to Open Bot DM output, not Build Alert Message
    send_node["parameters"]["specifyBody"] = "string"
    send_node["parameters"]["body"] = '={{ JSON.stringify({ channel: $json.channel.id, blocks: JSON.parse($("Build Alert Message").first().json.alertBlocks), text: $("Build Alert Message").first().json.alertText, username: $("Build Alert Message").first().json.assistantName, icon_emoji: $("Build Alert Message").first().json.assistantEmoji }) }}'
    # Remove jsonBody if present
    send_node["parameters"].pop("jsonBody", None)
    print("  Updated 'Send Alert DM' — sends blocks (cross-node refs)")
```

- [ ] **Step 2: Also update Prepare Alert Logs to capture alertHistoryId for buttons**

The alert_history rows need their IDs available for the overflow button values. Currently `Prepare Alert Logs` builds rows and `Log Alerts to DB` inserts them. The insert returns the created rows (with IDs) via `Prefer: return=representation`. But the alertHistoryId in the button value is set at Build Alert Message time (before insert).

**Solution**: Set `alertHistoryId` to empty string in Build Alert Message (already done above), and don't rely on it in the interactive handler — look up the alert by entity_name + user_id instead. This is simpler and avoids a chicken-and-egg problem.

No code change needed — the empty `alertHistoryId` is already handled.

- [ ] **Step 3: Add return statement to update_silence_monitor**

```python
    return wf
```

- [ ] **Step 4: Commit**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: Send Alert DM uses Block Kit, complete cron workflow updates"
```

---

## Chunk 3: On-Demand Silence Check + Interactive Events Handler

### Task 6: Update On-Demand Silence Check

**Files:**
- Modify: `scripts/add_silence_mute.py` — `update_on_demand_silence()` function

- [ ] **Step 1: Update Parse Silence Results to filter mutes and reclassify dead**

```python
def update_on_demand_silence():
    """Update On-Demand Silence Check with dead detection + overflow menus + mute filtering."""
    print("\n=== Updating On-Demand Silence Check ===\n")
    wf = fetch_workflow("7QaWpTuTp6oNVFjM")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── Add Fetch Muted Accounts node before Parse Silence Results ──
    fetch_mutes_name = "Fetch Muted Accounts"
    if not find_node(nodes, fetch_mutes_name):
        agent_node = find_node(nodes, "Silence Agent")
        agent_pos = agent_node["position"]

        fetch_mutes = make_supabase_http_node(
            name=fetch_mutes_name,
            method="GET",
            url_path="muted_alerts?alert_type_id=eq.silence_contract&unmuted_at=is.null&select=user_id,entity_name,muted_until",
            position=[agent_pos[0], agent_pos[1] + 150],
        )
        nodes.append(fetch_mutes)

        # Connect Build Silence Prompt → Fetch Muted Accounts (parallel with agent)
        # IMPORTANT: Do NOT connect Fetch Muted Accounts → Parse Silence Results.
        # Dual inputs would merge items and break the data flow.
        # Parse Silence Results accesses it via $('Fetch Muted Accounts').all() cross-node ref.
        # It just needs to have executed in the same run.
        if "Build Silence Prompt" not in connections:
            connections["Build Silence Prompt"] = {"main": [[]]}
        connections["Build Silence Prompt"]["main"][0].append(
            {"node": fetch_mutes_name, "type": "main", "index": 0}
        )
        # No downstream connection — just needs to execute
        connections[fetch_mutes_name] = {"main": [[]]}
        print(f"  Added '{fetch_mutes_name}'")
    else:
        print(f"  '{fetch_mutes_name}' already exists")

    # ── Update Parse Silence Results ──
    parse_node = find_node(nodes, "Parse Silence Results")

    PARSE_RESULTS_CODE = r"""const agentOutput = $('Silence Agent').first().json.output || '';
const inputData = $('Build Silence Prompt').first().json;

// Get muted accounts
let allMuted = [];
try {
  allMuted = $('Fetch Muted Accounts').all().map(i => i.json);
} catch (e) {}

const now = new Date();
const userId = inputData.userId;
const mutedSet = new Set();
for (const m of allMuted) {
  if (m.user_id !== userId) continue;
  if (m.muted_until && new Date(m.muted_until) < now) continue;
  mutedSet.add((m.entity_name || '').toLowerCase());
}

// Extract JSON from agent response
let silentAccounts = [];
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try {
    silentAccounts = JSON.parse(jsonMatch[1]).silent_accounts || [];
  } catch (e) {}
}

// Reclassify 60+ day accounts as 'dead'
for (const a of silentAccounts) {
  if ((a.days_silent || 0) >= 60) a.severity = 'dead';
}

// Filter out muted
const filtered = silentAccounts.filter(a => !mutedSet.has((a.account_name || '').toLowerCase()));

// Sort by severity then days
const order = { dead: 0, critical: 1, warning: 2, info: 3 };
filtered.sort((a, b) => (order[a.severity] || 9) - (order[b.severity] || 9) || (b.days_silent || 0) - (a.days_silent || 0));

// Dead accounts to auto-mute
const autoMuteAccounts = filtered
  .filter(a => a.severity === 'dead')
  .map(a => ({
    user_id: userId,
    organization_id: inputData.organizationId,
    alert_type_id: 'silence_contract',
    entity_name: a.account_name,
    mute_reason: 'auto_dead',
    muted_at: now.toISOString()
  }));

return [{ json: {
  ...inputData,
  silentAccounts: filtered,
  autoMuteAccounts,
  silentCount: filtered.length
} }];"""

    parse_node["parameters"]["jsCode"] = PARSE_RESULTS_CODE
    print("  Updated 'Parse Silence Results'")
```

- [ ] **Step 2: Update Build Alert Message with overflow menus**

```python
    # ── Update Build Alert Message — add overflow menus ──
    alert_node = find_node(nodes, "Build Alert Message")

    BUILD_ALERT_OD_CODE = r"""const data = $input.first().json;
const accounts = data.silentAccounts || [];

if (accounts.length === 0) {
  return [{ json: { ...data, blocks: JSON.stringify([
    { type: "section", text: { type: "mrkdwn", text: ":white_check_mark: *All clear!* None of your accounts have gone silent. Everything looks active." } }
  ]), notificationText: "All accounts active" } }];
}

const severityEmoji = { dead: ':skull:', critical: ':red_circle:', warning: ':large_orange_circle:', info: ':large_blue_circle:' };

const blocks = [
  { type: "section", text: { type: "mrkdwn", text: `:mag: *Silence Contract Check*\n${accounts.length} account${accounts.length === 1 ? '' : 's'} need${accounts.length === 1 ? 's' : ''} attention:` } }
];

for (const acct of accounts) {
  const emoji = severityEmoji[acct.severity] || ':grey_question:';
  const lastDate = acct.last_activity_date ? ` (last: ${acct.last_activity_type || 'activity'} on ${acct.last_activity_date})` : '';
  const line = `${emoji} *${acct.account_name}* \u2014 ${acct.days_silent} days silent${lastDate}`;

  // Slack overflow value has 75-char max. Use compact format: "action|accountName"
  const acctName = acct.account_name;

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: line },
    accessory: {
      type: "overflow",
      action_id: "silence_overflow_" + blocks.length,
      options: [
        { text: { type: "plain_text", text: "Snooze 7d" }, value: ("s7|" + acctName).slice(0, 75) },
        { text: { type: "plain_text", text: "Snooze 30d" }, value: ("s30|" + acctName).slice(0, 75) },
        { text: { type: "plain_text", text: "Mark as Lost" }, value: ("ml|" + acctName).slice(0, 75) }
      ]
    }
  });
}

blocks.push({ type: "context", elements: [{ type: "mrkdwn", text: "Use the menu on each account to snooze or mute alerts." }] });

if (blocks.length > 50) blocks.length = 50;
for (const b of blocks) {
  if (b.text && b.text.text && b.text.text.length > 3000) {
    b.text.text = b.text.text.slice(0, 2997) + '...';
  }
}

return [{ json: { ...data, blocks: JSON.stringify(blocks), notificationText: accounts.length + ' silent account' + (accounts.length === 1 ? '' : 's') + ' found' } }];"""

    alert_node["parameters"]["jsCode"] = BUILD_ALERT_OD_CODE
    print("  Updated 'Build Alert Message' — overflow menus")
```

- [ ] **Step 3: Add auto-mute insert node for on-demand flow**

```python
    # ── Add Auto-Mute insert after Send Silence Check ──
    auto_mute_name = "Auto-Mute Dead (OD)"
    if not find_node(nodes, auto_mute_name):
        send_node = find_node(nodes, "Send Silence Check")
        send_pos = send_node["position"]

        auto_mute = make_supabase_http_node(
            name=auto_mute_name,
            method="POST",
            url_path="muted_alerts",
            position=[send_pos[0] + 224, send_pos[1]],
            json_body='={{ JSON.stringify($json.autoMuteAccounts || []) }}',
            extra_headers=[
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"}
            ],
        )
        nodes.append(auto_mute)

        # Rewire: Send Silence Check → Auto-Mute Dead (OD)
        # Check current Send Silence Check connections
        send_conns = connections.get("Send Silence Check", {"main": [[]]})
        existing_targets = send_conns["main"][0]
        connections["Send Silence Check"]["main"][0] = [{"node": auto_mute_name, "type": "main", "index": 0}]
        connections[auto_mute_name] = {"main": [existing_targets]}

        print(f"  Added '{auto_mute_name}'")
    else:
        print(f"  '{auto_mute_name}' already exists")

    return wf
```

- [ ] **Step 4: Commit**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: on-demand silence check with mute filtering + overflow menus"
```

### Task 7: Update Interactive Events Handler — Mute Button Handlers

The Interactive Events Handler's `Route Action` Switch currently has 8 outputs matching exact `actionId` values. Overflow menus send a different payload structure — the `actionId` is the overflow's `action_id` (e.g., `silence_overflow_1`), and the selected option is in `selectedOption.value`. We need to:

1. Route any `actionId` starting with `silence_overflow_` to a new handler
2. Parse the selected option to determine the action (snooze_7d, snooze_30d, mark_lost)
3. Upsert to `muted_alerts`
4. Update the original message with confirmation

**Files:**
- Modify: `scripts/add_silence_mute.py` — `update_interactive_handler()` function

- [ ] **Step 1: Update Parse Interactive Payload to extract overflow selection**

First, check what Parse Interactive Payload currently extracts. We need to add `selectedOptionValue` for overflow menus.

```python
def update_interactive_handler():
    """Add silence mute button handlers to Interactive Events Handler."""
    print("\n=== Updating Interactive Events Handler ===\n")
    wf = fetch_workflow(WF_INTERACTIVE_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── Update Parse Interactive Payload to include overflow selection ──
    parse_node = find_node(nodes, "Parse Interactive Payload")
    code = parse_node["parameters"]["jsCode"]

    if "selectedOptionValue" not in code:
        # Add selectedOptionValue extraction
        # Find where actionValue is set and add after it
        old_line = "actionValue: action ? (action.value || '') : '',"
        new_line = """actionValue: action ? (action.value || '') : '',
    selectedOptionValue: action && action.selected_option ? action.selected_option.value : '',"""
        if old_line in code:
            code = code.replace(old_line, new_line)
            parse_node["parameters"]["jsCode"] = code
            print("  Updated 'Parse Interactive Payload' — extracts selectedOptionValue")
        else:
            print("  WARNING: Could not find actionValue line in Parse Interactive Payload")
            print("  Will add selectedOptionValue manually")
            # Fallback: the Parse Mute Action node will parse it from the raw payload
    else:
        print("  Parse Interactive Payload already has selectedOptionValue")
```

- [ ] **Step 2: Add new Switch output for silence_overflow_ prefix**

```python
    # ── Add silence_overflow route to Route Action Switch ──
    route_node = find_node(nodes, "Route Action")
    rules = route_node["parameters"]["rules"]["values"]

    # Check if silence route already exists
    silence_route_exists = any(
        r.get("outputKey", "").startswith("silence") or r.get("renameOutput") and "silence" in str(r.get("outputKey", ""))
        for r in rules
    )

    if not silence_route_exists:
        # Use "contains" operator for prefix matching
        silence_rule = {
            "outputKey": "Silence Mute",
            "renameOutput": True,
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {
                        "name": "filter.operator.startsWith",
                        "type": "string",
                        "operation": "startsWith",
                    },
                    "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                    "rightValue": "silence_overflow_",
                }],
            },
        }
        rules.append(silence_rule)
        print(f"  Added 'Silence Mute' route to Route Action (output {len(rules) - 1})")
    else:
        print("  Silence route already exists in Route Action")
```

- [ ] **Step 3: Add Parse Mute Action code node**

```python
    # ── Add Parse Mute Action node ──
    parse_mute_name = "Parse Mute Action"
    if not find_node(nodes, parse_mute_name):
        route_pos = route_node["position"]

        PARSE_MUTE_CODE = r"""// Parse overflow menu selection and build mute payload + updated message
const payload = $('Parse Interactive Payload').first().json;
const selectedValue = payload.selectedOptionValue || '';
// Use payload.message directly (not a 'message' variable which doesn't exist)
const messageBlocks = payload.messageBlocks || [];

// Parse compact "action|accountName" format (e.g. "s7|Elastic", "ml|Cyberhaven")
const pipeIdx = selectedValue.indexOf('|');
if (pipeIdx === -1) {
  return [{ json: { error: 'Invalid selection value', selectedValue } }];
}

const actionCode = selectedValue.substring(0, pipeIdx);
const accountName = selectedValue.substring(pipeIdx + 1);

// Get userId and organizationId from Lookup User (Action) — already fetched by the handler
const userRecord = $('Lookup User (Action)').first().json;
const userId = userRecord.id || '';
const organizationId = userRecord.organization_id || '';

// Determine mute parameters
let muteReason, mutedUntil, confirmText;
const now = new Date();

if (actionCode === 's7') {
  muteReason = 'snoozed';
  const until = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);
  mutedUntil = until.toISOString();
  confirmText = `:white_check_mark: *${accountName}* snoozed for 7 days.`;
} else if (actionCode === 's30') {
  muteReason = 'snoozed';
  const until = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
  mutedUntil = until.toISOString();
  confirmText = `:white_check_mark: *${accountName}* snoozed for 30 days.`;
} else if (actionCode === 'ml') {
  muteReason = 'marked_lost';
  mutedUntil = null;
  confirmText = `:white_check_mark: *${accountName}* muted — consider closing the open opps in Salesforce.`;
} else {
  return [{ json: { error: 'Unknown action: ' + actionCode } }];
}

// Build mute row for upsert
const mutePayload = {
  user_id: userId,
  organization_id: organizationId,
  alert_type_id: 'silence_contract',
  entity_name: accountName,
  mute_reason: muteReason,
  muted_at: now.toISOString(),
  muted_until: mutedUntil,
  unmuted_at: null
};

// Rebuild message blocks — replace the actioned account's section with confirmation
const updatedBlocks = [];
for (const block of messageBlocks) {
  if (block.type === 'section' && block.text && block.text.text &&
      block.text.text.includes('*' + accountName + '*') && block.accessory) {
    // Replace this section with confirmation (no accessory)
    updatedBlocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: confirmText }
    });
  } else {
    updatedBlocks.push(block);
  }
}

return [{ json: {
  mutePayload,
  updatedBlocks: JSON.stringify(updatedBlocks),
  channelId: payload.channelId,
  messageTs: payload.messageTs,
  accountName,
  confirmText
} }];"""

        parse_mute_node = make_code_node(parse_mute_name, PARSE_MUTE_CODE, [route_pos[0] + 400, route_pos[1] + 400])
        nodes.append(parse_mute_node)
        print(f"  Added '{parse_mute_name}'")
    else:
        print(f"  '{parse_mute_name}' already exists")
```

- [ ] **Step 4: Update Parse Interactive Payload to pass messageBlocks**

```python
    # Ensure Parse Interactive Payload passes message.blocks
    parse_pp = find_node(nodes, "Parse Interactive Payload")
    pp_code = parse_pp["parameters"]["jsCode"]
    if "messageBlocks" not in pp_code:
        old_msg_ts = "messageTs: message ? message.ts : '',"
        new_msg_ts = """messageTs: message ? message.ts : '',
    messageBlocks: payload.message ? (payload.message.blocks || []) : [],"""
        if old_msg_ts in pp_code:
            pp_code = pp_code.replace(old_msg_ts, new_msg_ts)
            parse_pp["parameters"]["jsCode"] = pp_code
            print("  Updated 'Parse Interactive Payload' — extracts messageBlocks")
```

- [ ] **Step 5: Add Upsert Mute node (Supabase HTTP)**

```python
    # ── Add Upsert Mute node ──
    upsert_name = "Upsert Mute"
    if not find_node(nodes, upsert_name):
        parse_mute_node = find_node(nodes, parse_mute_name)
        pm_pos = parse_mute_node["position"]

        upsert_node = make_supabase_http_node(
            name=upsert_name,
            method="POST",
            url_path="muted_alerts",
            position=[pm_pos[0] + 250, pm_pos[1]],
            json_body='={{ JSON.stringify($json.mutePayload) }}',
            extra_headers=[
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"}
            ],
        )
        nodes.append(upsert_node)
        print(f"  Added '{upsert_name}'")
    else:
        print(f"  '{upsert_name}' already exists")
```

- [ ] **Step 6: Add Update Alert Message node (Slack chat.update)**

```python
    # ── Add Update Alert Message node ──
    update_msg_name = "Update Alert Message"
    if not find_node(nodes, update_msg_name):
        upsert_node = find_node(nodes, upsert_name)
        u_pos = upsert_node["position"]

        # Use cross-node refs — $json after Upsert Mute is the Supabase response, not Parse Mute Action
        update_body = '={{ JSON.stringify({ channel: $("Parse Mute Action").first().json.channelId, ts: $("Parse Mute Action").first().json.messageTs, blocks: JSON.parse($("Parse Mute Action").first().json.updatedBlocks) }) }}'

        update_node = make_slack_http_node(
            name=update_msg_name,
            api_url=SLACK_CHAT_UPDATE,
            json_body=update_body,
            position=[u_pos[0] + 250, u_pos[1]],
        )
        # Use string body since blocks is a JSON string that needs parsing
        update_node["parameters"]["specifyBody"] = "string"
        update_node["parameters"]["body"] = update_body
        update_node["parameters"].pop("jsonBody", None)
        nodes.append(update_node)
        print(f"  Added '{update_msg_name}'")
    else:
        print(f"  '{update_msg_name}' already exists")
```

- [ ] **Step 7: Wire all connections**

```python
    # ── Wire connections ──
    # Route Action output N → Parse Mute Action → Upsert Mute → Update Alert Message
    silence_output_idx = len(rules) - 1  # The index of our new rule

    route_conns = connections.get("Route Action", {"main": []})
    # Extend main outputs to match rule count
    while len(route_conns["main"]) <= silence_output_idx:
        route_conns["main"].append([])
    route_conns["main"][silence_output_idx] = [{"node": parse_mute_name, "type": "main", "index": 0}]
    connections["Route Action"] = route_conns

    connections[parse_mute_name] = {"main": [[{"node": upsert_name, "type": "main", "index": 0}]]}
    connections[upsert_name] = {"main": [[{"node": update_msg_name, "type": "main", "index": 0}]]}

    print("  Wired: Route Action → Parse Mute Action → Upsert Mute → Update Alert Message")

    return wf
```

- [ ] **Step 8: Commit**

```bash
git add scripts/add_silence_mute.py
git commit -m "feat: interactive handler mute buttons — snooze + mark as lost"
```

---

## Chunk 4: Run, Test, and Verify

### Task 8: Run the Script

- [ ] **Step 1: Run the full script**

```bash
cd /Users/scottmetcalf/projects/oppassistant/scripts
python3 add_silence_mute.py
```

Expected output:
```
=== Dead Account Detection + Mute Buttons ===

=== Updating Silence Contract Monitor ===
  Added 'Fetch Muted Accounts'
  Updated 'Parse & Dedup'
  Added 'Auto-Mute Dead Accounts' + 'Insert Dead Mutes'
  Updated 'Build Alert Message' — Block Kit with overflow menus
  Updated 'Send Alert DM' — sends blocks
  Pushed cron: ~21 nodes

=== Updating On-Demand Silence Check ===
  Added 'Fetch Muted Accounts'
  Updated 'Parse Silence Results'
  Updated 'Build Alert Message' — overflow menus
  Added 'Auto-Mute Dead (OD)'
  Pushed on-demand: ~13 nodes

=== Updating Interactive Events Handler ===
  Updated 'Parse Interactive Payload' — extracts selectedOptionValue
  Added 'Silence Mute' route to Route Action (output 8)
  Added 'Parse Mute Action'
  Added 'Upsert Mute'
  Added 'Update Alert Message'
  Wired: Route Action → Parse Mute Action → Upsert Mute → Update Alert Message
  Pushed interactive: ~40 nodes
```

- [ ] **Step 2: If errors occur, debug and re-run**

Common issues:
- n8n may reject the Switch `startsWith` operator — check live node for exact operator name
- Connection wiring may conflict with existing connections — inspect with `fetch_workflow`
- Supabase HTTP node may need different header format — compare with working nodes

### Task 9: Manual Testing

- [ ] **Step 1: Test the on-demand silence command**

DM the bot with `silence`. Verify:
- Accounts appear with overflow menus (`[...]`)
- Accounts 60+ days silent show :skull: emoji
- Click an overflow menu → see 3 options (Snooze 7d, Snooze 30d, Mark as Lost)

- [ ] **Step 2: Test Mark as Lost**

Click "Mark as Lost" on a dead account. Verify:
- The account line is replaced with `:white_check_mark: *AccountName* muted — consider closing the open opps in Salesforce.`
- A row appears in `muted_alerts` with `mute_reason = 'marked_lost'`

- [ ] **Step 3: Test Snooze 7d**

Click "Snooze 7d" on an account. Verify:
- Confirmation message replaces the line
- `muted_alerts` row has `mute_reason = 'snoozed'` and `muted_until` is 7 days from now

- [ ] **Step 4: Test re-running silence after muting**

DM `silence` again. Verify muted accounts no longer appear.

- [ ] **Step 5: Commit final state**

```bash
git add scripts/add_silence_mute.py n8n/workflows/
git commit -m "feat: dead account detection + interactive mute buttons

- Dead severity tier (60+ days) — alerts once, auto-mutes
- Overflow menus on every alert: Snooze 7d / Snooze 30d / Mark as Lost
- Muted accounts filtered from cron + on-demand silence checks
- Interactive handler processes mute actions and updates messages"
```
