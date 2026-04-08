# Digest Task Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Tasks" section to the daily morning digest showing overdue and due-this-week Salesforce tasks when present.

**Architecture:** Add a synchronous `get_tasks_sync` action to the existing Workato "Assistant — Read from Salesforce" recipe that returns tasks in the webhook response body (instead of async callbacks). In the n8n Sales Digest workflow, add a per-user HTTP call to Workato before Resolve Identity, filter to urgent tasks, and inject task context into the Claude agent prompt.

**Tech Stack:** Workato (SOQL + Reply to webhook), n8n (HTTP Request + Code nodes), Claude prompt engineering

**Spec:** `docs/superpowers/specs/2026-03-29-digest-task-summary-design.md`

---

## Current Digest Flow (for reference)

```
6am Trigger → Get Auth Token → Fetch User Hierarchy → Parse Hierarchy
→ Fetch Open Opps → Parse Opps CSV → Get Digest Users → Filter Active Users
→ Split In Batches → [loop] Filter User Opps → Resolve Identity → Open Bot DM
→ Digest Agent → Parse Blocks → Send Digest → Prepare Message Log → Log to Messages
→ ... → [loop back]
```

Task data inserts into the per-user loop between **Filter User Opps** and **Resolve Identity**.

---

### Task 1: Add synchronous task action in Workato

**Where:** Workato recipe "Assistant — Read from Salesforce"

This task is done manually in Workato's UI — no code files to modify.

- [ ] **Step 1: Add new IF branch in Workato recipe**

In the existing "Assistant — Read from Salesforce" recipe, after the existing `get_my_tasks` branch (Step 9), add a new IF condition:

```
IF action Step 1 equals get_tasks_sync
```

- [ ] **Step 2: Add SOQL query step inside the new branch**

Add a "Search for records using SOQL query in Salesforce (Batch)" step with this query:

```sql
SELECT Id, Subject, Status, Priority, ActivityDate, Account.Name,
       Owner.Name, Owner.Email, Category__c
FROM Task
WHERE Owner.Email = '{User email from Step 1}'
  AND TaskSubtype = 'Task'
  AND Type NOT IN ('Reminder', 'Intercom Chat', 'Email')
  AND Status NOT IN ('Completed', 'Expired', 'Deferred', 'Cancelled')
  AND IsDeleted = false
ORDER BY ActivityDate ASC
```

Limit: 50

- [ ] **Step 3: Add "Reply to webhook" step**

After the SOQL step, add a Workato "Reply to webhook" action that returns the task records as JSON in the response body:

```json
{
  "tasks": [array of task records from SOQL step],
  "count": [list size of records]
}
```

If the SOQL returns 0 records, the reply should still fire with `{"tasks": [], "count": 0}`.

- [ ] **Step 4: Test the sync action**

Send a test request to the Workato webhook:

```bash
curl -X POST https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read \
  -H "Content-Type: application/json" \
  -d '{"action": "get_tasks_sync", "user_email": "scott.metcalf@people.ai"}'
```

Expected: HTTP 200 response with JSON body containing `tasks` array and `count`. Verify tasks match what `tasks` command shows in Slack.

- [ ] **Step 5: Verify empty case**

Test with an email that has no tasks:

```bash
curl -X POST https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read \
  -H "Content-Type: application/json" \
  -d '{"action": "get_tasks_sync", "user_email": "nobody@people.ai"}'
```

Expected: `{"tasks": [], "count": 0}`

---

### Task 2: Add "Fetch User Tasks" HTTP Request node to Sales Digest

**Where:** n8n workflow "Sales Digest" (ID `7sinwSgjkEA40zDj`)
**Method:** Python script using n8n REST API

- [ ] **Step 1: Create the upgrade script**

Create file: `scripts/add_digest_tasks.py`

```python
#!/usr/bin/env python3
"""Add task fetch and filtering to Sales Digest workflow for digest task summary."""

import json
import os
import sys
import uuid
import urllib.request
import ssl

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]
WORKFLOW_ID = "7sinwSgjkEA40zDj"

# Bypass SSL verification (same pattern as other scripts)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api(method, path, data=None):
    url = f"{N8N_URL}/api/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                  headers={"X-N8N-API-KEY": API_KEY,
                                           "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.load(resp)


def main():
    wf = api("GET", f"/workflows/{WORKFLOW_ID}")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already added
    if any(n["name"] == "Fetch User Tasks" for n in nodes):
        print("Fetch User Tasks node already exists. Skipping.")
        sys.exit(0)

    # Find positions of Filter User Opps and Resolve Identity
    filter_opps_node = next(n for n in nodes if n["name"] == "Filter User Opps")
    resolve_node = next(n for n in nodes if n["name"] == "Resolve Identity")

    # Position the new nodes between Filter User Opps and Resolve Identity
    fo_pos = filter_opps_node["position"]
    ri_pos = resolve_node["position"]
    mid_x = (fo_pos[0] + ri_pos[0]) // 2

    # --- Node 1: Fetch User Tasks (HTTP Request to Workato) ---
    fetch_tasks_node = {
        "parameters": {
            "method": "POST",
            "url": "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_read",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ action: "get_tasks_sync", user_email: $json.email || "" }) }}',
            "options": {
                "timeout": 15000
            }
        },
        "id": str(uuid.uuid4()),
        "name": "Fetch User Tasks",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [mid_x - 80, fo_pos[1]],
        "alwaysOutputData": True,
        "onError": "continueRegularOutput"
    }

    # --- Node 2: Filter Urgent Tasks (Code node) ---
    filter_tasks_code = r"""// Filter tasks to overdue + due-this-week only
const taskResponse = $input.first().json;
const userData = $('Filter User Opps').first().json;
const tasks = (taskResponse.tasks || []);

const now = new Date();
const ptNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }));
const todayStr = ptNow.toISOString().split('T')[0];

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const due = new Date(dateStr + 'T00:00:00');
  const today = new Date(todayStr + 'T00:00:00');
  return Math.round((due - today) / 86400000);
}

const overdue = [];
const dueThisWeek = [];

for (const t of tasks) {
  const days = daysUntil(t.ActivityDate);
  if (days === null) continue;
  if (days < 0) {
    overdue.push({ ...t, daysOverdue: Math.abs(days) });
  } else if (days <= 7) {
    dueThisWeek.push({ ...t, daysUntil: days });
  }
}

// Build task context string for the prompt
let taskContext = '';

if (overdue.length > 0 || dueThisWeek.length > 0) {
  const lines = [];
  lines.push(`TASK SUMMARY: ${overdue.length} overdue, ${dueThisWeek.length} due this week`);
  lines.push('');

  // Sort overdue by most overdue first
  overdue.sort((a, b) => b.daysOverdue - a.daysOverdue);
  for (const t of overdue.slice(0, 5)) {
    const acct = t['Account.Name'] || t.Account_Name || '';
    const acctTag = acct ? ` (${acct})` : '';
    lines.push(`- OVERDUE (${t.daysOverdue} days): ${t.Subject}${acctTag}`);
  }

  // Sort due-this-week by soonest first
  dueThisWeek.sort((a, b) => a.daysUntil - b.daysUntil);
  for (const t of dueThisWeek.slice(0, 5)) {
    const acct = t['Account.Name'] || t.Account_Name || '';
    const acctTag = acct ? ` (${acct})` : '';
    const dueLabel = t.daysUntil === 0 ? 'TODAY' : t.daysUntil === 1 ? 'TOMORROW' : `in ${t.daysUntil} days`;
    lines.push(`- DUE ${dueLabel}: ${t.Subject}${acctTag}`);
  }

  if (overdue.length > 5 || dueThisWeek.length > 5) {
    const remaining = (overdue.length - 5) + (dueThisWeek.length - 5);
    if (remaining > 0) lines.push(`- ... and ${remaining} more`);
  }

  taskContext = lines.join('\n');
}

// Pass through all user data + task context
return [{ json: { ...userData, taskContext, taskOverdueCount: overdue.length, taskDueThisWeekCount: dueThisWeek.length } }];
"""

    filter_tasks_node = {
        "parameters": {
            "jsCode": filter_tasks_code
        },
        "id": str(uuid.uuid4()),
        "name": "Filter Urgent Tasks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [mid_x + 80, fo_pos[1]]
    }

    nodes.append(fetch_tasks_node)
    nodes.append(filter_tasks_node)

    # --- Rewire connections ---
    # Before: Filter User Opps [0] -> Resolve Identity
    # After:  Filter User Opps [0] -> Fetch User Tasks -> Filter Urgent Tasks -> Resolve Identity

    # Remove old connection: Filter User Opps -> Resolve Identity
    fo_conns = connections.get("Filter User Opps", {}).get("main", [[]])
    fo_conns[0] = [c for c in fo_conns[0] if c["node"] != "Resolve Identity"]
    # Add: Filter User Opps -> Fetch User Tasks
    fo_conns[0].append({"node": "Fetch User Tasks", "type": "main", "index": 0})

    # Add: Fetch User Tasks -> Filter Urgent Tasks
    connections["Fetch User Tasks"] = {"main": [[{"node": "Filter Urgent Tasks", "type": "main", "index": 0}]]}

    # Add: Filter Urgent Tasks -> Resolve Identity
    connections["Filter Urgent Tasks"] = {"main": [[{"node": "Resolve Identity", "type": "main", "index": 0}]]}

    # --- Push updated workflow ---
    payload = {
        "name": wf["name"],
        "nodes": nodes,
        "connections": connections,
        "settings": wf["settings"],
        "staticData": wf.get("staticData"),
    }
    result = api("PUT", f"/workflows/{WORKFLOW_ID}", payload)
    print(f"Updated workflow: {result['name']} — {len(result['nodes'])} nodes")

    # Verify nodes exist
    node_names = [n["name"] for n in result["nodes"]]
    assert "Fetch User Tasks" in node_names, "Fetch User Tasks not found!"
    assert "Filter Urgent Tasks" in node_names, "Filter Urgent Tasks not found!"
    print("Verified: Fetch User Tasks and Filter Urgent Tasks nodes added")
    print("Connection chain: Filter User Opps -> Fetch User Tasks -> Filter Urgent Tasks -> Resolve Identity")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script to add the nodes**

```bash
python3 scripts/add_digest_tasks.py
```

Expected output:
```
Updated workflow: Sales Digest — 25 nodes
Verified: Fetch User Tasks and Filter Urgent Tasks nodes added
Connection chain: Filter User Opps -> Fetch User Tasks -> Filter Urgent Tasks -> Resolve Identity
```

- [ ] **Step 3: Verify in n8n UI**

Open `https://scottai.trackslife.com/workflow/7sinwSgjkEA40zDj` and confirm:
- "Fetch User Tasks" node appears between Filter User Opps and Resolve Identity
- "Filter Urgent Tasks" Code node appears between Fetch User Tasks and Resolve Identity
- Connections flow: Filter User Opps → Fetch User Tasks → Filter Urgent Tasks → Resolve Identity

- [ ] **Step 4: Commit**

```bash
git add scripts/add_digest_tasks.py
git commit -m "feat(digest): add task fetch nodes to Sales Digest workflow"
```

---

### Task 3: Update Resolve Identity to inject task context into prompt

**Where:** n8n workflow "Sales Digest" (ID `7sinwSgjkEA40zDj`), "Resolve Identity" Code node
**Method:** Python script using n8n REST API

- [ ] **Step 1: Create the prompt injection script**

Create file: `scripts/add_digest_task_prompt.py`

```python
#!/usr/bin/env python3
"""Update Resolve Identity in Sales Digest to inject task context into the agent prompt."""

import json
import os
import sys
import urllib.request
import ssl

N8N_URL = "https://scottai.trackslife.com"
API_KEY = os.environ["N8N_API_KEY"]
WORKFLOW_ID = "7sinwSgjkEA40zDj"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def api(method, path, data=None):
    url = f"{N8N_URL}/api/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                  headers={"X-N8N-API-KEY": API_KEY,
                                           "Content-Type": "application/json"})
    with urllib.request.urlopen(req, context=ctx) as resp:
        return json.load(resp)


def main():
    wf = api("GET", f"/workflows/{WORKFLOW_ID}")
    nodes = wf["nodes"]

    resolve_node = next(n for n in nodes if n["name"] == "Resolve Identity")
    code = resolve_node["parameters"]["jsCode"]

    # Check if already patched
    if "taskContext" in code:
        print("Resolve Identity already has task context. Skipping.")
        sys.exit(0)

    # --- Patch 1: Change data source from Filter User Opps to Filter Urgent Tasks ---
    # The first line reads user data. Now it comes from Filter Urgent Tasks.
    code = code.replace(
        "const user = $('Filter User Opps').first().json;",
        "const user = $('Filter Urgent Tasks').first().json;"
    )

    # --- Patch 2: Add task context to system prompt ---
    # Find where systemPrompt is assembled and add task section
    # The pattern is: const systemPrompt = roleContext + '\n\n' + focusContext + ...
    old_prompt_assembly = "const systemPrompt = roleContext + '\\n\\n' + focusContext + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"

    task_prompt_section = r"""
// === Task context (overdue + due this week) ===
const taskContext = user.taskContext || '';
const taskPromptSection = taskContext ? `
TASK CONTEXT:
${taskContext}

If the user has overdue or due-this-week tasks, add a *Tasks* section at the end of your briefing (before the context footer). List the most urgent items using :red_circle: for overdue and :warning: for due this week. Keep it brief — 3-5 items max. End with "Type \`tasks\` for the full list."
If there are no tasks in the context above, do NOT include a Tasks section.` : '';

"""

    new_prompt_assembly = task_prompt_section + "const systemPrompt = roleContext + '\\n\\n' + focusContext + (taskPromptSection ? '\\n\\n' + taskPromptSection : '') + '\\n\\n' + briefingStructure + '\\n\\n' + blockKitRules;"

    if old_prompt_assembly not in code:
        print("ERROR: Could not find prompt assembly pattern in Resolve Identity.")
        print("Manual patching required. The systemPrompt assembly line has changed.")
        sys.exit(1)

    code = code.replace(old_prompt_assembly, new_prompt_assembly)

    resolve_node["parameters"]["jsCode"] = code

    # Push
    payload = {
        "name": wf["name"],
        "nodes": nodes,
        "connections": wf["connections"],
        "settings": wf["settings"],
        "staticData": wf.get("staticData"),
    }
    result = api("PUT", f"/workflows/{WORKFLOW_ID}", payload)
    print(f"Updated workflow: {result['name']}")

    # Verify
    updated_resolve = next(n for n in result["nodes"] if n["name"] == "Resolve Identity")
    updated_code = updated_resolve["parameters"]["jsCode"]
    assert "taskContext" in updated_code, "taskContext not found in updated code!"
    assert "Filter Urgent Tasks" in updated_code, "Filter Urgent Tasks reference not found!"
    print("Verified: Resolve Identity now reads from Filter Urgent Tasks and injects task context")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
python3 scripts/add_digest_task_prompt.py
```

Expected output:
```
Updated workflow: Sales Digest
Verified: Resolve Identity now reads from Filter Urgent Tasks and injects task context
```

- [ ] **Step 3: Verify in n8n UI**

Open the Resolve Identity node in the n8n editor and confirm:
- First line reads from `$('Filter Urgent Tasks')` instead of `$('Filter User Opps')`
- Task context section exists before `systemPrompt` assembly
- `taskPromptSection` is included in the `systemPrompt` concatenation

- [ ] **Step 4: Commit**

```bash
git add scripts/add_digest_task_prompt.py
git commit -m "feat(digest): inject task context into digest agent prompt"
```

---

### Task 4: End-to-end test

**Where:** Slack DM + n8n execution logs

- [ ] **Step 1: Trigger a manual digest**

In the n8n UI, open the Sales Digest workflow and click "Test Workflow" (or trigger via the On-Demand Digest sub-workflow by typing `brief` in Slack DM).

- [ ] **Step 2: Check execution logs for the new nodes**

Open the execution in n8n. Verify:
- **Fetch User Tasks** node shows HTTP 200 response from Workato with `tasks` array
- **Filter Urgent Tasks** node shows `taskContext` string with overdue/due-this-week tasks (or empty string if none)
- **Resolve Identity** node output includes `systemPrompt` containing the task section (if tasks exist)

- [ ] **Step 3: Verify Slack output**

Check the digest message in Slack DM:
- If you have overdue/due-this-week tasks: a "Tasks" section appears at the bottom with :red_circle: and :warning: indicators
- If you have no urgent tasks: no Tasks section appears (digest looks unchanged)

- [ ] **Step 4: Test empty task case**

If your account has tasks, temporarily change your email in the Filter Urgent Tasks test to verify the empty case works (no Tasks section, no errors).

- [ ] **Step 5: Sync local workflow file**

```bash
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" "https://scottai.trackslife.com/api/v1/workflows/7sinwSgjkEA40zDj" > "n8n/workflows/Sales Digest.json"
git add "n8n/workflows/Sales Digest.json"
git commit -m "feat(digest): sync Sales Digest with task summary nodes"
```

---

### Task 5: Update Confluence documentation

**Where:** Confluence page "Personal Assistant - Skills & Capabilities" (page ID `59392262149`)

- [ ] **Step 1: Update the Morning Digest skill section**

In the Skill 1: Morning Digest section, add after the role table:

```markdown
### Task Summary (conditional)

When you have overdue or due-this-week Salesforce tasks, the digest includes a Tasks section at the bottom:
- :red_circle: Overdue tasks (past due date)
- :warning: Tasks due this week
- Top 3-5 most urgent items shown by name with account
- Type `tasks` for the full interactive list

The section is omitted entirely when no tasks need attention.
```

- [ ] **Step 2: Update via Atlassian MCP**

Use the `updateConfluencePage` tool to push the updated content.

- [ ] **Step 3: Commit any doc changes**

```bash
git add docs/
git commit -m "docs: document task summary in morning digest"
```
