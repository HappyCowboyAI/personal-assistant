"""
Create the "Task Resolution Handler" n8n workflow.

Webhook-based async callback handler that:
1. Receives open CRM tasks from Workato (async callback pattern)
2. Stores individual tasks in Supabase pending_actions
3. On "done" signal: fetches stored tasks, groups by account
4. Runs a Claude + People.ai MCP agent per account to detect completed tasks
5. Marks completed tasks via Workato webhook
6. Posts a summary DM to Slack (only if tasks were resolved)
7. Cleans up stored tasks from Supabase

Same async callback pattern as Task Callback Handler (q26UwKsj67DlBpYt).
"""

from n8n_helpers import (
    uid,
    create_or_update_workflow,
    find_node,
    modify_workflow,
    make_code_node,
    make_slack_http_node,
    make_supabase_http_node,
    make_agent_trio,
    NODE_HTTP_REQUEST,
    NODE_IF,
    NODE_SPLIT_IN_BATCHES,
    SUPABASE_CRED,
    SLACK_CRED,
    ANTHROPIC_CRED,
    MCP_CRED,
    SUPABASE_URL,
    SLACK_CHAT_POST,
    SLACK_CONVERSATIONS_OPEN,
    PEOPLEAI_MCP_URL,
    NODE_AGENT,
    NODE_ANTHROPIC_CHAT,
    NODE_MCP_CLIENT,
    MODEL_SONNET,
    WF_FOLLOWUP_CRON,
    WF_EVENTS_HANDLER,
)

WORKATO_WRITE_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"
PEOPLEGLASS_TASKS_URL = "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"


def create_resolution_handler():
    """Build and deploy the Task Resolution Handler workflow."""

    nodes = []
    connections = {}

    # ── Layout constants (x positions for the flow) ───────────────────
    x_start = 0
    y_main = 200
    y_store = 400  # branch for storing individual tasks

    # ── Node 1: Resolution Callback (Webhook) ────────────────────────
    webhook = {
        "parameters": {
            "httpMethod": "POST",
            "path": "task-resolution-callback",
            "options": {},
        },
        "id": uid(),
        "name": "Resolution Callback",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2.1,
        "position": [x_start, y_main],
        "webhookId": uid(),
    }
    nodes.append(webhook)

    # ── Node 2: Parse Callback (Code) ────────────────────────────────
    parse_callback_js = r"""const body = $input.first().json.body || $input.first().json;
const requestId = body.request_id || '';
const accountName = body.account_name || '';
const isDone = (body.done === 'true' || body.done === true);

if (!isDone) {
  return [{ json: {
    isDone: false,
    requestId,
    accountName,
    task: {
      Id: body.task_id || '',
      Subject: body.task_subject || '',
      Status: body.task_status || '',
      Priority: body.task_priority || '',
      ActivityDate: body.task_due_date || '',
      Description: body.task_description || '',
      Owner_Name: body.task_owner_name || '',
      Owner_Email: body.task_owner_email || '',
      Category: body.task_category || '',
      Account_Name: body.task_account_name || '',
    }
  }}];
} else {
  return [{ json: {
    isDone: true,
    requestId,
    accountName,
  }}];
}"""
    parse_callback = make_code_node("Parse Callback", parse_callback_js, [x_start + 240, y_main])
    nodes.append(parse_callback)

    # ── Node 3: Is Done? (IF) ────────────────────────────────────────
    is_done = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "caseSensitive": True,
                    "typeValidation": "loose",
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.isDone }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "true",
                        },
                    }
                ],
            },
            "options": {},
        },
        "id": uid(),
        "name": "Is Done?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [x_start + 480, y_main],
    }
    nodes.append(is_done)

    # ── Node 4 (false branch): Store Task ────────────────────────────
    store_task = {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Prefer", "value": "return=representation"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ user_id: null, action_type: 'resolution_task', opportunity_id: $json.requestId, draft_content: JSON.stringify($json.task), context: JSON.stringify({ account_name: $json.accountName }), status: 'pending' }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Store Task",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [x_start + 720, y_store],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(store_task)

    # ── Node 5 (true branch): Fetch Request Context ──────────────────
    fetch_request_context = {
        "parameters": {
            "url": f"={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $json.requestId }}}}&action_type=eq.resolution_request&select=*&limit=1",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Request Context",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [x_start + 720, y_main],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(fetch_request_context)

    # ── Node 6: Fetch All Tasks ──────────────────────────────────────
    fetch_all_tasks = {
        "parameters": {
            "url": f"={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $('Parse Callback').first().json.requestId }}}}&action_type=eq.resolution_task&select=draft_content",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": uid(),
        "name": "Fetch All Tasks",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [x_start + 960, y_main],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(fetch_all_tasks)

    # ── Node 7: Build Resolution Tasks (Code) ────────────────────────
    build_resolution_js = r"""const callbackData = $('Parse Callback').first().json;
const contextArr = $('Fetch Request Context').all().map(i => i.json);
const context = Array.isArray(contextArr[0]) ? contextArr[0][0] : contextArr[0];
const taskRows = $('Fetch All Tasks').all().map(i => i.json);
const allTaskRows = Array.isArray(taskRows[0]) ? taskRows[0] : taskRows;

let meta = context.context || {};
if (typeof meta === 'string') try { meta = JSON.parse(meta); } catch(e) { meta = {}; }

const tasks = allTaskRows.map(row => {
  try { return JSON.parse(row.draft_content || '{}'); } catch(e) { return {}; }
}).filter(t => t.Id);

// Only process open tasks
const openTasks = tasks.filter(t => t.Status !== 'Completed');

// Group by account
const byAccount = {};
for (const t of openTasks) {
  const acct = t.Account_Name || 'Unknown';
  if (!byAccount[acct]) byAccount[acct] = [];
  byAccount[acct].push(t);
}

const channelId = meta.channel_id || '';
const assistantName = meta.assistant_name || 'Aria';
const assistantEmoji = meta.assistant_emoji || ':robot_face:';
const requestId = callbackData.requestId;

// Build one item per account for the loop
const accounts = Object.entries(byAccount).map(([accountName, accountTasks]) => {
  const taskList = accountTasks.map(t => {
    return `- ID: ${t.Id} | Subject: ${t.Subject} | Status: ${t.Status} | Due: ${t.ActivityDate || 'none'} | Owner: ${t.Owner_Name || 'unknown'}`;
  }).join('\n');

  return {
    json: {
      accountName,
      taskList,
      tasks: accountTasks,
      channelId,
      assistantName,
      assistantEmoji,
      requestId,
      totalOpenTasks: openTasks.length,
    }
  };
});

if (accounts.length === 0) {
  // No open tasks to resolve — pass through with empty marker
  return [{ json: {
    accountName: '__NO_ACCOUNTS__',
    taskList: '',
    tasks: [],
    channelId,
    assistantName,
    assistantEmoji,
    requestId,
    totalOpenTasks: 0,
  }}];
}

return accounts;"""
    build_resolution = make_code_node("Build Resolution Tasks", build_resolution_js, [x_start + 1200, y_main])
    nodes.append(build_resolution)

    # ── Node 8: Loop Accounts (SplitInBatches) ───────────────────────
    loop_accounts = {
        "parameters": {"batchSize": 1, "options": {}},
        "id": uid(),
        "name": "Loop Accounts",
        "type": NODE_SPLIT_IN_BATCHES,
        "typeVersion": 3,
        "position": [x_start + 1440, y_main],
    }
    nodes.append(loop_accounts)

    # ── Node 9-11: Resolution Agent + Anthropic + MCP ────────────────
    system_prompt = r"""You are a task resolution analyst. You evaluate whether CRM tasks have been completed based on recent account activity from People.ai SalesAI.

RULES:
- Only mark a task COMPLETE if there is CLEAR evidence the work was done
- Evidence includes: email sent, meeting held, document delivered, issue resolved, follow-up completed
- When in doubt, leave as OPEN
- Be conservative — false completions are worse than missed completions
- Output ONLY valid JSON, no prose"""

    user_prompt_expr = """={{ 'Review these open CRM tasks for ' + $json.accountName + ':\\n' + $json.taskList + '\\n\\nUse People.ai SalesAI tools (ask_sales_ai_about_account) to check recent activity, emails, and meeting outcomes for ' + $json.accountName + '.\\n\\nFor each task, determine if it was completed based on evidence from recent activity.\\n\\nOutput JSON:\\n{\\n  "account_name": "' + $json.accountName + '",\\n  "results": [\\n    {"id": "SF_TASK_ID", "status": "COMPLETE" or "OPEN", "evidence": "one-line reason"}\\n  ]\\n}' }}"""

    agent_pos = [x_start + 1680, y_main]
    agent_trio = make_agent_trio(
        "Resolution Agent", "Resolution",
        system_prompt, user_prompt_expr,
        agent_pos, connections,
    )
    nodes.extend(agent_trio)

    # ── Node 12: Parse Resolution Results (Code) ─────────────────────
    parse_results_js = r"""const agentOutput = $('Resolution Agent').first().json.output || '';
const accountData = $('Loop Accounts').first().json;
const accountName = accountData.accountName;
const tasks = accountData.tasks || [];

let results = [];

// Try to extract JSON from the agent response
try {
  // Look for JSON block
  const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)```/) || agentOutput.match(/(\{[\s\S]*"results"[\s\S]*\})/);
  if (jsonMatch) {
    const parsed = JSON.parse(jsonMatch[1] || jsonMatch[0]);
    results = parsed.results || [];
  } else {
    // Try parsing the whole output as JSON
    const parsed = JSON.parse(agentOutput);
    results = parsed.results || [];
  }
} catch (e) {
  // Agent failed or returned non-JSON — leave all as OPEN
  results = tasks.map(t => ({
    id: t.Id,
    status: 'OPEN',
    evidence: 'Agent did not return valid results',
  }));
}

// Map results back to tasks
const completedTasks = [];
const openTasks = [];

for (const t of tasks) {
  const r = results.find(r => r.id === t.Id);
  if (r && r.status === 'COMPLETE') {
    completedTasks.push({
      id: t.Id,
      subject: t.Subject,
      evidence: r.evidence || '',
      accountName: t.Account_Name || accountName,
    });
  } else {
    openTasks.push({
      id: t.Id,
      subject: t.Subject,
      evidence: r ? r.evidence : 'No evidence found',
      accountName: t.Account_Name || accountName,
    });
  }
}

return [{ json: {
  accountName,
  completedTasks,
  openTasks,
  completedCount: completedTasks.length,
  openCount: openTasks.length,
  channelId: accountData.channelId,
  assistantName: accountData.assistantName,
  assistantEmoji: accountData.assistantEmoji,
  requestId: accountData.requestId,
}}];"""
    parse_results = make_code_node("Parse Resolution Results", parse_results_js, [x_start + 1920, y_main])
    nodes.append(parse_results)

    # ── Node 13: Prepare Completion Payloads (Code) ──────────────────
    prepare_payloads_js = r"""const data = $input.first().json;
const completed = data.completedTasks || [];

if (completed.length === 0) {
  // Nothing to mark complete — skip to next account
  return [{ json: { ...data, hasCompletions: false } }];
}

// Fan out one item per completed task for the Workato webhook
const items = completed.map(t => ({
  json: {
    payload: {
      action: 'update_task',
      salesforce_object: 'Task',
      task_id: t.id,
      fields: { Status: 'Completed' },
      context: { account_name: t.accountName },
    },
    // Carry forward metadata for downstream
    _meta: {
      accountName: data.accountName,
      completedTasks: data.completedTasks,
      openTasks: data.openTasks,
      completedCount: data.completedCount,
      openCount: data.openCount,
      channelId: data.channelId,
      assistantName: data.assistantName,
      assistantEmoji: data.assistantEmoji,
      requestId: data.requestId,
      hasCompletions: true,
    },
  }
}));

return items;"""
    prepare_payloads = make_code_node("Prepare Completion Payloads", prepare_payloads_js, [x_start + 2160, y_main])
    nodes.append(prepare_payloads)

    # ── Node 14: Mark Task Complete (HTTP POST to Workato) ───────────
    mark_complete = {
        "parameters": {
            "method": "POST",
            "url": WORKATO_WRITE_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.payload) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Mark Task Complete",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [x_start + 2400, y_main],
    }
    nodes.append(mark_complete)

    # ── Node 15: Collect All Results (Code) — after loop done ────────
    collect_results_js = r"""// Collect results from all loop iterations
const allItems = $('Parse Resolution Results').all();
let totalCompleted = 0;
let totalOpen = 0;
const completedDetails = [];
let channelId = '';
let assistantName = 'Aria';
let assistantEmoji = ':robot_face:';
let requestId = '';

for (const item of allItems) {
  const d = item.json;
  totalCompleted += (d.completedCount || 0);
  totalOpen += (d.openCount || 0);
  channelId = d.channelId || channelId;
  assistantName = d.assistantName || assistantName;
  assistantEmoji = d.assistantEmoji || assistantEmoji;
  requestId = d.requestId || requestId;

  for (const t of (d.completedTasks || [])) {
    completedDetails.push(t);
  }
}

return [{ json: {
  totalCompleted,
  totalOpen,
  completedDetails,
  channelId,
  assistantName,
  assistantEmoji,
  requestId,
  hasSummary: totalCompleted > 0,
}}];"""
    collect_results = make_code_node("Collect All Results", collect_results_js, [x_start + 1680, y_main - 250])
    nodes.append(collect_results)

    # ── Node 16: Build Summary (Code) — only if completedCount > 0 ───
    build_summary_js = r"""const data = $input.first().json;

if (!data.hasSummary || data.totalCompleted === 0) {
  return [{ json: { ...data, skipSummary: true } }];
}

const completed = data.completedDetails || [];
const lines = completed.map(t => {
  return `:white_check_mark: ~${(t.subject || 'Task').substring(0, 80)}~ (${t.evidence || 'activity detected'})`;
}).join('\n');

const summaryText = `:clipboard: *Task Update*\nI reviewed your open tasks against recent activity:\n\n${lines}\n\nMarked ${data.totalCompleted} task${data.totalCompleted !== 1 ? 's' : ''} complete \u00b7 ${data.totalOpen} still open`;

return [{ json: {
  ...data,
  summaryText,
  skipSummary: false,
}}];"""
    build_summary = make_code_node("Build Summary", build_summary_js, [x_start + 1920, y_main - 250])
    nodes.append(build_summary)

    # ── Node 17: Has Summary? (IF) ───────────────────────────────────
    has_summary = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "caseSensitive": True,
                    "typeValidation": "loose",
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.skipSummary }}",
                        "rightValue": True,
                        "operator": {
                            "type": "boolean",
                            "operation": "false",
                        },
                    }
                ],
            },
            "options": {},
        },
        "id": uid(),
        "name": "Has Summary?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [x_start + 2160, y_main - 250],
    }
    nodes.append(has_summary)

    # ── Node 18: Format Summary DM (Code) ────────────────────────────
    format_summary_js = r"""const data = $input.first().json;
const completed = data.completedDetails || [];

const blocks = [];

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: data.summaryText }
});

blocks.push({ type: "divider" });

blocks.push({
  type: "actions",
  elements: [{
    type: "button",
    text: { type: "plain_text", text: ":clipboard: All Tasks Today", emoji: true },
    url: "PEOPLEGLASS_URL",
    action_id: "resolution_view_tasks"
  }]
});

return [{ json: {
  channelId: data.channelId,
  assistantName: data.assistantName,
  assistantEmoji: data.assistantEmoji,
  blocks: JSON.stringify(blocks),
  text: 'Task Update: Marked ' + data.totalCompleted + ' task' + (data.totalCompleted !== 1 ? 's' : '') + ' complete',
}}];""".replace("PEOPLEGLASS_URL", PEOPLEGLASS_TASKS_URL)
    format_summary = make_code_node("Format Summary DM", format_summary_js, [x_start + 2400, y_main - 250])
    nodes.append(format_summary)

    # ── Node 19: Send Summary DM (Slack) ─────────────────────────────
    send_summary = make_slack_http_node(
        "Send Summary DM",
        SLACK_CHAT_POST,
        "={{ JSON.stringify({ channel: $json.channelId, text: $json.text, blocks: JSON.parse($json.blocks), username: $json.assistantName, icon_emoji: $json.assistantEmoji }) }}",
        [x_start + 2640, y_main - 250],
    )
    nodes.append(send_summary)

    # ── Node 20: Cleanup Stored Tasks (Supabase DELETE) ──────────────
    cleanup = {
        "parameters": {
            "method": "DELETE",
            "url": f"={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $('Parse Callback').first().json.requestId }}}}&action_type=in.(resolution_task,resolution_request)",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Prefer", "value": "return=representation"},
                ]
            },
            "options": {},
        },
        "id": uid(),
        "name": "Cleanup Stored Tasks",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [x_start + 2880, y_main - 250],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(cleanup)

    # ── Connections ───────────────────────────────────────────────────
    def conn(target_name, index=0):
        return [{"node": target_name, "type": "main", "index": index}]

    connections["Resolution Callback"] = {"main": [conn("Parse Callback")]}
    connections["Parse Callback"] = {"main": [conn("Is Done?")]}

    # IF node: output 0 = true (isDone), output 1 = false (store)
    connections["Is Done?"] = {
        "main": [
            conn("Fetch Request Context"),  # true → fetch context
            conn("Store Task"),              # false → store task
        ]
    }

    connections["Store Task"] = {"main": [[]]}  # dead end

    connections["Fetch Request Context"] = {"main": [conn("Fetch All Tasks")]}
    connections["Fetch All Tasks"] = {"main": [conn("Build Resolution Tasks")]}
    connections["Build Resolution Tasks"] = {"main": [conn("Loop Accounts")]}

    # SplitInBatches: output 0 = done, output 1 = loop
    connections["Loop Accounts"] = {
        "main": [
            conn("Collect All Results"),  # done → collect
            conn("Resolution Agent"),     # loop → agent
        ]
    }

    connections["Resolution Agent"] = {"main": [conn("Parse Resolution Results")]}
    connections["Parse Resolution Results"] = {"main": [conn("Prepare Completion Payloads")]}
    connections["Prepare Completion Payloads"] = {"main": [conn("Mark Task Complete")]}
    connections["Mark Task Complete"] = {"main": [conn("Loop Accounts")]}  # loop back

    connections["Collect All Results"] = {"main": [conn("Build Summary")]}
    connections["Build Summary"] = {"main": [conn("Has Summary?")]}

    # Has Summary?: output 0 = true (skipSummary is false → send), output 1 = false (skip)
    connections["Has Summary?"] = {
        "main": [
            conn("Format Summary DM"),       # true → format & send
            conn("Cleanup Stored Tasks"),     # false → cleanup only
        ]
    }

    connections["Format Summary DM"] = {"main": [conn("Send Summary DM")]}
    connections["Send Summary DM"] = {"main": [conn("Cleanup Stored Tasks")]}
    connections["Cleanup Stored Tasks"] = {"main": [[]]}

    # ── Assemble workflow ────────────────────────────────────────────
    workflow = {
        "name": "Task Resolution Handler",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
            "availableInMCP": False,
        },
        "staticData": None,
    }

    print("=== Creating Task Resolution Handler ===")
    result = create_or_update_workflow(workflow, "Task Resolution Handler.json")
    print(f"\nDone! Workflow ID: {result['id']}")
    print(f"Webhook URL: https://scottai.trackslife.com/webhook/task-resolution-callback")
    return result


WORKATO_READ_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read"
CALLBACK_URL = "https://scottai.trackslife.com/webhook/task-resolution-callback"


def _make_fire_task_resolution_node(name, position, parse_output_ref,
                                    channel_expr=None, open_dm_ref=None):
    """Create the 'Fire Task Resolution' Code node.

    parse_output_ref: n8n node name to pull meeting/email data from
    channel_expr:     JS expression for channelId (e.g. "data.channelId")
    open_dm_ref:      n8n node name whose .channel.id has the DM channel
                      (used when channel_expr is not provided)
    """
    if channel_expr:
        channel_js = channel_expr
    elif open_dm_ref:
        channel_js = f"$('{open_dm_ref}').first().json.channel.id || ''"
    else:
        channel_js = "data.channelId || ''"

    js = f"""const data = $('{parse_output_ref}').first().json;
const m = data.meeting || {{}};
const requestId = 'res_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

return [{{ json: {{
  ...data,
  resolutionRequestId: requestId,
  resolutionPayload: {{
    action: 'get_tasks_resolution',
    account_name: m.accountName || '',
    user_email: data.email || '',
    callback_url: '{CALLBACK_URL}',
    request_id: requestId,
  }},
  resolutionContext: {{
    channel_id: {channel_js},
    assistant_name: data.assistantName || 'Aria',
    assistant_emoji: data.assistantEmoji || ':robot_face:',
    mode: 'recap',
    account_name: m.accountName || '',
  }}
}}}}];"""
    return make_code_node(name, js, position)


def _make_store_resolution_request_node(name, position):
    """Create the 'Store Resolution Request' HTTP node (Supabase insert)."""
    return {
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
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
            "jsonBody": "={{ JSON.stringify({ opportunity_id: $json.resolutionRequestId, action_type: 'resolution_request', context: JSON.stringify($json.resolutionContext), status: 'pending' }) }}",
            "options": {},
        },
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }


def _make_send_resolution_to_workato_node(name, position):
    """Create the 'Send Resolution to Workato' HTTP node (fire-and-forget)."""
    return {
        "parameters": {
            "method": "POST",
            "url": WORKATO_READ_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.resolutionPayload) }}",
            "options": {"timeout": 15000},
        },
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "continueOnFail": True,
    }


def integrate_into_recap():
    """Add task resolution fire-and-forget nodes to Follow-up Cron and Events Handler."""

    # ── 1. Follow-up Cron ──────────────────────────────────────────────
    print("=" * 60)
    print("FOLLOW-UP CRON — adding task resolution nodes")
    print("=" * 60)

    def modify_followup(nodes, connections):
        changes = 0

        # Check if already added
        existing_names = {n["name"] for n in nodes}
        if "Fire Task Resolution" in existing_names:
            print("  Fire Task Resolution already exists — skipping")
            return 0

        # Find Build Auto-Save Payload position for layout reference
        auto_save = find_node(nodes, "Build Auto-Save Payload")
        if not auto_save:
            print("  ERROR: Build Auto-Save Payload not found")
            return 0
        ax, ay = auto_save["position"]

        # Place 3 new nodes in a chain below the existing branches
        # Existing: auto-save at [3620, 304], Send Recap CRM at [3870, 304], Prepare Task at [3870, 504]
        fire_pos = [ax + 250, ay + 400]      # [3870, 704]
        store_pos = [ax + 500, ay + 400]      # [4120, 704]
        send_pos = [ax + 750, ay + 400]       # [4370, 704]

        fire_node = _make_fire_task_resolution_node(
            "Fire Task Resolution", fire_pos,
            "Parse Recap Output", open_dm_ref="Open Bot DM",
        )
        store_node = _make_store_resolution_request_node("Store Resolution Request", store_pos)
        send_node = _make_send_resolution_to_workato_node("Send Resolution to Workato", send_pos)

        nodes.extend([fire_node, store_node, send_node])
        changes += 3
        print(f"  Added 3 nodes: Fire Task Resolution, Store Resolution Request, Send Resolution to Workato")

        # Wire: Build Auto-Save Payload → Fire Task Resolution (as 3rd parallel output)
        auto_save_conns = connections.get("Build Auto-Save Payload", {}).get("main", [[]])
        if auto_save_conns:
            auto_save_conns[0].append({
                "node": "Fire Task Resolution", "type": "main", "index": 0
            })
            print("  Wired Build Auto-Save Payload → Fire Task Resolution (parallel)")
        changes += 1

        # Wire chain: Fire → Store → Send
        connections["Fire Task Resolution"] = {
            "main": [[{"node": "Store Resolution Request", "type": "main", "index": 0}]]
        }
        connections["Store Resolution Request"] = {
            "main": [[{"node": "Send Resolution to Workato", "type": "main", "index": 0}]]
        }
        connections["Send Resolution to Workato"] = {"main": [[]]}
        print("  Wired Fire Task Resolution → Store Resolution Request → Send Resolution to Workato")
        changes += 3

        return changes

    modify_workflow(WF_FOLLOWUP_CRON, "Follow-up Cron.json", modify_followup)

    # ── 2. Slack Events Handler ────────────────────────────────────────
    print()
    print("=" * 60)
    print("SLACK EVENTS HANDLER — adding task resolution OD nodes")
    print("=" * 60)

    def modify_events(nodes, connections):
        changes = 0

        existing_names = {n["name"] for n in nodes}
        if "Fire Task Resolution OD" in existing_names:
            print("  Fire Task Resolution OD already exists — skipping")
            return 0

        # Find Build Auto-Save OD position
        auto_save_od = find_node(nodes, "Build Auto-Save OD")
        if not auto_save_od:
            print("  ERROR: Build Auto-Save OD not found")
            return 0
        ax, ay = auto_save_od["position"]

        # Place below existing branches
        # Existing: auto-save at [6800, 2000], Send CRM OD at [7000, 1900], Prepare Task OD at [7000, 2100]
        fire_pos = [ax + 200, ay + 300]       # [7000, 2300]
        store_pos = [ax + 400, ay + 300]      # [7200, 2300]
        send_pos = [ax + 600, ay + 300]       # [7400, 2300]

        # On-demand recap flow already has channelId in the data flow
        # (set upstream in Recap Build Context from the event data)
        fire_node = _make_fire_task_resolution_node(
            "Fire Task Resolution OD", fire_pos,
            "Recap Parse Output OD", channel_expr="data.channelId || ''",
        )
        store_node = _make_store_resolution_request_node("Store Resolution Request OD", store_pos)
        send_node = _make_send_resolution_to_workato_node("Send Resolution to Workato OD", send_pos)

        nodes.extend([fire_node, store_node, send_node])
        changes += 3
        print(f"  Added 3 nodes: Fire Task Resolution OD, Store Resolution Request OD, Send Resolution to Workato OD")

        # Wire: Build Auto-Save OD → Fire Task Resolution OD (parallel)
        auto_save_conns = connections.get("Build Auto-Save OD", {}).get("main", [[]])
        if auto_save_conns:
            auto_save_conns[0].append({
                "node": "Fire Task Resolution OD", "type": "main", "index": 0
            })
            print("  Wired Build Auto-Save OD → Fire Task Resolution OD (parallel)")
        changes += 1

        # Wire chain
        connections["Fire Task Resolution OD"] = {
            "main": [[{"node": "Store Resolution Request OD", "type": "main", "index": 0}]]
        }
        connections["Store Resolution Request OD"] = {
            "main": [[{"node": "Send Resolution to Workato OD", "type": "main", "index": 0}]]
        }
        connections["Send Resolution to Workato OD"] = {"main": [[]]}
        print("  Wired Fire Task Resolution OD → Store Resolution Request OD → Send Resolution to Workato OD")
        changes += 3

        return changes

    modify_workflow(WF_EVENTS_HANDLER, "Slack Events Handler.json", modify_events)

    print("\n=== Done: Task resolution integrated into both recap flows ===")


def add_scheduled_resolution():
    """Add a parallel branch from the Follow-up Cron trigger for scheduled task resolution.

    Adds 6 nodes:
      Get Resolution Users → Loop Resolution Users → Open DM (Resolution)
      → Build Scheduled Resolution → Store Scheduled Request → Send Scheduled Resolution
    Wired as a second output from the cron trigger, running for ALL active users.
    """

    print("=" * 60)
    print("FOLLOW-UP CRON — adding scheduled task resolution branch")
    print("=" * 60)

    def modify_followup(nodes, connections):
        changes = 0

        existing_names = {n["name"] for n in nodes}
        if "Get Resolution Users" in existing_names:
            print("  Get Resolution Users already exists — skipping")
            return 0

        # Find the trigger node
        trigger = find_node(nodes, "Followup Check (9am + 4pm PT)")
        if not trigger:
            # Fallback: find any scheduleTrigger
            for n in nodes:
                if "scheduleTrigger" in n.get("type", ""):
                    trigger = n
                    break
        if not trigger:
            print("  ERROR: Could not find schedule trigger node")
            return 0

        tx, ty = trigger["position"]
        # Place the new branch below existing nodes (y=800+)
        y_base = 900

        # ── Node 1: Get Resolution Users (Supabase HTTP GET) ────────
        get_users = {
            "parameters": {
                "url": f"{SUPABASE_URL}/rest/v1/users?onboarding_state=eq.complete&select=id,email,slack_user_id,assistant_name,assistant_emoji,digest_scope",
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "options": {},
            },
            "id": uid(),
            "name": "Get Resolution Users",
            "type": NODE_HTTP_REQUEST,
            "typeVersion": 4.2,
            "position": [tx + 224, y_base],
            "credentials": {"supabaseApi": SUPABASE_CRED},
        }
        nodes.append(get_users)
        changes += 1

        # ── Node 2: Loop Resolution Users (SplitInBatches) ──────────
        loop_users = {
            "parameters": {"batchSize": 1, "options": {}},
            "id": uid(),
            "name": "Loop Resolution Users",
            "type": NODE_SPLIT_IN_BATCHES,
            "typeVersion": 3,
            "position": [tx + 474, y_base],
        }
        nodes.append(loop_users)
        changes += 1

        # ── Node 3: Open DM (Resolution) (Slack conversations.open) ─
        open_dm = make_slack_http_node(
            "Open DM (Resolution)",
            SLACK_CONVERSATIONS_OPEN,
            '={{ JSON.stringify({ users: $json.slack_user_id }) }}',
            [tx + 724, y_base],
        )
        nodes.append(open_dm)
        changes += 1

        # ── Node 4: Build Scheduled Resolution (Code) ───────────────
        build_js = r"""const user = $('Loop Resolution Users').first().json;
const dm = $json.channel?.id || $json.channel || '';
const requestId = 'sched_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

return [{ json: {
  resolutionPayload: {
    action: 'get_tasks_resolution',
    account_name: '',
    user_email: user.email || '',
    callback_url: 'CALLBACK_URL_PLACEHOLDER',
    request_id: requestId,
  },
  resolutionContext: {
    channelId: dm,
    assistantName: user.assistant_name || 'Aria',
    assistantEmoji: user.assistant_emoji || ':robot_face:',
    mode: 'scheduled',
  },
  requestId,
}}];""".replace("CALLBACK_URL_PLACEHOLDER", CALLBACK_URL)
        build_node = make_code_node(
            "Build Scheduled Resolution", build_js, [tx + 974, y_base],
        )
        nodes.append(build_node)
        changes += 1

        # ── Node 5: Store Scheduled Request (Supabase HTTP POST) ────
        store_node = {
            "parameters": {
                "method": "POST",
                "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
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
                "jsonBody": "={{ JSON.stringify({ opportunity_id: $json.requestId, action_type: 'resolution_request', context: JSON.stringify($json.resolutionContext), status: 'pending' }) }}",
                "options": {},
            },
            "id": uid(),
            "name": "Store Scheduled Request",
            "type": NODE_HTTP_REQUEST,
            "typeVersion": 4.2,
            "position": [tx + 1224, y_base],
            "credentials": {"supabaseApi": SUPABASE_CRED},
        }
        nodes.append(store_node)
        changes += 1

        # ── Node 6: Send Scheduled Resolution (Workato HTTP POST) ───
        send_node = {
            "parameters": {
                "method": "POST",
                "url": WORKATO_READ_URL,
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify($json.resolutionPayload) }}",
                "options": {"timeout": 15000},
            },
            "id": uid(),
            "name": "Send Scheduled Resolution",
            "type": NODE_HTTP_REQUEST,
            "typeVersion": 4.2,
            "position": [tx + 1474, y_base],
            "continueOnFail": True,
        }
        nodes.append(send_node)
        changes += 1

        # ── Wiring ──────────────────────────────────────────────────
        def conn(target_name, index=0):
            return {"node": target_name, "type": "main", "index": index}

        # Add Get Resolution Users as a parallel output from the trigger
        trigger_name = trigger["name"]
        trigger_conns = connections.get(trigger_name, {}).get("main", [[]])
        if len(trigger_conns) == 0:
            trigger_conns = [[]]
        # Append to the first (and only) output's connection list
        trigger_conns[0].append(conn("Get Resolution Users"))
        connections[trigger_name] = {"main": trigger_conns}
        print(f"  Wired {trigger_name} → Get Resolution Users (parallel with existing)")

        # Get Resolution Users → Loop Resolution Users
        connections["Get Resolution Users"] = {
            "main": [[conn("Loop Resolution Users")]]
        }

        # Loop Resolution Users: output 0 = done (nothing), output 1 = loop
        connections["Loop Resolution Users"] = {
            "main": [
                [],                                    # output 0: done
                [conn("Open DM (Resolution)")],        # output 1: loop
            ]
        }

        # Open DM → Build → Store → Send → loop back
        connections["Open DM (Resolution)"] = {
            "main": [[conn("Build Scheduled Resolution")]]
        }
        connections["Build Scheduled Resolution"] = {
            "main": [[conn("Store Scheduled Request")]]
        }
        connections["Store Scheduled Request"] = {
            "main": [[conn("Send Scheduled Resolution")]]
        }
        connections["Send Scheduled Resolution"] = {
            "main": [[conn("Loop Resolution Users")]]
        }

        print(f"  Added 6 nodes for scheduled task resolution branch")
        print(f"  Chain: Get Resolution Users → Loop → Open DM → Build → Store → Send → Loop")
        return changes

    modify_workflow(WF_FOLLOWUP_CRON, "Follow-up Cron.json", modify_followup)
    print("\n=== Done: Scheduled task resolution branch added to Follow-up Cron ===")


if __name__ == "__main__":
    add_scheduled_resolution()
