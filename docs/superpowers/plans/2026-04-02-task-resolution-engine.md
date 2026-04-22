# Task Resolution Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an AI-powered Task Resolution Engine that detects completed tasks via Backstory SalesAI and auto-marks them in CRM, with two entry points: meeting recaps and a 2x daily scheduled job.

**Architecture:** New callback handler workflow collects open tasks from Workato, groups by account, runs a Claude + MCP agent per account to evaluate task completion, then fires Workato `update_task` for resolved items. Integrates into the existing recap flow and a new scheduled cron.

**Tech Stack:** n8n workflows (API-managed via Python), Workato webhook (async callback), Claude Sonnet 4.5, Backstory MCP, Supabase (pending_actions for callback state)

**Spec:** `docs/superpowers/specs/2026-04-02-task-resolution-engine-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `scripts/add_task_resolution.py` | Python script to create callback handler + integrate into recap + create scheduled job |
| `n8n/workflows/Task Resolution Handler.json` | New callback handler workflow (synced) |
| `n8n/workflows/Follow-up Cron.json` | Modified — recap flow fires task resolution |
| `n8n/workflows/Slack Events Handler.json` | Modified — on-demand recap fires task resolution |

---

### Task 1: Add `get_tasks_resolution` action to Workato (manual)

**Manual steps in Workato recipe "Assistant — Read from Salesforce":**

- [ ] **Step 1: Add IF branch for `get_tasks_resolution` action**

In the Workato recipe, after Step 14 (`action equals get_tasks_digest`), add a new IF step:

- Condition: `Step 1 action` equals `get_tasks_resolution`
- Yes branch: continues to SOQL query
- No branch: falls through to existing logic

- [ ] **Step 2: Add SOQL query for open tasks**

In the Yes branch, add "Search for records using SOQL query in Salesforce":

```sql
SELECT Id, Subject, Description, ActivityDate, Status, Priority, 
       Account.Name, Owner.Email, Owner.Name, CreatedDate
FROM Task
WHERE Owner.Email = '{user_email}'
  AND Status NOT IN ('Completed', 'Cancelled', 'Deferred', 'Expired')
  AND (CreatedDate >= LAST_N_DAYS:7 OR ActivityDate >= LAST_N_DAYS:7 OR ActivityDate >= TODAY)
ORDER BY ActivityDate ASC
```

If `account_name` is provided and not empty, add: `AND Account.Name = '{account_name}'`

Map `user_email` and `account_name` from Step 1 payload context fields.

- [ ] **Step 3: Add FOR EACH loop to send tasks to callback**

FOR EACH record in the SOQL results, add "Send request via HTTP":
- Method: POST
- URL: `{callback_url}` from Step 1 payload
- Body:
```json
{
  "request_id": "{Step 1 request_id}",
  "account_name": "{Record Account.Name}",
  "done": false,
  "task_id": "{Record Id}",
  "task_subject": "{Record Subject}",
  "task_description": "{Record Description}",
  "task_status": "{Record Status}",
  "task_priority": "{Record Priority}",
  "task_due_date": "{Record ActivityDate}",
  "task_owner_email": "{Record Owner.Email}",
  "task_owner_name": "{Record Owner.Name}",
  "task_created_date": "{Record CreatedDate}"
}
```

- [ ] **Step 4: Add "done" signal**

After the FOR EACH loop, add "Send request via HTTP":
- Method: POST
- URL: `{callback_url}` from Step 1 payload
- Body: `{ "request_id": "{Step 1 request_id}", "done": true, "task_count": "{Records count}" }`

- [ ] **Step 5: Test the new action**

```bash
curl -X POST "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "get_tasks_resolution",
    "account_name": "",
    "user_email": "scott.metcalf@people.ai",
    "callback_url": "https://httpbin.org/post",
    "request_id": "test_resolution_001"
  }'
```

Verify in Workato Jobs that the SOQL query runs and tasks are sent to the callback URL.

---

### Task 2: Create Task Resolution Handler workflow

**Files:**
- Create: `scripts/add_task_resolution.py`
- Synced: `n8n/workflows/Task Resolution Handler.json`

This new workflow receives task callbacks from Workato, collects them, runs the resolution agent, and marks completed tasks.

- [ ] **Step 1: Create the script skeleton**

Create `scripts/add_task_resolution.py`:

```python
#!/usr/bin/env python3
"""Task Resolution Engine: callback handler + recap integration + scheduled job."""

import sys, os, json, uuid, requests
sys.path.insert(0, os.path.dirname(__file__))
from n8n_helpers import fetch_workflow, push_workflow, sync_local, find_node

N8N_BASE = "https://scottai.trackslife.com"
WORKATO_WRITE_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"
WORKATO_READ_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read"
SUPABASE_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co"
SUPABASE_CRED = {"supabaseApi": {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}}
ANTHROPIC_CRED = {"anthropicApi": {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}}
MCP_CRED = {"httpMultipleHeadersAuth": {"id": "wvV5pwBeIL7f2vLG", "name": "Backstory MCP Multi-Header"}}
SLACK_CRED = {"httpHeaderAuth": {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}}
PEOPLEGLASS_TASKS = "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"

def make_node(name, node_type, position, parameters, credentials=None, **kwargs):
    node = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": node_type,
        "typeVersion": 2 if node_type == "n8n-nodes-base.code" else 4.2 if node_type == "n8n-nodes-base.httpRequest" else 1,
        "position": position,
        "parameters": parameters,
    }
    if credentials:
        node["credentials"] = credentials
    node.update(kwargs)
    return node
```

- [ ] **Step 2: Build the callback handler workflow nodes**

```python
def build_resolution_handler():
    nodes = []
    connections = {}

    # ── Callback Webhook ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Resolution Callback",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2.1,
        "position": [0, 0],
        "parameters": {"httpMethod": "POST", "path": "task-resolution-callback", "options": {}},
        "webhookId": str(uuid.uuid4()),
    })

    # ── Parse Callback ──
    PARSE_CODE = r"""
const body = $input.first().json.body || $input.first().json;
const requestId = body.request_id || '';
const isDone = (body.done === 'true' || body.done === true);

if (!isDone) {
  return [{ json: {
    isDone: false,
    requestId,
    task: {
      id: body.task_id || '',
      subject: body.task_subject || '',
      description: (body.task_description || '').substring(0, 200),
      status: body.task_status || '',
      dueDate: body.task_due_date || '',
      ownerEmail: body.task_owner_email || '',
      ownerName: body.task_owner_name || '',
      accountName: body.account_name || '',
      createdDate: body.task_created_date || '',
    }
  }}];
}

return [{ json: {
  isDone: true,
  requestId,
  taskCount: parseInt(body.task_count) || 0,
}}];
"""
    nodes.append(make_node("Parse Callback", "n8n-nodes-base.code", [200, 0],
        {"jsCode": PARSE_CODE}))

    # ── Is Done? ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Is Done?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [400, 0],
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [{
                    "id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.isDone }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"},
                }],
            },
            "options": {},
        },
    })

    # ── Store Task (not done — store in Supabase) ──
    nodes.append(make_node("Store Task", "n8n-nodes-base.httpRequest", [600, 200], {
        "method": "POST",
        "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Prefer", "value": "return=representation"},
        ]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ opportunity_id: $json.requestId, action_type: "resolution_task", draft_content: JSON.stringify($json.task), context: JSON.stringify({ account_name: $json.task.accountName }) }) }}',
        "options": {},
    }, credentials=SUPABASE_CRED))

    # ── Fetch Request Context (done signal — get original request metadata) ──
    nodes.append(make_node("Fetch Request Context", "n8n-nodes-base.httpRequest", [600, -200], {
        "url": f'={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $json.requestId }}}}&action_type=eq.resolution_request&select=*&limit=1',
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    }, credentials=SUPABASE_CRED))

    # ── Fetch All Stored Tasks ──
    nodes.append(make_node("Fetch All Tasks", "n8n-nodes-base.httpRequest", [800, -200], {
        "url": f'={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $("Parse Callback").first().json.requestId }}}}&action_type=eq.resolution_task&select=draft_content',
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    }, credentials=SUPABASE_CRED))

    # ── Group by Account + Run Resolution Agent ──
    RESOLVE_CODE = r"""
const callbackData = $('Parse Callback').first().json;
const contextArr = $('Fetch Request Context').all().map(i => i.json);
const rawContext = Array.isArray(contextArr[0]) ? contextArr[0][0] : contextArr[0];
let meta = rawContext?.context || '{}';
if (typeof meta === 'string') try { meta = JSON.parse(meta); } catch(e) { meta = {}; }

const taskRows = $('Fetch All Tasks').all().map(i => i.json);
const allRows = Array.isArray(taskRows[0]) ? taskRows[0] : taskRows;

// Parse stored tasks
const tasks = allRows.map(row => {
  try { return JSON.parse(row.draft_content || '{}'); } catch(e) { return null; }
}).filter(Boolean);

if (tasks.length === 0) {
  return [{ json: { skip: true, noTasks: true, ...meta } }];
}

// Group by account
const byAccount = {};
for (const t of tasks) {
  const acct = t.accountName || 'Unknown';
  if (!byAccount[acct]) byAccount[acct] = [];
  byAccount[acct].push(t);
}

// Build agent prompts per account
const accountGroups = Object.entries(byAccount).map(([acctName, acctTasks]) => ({
  accountName: acctName,
  tasks: acctTasks,
  taskList: acctTasks.map((t, i) =>
    `${i+1}. "${t.subject}" — ${t.ownerName || 'unassigned'}, due ${t.dueDate || 'no date'} (SF ID: ${t.id})`
  ).join('\n'),
  taskCount: acctTasks.length,
}));

return accountGroups.map(g => ({ json: { ...meta, ...g, requestId: callbackData.requestId } }));
"""
    nodes.append(make_node("Build Resolution Tasks", "n8n-nodes-base.code", [1000, -200],
        {"jsCode": RESOLVE_CODE}))

    # ── Loop Accounts ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Loop Accounts",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [1200, -200],
        "parameters": {"batchSize": 1, "options": {}},
    })

    # ── Resolution Agent ──
    AGENT_SYSTEM = r"""You are a task resolution analyst. You evaluate whether CRM tasks have been completed based on recent account activity from Backstory SalesAI.

RULES:
- Only mark a task COMPLETE if there is CLEAR evidence the work was done
- Evidence includes: email sent, meeting held, document delivered, issue resolved, follow-up completed
- When in doubt, leave as OPEN
- Be conservative — false completions are worse than missed completions
- Output ONLY valid JSON, no prose"""

    AGENT_PROMPT = r"""={{ "Review these open CRM tasks for " + $json.accountName + ":\n\n" + $json.taskList + "\n\nUse Backstory SalesAI tools (ask_sales_ai_about_account) to check recent activity, emails, and meeting outcomes for " + $json.accountName + ".\n\nFor each task, determine if it was completed based on evidence from recent activity.\n\nOutput JSON:\n{\n  \"account_name\": \"" + $json.accountName + "\",\n  \"results\": [\n    {\"id\": \"SF_TASK_ID\", \"status\": \"COMPLETE\" or \"OPEN\", \"evidence\": \"one-line reason\"}\n  ]\n}" }}"""

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Resolution Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [1400, -200],
        "parameters": {
            "promptType": "define",
            "text": AGENT_PROMPT,
            "options": {"systemMessage": AGENT_SYSTEM, "maxIterations": 8},
        },
        "continueOnFail": True,
    })

    # ── Anthropic Chat Model (Resolution) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Anthropic Chat Model (Resolution)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [1400, 0],
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-5-20250929", "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "credentials": ANTHROPIC_CRED,
    })

    # ── Backstory MCP (Resolution) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Backstory MCP (Resolution)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [1600, 0],
        "parameters": {"endpointUrl": "https://mcp.people.ai/mcp", "authentication": "multipleHeadersAuth"},
        "credentials": MCP_CRED,
    })

    # ── Parse Resolution Results ──
    PARSE_RESULTS_CODE = r"""
const agentOutput = $json.output || $json.text || '';
const accountData = $('Loop Accounts').first().json;

let results = [];
try {
  const match = agentOutput.match(/\{[\s\S]*\}/);
  if (match) {
    const parsed = JSON.parse(match[0]);
    results = parsed.results || [];
  }
} catch(e) {}

const completed = results.filter(r => r.status === 'COMPLETE');
const open = results.filter(r => r.status !== 'COMPLETE');

// Build update_task payloads for completed tasks
const updatePayloads = completed.map(r => ({
  action: 'update_task',
  salesforce_object: 'Task',
  task_id: r.id,
  fields: { Status: 'Completed' },
  context: { account_name: accountData.accountName },
}));

return [{ json: {
  accountName: accountData.accountName,
  completed,
  open,
  completedCount: completed.length,
  openCount: open.length,
  updatePayloads,
  requestId: accountData.requestId,
}}];
"""
    nodes.append(make_node("Parse Resolution Results", "n8n-nodes-base.code", [1600, -200],
        {"jsCode": PARSE_RESULTS_CODE}))

    # ── Send Completions to CRM ──
    COMPLETE_LOOP_CODE = r"""
const data = $input.first().json;
const payloads = data.updatePayloads || [];
if (payloads.length === 0) return [{ json: { ...data, skip: true } }];
return payloads.map(p => ({ json: { ...data, webhook_payload: p } }));
"""
    nodes.append(make_node("Prepare Completion Payloads", "n8n-nodes-base.code", [1800, -200],
        {"jsCode": COMPLETE_LOOP_CODE}))

    nodes.append(make_node("Mark Task Complete", "n8n-nodes-base.httpRequest", [2000, -200], {
        "method": "POST",
        "url": WORKATO_WRITE_URL,
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
        "options": {"timeout": 15000},
    }, continueOnFail=True))

    # ── Collect Results Across Accounts ──
    COLLECT_CODE = r"""
const allResults = $('Parse Resolution Results').all();
let totalCompleted = [];
let totalOpen = [];

for (const item of allResults) {
  const r = item.json;
  totalCompleted.push(...(r.completed || []).map(c => ({ ...c, accountName: r.accountName })));
  totalOpen.push(...(r.open || []).map(o => ({ ...o, accountName: r.accountName })));
}

// Get the original request context
const firstResult = allResults[0]?.json || {};
const requestId = firstResult.requestId || '';

return [{ json: {
  totalCompleted,
  totalOpen,
  completedCount: totalCompleted.length,
  openCount: totalOpen.length,
  requestId,
}}];
"""
    nodes.append(make_node("Collect All Results", "n8n-nodes-base.code", [2200, -400],
        {"jsCode": COLLECT_CODE}))

    # ── Post Summary to Slack ──
    SUMMARY_CODE = r"""
const data = $input.first().json;

// Fetch request context for Slack channel + assistant identity
const contextArr = $('Fetch Request Context').all().map(i => i.json);
const rawContext = Array.isArray(contextArr[0]) ? contextArr[0][0] : contextArr[0];
let meta = rawContext?.context || '{}';
if (typeof meta === 'string') try { meta = JSON.parse(meta); } catch(e) { meta = {}; }

const channelId = meta.channelId || '';
const assistantName = meta.assistantName || 'Aria';
const assistantEmoji = meta.assistantEmoji || ':robot_face:';
const mode = meta.mode || 'scheduled';

if (data.completedCount === 0) {
  // No tasks resolved — stay silent for scheduled, return empty for recap
  return [{ json: { skip: true, ...data, channelId, assistantName, assistantEmoji, mode } }];
}

const completedLines = data.totalCompleted.map(c =>
  `:white_check_mark: ~${c.subject || c.id}~ (${c.evidence || 'activity detected'})`
).join('\n');

let text = '';
if (mode === 'scheduled') {
  text = `:clipboard: *Task Update*\nI reviewed your open tasks against recent activity:\n\n${completedLines}\n\nMarked ${data.completedCount} task${data.completedCount === 1 ? '' : 's'} complete \u00b7 ${data.openCount} still open`;
} else {
  // recap mode — just return the data for the recap card to use
  text = completedLines;
}

return [{ json: {
  ...data,
  channelId,
  assistantName,
  assistantEmoji,
  mode,
  summaryText: text,
}}];
"""
    nodes.append(make_node("Build Summary", "n8n-nodes-base.code", [2400, -400],
        {"jsCode": SUMMARY_CODE}))

    # ── Send Summary DM (only for scheduled mode) ──
    SEND_SUMMARY_CODE = r"""
const data = $input.first().json;
if (data.skip || !data.channelId || data.mode !== 'scheduled') {
  return [{ json: data }];
}

const blocks = [
  { type: "section", text: { type: "mrkdwn", text: data.summaryText } },
  { type: "actions", elements: [
    { type: "button", text: { type: "plain_text", text: "All Tasks Today", emoji: true },
      url: "TASKS_URL", action_id: "pg_tasks_link" }
  ]}
];

return [{ json: {
  ...data,
  slackBody: JSON.stringify({
    channel: data.channelId,
    text: 'Task Update',
    blocks,
    username: data.assistantName,
    icon_emoji: data.assistantEmoji,
    unfurl_links: false,
  })
}}];
""".replace('TASKS_URL', PEOPLEGLASS_TASKS)
    nodes.append(make_node("Format Summary DM", "n8n-nodes-base.code", [2600, -400],
        {"jsCode": SEND_SUMMARY_CODE}))

    nodes.append(make_node("Send Summary DM", "n8n-nodes-base.httpRequest", [2800, -400], {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $json.slackBody }}",
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Cleanup Supabase ──
    nodes.append(make_node("Cleanup Stored Tasks", "n8n-nodes-base.httpRequest", [3000, -400], {
        "method": "DELETE",
        "url": f'={SUPABASE_URL}/rest/v1/pending_actions?opportunity_id=eq.{{{{ $("Parse Callback").first().json.requestId }}}}&action_type=in.(resolution_task,resolution_request)',
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    }, credentials=SUPABASE_CRED))

    # ── Connections ──
    connections = {
        "Resolution Callback": {"main": [[{"node": "Parse Callback", "type": "main", "index": 0}]]},
        "Parse Callback": {"main": [[{"node": "Is Done?", "type": "main", "index": 0}]]},
        "Is Done?": {"main": [
            [{"node": "Fetch Request Context", "type": "main", "index": 0}],  # true (done)
            [{"node": "Store Task", "type": "main", "index": 0}],  # false (store)
        ]},
        "Fetch Request Context": {"main": [[{"node": "Fetch All Tasks", "type": "main", "index": 0}]]},
        "Fetch All Tasks": {"main": [[{"node": "Build Resolution Tasks", "type": "main", "index": 0}]]},
        "Build Resolution Tasks": {"main": [[{"node": "Loop Accounts", "type": "main", "index": 0}]]},
        "Loop Accounts": {"main": [
            [{"node": "Collect All Results", "type": "main", "index": 0}],  # done
            [{"node": "Resolution Agent", "type": "main", "index": 0}],  # loop
        ]},
        "Resolution Agent": {"main": [[{"node": "Parse Resolution Results", "type": "main", "index": 0}]]},
        "Anthropic Chat Model (Resolution)": {"ai_languageModel": [[{"node": "Resolution Agent", "type": "ai_languageModel", "index": 0}]]},
        "Backstory MCP (Resolution)": {"ai_tool": [[{"node": "Resolution Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Resolution Results": {"main": [[{"node": "Prepare Completion Payloads", "type": "main", "index": 0}]]},
        "Prepare Completion Payloads": {"main": [[{"node": "Mark Task Complete", "type": "main", "index": 0}]]},
        "Mark Task Complete": {"main": [[{"node": "Loop Accounts", "type": "main", "index": 0}]]},
        "Collect All Results": {"main": [[{"node": "Build Summary", "type": "main", "index": 0}]]},
        "Build Summary": {"main": [[{"node": "Format Summary DM", "type": "main", "index": 0}]]},
        "Format Summary DM": {"main": [[{"node": "Send Summary DM", "type": "main", "index": 0}]]},
        "Send Summary DM": {"main": [[{"node": "Cleanup Stored Tasks", "type": "main", "index": 0}]]},
    }

    return nodes, connections
```

- [ ] **Step 3: Add create + push function**

```python
def create_resolution_handler():
    nodes, connections = build_resolution_handler()
    payload = {
        "name": "Task Resolution Handler",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }
    headers = {"X-N8N-API-KEY": os.getenv("N8N_API_KEY"), "Content-Type": "application/json"}
    resp = requests.post(f"{N8N_BASE}/api/v1/workflows", headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"Created Task Resolution Handler: {wf_id} ({len(result['nodes'])} nodes)")

    # Activate
    resp2 = requests.post(f"{N8N_BASE}/api/v1/workflows/{wf_id}/activate", headers=headers)
    print(f"Activated: {resp2.status_code}")

    sync_local(fetch_workflow(wf_id), "Task Resolution Handler.json")
    return wf_id
```

- [ ] **Step 4: Run and verify**

```bash
cd scripts && python3 -c "from add_task_resolution import create_resolution_handler; create_resolution_handler()"
```

Expected: `Created Task Resolution Handler: <id> (XX nodes)`, `Activated: 200`

- [ ] **Step 5: Commit**

```bash
git add scripts/add_task_resolution.py n8n/workflows/Task\ Resolution\ Handler.json
git commit -m "feat: create Task Resolution Handler workflow"
```

---

### Task 3: Integrate task resolution into recap flow

**Files:**
- Modify: `scripts/add_task_resolution.py`
- Synced: `n8n/workflows/Follow-up Cron.json`, `n8n/workflows/Slack Events Handler.json`

Add a step after auto-save that fires `get_tasks_resolution` to Workato, triggering the resolution callback handler.

- [ ] **Step 1: Add integration function for both recap paths**

Add to `scripts/add_task_resolution.py`:

```python
def integrate_into_recap(resolution_wf_id):
    """Add task resolution trigger to both cron and on-demand recap flows."""

    RESOLUTION_CALLBACK_URL = f"{N8N_BASE}/webhook/task-resolution-callback"

    # Code node that fires Workato get_tasks_resolution
    FIRE_RESOLUTION_CODE = r"""
const data = $input.first().json;
const m = data.meeting || {};
const requestId = 'res_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

// Store request context in Supabase so the callback handler can find it
return [{ json: {
  ...data,
  resolutionRequestId: requestId,
  resolutionPayload: {
    action: 'get_tasks_resolution',
    account_name: m.accountName || '',
    user_email: data.email || '',
    callback_url: 'CALLBACK_URL',
    request_id: requestId,
  },
  resolutionContext: {
    channelId: data.channelId || '',
    assistantName: data.assistantName || 'Aria',
    assistantEmoji: data.assistantEmoji || ':robot_face:',
    mode: 'recap',
    accountName: m.accountName || '',
  }
}}];
""".replace('CALLBACK_URL', RESOLUTION_CALLBACK_URL)

    # Apply to both Follow-up Cron and Events Handler
    for wf_id, save_node_name, card_node_name, local_name in [
        ('JhDuCvZdFN4PFTOW', 'Build Auto-Save Payload', 'Build Recap Card', 'Follow-up Cron.json'),
        ('QuQbIaWetunUOFUW', 'Build Auto-Save OD', 'Recap Build Card OD', 'Slack Events Handler.json'),
    ]:
        wf = fetch_workflow(wf_id)
        nodes = wf['nodes']
        conns = wf['connections']

        suffix = ' OD' if 'OD' in save_node_name else ''

        # Add: Fire Task Resolution node
        nodes.append(make_node(f"Fire Task Resolution{suffix}", "n8n-nodes-base.code", [2500, 600],
            {"jsCode": FIRE_RESOLUTION_CODE}))

        # Add: Store Resolution Request in Supabase
        nodes.append(make_node(f"Store Resolution Request{suffix}", "n8n-nodes-base.httpRequest", [2700, 600], {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Prefer", "value": "return=representation"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ opportunity_id: $json.resolutionRequestId, action_type: "resolution_request", context: JSON.stringify($json.resolutionContext) }) }}',
            "options": {},
        }, credentials=SUPABASE_CRED))

        # Add: Send Resolution Request to Workato
        nodes.append(make_node(f"Send Resolution to Workato{suffix}", "n8n-nodes-base.httpRequest", [2900, 600], {
            "method": "POST",
            "url": WORKATO_READ_URL,
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.resolutionPayload) }}",
            "options": {"timeout": 15000},
        }, continueOnFail=True))

        # Wire: Send Recap to CRM → Fire Task Resolution (parallel with card build)
        # The resolution runs async (callback pattern) so it doesn't block the Slack card
        send_crm_name = f"Send Recap to CRM{suffix}"
        if send_crm_name not in conns:
            send_crm_name = "Send Recap to CRM" if suffix == '' else "Send Recap to CRM OD"

        # Add Fire Resolution as parallel output from the auto-save node
        save_conns = conns.get(save_node_name, {"main": [[]]})
        save_conns["main"][0].append(
            {"node": f"Fire Task Resolution{suffix}", "type": "main", "index": 0}
        )

        conns[f"Fire Task Resolution{suffix}"] = {"main": [[
            {"node": f"Store Resolution Request{suffix}", "type": "main", "index": 0}
        ]]}
        conns[f"Store Resolution Request{suffix}"] = {"main": [[
            {"node": f"Send Resolution to Workato{suffix}", "type": "main", "index": 0}
        ]]}
        # Send Resolution to Workato has no downstream — fire and forget
        # The callback handler posts results to Slack independently

        result = push_workflow(wf_id, wf)
        print(f"Updated {local_name}: {len(result['nodes'])} nodes")
        sync_local(fetch_workflow(wf_id), local_name)
```

- [ ] **Step 2: Add main() and run**

```python
def main():
    print("=== Task 2: Creating Task Resolution Handler ===")
    resolution_wf_id = create_resolution_handler()

    print(f"\n=== Task 3: Integrating into recap flows ===")
    integrate_into_recap(resolution_wf_id)

    print(f"\n=== Done! ===")
    print(f"Task Resolution Handler ID: {resolution_wf_id}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script**

```bash
cd scripts && python3 add_task_resolution.py
```

Expected: Creates handler workflow + updates both recap flows.

- [ ] **Step 4: Commit**

```bash
git add scripts/add_task_resolution.py n8n/workflows/
git commit -m "feat: integrate task resolution into recap flows"
```

---

### Task 4: Create scheduled task resolution job

**Files:**
- Modify: `scripts/add_task_resolution.py`
- Synced: new workflow or added to Follow-up Cron

- [ ] **Step 1: Add scheduled job function**

This adds a parallel path to the Follow-up Cron that runs task resolution for all users (not just those with meetings). Add to `scripts/add_task_resolution.py`:

```python
def add_scheduled_resolution():
    """Add task resolution as a parallel job on the Follow-up Cron schedule."""
    # The Follow-up Cron already runs at 9am + 4pm PT.
    # Add a parallel branch from the cron trigger that:
    # 1. Gets all active users from Supabase
    # 2. Loops through each user
    # 3. Opens their DM channel
    # 4. Fires Workato get_tasks_resolution (no account filter)
    # 5. The callback handler does the rest (agent + mark complete + DM)

    wf = fetch_workflow('JhDuCvZdFN4PFTOW')
    nodes = wf['nodes']
    conns = wf['connections']

    RESOLUTION_CALLBACK_URL = f"{N8N_BASE}/webhook/task-resolution-callback"

    # Find the trigger node name
    trigger_name = None
    for n in nodes:
        if 'schedule' in n['type'].lower() or 'cron' in n['type'].lower():
            trigger_name = n['name']
            break

    if not trigger_name:
        print("ERROR: Could not find trigger node")
        return

    # Add: Get Resolution Users (Supabase getAll)
    nodes.append(make_node("Get Resolution Users", "n8n-nodes-base.httpRequest", [400, 800], {
        "url": f"{SUPABASE_URL}/rest/v1/users?onboarding_state=eq.complete&select=id,email,slack_user_id,assistant_name,assistant_emoji,digest_scope",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    }, credentials=SUPABASE_CRED))

    # Add: Loop Resolution Users
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Loop Resolution Users",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [600, 800],
        "parameters": {"batchSize": 1, "options": {}},
    })

    # Add: Open DM for Resolution
    nodes.append(make_node("Open DM (Resolution)", "n8n-nodes-base.httpRequest", [800, 900], {
        "method": "POST",
        "url": "https://slack.com/api/conversations.open",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ users: $json.slack_user_id }) }}",
        "options": {},
    }, credentials=SLACK_CRED))

    # Add: Build Resolution Request
    BUILD_REQ_CODE = r"""
const user = $('Loop Resolution Users').first().json;
const dm = $json.channel?.id || $json.channel || '';
const requestId = 'sched_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

return [{ json: {
  resolutionPayload: {
    action: 'get_tasks_resolution',
    account_name: '',
    user_email: user.email || '',
    callback_url: 'CALLBACK_URL',
    request_id: requestId,
  },
  resolutionContext: {
    channelId: dm,
    assistantName: user.assistant_name || 'Aria',
    assistantEmoji: user.assistant_emoji || ':robot_face:',
    mode: 'scheduled',
  },
  requestId,
}}];
""".replace('CALLBACK_URL', RESOLUTION_CALLBACK_URL)
    nodes.append(make_node("Build Scheduled Resolution", "n8n-nodes-base.code", [1000, 900],
        {"jsCode": BUILD_REQ_CODE}))

    # Add: Store Scheduled Request
    nodes.append(make_node("Store Scheduled Request", "n8n-nodes-base.httpRequest", [1200, 900], {
        "method": "POST",
        "url": f"{SUPABASE_URL}/rest/v1/pending_actions",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Prefer", "value": "return=representation"},
        ]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ opportunity_id: $json.requestId, action_type: "resolution_request", context: JSON.stringify($json.resolutionContext) }) }}',
        "options": {},
    }, credentials=SUPABASE_CRED))

    # Add: Send Scheduled Resolution to Workato
    nodes.append(make_node("Send Scheduled Resolution", "n8n-nodes-base.httpRequest", [1400, 900], {
        "method": "POST",
        "url": WORKATO_READ_URL,
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify($json.resolutionPayload) }}",
        "options": {"timeout": 15000},
    }, continueOnFail=True))

    # Wire: Trigger → Get Resolution Users (parallel with existing recap flow)
    if trigger_name in conns:
        conns[trigger_name]["main"][0].append(
            {"node": "Get Resolution Users", "type": "main", "index": 0}
        )
    else:
        conns[trigger_name] = {"main": [[{"node": "Get Resolution Users", "type": "main", "index": 0}]]}

    conns["Get Resolution Users"] = {"main": [[{"node": "Loop Resolution Users", "type": "main", "index": 0}]]}
    conns["Loop Resolution Users"] = {"main": [
        [],  # done (no action needed)
        [{"node": "Open DM (Resolution)", "type": "main", "index": 0}],  # loop
    ]}
    conns["Open DM (Resolution)"] = {"main": [[{"node": "Build Scheduled Resolution", "type": "main", "index": 0}]]}
    conns["Build Scheduled Resolution"] = {"main": [[{"node": "Store Scheduled Request", "type": "main", "index": 0}]]}
    conns["Store Scheduled Request"] = {"main": [[{"node": "Send Scheduled Resolution", "type": "main", "index": 0}]]}
    conns["Send Scheduled Resolution"] = {"main": [[{"node": "Loop Resolution Users", "type": "main", "index": 0}]]}

    result = push_workflow('JhDuCvZdFN4PFTOW', wf)
    print(f"Added scheduled resolution to Follow-up Cron: {len(result['nodes'])} nodes")
    sync_local(fetch_workflow('JhDuCvZdFN4PFTOW'), "Follow-up Cron.json")
```

- [ ] **Step 2: Update main() to include scheduled job**

```python
def main():
    print("=== Creating Task Resolution Handler ===")
    resolution_wf_id = create_resolution_handler()

    print(f"\n=== Integrating into recap flows ===")
    integrate_into_recap(resolution_wf_id)

    print(f"\n=== Adding scheduled resolution job ===")
    add_scheduled_resolution()

    print(f"\n=== Done! ===")
    print(f"Task Resolution Handler ID: {resolution_wf_id}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run and verify**

```bash
cd scripts && python3 add_task_resolution.py
```

- [ ] **Step 4: Commit**

```bash
git add scripts/add_task_resolution.py n8n/workflows/
git commit -m "feat: add scheduled task resolution job (2x daily)"
```

---

### Task 5: Test end-to-end

- [ ] **Step 1: Test Workato action**

Verify `get_tasks_resolution` sends tasks to the callback URL (done in Task 1).

- [ ] **Step 2: Test on-demand recap with resolution**

```
recap transunion
```

Verify: recap card shows both marked-complete and new tasks.

- [ ] **Step 3: Test scheduled job**

Wait for next 9am or 4pm cron run, or trigger the Follow-up Cron manually. Verify the resolution DM posts if any tasks were resolved.

- [ ] **Step 4: Verify CRM updates**

Check in PeopleGlass that resolved tasks show Status = Completed.

---

### Task 6: Update Confluence and memory

- [ ] **Step 1: Update Confluence Skills page**

Add task resolution to Skill 3 (Meeting Recap) and as a new proactive feature in the Quick Reference table.

- [ ] **Step 2: Update MEMORY.md**

Add Task Resolution Handler workflow ID.
