#!/usr/bin/env python3
"""
Add `tasks` command to the People.ai Personal Assistant.

Creates:
1. Task Callback Handler workflow (new) — receives Workato callback with SF tasks, posts to Slack
2. `tasks` command in Slack Events Handler — triggers the read flow
3. `task_complete_*` button handler in Interactive Events Handler

Modifies:
- Slack Events Handler (QuQbIaWetunUOFUW)
- Interactive Events Handler (JgVjCqoT6ZwGuDL1)
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.n8n_helpers import (
    fetch_workflow, push_workflow, sync_local, find_node, uid,
    create_or_update_workflow, modify_workflow, activate_workflow,
    make_code_node, make_slack_http_node, make_supabase_http_node,
    make_switch_condition,
    WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
    SLACK_CRED, SUPABASE_CRED,
    SUPABASE_URL, SLACK_CHAT_POST, SLACK_CHAT_UPDATE,
    NODE_HTTP_REQUEST, NODE_CODE,
)

WORKATO_READ_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read"
WORKATO_WRITE_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"
CALLBACK_WEBHOOK_PATH = "sf-read-callback"
CALLBACK_WEBHOOK_URL = f"https://scottai.trackslife.com/webhook/{CALLBACK_WEBHOOK_PATH}"


# ═══════════════════════════════════════════════════════════════════════
# Part 1: Task Callback Handler (new workflow)
# ═══════════════════════════════════════════════════════════════════════

def build_callback_workflow():
    """Build the Task Callback Handler workflow dict."""

    # --- Node 1: Webhook ---
    webhook_node = {
        "parameters": {
            "httpMethod": "POST",
            "path": CALLBACK_WEBHOOK_PATH,
            "responseMode": "onReceived",
            "options": {},
        },
        "id": uid(),
        "name": "Callback Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [260, 300],
        "webhookId": uid(),
    }

    # --- Node 2: Parse Callback (Code) ---
    parse_code = r"""
const body = $input.first().json.body || $input.first().json;
const requestId = body.request_id || '';
const accountName = body.account_name || '';
const tasks = body.tasks || [];

// Build Supabase lookup URL — query pending_actions by opportunity_id (stores request_id)
const lookupUrl = '""" + SUPABASE_URL + r"""/rest/v1/pending_actions?opportunity_id=eq.' + encodeURIComponent(requestId) + '&action_type=eq.get_tasks&select=*';

return [{ json: { requestId, accountName, tasks, lookupUrl } }];
""".strip()

    parse_node = make_code_node("Parse Callback", parse_code, [660, 300])

    # --- Node 3: Fetch Request Context (HTTP → Supabase) ---
    fetch_context_node = {
        "parameters": {
            "method": "GET",
            "url": "={{ $json.lookupUrl }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Request Context",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1060, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }

    # --- Node 4: Build Task List (Code) ---
    build_code = r"""
const callbackData = $('Parse Callback').first().json;
const contextArr = $('Fetch Request Context').first().json;

// Supabase returns array; take first match
const row = Array.isArray(contextArr) ? contextArr[0] : contextArr;
let meta = (row && row.context) || {};
if (typeof meta === 'string') try { meta = JSON.parse(meta); } catch(e) { meta = {}; }

const tasks = callbackData.tasks || [];
const accountName = callbackData.accountName || meta.account_name || 'Account';
const channelId = meta.channel_id || '';
const messageTs = meta.message_ts || '';
const assistantName = meta.assistant_name || 'Aria';
const assistantEmoji = meta.assistant_emoji || ':robot_face:';

// Separate open vs completed
const openTasks = tasks.filter(t => t.Status !== 'Completed');
const completedTasks = tasks.filter(t => t.Status === 'Completed');

const blocks = [];

// Header
blocks.push({
  type: "header",
  text: { type: "plain_text", text: `\u{1F4CB} ${accountName} \u2014 Tasks`, emoji: true }
});

// Open tasks
if (openTasks.length > 0) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Open Tasks (${openTasks.length})*` }
  });

  for (const t of openTasks.slice(0, 15)) {
    const ownerName = t.Owner_Name || t['Owner.Name'] || '';
    const dueDate = t.ActivityDate || '';
    const category = t.Category__c || t.Category || '';

    let taskLine = `\u2022 ${t.Subject || 'Task'}`;
    if (ownerName) taskLine += ` \u2014 ${ownerName}`;
    if (dueDate) taskLine += ` \u00b7 Due ${dueDate}`;
    if (category) taskLine += ` \u00b7 ${category}`;

    const completePayload = JSON.stringify({
      action: 'complete_task',
      task_id: t.Id,
      task_subject: (t.Subject || '').substring(0, 100),
      account_name: accountName,
    });

    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: taskLine },
      accessory: {
        type: "button",
        text: { type: "plain_text", text: "\u2705 Complete", emoji: true },
        action_id: "task_complete_" + (t.Id || '').substring(0, 15),
        value: completePayload
      }
    });
  }
} else {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Open Tasks (0)* \u2014 All caught up! :tada:" }
  });
}

// Completed tasks (recent)
if (completedTasks.length > 0) {
  blocks.push({ type: "divider" });
  const completedLines = completedTasks.slice(0, 5).map(t => {
    const owner = t.Owner_Name || t['Owner.Name'] || '';
    return `\u2022 ${t.Subject || 'Task'} \u2014 ${owner} \u00b7 Completed`;
  }).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*\u2705 Recently Completed (${completedTasks.length})*\n${completedLines}` }
  });
}

// PeopleGlass links
blocks.push({ type: "divider" });
blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: "<https://glass.people.ai/sheet/514ff6d1-7e51-4bab-872e-b1f35ce13f5b|My Open Tasks>  \u00b7  <https://glass.people.ai/sheet/3be9132b-cf08-4f94-9164-651bb5804e51|My Completed Tasks>  \u00b7  <https://glass.people.ai/sheet/40ce97c4-0237-4afb-8d47-b10cf4792253|Last 30 Days>" }]
});

const notificationText = `${accountName} \u2014 ${openTasks.length} open task${openTasks.length === 1 ? '' : 's'}`;

return [{ json: {
  blocks: JSON.stringify(blocks),
  notificationText,
  channelId,
  messageTs,
  assistantName,
  assistantEmoji,
  requestId: callbackData.requestId,
}}];
""".strip()

    build_node = make_code_node("Build Task List", build_code, [1460, 300])

    # --- Node 5: Update Thinking Message (chat.update) ---
    update_body = (
        '={{ JSON.stringify({ '
        'channel: $json.channelId, '
        'ts: $json.messageTs, '
        'text: $json.notificationText, '
        'blocks: JSON.parse($json.blocks), '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji '
        '}) }}'
    )
    update_node = make_slack_http_node(
        "Update Thinking Message", SLACK_CHAT_UPDATE,
        update_body, [1860, 300]
    )

    # --- Node 6: Mark Request Done (PATCH pending_actions) ---
    mark_done_node = {
        "parameters": {
            "method": "PATCH",
            "url": f"={{{{{SUPABASE_URL}}}}}/rest/v1/pending_actions?opportunity_id=eq.{{{{{{ $json.requestId }}}}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Prefer", "value": "return=representation"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ status: "resolved", resolved_at: new Date().toISOString() }) }}',
            "options": {},
        },
        "id": uid(),
        "name": "Mark Request Done",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [2260, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }

    # Fix the URL to use the actual Supabase URL (not expression-wrapped constant)
    mark_done_node["parameters"]["url"] = (
        f"={SUPABASE_URL}/rest/v1/pending_actions"
        "?opportunity_id=eq.{{ $json.requestId }}"
        "&action_type=eq.get_tasks"
    )

    nodes = [webhook_node, parse_node, fetch_context_node, build_node, update_node, mark_done_node]

    connections = {
        "Callback Webhook": {"main": [[{"node": "Parse Callback", "type": "main", "index": 0}]]},
        "Parse Callback": {"main": [[{"node": "Fetch Request Context", "type": "main", "index": 0}]]},
        "Fetch Request Context": {"main": [[{"node": "Build Task List", "type": "main", "index": 0}]]},
        "Build Task List": {"main": [[{"node": "Update Thinking Message", "type": "main", "index": 0}]]},
        "Update Thinking Message": {"main": [[{"node": "Mark Request Done", "type": "main", "index": 0}]]},
    }

    return {
        "name": "Task Callback Handler",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Part 2: Slack Events Handler — add `tasks` command
# ═══════════════════════════════════════════════════════════════════════

def modify_events_handler(nodes, connections):
    changes = 0

    # ── 1. Route by State — add `tasks` routing ──────────────────────
    rbs = find_node(nodes, "Route by State")
    code = rbs["parameters"]["jsCode"]

    # Insert tasks exact match before the recap line
    recap_marker = "  else if (lower === 'recap' || lower.startsWith('recap ')) route = 'cmd_recap';"
    tasks_exact = "  else if (lower === 'tasks' || lower === 'task' || lower.startsWith('tasks ')) route = 'cmd_tasks';\n"
    if "cmd_tasks" not in code:
        code = code.replace(recap_marker, tasks_exact + recap_marker)
        changes += 1

    # Add fuzzy matching
    recap_fuzzy_marker = "    else if (/\\b(recap|meeting\\s+recap)\\b/i.test(lower)) route = 'cmd_recap';"
    tasks_fuzzy = "    else if (/\\bmy tasks\\b/i.test(lower)) route = 'cmd_tasks';\n"
    if "my tasks" not in code:
        code = code.replace(recap_fuzzy_marker, tasks_fuzzy + recap_fuzzy_marker)
        changes += 1

    rbs["parameters"]["jsCode"] = code

    # ── 2. Switch Route — add cmd_tasks output ───────────────────────
    sw = find_node(nodes, "Switch Route")
    rules = sw["parameters"]["rules"]["values"]

    has_tasks = any(r.get("outputKey") == "cmd_tasks" for r in rules)
    if not has_tasks:
        new_rule = {
            "outputKey": "cmd_tasks",
            "renameOutput": True,
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [make_switch_condition("={{ $json.route }}", "cmd_tasks")],
            },
        }
        rules.append(new_rule)
        changes += 1

    tasks_output_idx = next(
        i for i, r in enumerate(rules) if r.get("outputKey") == "cmd_tasks"
    )

    # ── 3. Build Help Response — add `tasks` ─────────────────────────
    help_node = find_node(nodes, "Build Help Response")
    hcode = help_node["parameters"]["jsCode"]

    # Add to skills list (on the Available shortcuts line)
    old_avail = "Available shortcuts: `brief` \u00b7 `meet` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `stakeholders` \u00b7 `followup`"
    new_avail = "Available shortcuts: `brief` \u00b7 `meet` \u00b7 `tasks` \u00b7 `insights` \u00b7 `presentation` \u00b7 `bbr` \u00b7 `stakeholders` \u00b7 `followup`"
    if "`tasks`" not in hcode:
        hcode = hcode.replace(old_avail, new_avail)
        changes += 1

    # Add detailed help entry before 'recap' entry
    tasks_help = (
        "    'tasks': \"*`tasks` \\u2014 Salesforce Tasks*\\n\\n\""
        " +\n      \"View your Salesforce tasks for any account, with the ability to mark them complete directly from Slack.\\n\\n\""
        " +\n      \"*Usage:*\\n\""
        " +\n      \"\\u2022 `tasks AiDoc` \\u2014 see open tasks for AiDoc\\n\""
        " +\n      \"\\u2022 `tasks` \\u2014 see all your tasks\\n\\n\""
        " +\n      \"_Or just ask naturally: \\\"my tasks for AiDoc\\\"_\","
    )
    if "'tasks':" not in hcode:
        hcode = hcode.replace("    'recap':", tasks_help + "\n    'recap':")
        changes += 1

    # Add aliases
    old_alias_end = "'recaps': 'recap', 'meeting recap': 'recap', 'meeting recaps': 'recap'"
    new_alias_end = "'recaps': 'recap', 'meeting recap': 'recap', 'meeting recaps': 'recap', 'my tasks': 'tasks', 'task': 'tasks', 'sf tasks': 'tasks'"
    if "'my tasks': 'tasks'" not in hcode:
        hcode = hcode.replace(old_alias_end, new_alias_end)
        changes += 1

    help_node["parameters"]["jsCode"] = hcode

    # ── 4. Create new nodes ──────────────────────────────────────────
    base_x = 2672
    base_y = 7600  # Below existing nodes

    # --- Prepare Tasks Input ---
    prepare_tasks_code = r"""
const data = $('Route by State').first().json;
const text = (data.text || '').trim();

// Strip command keywords to find account name
const accountArg = text
  .replace(/^tasks?\s*/i, '')
  .replace(/\b(my|the|a|for|with|about|on|please|sf|salesforce)\b/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const requestId = 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

const ur = data.userRecord || {};

return [{ json: {
  ...data,
  hasAccount: !!accountArg,
  accountArg: accountArg || 'all',
  requestId,
  userEmail: ur.email || '',
  assistantName: ur.assistant_name || data.assistantName || 'Aria',
  assistantEmoji: ur.assistant_emoji || data.assistantEmoji || ':robot_face:',
}}];
""".strip()

    prepare_tasks = make_code_node("Prepare Tasks Input", prepare_tasks_code, [base_x, base_y])
    nodes.append(prepare_tasks)
    changes += 1

    # --- Send Tasks Thinking ---
    thinking_body = (
        '={{ JSON.stringify({ '
        'channel: $json.channelId, '
        'text: $json.assistantEmoji + " Looking up tasks" + ($json.accountArg !== "all" ? " for *" + $json.accountArg + "*" : "") + "...", '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji '
        '}) }}'
    )
    send_thinking = make_slack_http_node(
        "Send Tasks Thinking", SLACK_CHAT_POST,
        thinking_body, [base_x + 400, base_y]
    )
    nodes.append(send_thinking)
    changes += 1

    # --- Store Request Context (Supabase HTTP insert) ---
    store_context_body = (
        '={{ JSON.stringify({ '
        'user_id: $("Route by State").first().json.dbUserId, '
        'action_type: "get_tasks", '
        'status: "pending", '
        'opportunity_id: $("Prepare Tasks Input").first().json.requestId, '
        'draft_content: "tasks lookup", '
        'context: JSON.stringify({ '
        '  channel_id: $("Route by State").first().json.channelId, '
        '  message_ts: $("Send Tasks Thinking").first().json.ts, '
        '  assistant_name: $("Prepare Tasks Input").first().json.assistantName, '
        '  assistant_emoji: $("Prepare Tasks Input").first().json.assistantEmoji, '
        '  account_name: $("Prepare Tasks Input").first().json.accountArg '
        '}) '
        '}) }}'
    )
    store_context = make_supabase_http_node(
        "Store Task Request", "POST", "pending_actions",
        [base_x + 800, base_y],
        json_body=store_context_body,
    )
    nodes.append(store_context)
    changes += 1

    # --- Send to Workato ---
    workato_body = (
        '={{ JSON.stringify({ '
        'action: "get_tasks", '
        'account_name: $("Prepare Tasks Input").first().json.accountArg, '
        'user_email: $("Prepare Tasks Input").first().json.userEmail, '
        'callback_url: "' + CALLBACK_WEBHOOK_URL + '", '
        'request_id: $("Prepare Tasks Input").first().json.requestId '
        '}) }}'
    )
    send_workato = {
        "parameters": {
            "method": "POST",
            "url": WORKATO_READ_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": workato_body,
            "options": {},
        },
        "id": uid(),
        "name": "Send to Workato",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 1200, base_y],
    }
    nodes.append(send_workato)
    changes += 1

    # ── 5. Wire connections ──────────────────────────────────────────
    sw_name = "Switch Route"

    # Initialize Switch Route connections if needed
    if sw_name not in connections:
        connections[sw_name] = {"main": []}
    main_outputs = connections[sw_name]["main"]

    # Pad outputs to the right index
    while len(main_outputs) <= tasks_output_idx:
        main_outputs.append([])

    main_outputs[tasks_output_idx] = [{"node": "Prepare Tasks Input", "type": "main", "index": 0}]

    # Chain: Prepare → Send Thinking → Store Context → Send to Workato
    connections["Prepare Tasks Input"] = {
        "main": [[{"node": "Send Tasks Thinking", "type": "main", "index": 0}]]
    }
    connections["Send Tasks Thinking"] = {
        "main": [[{"node": "Store Task Request", "type": "main", "index": 0}]]
    }
    connections["Store Task Request"] = {
        "main": [[{"node": "Send to Workato", "type": "main", "index": 0}]]
    }
    changes += 1

    return changes


# ═══════════════════════════════════════════════════════════════════════
# Part 3: Interactive Events Handler — add task_complete button
# ═══════════════════════════════════════════════════════════════════════

def modify_interactive_handler(nodes, connections):
    changes = 0

    # ── 1. Route Action — add task_complete_ output ──────────────────
    sw = find_node(nodes, "Route Action")
    rules = sw["parameters"]["rules"]["values"]

    has_task_complete = any(
        r.get("outputKey") == "Task Complete" for r in rules
    )
    if not has_task_complete:
        new_rule = {
            "outputKey": "Task Complete",
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
                    "rightValue": "task_complete_",
                }],
            },
        }
        rules.append(new_rule)
        changes += 1

    task_complete_idx = next(
        i for i, r in enumerate(rules) if r.get("outputKey") == "Task Complete"
    )

    # ── 2. Build Complete Payload (Code) ─────────────────────────────
    base_x = 3600
    base_y = 3400

    build_payload_code = r"""
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

return [{ json: {
  webhook_payload: {
    action: 'update_task',
    task_id: context.task_id || '',
    fields: { Status: 'Completed' }
  },
  channelId: payload.channelId || '',
  messageTs: payload.messageTs || '',
  taskSubject: context.task_subject || '',
  accountName: context.account_name || '',
  userId: payload.userId || '',
}}];
""".strip()

    build_payload = make_code_node("Build Complete Payload", build_payload_code, [base_x, base_y])
    nodes.append(build_payload)
    changes += 1

    # ── 3. Send Complete to Workato (HTTP) ───────────────────────────
    send_complete = {
        "parameters": {
            "method": "POST",
            "url": WORKATO_WRITE_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Send Complete to Workato",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 400, base_y],
    }
    nodes.append(send_complete)
    changes += 1

    # ── 4. Confirm Task Complete (Slack thread reply) ────────────────
    confirm_body = (
        '={{ JSON.stringify({ '
        'channel: $("Build Complete Payload").first().json.channelId, '
        'thread_ts: $("Build Complete Payload").first().json.messageTs, '
        'text: ":white_check_mark: Marked complete: " + $("Build Complete Payload").first().json.taskSubject '
        '}) }}'
    )
    confirm_node = make_slack_http_node(
        "Confirm Task Complete", SLACK_CHAT_POST,
        confirm_body, [base_x + 800, base_y]
    )
    nodes.append(confirm_node)
    changes += 1

    # ── 5. Wire connections ──────────────────────────────────────────
    sw_name = "Route Action"
    if sw_name not in connections:
        connections[sw_name] = {"main": []}
    main_outputs = connections[sw_name]["main"]

    while len(main_outputs) <= task_complete_idx:
        main_outputs.append([])

    main_outputs[task_complete_idx] = [{"node": "Build Complete Payload", "type": "main", "index": 0}]

    connections["Build Complete Payload"] = {
        "main": [[{"node": "Send Complete to Workato", "type": "main", "index": 0}]]
    }
    connections["Send Complete to Workato"] = {
        "main": [[{"node": "Confirm Task Complete", "type": "main", "index": 0}]]
    }
    changes += 1

    return changes


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Part 1: Creating Task Callback Handler workflow")
    print("=" * 60)
    callback_wf = build_callback_workflow()
    result = create_or_update_workflow(callback_wf, "Task Callback Handler.json")
    print(f"  Workflow ID: {result['id']}")
    print(f"  Webhook: {CALLBACK_WEBHOOK_URL}")

    print()
    print("=" * 60)
    print("Part 2: Adding `tasks` command to Slack Events Handler")
    print("=" * 60)
    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modify_events_handler,
    )

    print()
    print("=" * 60)
    print("Part 3: Adding task_complete handler to Interactive Events Handler")
    print("=" * 60)
    modify_workflow(
        WF_INTERACTIVE_HANDLER,
        "Interactive Events Handler.json",
        modify_interactive_handler,
    )

    print()
    print("Done! All three parts deployed.")


if __name__ == "__main__":
    main()
