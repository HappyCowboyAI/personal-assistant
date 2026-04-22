# Meeting Recap + Action Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the Follow-up Cron from a simple "draft follow-up?" prompt into a Meeting Recap + Action Hub — an AI-generated post-meeting summary with extracted tasks and Salesforce write-back via Workato webhooks.

**Architecture:** The Follow-up Cron (9am + 4pm PT) detects ended meetings with ingested transcript data and generates AI recaps. The recap is delivered as a rich Slack Block Kit message with interactive buttons for: creating SF Tasks (via Workato webhook), saving the recap as a SF Activity (via Workato), and drafting a follow-up email (existing flow). The Interactive Events Handler gains new action routes for recap interactions.

**Tech Stack:** n8n workflows (Follow-up Cron, Interactive Events Handler), Claude Sonnet 4.5 via Anthropic API, Backstory MCP for transcript/activity data, Slack Block Kit with interactive buttons, Workato webhook for Salesforce writes, Supabase for logging/dedup.

---

## System Context

### Current Follow-up Cron Flow (workflow `JhDuCvZdFN4PFTOW`, 16 nodes)
```
Trigger (9am+4pm PT) → Get Auth Token → Build Query (meetings last 24h) →
Fetch Today Meetings → Parse Meetings → Get Followup Users → Compute Dedup Window →
Check Sent Followups → Match Users to Ended Meetings (4h+ elapsed, participant match, dedup) →
Has Matches? → Split In Batches → Build Follow-up Prompt (Block Kit with Draft/Skip buttons) →
Open Bot DM → Send Follow-up Prompt → Prepare Log Data → Log Follow-up Prompt → loop
```

### Current Interactive Events Handler Follow-up Flow (workflow `JgVjCqoT6ZwGuDL1`, 48 nodes)
When user clicks "Draft Follow-up" button:
```
Route Action (followup_draft) → Is Draft Followup? → Post Drafting Message →
Build Re-engagement Prompt → Update Msg - Drafting → Build Followup Context →
Followup Draft Agent (Claude + Backstory MCP) → Format Draft with Mailto →
Post Draft Reply → Update Msg - Done
```

### Key Design Decisions
- **Recap replaces the current follow-up prompt** — not an additional message. The recap IS the post-meeting touchpoint.
- **Workato webhook is generic** — receives `{object, recordId, fields, action}` and writes to SF. One Workato recipe covers Tasks, Activities, and future SF writes.
- **Recap is AI-generated from Backstory transcript data** — no user input required. The 9am/4pm cadence ensures transcript ingestion (3-4 hour delay) is complete.
- **Tasks are extracted by the AI** — presented as interactive buttons, each creating a SF Task via Workato when clicked.
- **"Draft Follow-up" remains available** — but now it's enriched with recap context instead of raw MCP lookup.
- **Dedup stays on `messages` table** — same `user_id:activity_uid` pattern, new `message_type: 'meeting_recap'`.

### Workato Webhook Contract
The Workato side is a separate setup (not in this plan). This plan assumes a Workato webhook URL is configured that accepts:
```json
{
  "action": "create_task" | "log_activity",
  "salesforce_object": "Task" | "Event",
  "record_id": "SF opportunity/account ID (optional)",
  "fields": {
    "Subject": "...",
    "Description": "...",
    "ActivityDate": "2026-03-20",
    "WhoId": "contact SF ID (optional)",
    "WhatId": "opportunity SF ID (optional)",
    "OwnerId": "user SF ID (optional)",
    "Status": "Not Started",
    "Priority": "Normal"
  },
  "context": {
    "user_email": "scott.metcalf@people.ai",
    "account_name": "Abnormal Security",
    "meeting_subject": "Bi-Weekly Sync"
  }
}
```
The Workato webhook URL will be stored as an n8n credential or environment variable. For this plan, we'll use a placeholder `WORKATO_WEBHOOK_URL` that can be configured later.

---

## File Structure

### Modified Workflows
- **Follow-up Cron** (`JhDuCvZdFN4PFTOW`) — Replace `Build Follow-up Prompt` with recap agent flow. Nodes modified/added:
  - `Build Follow-up Prompt` → renamed to `Build Recap Prompt` — now builds a recap agent prompt instead of simple button list
  - New: `Recap Agent` — Claude Sonnet 4.5 + Backstory MCP, generates structured meeting recap
  - New: `Parse Recap Output` — extracts summary, tasks, sentiment from agent JSON output
  - New: `Build Recap Blocks` — constructs Block Kit message with interactive buttons
  - `Send Follow-up Prompt` → renamed to `Send Recap` — sends the recap message
  - `Prepare Log Data` → updated for `message_type: 'meeting_recap'` with recap metadata

- **Interactive Events Handler** (`JgVjCqoT6ZwGuDL1`) — Add new action routes:
  - New route in `Route Action` switch: `recap_create_task` — handles "Create in Salesforce" button
  - New route in `Route Action` switch: `recap_save_activity` — handles "Save Recap to SF" button
  - New route in `Route Action` switch: `recap_draft_followup` — passes enriched context to existing draft flow
  - New: `Build Task Payload` — constructs Workato webhook payload for SF Task creation
  - New: `Send to Workato` — HTTP POST to Workato webhook
  - New: `Update Msg - Task Created` — updates button to show confirmation
  - New: `Build Activity Payload` — constructs Workato webhook payload for SF Activity log
  - New: `Send Activity to Workato` — HTTP POST to Workato webhook
  - New: `Update Msg - Activity Saved` — updates button to show confirmation

### Modified Scripts
- New: `scripts/build_meeting_recap.py` — Python script to push all workflow changes via n8n API

### Supabase
- No schema changes needed. Uses existing `messages` table with `message_type: 'meeting_recap'` and `pending_actions` table for task tracking.

---

## Task 1: Recap Agent — Replace Follow-up Prompt with AI Recap Generation

**What:** Replace the simple "Draft Follow-up?" button prompt with an AI agent that generates a structured meeting recap from Backstory transcript data.

**Files:**
- Modify: Follow-up Cron workflow `JhDuCvZdFN4PFTOW` — nodes: `Build Follow-up Prompt`, add `Recap Agent`, `Anthropic Chat Model (Recap)`, `Backstory MCP (Recap)`, `Parse Recap Output`
- Script: `scripts/build_meeting_recap.py`

**Current state:** `Build Follow-up Prompt` creates a Block Kit message listing meetings with "Draft Follow-up" buttons. No AI processing at the cron level.

**Target state:** For each user's batch of meetings, an AI agent generates a structured recap per meeting, then a Code node builds the Block Kit message with recap content and interactive buttons.

- [ ] **Step 1: Create the script scaffold**

Create `scripts/build_meeting_recap.py` with the n8n API helper imports and workflow fetch:

```python
"""
Meeting Recap + Action Hub
Evolves Follow-up Cron from simple prompt to AI-generated recap with SF actions.
"""
import json
import uuid
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import fetch_workflow, find_node, push_workflow, sync_local

FOLLOWUP_CRON_ID = "JhDuCvZdFN4PFTOW"
INTERACTIVE_ID = "JgVjCqoT6ZwGuDL1"

def build_recap_cron():
    """Modify Follow-up Cron to generate AI recaps instead of simple prompts."""
    wf = fetch_workflow(FOLLOWUP_CRON_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"Fetched Follow-up Cron: {len(nodes)} nodes")
    # ... (steps below fill this in)

if __name__ == "__main__":
    build_recap_cron()
```

- [ ] **Step 2: Rename Build Follow-up Prompt → Build Recap Context**

In the script, rename the existing node and rewrite its code. The new node prepares context for the recap agent — one item per meeting (not consolidated). This is a key change: the current flow consolidates all meetings into one message, but the recap flow needs per-meeting agent calls.

The node should output one item per meeting with:
- All meeting context (account, subject, participants, timestamps)
- User identity (assistant name/emoji/persona, rep name)
- A system prompt for the recap agent
- An agent prompt for the recap agent

System prompt structure:
```
You are {assistantName}, a personal sales assistant for {repName}.

TODAY IS {date}. {repName} is in {timezone}.

MEETING CONTEXT:
- Account: {accountName}
- Subject: {meetingSubject}
- Time: {meetingTime}
- Participants: {participants}

Use Backstory MCP tools to research this meeting:
1. Find the meeting transcript, notes, topics discussed, and action items
2. Look up participant roles and recent engagement
3. Check the related opportunity status if one exists

Generate a structured meeting recap as a JSON object:
{
  "summary": "2-3 sentence recap of what was discussed and key outcomes",
  "sentiment": "positive|neutral|negative|mixed",
  "sentiment_signal": "brief explanation of sentiment read",
  "tasks": [
    {
      "description": "specific action item extracted from the meeting",
      "owner": "person's name who should do this",
      "due_hint": "suggested timeframe (e.g., 'by Friday', 'next week', 'ASAP')"
    }
  ],
  "key_decisions": ["decision 1", "decision 2"],
  "follow_up_context": "brief context to enrich a follow-up email draft"
}

RULES:
- Extract REAL tasks from the meeting — do not fabricate
- If transcript data is limited, note this and provide what you can
- Tasks should be specific and actionable, not vague ("Send pricing proposal to Mark" not "Follow up")
- Sentiment should reflect the tone of the meeting relative to the deal/relationship
- Keep summary under 100 words
- Maximum 5 tasks
- Output ONLY the JSON object, no prose
```

```python
# In build_recap_cron():
node = find_node(nodes, "Build Follow-up Prompt")
node["name"] = "Build Recap Context"
node["parameters"]["jsCode"] = """// Build per-meeting recap context for AI agent
// Output ONE item per meeting (agent processes each individually)
const data = $input.first().json;
const meetings = data.meetings || [];

if (meetings.length === 0) {
  return [{ json: { ...data, skip: true } }];
}

const todayStr = new Date().toLocaleDateString('en-US', {
  weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
});
const tz = data.timezone || 'America/Los_Angeles';
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const assistantPersona = data.assistantPersona || 'direct, action-oriented, and conversational';
const repName = data.repName || 'Rep';

const results = [];

for (const m of meetings) {
  const systemPrompt = `You are ${assistantName}, a personal sales assistant for ${repName}.
Your personality: ${assistantPersona}

TODAY IS ${todayStr}. ${repName} is in ${tz}.

MEETING CONTEXT:
- Account: ${m.accountName}
- Subject: ${m.subject}
- Time: ${m.dayStr} ${m.timeStr}
- Participants: ${m.participants || 'Unknown'}

Use Backstory MCP tools to research this meeting:
1. Find the meeting transcript, notes, topics discussed, and action items
2. Look up participant roles and recent engagement history
3. Check the related opportunity status if one exists
4. Get recent account activity for context

Generate a structured meeting recap as a JSON object with this exact shape:
{
  "summary": "2-3 sentence recap of what was discussed and key outcomes",
  "sentiment": "positive|neutral|negative|mixed",
  "sentiment_signal": "one sentence explaining the sentiment",
  "tasks": [
    {
      "description": "specific action item from the meeting",
      "owner": "person name",
      "due_hint": "timeframe suggestion"
    }
  ],
  "key_decisions": ["decision 1", "decision 2"],
  "follow_up_context": "context to enrich a follow-up email"
}

TOOL CALL BUDGET: You have limited tool calls. After ~8 calls, produce your output.
If a tool returns no data, move on. Do not retry.

RULES:
- Extract REAL tasks mentioned in the meeting — do NOT fabricate
- If transcript data is limited, say so in the summary and provide what you can from account context
- Tasks must be specific and actionable ("Send pricing proposal to Mark by Friday" not "Follow up")
- Maximum 5 tasks
- Keep summary under 100 words
- Output ONLY the JSON object — no prose, no markdown fences`;

  const agentPrompt = `Generate a meeting recap for my ${m.subject} meeting with ${m.accountName}.` +
    (m.participants ? ` Participants: ${m.participants}.` : '') +
    ` Use Backstory MCP tools to find transcript data, topics, and action items.` +
    ` Output ONLY the JSON object.`;

  results.push({
    json: {
      ...data,
      meeting: m,
      accountName: m.accountName,
      meetingSubject: m.subject,
      activityUid: m.activityUid,
      systemPrompt,
      agentPrompt,
      assistantName,
      assistantEmoji,
      repName,
    }
  });
}

return results;"""
```

- [ ] **Step 3: Add Recap Agent nodes**

Add three new nodes: `Recap Agent` (langchain agent), `Anthropic Chat Model (Recap)`, `Backstory MCP (Recap)`. The agent processes one meeting at a time (each item from Build Recap Context).

```python
# Position relative to existing nodes
recap_context = find_node(nodes, "Build Recap Context")
rc_pos = recap_context["position"]

# Anthropic Chat Model for Recap (matches live format: model with __rl wrapper, typeVersion 1.3)
recap_model_id = str(uuid.uuid4())
nodes.append({
    "parameters": {
        "model": {
            "__rl": True,
            "mode": "list",
            "value": "claude-sonnet-4-5-20250929",
            "cachedResultName": "Claude Sonnet 4.5"
        },
        "options": {}
    },
    "id": recap_model_id,
    "name": "Anthropic Chat Model (Recap)",
    "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "typeVersion": 1.3,
    "position": [rc_pos[0] + 400, rc_pos[1] + 150],
    "credentials": {"anthropicApi": {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}}
})

# Backstory MCP for Recap
recap_mcp_id = str(uuid.uuid4())
nodes.append({
    "parameters": {
        "endpointUrl": "https://mcp-canary.people.ai/mcp",
        "authentication": "multipleHeadersAuth"
    },
    "id": recap_mcp_id,
    "name": "Backstory MCP (Recap)",
    "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
    "typeVersion": 1.2,
    "position": [rc_pos[0] + 550, rc_pos[1] + 150],
    "credentials": {"httpMultipleHeadersAuth": {"id": "wvV5pwBeIL7f2vLG", "name": "Backstory MCP Multi-Header"}}
})

# Recap Agent (typeVersion 1.7 to match live agents, continueOnFail: true to not break cron loop)
recap_agent_id = str(uuid.uuid4())
nodes.append({
    "parameters": {
        "options": {
            "systemMessage": "={{ $json.systemPrompt }}",
            "maxIterations": 15
        },
        "text": "={{ $json.agentPrompt }}",
        "promptType": "define"
    },
    "id": recap_agent_id,
    "name": "Recap Agent",
    "type": "@n8n/n8n-nodes-langchain.agent",
    "typeVersion": 1.7,
    "position": [rc_pos[0] + 400, rc_pos[1]],
    "continueOnFail": True
})

# Wire sub-nodes into agent
connections["Anthropic Chat Model (Recap)"] = {
    "ai_languageModel": [[{"node": "Recap Agent", "type": "ai_languageModel", "index": 0}]]
}
connections["Backstory MCP (Recap)"] = {
    "ai_tool": [[{"node": "Recap Agent", "type": "ai_tool", "index": 0}]]
}
```

- [ ] **Step 4: Add Parse Recap Output node**

This Code node parses the agent's JSON output and prepares structured data for the Block Kit builder.

```python
parse_recap_id = str(uuid.uuid4())
nodes.append({
    "parameters": {
        "jsCode": """// Parse recap agent output into structured data
const agentOutput = $('Recap Agent').first().json.output || '';
const context = $('Build Recap Context').first().json;

let recap = {};
try {
  // Try to parse JSON from agent output (may be wrapped in code fences)
  let jsonStr = agentOutput;
  const fenceMatch = jsonStr.match(/```(?:json)?\\s*([\\s\\S]*?)```/);
  if (fenceMatch) jsonStr = fenceMatch[1];
  // Also try to find JSON object in the text
  const objMatch = jsonStr.match(/\\{[\\s\\S]*\\}/);
  if (objMatch) jsonStr = objMatch[0];
  recap = JSON.parse(jsonStr);
} catch(e) {
  recap = {
    summary: agentOutput.substring(0, 500) || 'Meeting recap could not be generated.',
    sentiment: 'neutral',
    sentiment_signal: '',
    tasks: [],
    key_decisions: [],
    follow_up_context: ''
  };
}

const sentimentEmoji = {
  'positive': ':white_check_mark:',
  'neutral': ':large_blue_circle:',
  'negative': ':red_circle:',
  'mixed': ':warning:'
}[recap.sentiment] || ':large_blue_circle:';

return [{ json: {
  ...context,
  recap: {
    summary: recap.summary || '',
    sentiment: recap.sentiment || 'neutral',
    sentimentEmoji,
    sentimentSignal: recap.sentiment_signal || '',
    tasks: (recap.tasks || []).slice(0, 5),
    keyDecisions: recap.key_decisions || [],
    followUpContext: recap.follow_up_context || ''
  }
}}];"""
    },
    "id": parse_recap_id,
    "name": "Parse Recap Output",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [rc_pos[0] + 650, rc_pos[1]]
})
```

- [ ] **Step 5: Add Build Recap Blocks node**

This Code node constructs the Slack Block Kit message with the recap content and interactive buttons.

```python
build_blocks_id = str(uuid.uuid4())
nodes.append({
    "parameters": {
        "jsCode": """// Build Block Kit recap message with interactive buttons
const data = $('Parse Recap Output').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Header
blocks.push({
  type: "header",
  text: { type: "plain_text", text: `:clipboard: Meeting Recap — ${m.accountName}`, emoji: true }
});

// Meeting info + sentiment
const subjectLine = m.subject || 'Customer Meeting';
const sentLine = `${recap.sentimentEmoji} ${recap.sentimentSignal || recap.sentiment}`;
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `*${subjectLine}*  |  ${m.dayStr} ${m.timeStr}\\n${sentLine}` }
});

blocks.push({ type: "divider" });

// Summary
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: recap.summary }
});

// Key decisions (if any)
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `• ${d}`).join('\\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\\n${decisionText}` }
  });
}

// Tasks with individual "Create in SF" buttons
if (recap.tasks && recap.tasks.length > 0) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Action Items*" }
  });

  for (let i = 0; i < recap.tasks.length; i++) {
    const task = recap.tasks[i];
    const taskText = `• ${task.description}` +
      (task.owner ? ` — _${task.owner}_` : '') +
      (task.due_hint ? ` (${task.due_hint})` : '');

    // Slack button value is limited to 2000 chars — keep payloads lean
    const taskPayload = JSON.stringify({
      action: 'create_task',
      task_index: i,
      task_description: task.description,
      task_owner: task.owner || '',
      task_due_hint: task.due_hint || '',
      account_name: m.accountName,
      account_id: m.accountId || '',
      activity_uid: m.activityUid,
      meeting_subject: m.subject,
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      rep_name: data.repName,
      rep_email: data.email || '',
    });

    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: taskText },
      accessory: {
        type: "button",
        text: { type: "plain_text", text: ":salesforce: Create Task", emoji: true },
        action_id: `recap_create_task_${i}`,
        value: taskPayload
      }
    });
  }
}

blocks.push({ type: "divider" });

// Action buttons row
// Truncate follow_up_context to stay under Slack's 2000 char button value limit
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

const savePayload = JSON.stringify({
  action: 'save_activity',
  account_name: m.accountName,
  account_id: m.accountId || '',
  activity_uid: m.activityUid,
  meeting_subject: m.subject,
  summary: recap.summary,
  key_decisions: recap.keyDecisions || [],
  tasks: recap.tasks || [],
  sentiment: recap.sentiment,
  user_id: data.userId,
  slack_user_id: data.slackUserId,
  rep_name: data.repName,
  rep_email: data.email || '',
});

blocks.push({
  type: "actions",
  elements: [
    {
      type: "button",
      text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true },
      style: "primary",
      action_id: "recap_draft_followup",
      value: draftPayload
    },
    {
      type: "button",
      text: { type: "plain_text", text: ":salesforce: Save Recap to SF", emoji: true },
      action_id: "recap_save_activity",
      value: savePayload
    }
  ]
});

// Footer
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "Backstory meeting intelligence • Type `stop followups` to pause" }
  ]
});

const promptText = `Meeting Recap — ${m.accountName}: ${subjectLine}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  activityUids: [m.activityUid],
}}];"""
    },
    "id": build_blocks_id,
    "name": "Build Recap Blocks",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [rc_pos[0] + 900, rc_pos[1]]
})
```

- [ ] **Step 6: Rewire the Follow-up Cron connections**

**Multi-meeting handling:** `Build Recap Context` returns multiple items (one per meeting) from a single user's batch item. In n8n, when a Code node returns N items, all downstream nodes execute N times — once per item. The agent, parser, block builder, and send nodes each process one meeting at a time. The `$('NodeName').first()` references within each execution context correctly refer to that execution's item, not the global first. This means each meeting gets its own recap Slack message, which is the desired UX.

Replace the old chain with the new recap flow. Key changes:
- `Split In Batches` output 1 (loop) → `Build Recap Context` (was `Build Follow-up Prompt`)
- `Build Recap Context` → `Recap Agent`
- `Recap Agent` → `Parse Recap Output`
- `Parse Recap Output` → `Build Recap Blocks`
- `Build Recap Blocks` → `Open Bot DM`
- `Open Bot DM` → `Send Recap` (renamed from `Send Follow-up Prompt`)
- `Send Recap` → `Prepare Log Data`
- `Prepare Log Data` → `Log Follow-up Prompt` → `Split In Batches` (loop back)

```python
# Rename Send Follow-up Prompt
send_node = find_node(nodes, "Send Follow-up Prompt")
send_node["name"] = "Send Recap"
# Update its jsonBody to reference Build Recap Blocks instead of Build Follow-up Prompt
send_node["parameters"]["jsonBody"] = send_node["parameters"]["jsonBody"].replace(
    "Build Follow-up Prompt", "Build Recap Blocks"
)

# Rewire connections
# Remove old: Build Follow-up Prompt → Open Bot DM
# The SplitInBatches output 1 (loop) currently connects to Build Follow-up Prompt
# Find and update that connection
split_conns = connections.get("Split In Batches", {}).get("main", [[], []])
# Output 1 is the loop output - update to point to Build Recap Context
if len(split_conns) > 1:
    split_conns[1] = [{"node": "Build Recap Context", "type": "main", "index": 0}]

# New chain
connections["Build Recap Context"] = {"main": [[{"node": "Recap Agent", "type": "main", "index": 0}]]}
connections["Recap Agent"] = {"main": [[{"node": "Parse Recap Output", "type": "main", "index": 0}]]}
connections["Parse Recap Output"] = {"main": [[{"node": "Build Recap Blocks", "type": "main", "index": 0}]]}
connections["Build Recap Blocks"] = {"main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]}
connections["Open Bot DM"] = {"main": [[{"node": "Send Recap", "type": "main", "index": 0}]]}
connections["Send Recap"] = {"main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]}

# Remove old connection key if it exists
if "Build Follow-up Prompt" in connections:
    del connections["Build Follow-up Prompt"]
if "Send Follow-up Prompt" in connections:
    del connections["Send Follow-up Prompt"]
```

- [ ] **Step 7: Update Prepare Log Data for recap metadata**

```python
log_node = find_node(nodes, "Prepare Log Data")
log_node["parameters"]["jsCode"] = """// Log recap delivery for dedup
const data = $('Build Recap Blocks').first().json;
const sendResult = $('Send Recap').first().json;
const m = data.meeting || {};

return [{ json: {
  user_id: data.userId,
  message_type: 'meeting_recap',
  channel: 'slack',
  direction: 'outbound',
  content: data.promptText || 'Meeting recap',
  metadata: JSON.stringify({
    activity_uid: m.activityUid || data.activityUid,
    account_name: m.accountName || '',
    meeting_subject: m.subject || '',
    slack_ts: sendResult.ts || null,
    slack_channel: sendResult.channel || null,
    recap_sentiment: data.recap ? data.recap.sentiment : null,
    recap_task_count: data.recap ? (data.recap.tasks || []).length : 0,
  }),
}}];"""
```

- [ ] **Step 8: Update dedup check message_type**

The dedup URL is dynamically built in the `Compute Dedup Window` Code node (not hardcoded in `Check Sent Followups`). Update `Compute Dedup Window` to include both old `followup_prompt` and new `meeting_recap` message types:

```python
dedup_node = find_node(nodes, "Compute Dedup Window")
code = dedup_node["parameters"]["jsCode"]
# Replace the single message_type filter with an IN filter
code = code.replace(
    "message_type=eq.followup_prompt",
    "message_type=in.(followup_prompt,meeting_recap)"
)
dedup_node["parameters"]["jsCode"] = code
```

- [ ] **Step 9: Push and sync**

```python
result = push_workflow(FOLLOWUP_CRON_ID, wf)
print(f"Pushed Follow-up Cron: {len(result['nodes'])} nodes")
sync_local(result, "Follow-up Cron.json")
```

- [ ] **Step 10: Test the recap cron manually**

Run the workflow manually in n8n. Verify:
- Build Recap Context outputs one item per meeting with systemPrompt/agentPrompt
- Recap Agent calls Backstory MCP tools and returns JSON
- Parse Recap Output extracts summary, tasks, sentiment
- Build Recap Blocks produces valid Block Kit JSON
- Slack message renders with recap content and buttons

---

## Task 2: Interactive Handler — Recap Action Routes

**What:** Add new action routes to the Interactive Events Handler for recap button interactions: Create SF Task, Save Recap to SF, and Draft Follow-up (enriched).

**Files:**
- Modify: Interactive Events Handler workflow `JgVjCqoT6ZwGuDL1` — `Route Action` switch, new nodes for each action
- Script: `scripts/build_meeting_recap.py` (add `build_interactive_handler()` function)

**Current state:** `Route Action` switch handles: edit_name, edit_emoji, edit_persona, edit_scope, followup_draft, followup_skip, plus silence/mute actions. When `followup_draft` is clicked, it runs the Followup Draft Agent.

**Target state:** Three new routes added:
- `recap_create_task_*` — creates SF Task via Workato webhook
- `recap_save_activity` — logs recap as SF Activity via Workato webhook
- `recap_draft_followup` — enriches existing draft flow with recap context

- [ ] **Step 1: Add recap_create_task route to Route Action switch**

The action_id for task buttons is `recap_create_task_0`, `recap_create_task_1`, etc. Use a "contains" condition to match all of them.

```python
def build_interactive_handler():
    wf = fetch_workflow(INTERACTIVE_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"Fetched Interactive Handler: {len(nodes)} nodes")

    route_node = find_node(nodes, "Route Action")
    rules = route_node["parameters"]["rules"]["values"]

    # Add recap_create_task route (matches recap_create_task_*)
    rules.append({
        "outputKey": "Recap Create Task",
        "renameOutput": True,
        "conditions": {
            "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
            "combinator": "and",
            "conditions": [{
                "id": str(uuid.uuid4()),
                "operator": {"name": "filter.operator.contains", "type": "string", "operation": "contains"},
                "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                "rightValue": "recap_create_task"
            }]
        }
    })

    # Add recap_save_activity route
    rules.append({
        "outputKey": "Recap Save Activity",
        "renameOutput": True,
        "conditions": {
            "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
            "combinator": "and",
            "conditions": [{
                "id": str(uuid.uuid4()),
                "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                "rightValue": "recap_save_activity"
            }]
        }
    })

    # Add recap_draft_followup route
    rules.append({
        "outputKey": "Recap Draft Followup",
        "renameOutput": True,
        "conditions": {
            "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
            "combinator": "and",
            "conditions": [{
                "id": str(uuid.uuid4()),
                "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                "leftValue": "={{ $('Parse Interactive Payload').first().json.actionId }}",
                "rightValue": "recap_draft_followup"
            }]
        }
    })
```

- [ ] **Step 2: Add Build Task Payload node**

```python
    # Position near existing followup nodes
    ref_node = find_node(nodes, "Build Followup Context")
    ref_pos = ref_node["position"]

    build_task_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": """// Build Workato webhook payload for SF Task creation
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const now = new Date();
// Parse due_hint into a date
let dueDate = '';
const hint = (context.task_due_hint || '').toLowerCase();
if (hint.includes('asap') || hint.includes('today')) {
  dueDate = now.toISOString().split('T')[0];
} else if (hint.includes('tomorrow')) {
  const d = new Date(now.getTime() + 86400000);
  dueDate = d.toISOString().split('T')[0];
} else if (hint.includes('friday') || hint.includes('end of week')) {
  const d = new Date(now);
  d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7 || 7));
  dueDate = d.toISOString().split('T')[0];
} else if (hint.includes('next week')) {
  const d = new Date(now.getTime() + 7 * 86400000);
  dueDate = d.toISOString().split('T')[0];
} else {
  // Default: 1 week from now
  const d = new Date(now.getTime() + 7 * 86400000);
  dueDate = d.toISOString().split('T')[0];
}

return [{ json: {
  webhook_payload: {
    action: 'create_task',
    salesforce_object: 'Task',
    fields: {
      Subject: context.task_description || 'Follow-up task',
      Description: 'From meeting: ' + (context.meeting_subject || '') + ' with ' + (context.account_name || '') + '\\nAssigned to: ' + (context.task_owner || 'TBD'),
      ActivityDate: dueDate,
      Status: 'Not Started',
      Priority: 'Normal'
    },
    context: {
      user_email: context.rep_email || '',
      account_name: context.account_name || '',
      meeting_subject: context.meeting_subject || '',
      activity_uid: context.activity_uid || ''
    }
  },
  // Pass through for UI update
  channelId: payload.channelId,
  messageTs: payload.messageTs,
  actionId: payload.actionId,
  task_description: context.task_description || '',
  assistantName: context.assistant_name || 'Aria',
  assistantEmoji: context.assistant_emoji || ':robot_face:',
}}];"""
        },
        "id": build_task_id,
        "name": "Build Task Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [ref_pos[0], ref_pos[1] + 400]
    })
```

- [ ] **Step 3: Add Send Task to Workato node**

```python
    send_task_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "={{ $env.WORKATO_WEBHOOK_URL || 'https://WORKATO_WEBHOOK_PLACEHOLDER' }}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
            "options": {"timeout": 15000}
        },
        "id": send_task_id,
        "name": "Send Task to Workato",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [ref_pos[0] + 250, ref_pos[1] + 400]
    })
```

- [ ] **Step 4: Add Update Msg - Task Created node**

This updates the original recap message to show the task was created (replaces the button with a confirmation).

```python
    update_task_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ channel: $('Build Task Payload').first().json.channelId, thread_ts: $('Build Task Payload').first().json.messageTs, text: ':white_check_mark: Task created in Salesforce: ' + $('Build Task Payload').first().json.task_description, username: $('Build Task Payload').first().json.assistantName, icon_emoji: $('Build Task Payload').first().json.assistantEmoji }) }}",
            "options": {}
        },
        "id": update_task_id,
        "name": "Confirm Task Created",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [ref_pos[0] + 500, ref_pos[1] + 400],
        "credentials": {"httpHeaderAuth": {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}}
    })
```

- [ ] **Step 5: Add Build Activity Payload node**

```python
    build_activity_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": """// Build Workato webhook payload for SF Activity log
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const taskList = (context.tasks || []).map(t =>
  '- ' + t.description + (t.owner ? ' (' + t.owner + ')' : '')
).join('\\n');
const decisionList = (context.key_decisions || []).map(d => '- ' + d).join('\\n');

const description = [
  'Meeting: ' + (context.meeting_subject || ''),
  'Account: ' + (context.account_name || ''),
  '',
  'Summary:',
  context.summary || '',
  '',
  decisionList ? 'Key Decisions:\\n' + decisionList : '',
  '',
  taskList ? 'Action Items:\\n' + taskList : '',
].filter(Boolean).join('\\n');

return [{ json: {
  webhook_payload: {
    action: 'log_activity',
    salesforce_object: 'Event',
    fields: {
      Subject: context.meeting_subject || 'Customer Meeting',
      Description: description,
      ActivityDate: new Date().toISOString().split('T')[0],
    },
    context: {
      user_email: context.rep_email || '',
      account_name: context.account_name || '',
      activity_uid: context.activity_uid || ''
    }
  },
  channelId: payload.channelId,
  messageTs: payload.messageTs,
  assistantName: context.assistant_name || 'Aria',
  assistantEmoji: context.assistant_emoji || ':robot_face:',
}}];"""
        },
        "id": build_activity_id,
        "name": "Build Activity Payload",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [ref_pos[0], ref_pos[1] + 600]
    })
```

- [ ] **Step 6: Add Send Activity to Workato and confirmation nodes**

```python
    send_activity_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "={{ $env.WORKATO_WEBHOOK_URL || 'https://WORKATO_WEBHOOK_PLACEHOLDER' }}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
            "options": {"timeout": 15000}
        },
        "id": send_activity_id,
        "name": "Send Activity to Workato",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [ref_pos[0] + 250, ref_pos[1] + 600]
    })

    confirm_activity_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ channel: $('Build Activity Payload').first().json.channelId, thread_ts: $('Build Activity Payload').first().json.messageTs, text: ':white_check_mark: Meeting recap saved to Salesforce', username: $('Build Activity Payload').first().json.assistantName, icon_emoji: $('Build Activity Payload').first().json.assistantEmoji }) }}",
            "options": {}
        },
        "id": confirm_activity_id,
        "name": "Confirm Activity Saved",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [ref_pos[0] + 500, ref_pos[1] + 600],
        "credentials": {"httpHeaderAuth": {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}}
    })
```

- [ ] **Step 7: Add Recap Draft Followup bridge**

This route passes the recap's `follow_up_context` into the existing Build Followup Context flow, enriching the draft agent's context.

```python
    # Bridge node that reformats recap context into the format Build Followup Context expects
    bridge_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": """// Bridge recap draft request to existing followup flow
// Enriches the existing flow with recap context
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

// Reformat to match what Build Followup Context expects in actionValue
const enrichedValue = JSON.stringify({
  accountName: context.account_name || '',
  accountId: context.account_id || '',
  activityUid: context.activity_uid || '',
  meetingSubject: context.meeting_subject || '',
  participants: context.participants || '',
  userId: context.user_id || '',
  dbUserId: context.db_user_id || context.user_id || '',
  slackUserId: context.slack_user_id || '',
  organizationId: context.organization_id || '',
  assistantName: context.assistant_name || 'Aria',
  assistantEmoji: context.assistant_emoji || ':robot_face:',
  repName: context.rep_name || '',
  recapContext: context.follow_up_context || '',
});

return [{ json: {
  ...payload,
  actionValue: enrichedValue,
  actionId: 'followup_draft',
}}];"""
        },
        "id": bridge_id,
        "name": "Bridge Recap to Draft",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [ref_pos[0], ref_pos[1] + 200]
    })
```

- [ ] **Step 8: Wire all new connections**

```python
    # Get the output index for each new route (they're appended to the end of rules)
    # Route Action outputs map to rules array index
    num_existing_rules = len(rules) - 3  # we added 3 rules
    recap_task_output = num_existing_rules
    recap_activity_output = num_existing_rules + 1
    recap_draft_output = num_existing_rules + 2

    # Wire Route Action new outputs
    route_conns = connections.get("Route Action", {}).get("main", [])
    # Extend to cover new output indices
    while len(route_conns) <= recap_draft_output:
        route_conns.append([])
    route_conns[recap_task_output] = [{"node": "Build Task Payload", "type": "main", "index": 0}]
    route_conns[recap_activity_output] = [{"node": "Build Activity Payload", "type": "main", "index": 0}]
    route_conns[recap_draft_output] = [{"node": "Bridge Recap to Draft", "type": "main", "index": 0}]
    connections["Route Action"]["main"] = route_conns

    # Task flow
    connections["Build Task Payload"] = {"main": [[{"node": "Send Task to Workato", "type": "main", "index": 0}]]}
    connections["Send Task to Workato"] = {"main": [[{"node": "Confirm Task Created", "type": "main", "index": 0}]]}

    # Activity flow
    connections["Build Activity Payload"] = {"main": [[{"node": "Send Activity to Workato", "type": "main", "index": 0}]]}
    connections["Send Activity to Workato"] = {"main": [[{"node": "Confirm Activity Saved", "type": "main", "index": 0}]]}

    # Draft bridge → existing Update Msg - Drafting (which feeds into Build Followup Context)
    connections["Bridge Recap to Draft"] = {"main": [[{"node": "Update Msg - Drafting", "type": "main", "index": 0}]]}
```

- [ ] **Step 9: Enrich Build Followup Context with recap data**

Update the existing `Build Followup Context` to check for `recapContext` in the button payload and inject it into the agent's system prompt.

```python
    followup_ctx = find_node(nodes, "Build Followup Context")
    code = followup_ctx["parameters"]["jsCode"]

    # Add recapContext injection after the existing context parsing
    # Find where the systemPrompt is being built and add recap context
    old_known_context = "## KNOWN MEETING CONTEXT (from Backstory Query API — confirmed data):"
    new_known_context = """## KNOWN MEETING CONTEXT (from Backstory Query API — confirmed data):"""

    # Add after the meeting context section, before CRITICAL: DATA LATENCY PROTOCOL
    old_latency = "## CRITICAL: DATA LATENCY PROTOCOL"
    new_latency = """## MEETING RECAP CONTEXT (from AI-generated recap):
${context.recapContext ? context.recapContext : '[No recap context available — research from scratch]'}

Use this recap context to anchor your follow-up email. The recap was generated from transcript data and is more reliable than generic account context.

## CRITICAL: DATA LATENCY PROTOCOL"""

    code = code.replace(old_latency, new_latency)
    followup_ctx["parameters"]["jsCode"] = code
```

- [ ] **Step 10: Push and sync**

```python
    result = push_workflow(INTERACTIVE_ID, wf)
    print(f"Pushed Interactive Handler: {len(result['nodes'])} nodes")
    sync_local(result, "Interactive Events Handler.json")
```

- [ ] **Step 11: Test interactive buttons**

Manually trigger a recap message, then test each button:
1. "Create Task" → verify Workato webhook receives payload, Slack shows confirmation
2. "Save Recap to SF" → verify Workato webhook receives payload, Slack shows confirmation
3. "Draft Follow-up" → verify existing draft flow works with enriched context

---

## Task 3: Workato Webhook Configuration

**What:** Set up the Workato webhook URL as an n8n environment variable and document the expected webhook contract for the Workato recipe.

**Files:**
- n8n environment variable: `WORKATO_WEBHOOK_URL`
- Document: update `CLAUDE.md` with Workato integration notes

- [ ] **Step 1: Document the Workato webhook contract**

The Workato recipe should accept POST requests with this payload structure and route to the appropriate SF write:

```json
{
  "action": "create_task",
  "salesforce_object": "Task",
  "fields": {
    "Subject": "Send pricing proposal to Mark",
    "Description": "From meeting: Bi-Weekly Sync with Abnormal Security",
    "ActivityDate": "2026-03-21",
    "Status": "Not Started",
    "Priority": "Normal"
  },
  "context": {
    "user_email": "scott.metcalf@people.ai",
    "account_name": "Abnormal Security",
    "meeting_subject": "Bi-Weekly Sync"
  }
}
```

For activity logging:
```json
{
  "action": "log_activity",
  "salesforce_object": "Event",
  "fields": {
    "Subject": "Bi-Weekly Sync",
    "Description": "Meeting recap with summary, decisions, and action items",
    "ActivityDate": "2026-03-19"
  },
  "context": {
    "user_email": "scott.metcalf@people.ai",
    "account_name": "Abnormal Security"
  }
}
```

The `context` block helps Workato resolve SF record IDs (Account, Contact, Opportunity) from names/emails. The Workato recipe handles the SF ID lookup — n8n just sends names and context.

- [ ] **Step 2: Configure n8n environment variable**

Once the Workato recipe is created and provides a webhook URL:
1. In n8n Settings → Environment Variables, add `WORKATO_WEBHOOK_URL`
2. The `Send Task to Workato` and `Send Activity to Workato` nodes reference `$env.WORKATO_WEBHOOK_URL`
3. Until configured, the nodes will POST to the placeholder URL and fail gracefully

- [ ] **Step 3: Update CLAUDE.md with Workato integration**

Add a section documenting the n8n → Workato → Salesforce pattern for future reference.

---

## Execution Order

1. **Task 1** (Recap Agent in Follow-up Cron) — can be tested independently without Workato
2. **Task 2** (Interactive Handler routes) — depends on Task 1 for the recap message format
3. **Task 3** (Workato config) — can be done in parallel, but SF writes won't work until Workato recipe is live

**MVP without Workato:** Tasks 1 and 2 can be deployed immediately. The "Create Task" and "Save Recap" buttons will be visible but the Workato HTTP calls will fail gracefully. The "Draft Follow-up" button works immediately since it uses the existing flow. This lets you validate the recap experience before wiring up Workato.
