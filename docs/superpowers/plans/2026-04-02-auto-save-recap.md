# Auto-Save Meeting Recap & Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-save meeting recaps and tasks to CRM immediately when generated, replacing the human review gate with PeopleGlass edit links.

**Architecture:** Modify the Follow-up Cron workflow to fire Workato webhooks immediately after the Recap Agent generates output, then post a simplified Slack card confirming what was saved with PeopleGlass links. Workato recipe updated to prepend recap to Event Description (not overwrite) and only set Category if blank.

**Tech Stack:** n8n workflows (API-managed via Python), Workato webhook, Slack Block Kit, PeopleGlass

**Spec:** `docs/superpowers/specs/2026-04-02-auto-save-recap-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `scripts/auto_save_recap.py` | Python script to modify Follow-up Cron workflow |
| `n8n/workflows/Follow-up Cron.json` | Modified workflow (synced after push) |

---

### Task 1: Add Auto-Save nodes to Follow-up Cron

**Files:**
- Create: `scripts/auto_save_recap.py`
- Synced: `n8n/workflows/Follow-up Cron.json`

This task adds two new nodes after Parse Recap Output and rewires the flow.

- [ ] **Step 1: Create the script with helpers and constants**

Create `scripts/auto_save_recap.py`:

```python
#!/usr/bin/env python3
"""Auto-save recap: add auto-save nodes + simplify recap card in Follow-up Cron."""

import sys, os, json, uuid
sys.path.insert(0, os.path.dirname(__file__))
from n8n_helpers import fetch_workflow, push_workflow, sync_local, find_node

WF_FOLLOWUP_CRON = "JhDuCvZdFN4PFTOW"
WORKATO_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"
SLACK_CRED = {"httpHeaderAuth": {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}}
PEOPLEGLASS_EVENTS = "https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61"
PEOPLEGLASS_TASKS = "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"
```

- [ ] **Step 2: Add the Build Auto-Save Payload node**

This Code node runs after Parse Recap Output. It builds both the `log_activity` and `create_task` Workato payloads from the AI-generated recap — no human edit step.

```python
AUTO_SAVE_CODE = r"""
// Build Workato payloads for auto-save (no human gate)
const data = $('Parse Recap Output').first().json;
const recap = data.recap;
const m = data.meeting;

// Build description from AI recap
const description = [
  'Summary:',
  recap.summary,
  '',
  recap.keyDecisions && recap.keyDecisions.length > 0
    ? 'Key Decisions:\n' + recap.keyDecisions.map(d => '• ' + d).join('\n') : '',
  '',
  recap.tasks && recap.tasks.length > 0
    ? 'Action Items:\n' + recap.tasks.map(t =>
        '• ' + t.description + (t.owner ? ' — ' + t.owner : '') +
        (t.due_hint ? ' · ' + t.due_hint : '')
      ).join('\n') : '',
].filter(Boolean).join('\n');

// log_activity payload
const activityPayload = {
  action: 'log_activity',
  salesforce_object: 'Event',
  fields: {
    Subject: m.subject || 'Customer Meeting',
    Description: description,
    ActivityDate: new Date().toLocaleDateString('en-CA', { timeZone: 'America/Los_Angeles' }),
    meeting_category: recap.meetingCategory || '',
    cs_category: recap.csCategory || '',
  },
  context: {
    user_email: data.email || '',
    account_name: m.accountName || '',
    activity_uid: m.activityUid || '',
    prepend_description: true,
  }
};

// create_task payloads
const now = new Date();
const ptNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }));

function parseDueDate(hint) {
  const h = (hint || '').toLowerCase();
  if (h.includes('today') || h.includes('asap') || h.includes('immediate'))
    return ptNow.toISOString().split('T')[0];
  if (h.includes('tomorrow')) {
    const d = new Date(ptNow.getTime() + 86400000);
    return d.toISOString().split('T')[0];
  }
  if (h.includes('friday') || h.includes('this week') || h.includes('end of week')) {
    const d = new Date(ptNow);
    d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7 || 7));
    return d.toISOString().split('T')[0];
  }
  if (h.includes('next week')) {
    const d = new Date(ptNow.getTime() + 7 * 86400000);
    return d.toISOString().split('T')[0];
  }
  // Check for specific date patterns like "April 14" or "Apr 14, 2026"
  const dateMatch = (hint || '').match(/(\w+ \d{1,2}(?:,? \d{4})?)/);
  if (dateMatch) {
    const parsed = new Date(dateMatch[1]);
    if (!isNaN(parsed.getTime())) return parsed.toISOString().split('T')[0];
  }
  // Default: 1 week from now
  const d = new Date(ptNow.getTime() + 7 * 86400000);
  return d.toISOString().split('T')[0];
}

const taskPayloads = (recap.tasks || []).slice(0, 5).map(t => ({
  action: 'create_task',
  salesforce_object: 'Task',
  fields: {
    Subject: (t.description || '').substring(0, 255),
    Description: 'From meeting: ' + (m.subject || '') + ' with ' + (m.accountName || '') +
      '\nAssigned to: ' + (t.owner || '') + (t.assignee_role ? ' (' + t.assignee_role + ')' : '') +
      '\nEstimated duration: ' + (t.duration_minutes || 30) + ' minutes',
    ActivityDate: parseDueDate(t.due_hint),
    Status: 'Not Started',
    Priority: 'Normal',
    TaskDuration: parseInt(t.duration_minutes) || 30,
    Category: t.task_category || '',
  },
  context: {
    user_email: '',
    account_name: m.accountName || '',
    meeting_subject: m.subject || '',
    assignee_name: t.owner || '',
    assignee_email: t.owner_email || '',
    assignee_role: t.assignee_role || '',
  }
}));

return [{ json: {
  ...data,
  activityPayload,
  taskPayloads,
  taskCount: taskPayloads.length,
}}];
"""
```

- [ ] **Step 3: Add the Send Auto-Save to Workato node**

HTTP Request node that fires the `log_activity` payload to Workato:

```python
def add_auto_save_nodes(wf):
    nodes = wf['nodes']
    conns = wf['connections']

    # Node: Build Auto-Save Payload
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Build Auto-Save Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2200, 400],
        "parameters": {"jsCode": AUTO_SAVE_CODE},
    })

    # Node: Send Recap to CRM
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Send Recap to CRM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2400, 300],
        "parameters": {
            "method": "POST",
            "url": WORKATO_URL,
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.activityPayload) }}",
            "options": {"timeout": 15000},
        },
    })

    # Node: Send Tasks to CRM (loop through taskPayloads)
    TASK_LOOP_CODE = r"""
const data = $('Build Auto-Save Payload').first().json;
const payloads = data.taskPayloads || [];
if (payloads.length === 0) return [{ json: { ...data, skip: true } }];
return payloads.map(p => ({ json: { ...data, webhook_payload: p } }));
"""
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Prepare Task Payloads",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2400, 500],
        "parameters": {"jsCode": TASK_LOOP_CODE},
    })

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Send Tasks to CRM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2600, 500],
        "parameters": {
            "method": "POST",
            "url": WORKATO_URL,
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
            "options": {"timeout": 15000},
        },
    })

    return wf
```

- [ ] **Step 4: Rewire the flow**

New flow: Parse Recap Output → Build Auto-Save Payload → [Send Recap to CRM + Prepare Task Payloads (parallel)] → Prepare Task Payloads → Send Tasks to CRM → Build Recap Card → Open Bot DM → Send Recap → Build Recap Thread → Send Recap Thread

```python
def rewire_flow(wf):
    conns = wf['connections']

    # Parse Recap Output → Build Auto-Save Payload (was → Build Recap Card)
    conns['Parse Recap Output'] = {'main': [[
        {'node': 'Build Auto-Save Payload', 'type': 'main', 'index': 0}
    ]]}

    # Build Auto-Save Payload → Send Recap to CRM + Prepare Task Payloads (parallel)
    conns['Build Auto-Save Payload'] = {'main': [[
        {'node': 'Send Recap to CRM', 'type': 'main', 'index': 0},
        {'node': 'Prepare Task Payloads', 'type': 'main', 'index': 0},
    ]]}

    # Prepare Task Payloads → Send Tasks to CRM
    conns['Prepare Task Payloads'] = {'main': [[
        {'node': 'Send Tasks to CRM', 'type': 'main', 'index': 0}
    ]]}

    # Send Recap to CRM → Build Recap Card (card waits for save to complete)
    conns['Send Recap to CRM'] = {'main': [[
        {'node': 'Build Recap Card', 'type': 'main', 'index': 0}
    ]]}

    # Keep existing: Build Recap Card → Open Bot DM → Send Recap → Build Recap Thread → Send Recap Thread

    return wf
```

- [ ] **Step 5: Update Build Recap Card with new layout**

Replace the existing Build Recap Card code with the simplified confirmation card:

```python
NEW_CARD_CODE = r"""
// Simplified card — auto-saved confirmation with PeopleGlass links
const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const blocks = [];

// Header with account + meeting info
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr} ${m.timeStr} \u2014 ${m.subject || 'Customer Meeting'}` }
});

// Confirmation line in assistant voice
const taskWord = taskCount === 1 ? 'task' : 'tasks';
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:white_check_mark: I saved this recap to CRM and created ${taskCount} ${taskWord}:` }
});

// Task list (compact, one line per task)
if (recap.tasks && recap.tasks.length > 0) {
  const taskLines = recap.tasks.slice(0, 5).map(t => {
    const due = t.due_hint ? ` \u00b7 ${t.due_hint}` : '';
    return `\u2022 ${t.description}${t.owner ? ' \u2014 *' + t.owner + '*' : ''}${due}`;
  }).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: taskLines }
  });
}

// Action buttons: Draft Follow-up + PeopleGlass links
const truncContext = (recap.followUpContext || '').substring(0, 500);
const draftPayload = JSON.stringify({
  action: 'draft_followup',
  account_name: m.accountName,
  account_id: m.accountId || '',
  activity_uid: m.activityUid,
  meeting_subject: m.subject,
  participants: m.participants || '',
  follow_up_context: truncContext,
  user_id: data.userId,
  db_user_id: data.userId,
  slack_user_id: data.slackUserId,
  organization_id: data.organizationId || '',
  assistant_name: data.assistantName,
  assistant_emoji: data.assistantEmoji,
  rep_name: data.repName,
});

blocks.push({
  type: "actions",
  elements: [
    {
      type: "button",
      text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true },
      action_id: "recap_draft_followup",
      value: draftPayload
    },
    {
      type: "button",
      text: { type: "plain_text", text: "My Events Today", emoji: true },
      url: "PEOPLEGLASS_EVENTS_URL",
      action_id: "pg_events_link"
    },
    {
      type: "button",
      text: { type: "plain_text", text: "All Tasks Today", emoji: true },
      url: "PEOPLEGLASS_TASKS_URL",
      action_id: "pg_tasks_link"
    }
  ]
});

const promptText = `Meeting Recap \u2014 ${m.accountName}: ${m.subject || 'Customer Meeting'}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  activityUids: [m.activityUid],
}}];
""".replace('PEOPLEGLASS_EVENTS_URL', PEOPLEGLASS_EVENTS).replace('PEOPLEGLASS_TASKS_URL', PEOPLEGLASS_TASKS)
```

- [ ] **Step 6: Update Build Recap Thread with simplified layout**

Remove individual "Create Task" buttons, keep recap text as read-only:

```python
NEW_THREAD_CODE = r"""
// Simplified thread — recap details + task confirmation (no action buttons)
const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const sendResult = $('Send Recap').first().json;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Summary + sentiment
const sentLine = `${recap.sentimentEmoji} ${recap.sentimentSignal || recap.sentiment}`;
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `${sentLine}\n\n${recap.summary}` }
});

blocks.push({ type: "divider" });

// Key Decisions
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `\u2022 ${d}`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\n${decisionText}` }
  });
  blocks.push({ type: "divider" });
}

// Action Items (read-only confirmation, no buttons)
if (recap.tasks && recap.tasks.length > 0) {
  const taskText = recap.tasks.map(t => {
    const roleBadge = t.assignee_role ? ` (${t.assignee_role})` : '';
    const durationBadge = t.duration_minutes ? ` \u00b7 ${t.duration_minutes} min` : '';
    return `\u2022 ${t.description}` +
      (t.owner ? ` \u2014 _${t.owner}_` + roleBadge : '') +
      durationBadge +
      (t.due_hint ? ` \u00b7 ${t.due_hint}` : '');
  }).join('\n');

  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Action Items* (saved to CRM)\n${taskText}` }
  });
}

if ((!recap.keyDecisions || recap.keyDecisions.length === 0) &&
    (!recap.tasks || recap.tasks.length === 0)) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "_No key decisions or action items were captured for this meeting._" }
  });
}

// Footer with edit instructions
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "Tasks and recap saved to CRM \u2022 Use PeopleGlass to review or modify \u2022 Reply in this thread to discuss" }
  ]
});

return [{ json: {
  threadBlocks: JSON.stringify(blocks),
  threadTs: sendResult.ts,
  channelId: sendResult.channel,
  assistantName,
  assistantEmoji,
}}];
"""
```

- [ ] **Step 7: Assemble main() and run**

```python
def main():
    print("=== Auto-Save Recap: Modifying Follow-up Cron ===")
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    print(f"Fetched: {len(wf['nodes'])} nodes")

    # Add new nodes
    wf = add_auto_save_nodes(wf)
    print("Added: Build Auto-Save Payload, Send Recap to CRM, Prepare Task Payloads, Send Tasks to CRM")

    # Update existing nodes
    find_node(wf['nodes'], 'Build Recap Card')['parameters']['jsCode'] = NEW_CARD_CODE
    print("Updated: Build Recap Card (simplified with PeopleGlass links)")

    find_node(wf['nodes'], 'Build Recap Thread')['parameters']['jsCode'] = NEW_THREAD_CODE
    print("Updated: Build Recap Thread (read-only, no task buttons)")

    # Rewire
    wf = rewire_flow(wf)
    print("Rewired: Parse Recap → Auto-Save → Card → Send")

    # Push
    result = push_workflow(WF_FOLLOWUP_CRON, wf)
    print(f"Pushed Follow-up Cron: {len(result['nodes'])} nodes")
    sync_local(fetch_workflow(WF_FOLLOWUP_CRON), "Follow-up Cron.json")
    print("Done!")

if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run the script**

```bash
cd scripts && python3 auto_save_recap.py
```

Expected: `Pushed Follow-up Cron: 27 nodes` (23 original + 4 new)

- [ ] **Step 9: Commit**

```bash
git add scripts/auto_save_recap.py n8n/workflows/Follow-up\ Cron.json
git commit -m "feat: auto-save meeting recaps and tasks to CRM, replace review gate with PeopleGlass links"
```

---

### Task 2: Update Workato recipe

**Manual steps** — not automated via script.

- [ ] **Step 1: Update `log_activity` action in Workato**

In the Workato recipe "People.ai Assistant — Save to Salesforce":

1. After the SOQL lookup finds the Event, build the update payload conditionally:
   - **Meeting Category:** If `Event.Meeting_Category IS NULL` → set to `fields.meeting_category`. If already set → skip.
   - **CS Category:** If `Event.CS_Category IS NULL` → set to `fields.cs_category`. If already set → skip.
   - Both fields use the same null-check pattern independently.

2. For Description prepend:
   - **New Description** = `fields.Description` + `"\n\n---\n\n"` + `Event.Description` (existing)
   - If existing Description is blank, just use `fields.Description`

- [ ] **Step 2: Verify `create_task` action**

No changes needed — confirm the existing `create_task` action creates Task with all fields including Category. The auto-save sends the same payload format as the current modal-based flow.

- [ ] **Step 3: Test the Workato changes**

Send a test payload manually to verify:
- Category protection works (set Category, send another payload, verify it wasn't overwritten)
- Description prepend works (send payload to an Event that already has a Description)

---

### Task 3: Test end-to-end

- [ ] **Step 1: Trigger a test recap**

Wait for the next Follow-up Cron run (9am or 4pm PT), or trigger manually by having a recent customer meeting in People.ai data.

- [ ] **Step 2: Verify auto-save**

Check in Salesforce/PeopleGlass:
- Event Description has the AI recap prepended
- Event Category set (if was blank)
- Tasks created with correct assignees, dates, categories

- [ ] **Step 3: Verify Slack card**

The Slack card should show:
- `:white_check_mark: I saved this recap to CRM and created N tasks:`
- Task list with owners and due dates
- Three buttons: Draft Follow-up, My Events Today, All Tasks Today
- PeopleGlass links work and show the modified records

- [ ] **Step 4: Verify thread**

The thread should show:
- Full recap text (summary, sentiment, key decisions)
- Task list as read-only (no "Create Task" buttons)
- Footer: "Tasks and recap saved to CRM - Use PeopleGlass to review or modify"

- [ ] **Step 5: Verify Category protection**

Find an Event that already has a Category set. Trigger a recap for that meeting. Verify the Category was NOT overwritten.

---

### Task 4: Update Confluence documentation

- [ ] **Step 1: Update the Skills & Capabilities page**

Update Skill 3 (Meeting Recap + Action Hub) on the Confluence page to reflect:
- Auto-save behavior (no review gate)
- PeopleGlass links for editing
- Category protection logic
- Remove references to "Review & Log" and "Tasks" buttons

Page: `https://peopleai.atlassian.net/wiki/spaces/CS/pages/59392262149`
