"""
Add announcement broadcast route to the Slack Events Handler.

Adds:
1. 'Check Pending Action' HTTP Request node (before Route by State)
2. 'announce:' detection in Route by State code
3. Four new Switch outputs: cmd_announce, confirm_announce, cancel_announce, expire_pending
4. Admin Gate code node
5. Fetch Eligible Users node
6. Preview + Store Pending Action code node
7. Send Preview node
8. Store Pending Action HTTP Request node
9. Confirm Announce code node + Execute Sub-workflow node
10. Cancel Announce code node + Update Pending Action node + Send Cancel Confirmation
11. Expire Pending path

Usage:
    N8N_API_KEY=... python scripts/add_announce_route.py
"""

import json
import requests
import os
from n8n_helpers import (
    uid, find_node, modify_workflow,
    make_code_node, make_slack_http_node, make_supabase_http_node,
    make_switch_condition, make_switch_rule,
    SUPABASE_CRED, SLACK_CRED, SUPABASE_URL,
    SLACK_CHAT_POST,
    WF_EVENTS_HANDLER,
    N8N_BASE_URL, HEADERS,
)


def find_broadcast_workflow_id():
    """Find the Announcement Broadcast sub-workflow ID."""
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS)
    resp.raise_for_status()
    for w in resp.json().get("data", []):
        if w["name"] == "Announcement Broadcast":
            return w["id"]
    raise RuntimeError("Announcement Broadcast workflow not found — run create_announcement_broadcast.py first")


def modifier(nodes, connections):
    changes = 0

    broadcast_wf_id = find_broadcast_workflow_id()
    print(f"  Found Announcement Broadcast workflow: {broadcast_wf_id}")

    # ── 1. Add "Check Pending Action" node ────────────────────────────
    lookup_node = find_node(nodes, "Lookup User")
    route_node = find_node(nodes, "Route by State")

    if not lookup_node or not route_node:
        print("ERROR: Could not find 'Lookup User' or 'Route by State' nodes")
        return 0

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

    pending_block = """
  // --- Pending action routing (announcement confirmation) ---
  const pendingRaw = $('Check Pending Action').first().json;
  const hasPending = Array.isArray(pendingRaw)
    ? pendingRaw.length > 0 && pendingRaw[0].id
    : (pendingRaw && pendingRaw.id);

  if (hasPending) {
    if (lower === 'send') route = 'confirm_announce';
    else if (lower === 'cancel') route = 'cancel_announce';
    else route = 'expire_pending';
  }

  // Announce command
  if (route === 'unknown' && (lower.startsWith('announce:') || lower.startsWith('announce '))) {
    route = 'cmd_announce';
  }

"""

    marker = "// --- Pass 1: Exact command matching (keyword at start of text) ---"
    if marker in old_code:
        new_code = old_code.replace(marker, pending_block + "  " + marker)
        route_node["parameters"]["jsCode"] = new_code
        changes += 1
    else:
        print("WARNING: Could not find Pass 1 marker in Route by State code")

    # ── 3. Add four new Switch outputs ────────────────────────────────
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
    base_y = sw_pos[1] + 1200

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

    # Execute Announcement Broadcast sub-workflow
    execute_broadcast = {
        "parameters": {
            "source": "database",
            "workflowId": {
                "__rl": True,
                "mode": "list",
                "value": broadcast_wf_id,
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

    # ── Wire new connections ──────────────────────────────────────────
    num_existing = len(switch_node["parameters"]["rules"]["values"]) - 4
    announce_idx = num_existing
    confirm_idx = num_existing + 1
    cancel_idx = num_existing + 2
    expire_idx = num_existing + 3

    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}

    switch_main = connections["Switch Route"]["main"]
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
            [],
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

    return changes


if __name__ == "__main__":
    result = modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modifier,
    )
    print(f"\nDone! {len(result['nodes'])} total nodes")
