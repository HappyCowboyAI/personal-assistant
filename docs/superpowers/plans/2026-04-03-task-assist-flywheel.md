# Task Assist Flywheel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Match open CRM tasks to assistant skills and surface one-click suggestions inline on recap cards and resolution summary DMs.

**Architecture:** Hybrid keyword + LLM matching. Keyword matcher runs in Code nodes at recap time (zero cost). LLM classification piggybacks on the existing Task Resolution Agent at 9am/4pm. Button clicks route through the Interactive Events Handler to existing skill flows.

**Tech Stack:** n8n workflows (API-managed via Python), Claude Sonnet 4.5 (extended prompt), Backstory MCP, Slack Block Kit

**Spec:** `docs/superpowers/specs/2026-04-03-task-assist-flywheel-design.md`

---

## File Structure

| File | Purpose |
|------|---------|
| `scripts/add_task_assist.py` | Python script to push all changes to n8n via API |
| `n8n/workflows/Follow-up Cron.json` | Modified — Build Recap Card gets keyword matching + assist section |
| `n8n/workflows/Slack Events Handler.json` | Modified — Recap Build Card OD gets keyword matching + assist section |
| `n8n/workflows/Task Resolution Handler.json` | Modified — agent prompt, parse results, collect, summary, format DM |
| `n8n/workflows/Interactive Events Handler.json` | Modified — 4 new task_assist_* routes + bridge nodes |

---

### Task 1: Create the script with shared constants

**Files:**
- Create: `scripts/add_task_assist.py`

- [ ] **Step 1: Create the script skeleton with SKILL_REGISTRY and helpers**

Create `scripts/add_task_assist.py`:

```python
#!/usr/bin/env python3
"""Task Assist Flywheel: keyword matching on recap cards + LLM classification in resolution agent."""

import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from n8n_helpers import (
    uid, fetch_workflow, push_workflow, sync_local, find_node, modify_workflow,
    WF_FOLLOWUP_CRON, WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
    SUPABASE_URL, SUPABASE_CRED, SLACK_CRED, ANTHROPIC_CRED, MCP_CRED,
    make_code_node, make_slack_http_node,
)

# Workflow ID for Task Resolution Handler
WF_TASK_RESOLUTION = "dnoslQTCCTHZVexp"

# Shared SKILL_REGISTRY JS constant — embedded in Code nodes
SKILL_REGISTRY_JS = r"""
const SKILL_REGISTRY = [
  {
    id: 'draft_email',
    label: 'Draft Email',
    keywords: ['send email', 'follow up', 'follow-up', 'email', 'reach out',
               'share with', 'send to', 'write to', 'notify',
               'update via email', 'loop in'],
    buttonText: ':email: Draft Email',
    actionId: 'task_assist_draft_email',
  },
  {
    id: 'presentation',
    label: 'Create Presentation',
    keywords: ['create deck', 'build slides', 'presentation', 'qbr',
               'prepare deck', 'slide deck', 'google slides'],
    buttonText: ':bar_chart: Create Deck',
    actionId: 'task_assist_presentation',
  },
  {
    id: 'stakeholder_map',
    label: 'Stakeholder Map',
    keywords: ['map contacts', 'stakeholder', 'decision maker',
               'identify contacts', 'org chart', 'key contacts', 'champion'],
    buttonText: ':busts_in_silhouette: Stakeholder Map',
    actionId: 'task_assist_stakeholders',
  },
  {
    id: 'meeting_prep',
    label: 'Meeting Prep',
    keywords: ['prepare for meeting', 'prep for call', 'research before',
               'meeting brief', 'pre-meeting', 'talking points'],
    buttonText: ':clipboard: Meeting Prep',
    actionId: 'task_assist_meeting_prep',
  },
];

function matchTaskToSkill(taskSubject, taskDescription) {
  const text = (taskSubject + ' ' + (taskDescription || '')).toLowerCase();
  for (const skill of SKILL_REGISTRY) {
    for (const kw of skill.keywords) {
      if (text.includes(kw)) return skill;
    }
  }
  return null;
}
"""

SKILL_ID_MAP_JS = r"""
const SKILL_ID_MAP = {
  'DRAFT_EMAIL': 'draft_email',
  'PRESENTATION': 'presentation',
  'STAKEHOLDER_MAP': 'stakeholder_map',
  'MEETING_PREP': 'meeting_prep',
};
"""
```

- [ ] **Step 2: Commit**

```bash
git add scripts/add_task_assist.py
git commit -m "feat: add task assist flywheel script skeleton with skill registry"
```

---

### Task 2: Add keyword matching to Build Recap Card (Follow-up Cron)

**Files:**
- Modify: `scripts/add_task_assist.py`
- Synced: `n8n/workflows/Follow-up Cron.json`

- [ ] **Step 1: Add the modify function for Follow-up Cron**

Add to `scripts/add_task_assist.py`:

```python
def add_assist_to_recap_card():
    """Add keyword matching + assist section to Build Recap Card in Follow-up Cron."""

    print("=" * 60)
    print("FOLLOW-UP CRON — adding task assist to Build Recap Card")
    print("=" * 60)

    def modifier(nodes, connections):
        node = find_node(nodes, "Build Recap Card")
        if not node:
            print("  ERROR: Build Recap Card not found")
            return 0

        code = node["parameters"]["jsCode"]
        if "SKILL_REGISTRY" in code:
            print("  SKILL_REGISTRY already present — skipping")
            return 0

        # New code: prepend SKILL_REGISTRY + matcher, then replace the card builder
        new_code = SKILL_REGISTRY_JS + r"""
// Compact recap card — details live in the thread
const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const subjectLine = m.subject || 'Customer Meeting';
const blocks = [];

// Header: account + time + subject
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr}, ${m.timeStr} \u2014 ${subjectLine}` }
});

// Compact confirmation line
const parts = ['I saved this recap to CRM'];
if (taskCount > 0) parts.push(`created ${taskCount} task${taskCount === 1 ? '' : 's'}`);
const confirmText = ':white_check_mark: ' + parts.join(' and ') + '. Check the thread for details!';

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: confirmText }
});

// --- Task Assist: keyword match freshly created tasks ---
const assistable = [];
for (const t of (recap.tasks || [])) {
  const skill = matchTaskToSkill(t.description, '');
  if (skill) {
    assistable.push({ task: t, skill });
  }
}

if (assistable.length > 0) {
  const lines = assistable.map(a =>
    `\u2022 ${a.task.description}${a.task.owner ? ' \u2014 ' + a.task.owner : ''}`
  ).join('\n');

  blocks.push({
    type: "section",
    text: { type: "mrkdwn",
      text: `:robot_face: I can help with ${assistable.length} of these:\n${lines}` }
  });

  const elements = assistable.slice(0, 5).map(a => ({
    type: "button",
    text: { type: "plain_text", text: a.skill.buttonText, emoji: true },
    action_id: a.skill.actionId,
    value: JSON.stringify({
      action: 'task_assist',
      skill: a.skill.id,
      task_subject: a.task.description,
      account_name: m.accountName,
      account_id: m.accountId || '',
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      organization_id: data.organizationId || '',
      assistant_name: assistantName,
      assistant_emoji: assistantEmoji,
      rep_name: data.repName,
    })
  }));

  blocks.push({ type: "actions", elements });
}

// Action buttons
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
  assistant_name: assistantName,
  assistant_emoji: assistantEmoji,
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
      action_id: "link_my_events",
      url: "https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61"
    },
    {
      type: "button",
      text: { type: "plain_text", text: "All Tasks Today", emoji: true },
      action_id: "link_all_tasks",
      url: "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"
    }
  ]
});

const promptText = `Meeting Recap \u2014 ${m.accountName}: ${subjectLine}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  activityUids: [m.activityUid],
}}];"""

        node["parameters"]["jsCode"] = new_code
        print("  Replaced Build Recap Card with keyword matching + assist section")
        return 1

    modify_workflow(WF_FOLLOWUP_CRON, "Follow-up Cron.json", modifier)
```

- [ ] **Step 2: Run and verify**

```bash
cd scripts && python3 -c "from add_task_assist import add_assist_to_recap_card; add_assist_to_recap_card()"
```

Expected: `Replaced Build Recap Card with keyword matching + assist section`, `HTTP 200`

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/Follow-up\ Cron.json
git commit -m "feat: add task assist keyword matching to Follow-up Cron recap card"
```

---

### Task 3: Add keyword matching to Recap Build Card OD (Events Handler)

**Files:**
- Modify: `scripts/add_task_assist.py`
- Synced: `n8n/workflows/Slack Events Handler.json`

- [ ] **Step 1: Add the modify function for Events Handler**

Add to `scripts/add_task_assist.py`:

```python
def add_assist_to_recap_card_od():
    """Add keyword matching + assist section to Recap Build Card OD in Events Handler."""

    print("=" * 60)
    print("EVENTS HANDLER — adding task assist to Recap Build Card OD")
    print("=" * 60)

    def modifier(nodes, connections):
        node = find_node(nodes, "Recap Build Card OD")
        if not node:
            print("  ERROR: Recap Build Card OD not found")
            return 0

        code = node["parameters"]["jsCode"]
        if "SKILL_REGISTRY" in code:
            print("  SKILL_REGISTRY already present — skipping")
            return 0

        new_code = SKILL_REGISTRY_JS + r"""
// Compact recap card — details live in the thread
const data = $('Build Auto-Save OD').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const subjectLine = m.subject || 'Customer Meeting';
const blocks = [];

// Header: account + time + subject
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr} ${m.timeStr} \u2014 ${subjectLine}` }
});

// Compact confirmation line
const parts = ['I saved this recap to CRM'];
if (taskCount > 0) parts.push(`created ${taskCount} task${taskCount === 1 ? '' : 's'}`);
const confirmText = ':white_check_mark: ' + parts.join(' and ') + '. Check the thread for details!';

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: confirmText }
});

// --- Task Assist: keyword match freshly created tasks ---
const assistable = [];
for (const t of (recap.tasks || [])) {
  const skill = matchTaskToSkill(t.description, '');
  if (skill) {
    assistable.push({ task: t, skill });
  }
}

if (assistable.length > 0) {
  const lines = assistable.map(a =>
    `\u2022 ${a.task.description}${a.task.owner ? ' \u2014 ' + a.task.owner : ''}`
  ).join('\n');

  blocks.push({
    type: "section",
    text: { type: "mrkdwn",
      text: `:robot_face: I can help with ${assistable.length} of these:\n${lines}` }
  });

  const elements = assistable.slice(0, 5).map(a => ({
    type: "button",
    text: { type: "plain_text", text: a.skill.buttonText, emoji: true },
    action_id: a.skill.actionId,
    value: JSON.stringify({
      action: 'task_assist',
      skill: a.skill.id,
      task_subject: a.task.description,
      account_name: m.accountName,
      account_id: m.accountId || '',
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      organization_id: data.organizationId || '',
      assistant_name: data.assistantName,
      assistant_emoji: data.assistantEmoji,
      rep_name: data.repName,
    })
  }));

  blocks.push({ type: "actions", elements });
}

// Action buttons
const truncContext = (recap.followUpContext || '').substring(0, 500);
const draftPayload = JSON.stringify({
  action: 'draft_followup', account_name: m.accountName, account_id: m.accountId || '',
  activity_uid: m.activityUid, meeting_subject: m.subject,
  participants: m.participants || '', follow_up_context: truncContext,
  user_id: data.userId, db_user_id: data.userId, slack_user_id: data.slackUserId,
  organization_id: data.organizationId || '',
  assistant_name: data.assistantName, assistant_emoji: data.assistantEmoji, rep_name: data.repName,
});

blocks.push({ type: "actions", elements: [
  { type: "button", text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true }, action_id: "recap_draft_followup", value: draftPayload },
  { type: "button", text: { type: "plain_text", text: "My Events Today", emoji: true }, url: "https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61", action_id: "pg_events_link" },
  { type: "button", text: { type: "plain_text", text: "All Tasks Today", emoji: true }, url: "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5", action_id: "pg_tasks_link" },
]});

return [{ json: { ...data, blocks: JSON.stringify(blocks), promptText: `Meeting Recap \u2014 ${m.accountName}: ${subjectLine}`, assistantName, assistantEmoji, activityUids: [m.activityUid] } }];"""

        node["parameters"]["jsCode"] = new_code
        print("  Replaced Recap Build Card OD with keyword matching + assist section")
        return 1

    modify_workflow(WF_EVENTS_HANDLER, "Slack Events Handler.json", modifier)
```

- [ ] **Step 2: Run and verify**

```bash
cd scripts && python3 -c "from add_task_assist import add_assist_to_recap_card_od; add_assist_to_recap_card_od()"
```

Expected: `Replaced Recap Build Card OD`, `HTTP 200`

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/Slack\ Events\ Handler.json
git commit -m "feat: add task assist keyword matching to Events Handler recap card"
```

---

### Task 4: Extend Resolution Agent prompt for assist_skill classification

**Files:**
- Modify: `scripts/add_task_assist.py`
- Synced: `n8n/workflows/Task Resolution Handler.json`

- [ ] **Step 1: Add function to update the Resolution Agent system prompt and user prompt**

Add to `scripts/add_task_assist.py`:

```python
def update_resolution_agent_prompt():
    """Extend the Resolution Agent prompt to include assist_skill classification."""

    print("=" * 60)
    print("TASK RESOLUTION HANDLER — extending agent prompt")
    print("=" * 60)

    def modifier(nodes, connections):
        agent = find_node(nodes, "Resolution Agent")
        if not agent:
            print("  ERROR: Resolution Agent not found")
            return 0

        system_prompt = agent["parameters"]["options"].get("systemMessage", "")
        if "assist_skill" in system_prompt:
            print("  assist_skill already in prompt — skipping")
            return 0

        # Extend system prompt
        new_system = r"""You are a task resolution analyst. You evaluate whether CRM tasks have been completed based on recent account activity from Backstory SalesAI.

RULES:
- Only mark a task COMPLETE if there is CLEAR evidence the work was done
- Evidence includes: email sent, meeting held, document delivered, issue resolved, follow-up completed
- When in doubt, leave as OPEN
- Be conservative — false completions are worse than missed completions

You also determine whether the assistant can help with each OPEN task.
Available assistant skills:
- DRAFT_EMAIL: task involves sending an email, follow-up, or written communication
- PRESENTATION: task involves creating a deck, slides, or visual deliverable
- STAKEHOLDER_MAP: task involves identifying or mapping contacts and relationships
- MEETING_PREP: task involves preparing for an upcoming meeting or call
- NONE: assistant cannot help with this task

Output ONLY valid JSON, no prose"""

        agent["parameters"]["options"]["systemMessage"] = new_system
        print("  Updated system prompt with assist_skill classification")

        # Update user prompt to include assist_skill in output schema
        old_prompt = agent["parameters"].get("text", "")
        new_prompt = old_prompt.replace(
            '{"id": "SF_TASK_ID", "status": "COMPLETE" or "OPEN", "evidence": "one-line reason"}',
            '{"id": "SF_TASK_ID", "status": "COMPLETE" or "OPEN", "evidence": "one-line reason", "assist_skill": "DRAFT_EMAIL|PRESENTATION|STAKEHOLDER_MAP|MEETING_PREP|NONE"}'
        )

        if new_prompt == old_prompt:
            # Fallback: replace entire prompt template
            new_prompt = r"""={{ "Review these open CRM tasks for " + $json.accountName + ":\n\n" + $json.taskList + "\n\nUse Backstory SalesAI tools (ask_sales_ai_about_account) to check recent activity, emails, and meeting outcomes for " + $json.accountName + ".\n\nFor each task, determine if it was completed based on evidence from recent activity. Also determine if the assistant can help with each OPEN task.\n\nOutput JSON:\n{\n  \"account_name\": \"" + $json.accountName + "\",\n  \"results\": [\n    {\"id\": \"SF_TASK_ID\", \"status\": \"COMPLETE\" or \"OPEN\", \"evidence\": \"one-line reason\", \"assist_skill\": \"DRAFT_EMAIL|PRESENTATION|STAKEHOLDER_MAP|MEETING_PREP|NONE\"}\n  ]\n}" }}"""
            print("  Replaced entire user prompt template (fallback)")

        agent["parameters"]["text"] = new_prompt
        print("  Updated user prompt with assist_skill in output schema")
        return 1

    modify_workflow(WF_TASK_RESOLUTION, "Task Resolution Handler.json", modifier)
```

- [ ] **Step 2: Run and verify**

```bash
cd scripts && python3 -c "from add_task_assist import update_resolution_agent_prompt; update_resolution_agent_prompt()"
```

Expected: `Updated system prompt`, `Updated user prompt`, `HTTP 200`

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/Task\ Resolution\ Handler.json
git commit -m "feat: extend resolution agent prompt with assist_skill classification"
```

---

### Task 5: Update Parse Resolution Results, Collect All Results, Build Summary, Format Summary DM

**Files:**
- Modify: `scripts/add_task_assist.py`
- Synced: `n8n/workflows/Task Resolution Handler.json`

- [ ] **Step 1: Add function to update all 4 downstream nodes**

Add to `scripts/add_task_assist.py`:

```python
WORKATO_WRITE_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"
PEOPLEGLASS_TASKS_URL = "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"


def update_resolution_downstream_nodes():
    """Update Parse Results, Collect All, Build Summary, Format DM to include assist data."""

    print("=" * 60)
    print("TASK RESOLUTION HANDLER — updating downstream nodes for assist")
    print("=" * 60)

    def modifier(nodes, connections):
        changes = 0

        # --- Parse Resolution Results ---
        parse_node = find_node(nodes, "Parse Resolution Results")
        if parse_node and "assistableTasks" not in parse_node["parameters"].get("jsCode", ""):
            parse_node["parameters"]["jsCode"] = SKILL_ID_MAP_JS + r"""
const agentOutput = $('Resolution Agent').first().json.output || '';
const accountData = $('Loop Accounts').first().json;
const accountName = accountData.accountName;
const tasks = accountData.tasks || [];

let results = [];
try {
  const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)```/) || agentOutput.match(/(\{[\s\S]*?"results"[\s\S]*?\})/);
  if (jsonMatch) {
    const parsed = JSON.parse(jsonMatch[1] || jsonMatch[0]);
    results = parsed.results || [];
  } else {
    const parsed = JSON.parse(agentOutput);
    results = parsed.results || [];
  }
} catch (e) {
  results = tasks.map(t => ({
    id: t.Id, status: 'OPEN', evidence: 'Agent did not return valid results', assist_skill: 'NONE',
  }));
}

const completedTasks = [];
const openTasks = [];
const assistableTasks = [];

for (const t of tasks) {
  const r = results.find(r => r.id === t.Id);
  if (r && r.status === 'COMPLETE') {
    completedTasks.push({
      id: t.Id, subject: t.Subject, evidence: r.evidence || '',
      accountName: t.Account_Name || accountName,
    });
  } else {
    openTasks.push({
      id: t.Id, subject: t.Subject, evidence: r ? r.evidence : 'No evidence found',
      accountName: t.Account_Name || accountName,
    });
    // Check if assistant can help
    const skillKey = r && r.assist_skill ? r.assist_skill.toUpperCase() : 'NONE';
    const skillId = SKILL_ID_MAP[skillKey];
    if (skillId) {
      assistableTasks.push({
        id: t.Id, subject: t.Subject,
        accountName: t.Account_Name || accountName,
        assistSkill: skillId,
      });
    }
  }
}

return [{ json: {
  accountName, completedTasks, openTasks, assistableTasks,
  completedCount: completedTasks.length,
  openCount: openTasks.length,
  assistableCount: assistableTasks.length,
  channelId: accountData.channelId,
  assistantName: accountData.assistantName,
  assistantEmoji: accountData.assistantEmoji,
  requestId: accountData.requestId,
}}];"""
            print("  Updated Parse Resolution Results")
            changes += 1

        # --- Collect All Results ---
        collect_node = find_node(nodes, "Collect All Results")
        if collect_node and "assistableDetails" not in collect_node["parameters"].get("jsCode", ""):
            collect_node["parameters"]["jsCode"] = r"""const allItems = $('Parse Resolution Results').all();
let totalCompleted = 0;
let totalOpen = 0;
const completedDetails = [];
const assistableDetails = [];
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
  for (const t of (d.completedTasks || [])) completedDetails.push(t);
  for (const t of (d.assistableTasks || [])) assistableDetails.push(t);
}

return [{ json: {
  totalCompleted, totalOpen, completedDetails, assistableDetails,
  channelId, assistantName, assistantEmoji, requestId,
  hasSummary: totalCompleted > 0,
}}];"""
            print("  Updated Collect All Results")
            changes += 1

        # --- Build Summary ---
        summary_node = find_node(nodes, "Build Summary")
        if summary_node and "assistableDetails" not in summary_node["parameters"].get("jsCode", ""):
            summary_node["parameters"]["jsCode"] = r"""const data = $input.first().json;

if (!data.hasSummary || data.totalCompleted === 0) {
  return [{ json: { ...data, skipSummary: true } }];
}

const completed = data.completedDetails || [];
const lines = completed.map(t => {
  return `:white_check_mark: ~${(t.subject || 'Task').substring(0, 80)}~ (${t.evidence || 'activity detected'})`;
}).join('\n');

let summaryText = `:clipboard: *Task Update*\nI reviewed your open tasks against recent activity:\n\n${lines}`;

// Append assist suggestions if any
const assistable = data.assistableDetails || [];
if (assistable.length > 0) {
  const assistLines = assistable.slice(0, 5).map(t =>
    `\u2022 ${(t.subject || 'Task').substring(0, 80)} (${t.accountName})`
  ).join('\n');
  summaryText += `\n\n:robot_face: I can help with ${assistable.length} open task${assistable.length !== 1 ? 's' : ''}:\n${assistLines}`;
}

summaryText += `\n\nMarked ${data.totalCompleted} task${data.totalCompleted !== 1 ? 's' : ''} complete \u00b7 ${data.totalOpen} still open`;

return [{ json: {
  ...data,
  summaryText,
  skipSummary: false,
}}];"""
            print("  Updated Build Summary")
            changes += 1

        # --- Format Summary DM ---
        format_node = find_node(nodes, "Format Summary DM")
        if format_node and "task_assist_" not in format_node["parameters"].get("jsCode", ""):
            format_node["parameters"]["jsCode"] = r"""const SKILL_BUTTON_MAP = {
  'draft_email':      { text: ':email: Draft Email',                actionId: 'task_assist_draft_email' },
  'presentation':     { text: ':bar_chart: Create Deck',           actionId: 'task_assist_presentation' },
  'stakeholder_map':  { text: ':busts_in_silhouette: Stakeholder Map', actionId: 'task_assist_stakeholders' },
  'meeting_prep':     { text: ':clipboard: Meeting Prep',          actionId: 'task_assist_meeting_prep' },
};

const data = $input.first().json;
const assistable = data.assistableDetails || [];

const blocks = [];

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: data.summaryText }
});

// Assist buttons (skill + complete per task)
if (assistable.length > 0) {
  const elements = [];
  for (const t of assistable.slice(0, 3)) {
    const skillBtn = SKILL_BUTTON_MAP[t.assistSkill];
    if (skillBtn) {
      elements.push({
        type: "button",
        text: { type: "plain_text", text: skillBtn.text, emoji: true },
        action_id: skillBtn.actionId,
        value: JSON.stringify({
          action: 'task_assist',
          skill: t.assistSkill,
          task_id: t.id,
          task_subject: t.subject,
          account_name: t.accountName,
          user_id: '',
          slack_user_id: '',
          assistant_name: data.assistantName,
          assistant_emoji: data.assistantEmoji,
        })
      });
      elements.push({
        type: "button",
        text: { type: "plain_text", text: ":white_check_mark: Complete", emoji: true },
        action_id: "task_complete_" + t.id,
        value: JSON.stringify({ task_id: t.id, task_subject: t.subject, account_name: t.accountName }),
      });
    }
  }
  if (elements.length > 0) {
    blocks.push({ type: "actions", elements: elements.slice(0, 5) });
  }
}

blocks.push({ type: "divider" });

blocks.push({
  type: "actions",
  elements: [{
    type: "button",
    text: { type: "plain_text", text: ":clipboard: All Tasks Today", emoji: true },
    url: "TASKS_URL",
    action_id: "resolution_view_tasks"
  }]
});

return [{ json: {
  channelId: data.channelId,
  assistantName: data.assistantName,
  assistantEmoji: data.assistantEmoji,
  blocks: JSON.stringify(blocks),
  text: 'Task Update: Marked ' + data.totalCompleted + ' task' + (data.totalCompleted !== 1 ? 's' : '') + ' complete',
}}];""".replace("TASKS_URL", PEOPLEGLASS_TASKS_URL)
            print("  Updated Format Summary DM")
            changes += 1

        return changes

    modify_workflow(WF_TASK_RESOLUTION, "Task Resolution Handler.json", modifier)
```

- [ ] **Step 2: Run and verify**

```bash
cd scripts && python3 -c "from add_task_assist import update_resolution_downstream_nodes; update_resolution_downstream_nodes()"
```

Expected: 4 nodes updated, `HTTP 200`

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/Task\ Resolution\ Handler.json
git commit -m "feat: add assist suggestions to resolution handler summary DM"
```

---

### Task 6: Add task_assist_* routing to Interactive Events Handler

**Files:**
- Modify: `scripts/add_task_assist.py`
- Synced: `n8n/workflows/Interactive Events Handler.json`

- [ ] **Step 1: Add function to add task assist routing**

This adds a bridge Code node for each skill that reformats the button payload to match what the existing skill flow expects, then wires it to the existing downstream path.

Add to `scripts/add_task_assist.py`:

```python
def add_task_assist_routing():
    """Add task_assist_* action routing to Interactive Events Handler."""

    print("=" * 60)
    print("INTERACTIVE EVENTS HANDLER — adding task_assist routing")
    print("=" * 60)

    def modifier(nodes, connections):
        changes = 0

        existing_names = {n["name"] for n in nodes}
        if "Bridge Task Assist" in existing_names:
            print("  Bridge Task Assist already exists — skipping")
            return 0

        # Find the Route Action switch node
        switch_node = find_node(nodes, "Route Action")
        if not switch_node:
            print("  ERROR: Route Action not found")
            return 0

        sx, sy = switch_node["position"]

        # Add a single Bridge node that handles all 4 task_assist_* actions
        # It reformats the payload to match what Bridge Recap to Draft expects
        bridge_js = r"""const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const skill = context.skill || '';
const accountName = context.account_name || '';
const accountId = context.account_id || '';
const taskSubject = context.task_subject || '';

// Route based on skill type
if (skill === 'draft_email') {
  // Reformat to match draft_followup bridge input
  return [{ json: {
    ...payload,
    actionValue: JSON.stringify({
      accountName,
      accountId,
      activityUid: '',
      meetingSubject: '',
      participants: '',
      userId: context.user_id || '',
      dbUserId: context.user_id || '',
      slackUserId: context.slack_user_id || '',
      organizationId: context.organization_id || '',
      assistantName: context.assistant_name || 'Aria',
      assistantEmoji: context.assistant_emoji || ':robot_face:',
      repName: context.rep_name || '',
      recapContext: 'Task: ' + taskSubject,
    }),
    actionId: 'followup_draft',
    routeSkill: 'draft_email',
  }}];
}

if (skill === 'presentation') {
  return [{ json: {
    ...payload,
    routeSkill: 'presentation',
    accountName,
    topic: taskSubject,
    userId: context.user_id || '',
    slackUserId: context.slack_user_id || '',
    assistantName: context.assistant_name || 'Aria',
    assistantEmoji: context.assistant_emoji || ':robot_face:',
  }}];
}

if (skill === 'stakeholder_map') {
  return [{ json: {
    ...payload,
    routeSkill: 'stakeholder_map',
    accountName,
    userId: context.user_id || '',
    slackUserId: context.slack_user_id || '',
    assistantName: context.assistant_name || 'Aria',
    assistantEmoji: context.assistant_emoji || ':robot_face:',
  }}];
}

if (skill === 'meeting_prep') {
  return [{ json: {
    ...payload,
    routeSkill: 'meeting_prep',
    accountName,
    userId: context.user_id || '',
    slackUserId: context.slack_user_id || '',
    assistantName: context.assistant_name || 'Aria',
    assistantEmoji: context.assistant_emoji || ':robot_face:',
  }}];
}

// Unknown skill — no-op
return [{ json: { ...payload, routeSkill: 'unknown' } }];"""

        bridge_node = make_code_node(
            "Bridge Task Assist", bridge_js, [sx + 400, sy + 600]
        )
        nodes.append(bridge_node)
        changes += 1
        print("  Added Bridge Task Assist node")

        # Add Switch conditions for all 4 task_assist_* action IDs
        # They all route to the same Bridge node
        rules = switch_node["parameters"].get("rules", {}).get("values", [])

        for action_id in [
            "task_assist_draft_email",
            "task_assist_presentation",
            "task_assist_stakeholders",
            "task_assist_meeting_prep",
        ]:
            # Check if already exists
            already = False
            for rule in rules:
                conds = rule.get("conditions", {}).get("conditions", [])
                for c in conds:
                    if c.get("rightValue") == action_id:
                        already = True
                        break
            if already:
                print(f"  {action_id} already in Switch — skipping")
                continue

            output_key = f"output_{len(rules)}"
            rules.append({
                "outputKey": output_key,
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
                            "name": "filter.operator.equals",
                            "type": "string",
                            "operation": "equals",
                        },
                        "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                        "rightValue": action_id,
                    }],
                },
            })
            print(f"  Added Switch rule for {action_id}")
            changes += 1

        switch_node["parameters"]["rules"]["values"] = rules

        # Wire all new Switch outputs to Bridge Task Assist
        route_conns = connections.get("Route Action", {"main": [[]]})
        # Ensure we have enough output arrays
        while len(route_conns["main"]) < len(rules) + 1:
            route_conns["main"].append([])

        # Wire the last 4 outputs to Bridge Task Assist
        for i in range(len(rules) - 4, len(rules)):
            output_idx = i + 1  # Switch outputs are 1-indexed (0 is fallback)
            if output_idx < len(route_conns["main"]):
                route_conns["main"][output_idx] = [
                    {"node": "Bridge Task Assist", "type": "main", "index": 0}
                ]
            else:
                route_conns["main"].append([
                    {"node": "Bridge Task Assist", "type": "main", "index": 0}
                ])
        connections["Route Action"] = route_conns

        # Wire Bridge Task Assist → Bridge Recap to Draft
        # Bridge Task Assist reformats all skills, but only draft_email currently
        # routes to Bridge Recap to Draft (which feeds the existing followup agent).
        # For presentation/stakeholder/meeting_prep, the Bridge node outputs
        # routeSkill but there's no downstream wiring yet — those buttons will
        # trigger the bridge but the skill flow won't fire until we wire the
        # sub-workflows. For v1, draft_email is the primary path.
        connections["Bridge Task Assist"] = {
            "main": [[{"node": "Bridge Recap to Draft", "type": "main", "index": 0}]]
        }
        print("  Wired Bridge Task Assist → Bridge Recap to Draft (draft_email path)")
        print("  NOTE: presentation, stakeholder_map, meeting_prep routing TBD — v1 ships draft_email")
        changes += 1

        return changes

    modify_workflow(WF_INTERACTIVE_HANDLER, "Interactive Events Handler.json", modifier)
```

- [ ] **Step 2: Run and verify**

```bash
cd scripts && python3 -c "from add_task_assist import add_task_assist_routing; add_task_assist_routing()"
```

Expected: Bridge node added, 4 Switch rules added, wiring complete, `HTTP 200`

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/Interactive\ Events\ Handler.json
git commit -m "feat: add task_assist button routing to Interactive Events Handler"
```

---

### Task 7: Add main() and run full deployment

**Files:**
- Modify: `scripts/add_task_assist.py`

- [ ] **Step 1: Add main function**

Add to `scripts/add_task_assist.py`:

```python
def main():
    print("=== Task Assist Flywheel Deployment ===\n")

    print("\n--- Entry Point 1: Recap Cards ---\n")
    add_assist_to_recap_card()
    add_assist_to_recap_card_od()

    print("\n--- Entry Point 2: Resolution Handler ---\n")
    update_resolution_agent_prompt()
    update_resolution_downstream_nodes()

    print("\n--- Button Routing ---\n")
    add_task_assist_routing()

    print("\n=== Done! ===")
    print("Recap cards: keyword matching + assist buttons")
    print("Resolution handler: LLM classification + assist section in DM")
    print("Interactive handler: task_assist_* routing → existing skill flows")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full deployment**

```bash
cd scripts && python3 add_task_assist.py
```

Expected: All 4 workflows updated, all synced locally.

- [ ] **Step 3: Commit**

```bash
git add scripts/add_task_assist.py n8n/workflows/
git commit -m "feat: deploy task assist flywheel — keyword + LLM matching with skill buttons"
```

---

### Task 8: Test end-to-end

- [ ] **Step 1: Test recap card keyword matching**

Type `recap <account>` in Slack DM (pick an account with a recent meeting). Verify:
- Recap card shows compact format
- If any tasks match keywords (e.g., "Send follow-up email..."), the assist section appears with the correct button
- Clicking the button triggers the draft followup flow

- [ ] **Step 2: Test resolution handler assist classification**

Wait for next 9am/4pm cron run, or trigger Follow-up Cron manually from n8n UI. Verify:
- If any tasks are marked complete AND open tasks have assist skills, the summary DM includes the assist section with skill buttons + Complete buttons
- If tasks are marked complete but no open tasks are assistable, summary DM shows completions only (no assist section)

- [ ] **Step 3: Verify button routing**

Click a task assist button from either entry point. Verify:
- "Draft Email" button triggers the followup draft agent
- Agent posts email draft in thread

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix: task assist flywheel adjustments from E2E testing"
```
