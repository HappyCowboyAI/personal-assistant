"""
Meeting Recap + Action Hub — Task 1
Evolves Follow-up Cron from simple prompt to AI-generated recap with SF actions.

Modifies the Follow-up Cron workflow (JhDuCvZdFN4PFTOW):
- Renames Build Follow-up Prompt → Build Recap Context (rewritten code)
- Adds Recap Agent + Anthropic Chat Model (Recap) + People.ai MCP (Recap)
- Adds Parse Recap Output Code node
- Adds Build Recap Blocks Code node
- Renames Send Follow-up Prompt → Send Recap
- Rewires all connections
- Updates Prepare Log Data for meeting_recap message_type
- Updates Compute Dedup Window for new message_type
"""
import json
import uuid
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import fetch_workflow, find_node, push_workflow, sync_local

FOLLOWUP_CRON_ID = "JhDuCvZdFN4PFTOW"


def build_recap_cron():
    """Modify Follow-up Cron to generate AI recaps instead of simple prompts."""
    wf = fetch_workflow(FOLLOWUP_CRON_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"Fetched Follow-up Cron: {len(nodes)} nodes")

    # ── Step 2: Rename Build Follow-up Prompt → Build Recap Context ──────
    node = find_node(nodes, "Build Follow-up Prompt")
    if not node:
        print("ERROR: Could not find 'Build Follow-up Prompt' node")
        return
    old_name = node["name"]
    node["name"] = "Build Recap Context"
    node["parameters"]["jsCode"] = r"""// Build per-meeting recap context for AI agent
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

Use People.ai MCP tools to research this meeting:
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
    ` Use People.ai MCP tools to find transcript data, topics, and action items.` +
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
    print(f"  Renamed '{old_name}' → 'Build Recap Context' and rewrote code")

    # ── Step 3: Add Recap Agent nodes ─────────────────────────────────────
    recap_context = find_node(nodes, "Build Recap Context")
    rc_pos = recap_context["position"]

    # Anthropic Chat Model (Recap)
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

    # People.ai MCP (Recap)
    recap_mcp_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "endpointUrl": "https://mcp-canary.people.ai/mcp",
            "authentication": "multipleHeadersAuth"
        },
        "id": recap_mcp_id,
        "name": "People.ai MCP (Recap)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [rc_pos[0] + 550, rc_pos[1] + 150],
        "credentials": {"httpMultipleHeadersAuth": {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}}
    })

    # Recap Agent
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
    connections["People.ai MCP (Recap)"] = {
        "ai_tool": [[{"node": "Recap Agent", "type": "ai_tool", "index": 0}]]
    }
    print("  Added Recap Agent + Anthropic Chat Model (Recap) + People.ai MCP (Recap)")

    # ── Step 4: Add Parse Recap Output node ───────────────────────────────
    parse_recap_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": r"""// Parse recap agent output into structured data
const agentOutput = $('Recap Agent').first().json.output || '';
const context = $('Build Recap Context').first().json;

let recap = {};
try {
  // Try to parse JSON from agent output (may be wrapped in code fences)
  let jsonStr = agentOutput;
  const fenceMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenceMatch) jsonStr = fenceMatch[1];
  // Also try to find JSON object in the text
  const objMatch = jsonStr.match(/\{[\s\S]*\}/);
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
    print("  Added Parse Recap Output")

    # ── Step 5: Add Build Recap Blocks node ───────────────────────────────
    build_blocks_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": r"""// Build Block Kit recap message with interactive buttons
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
  text: { type: "mrkdwn", text: `*${subjectLine}*  |  ${m.dayStr} ${m.timeStr}\n${sentLine}` }
});

blocks.push({ type: "divider" });

// Summary
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: recap.summary }
});

// Key decisions (if any)
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `• ${d}`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\n${decisionText}` }
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
    { type: "mrkdwn", text: "People.ai meeting intelligence • Type `stop followups` to pause" }
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
    print("  Added Build Recap Blocks")

    # ── Step 6: Rewire connections ────────────────────────────────────────
    # Rename Send Follow-up Prompt → Send Recap
    send_node = find_node(nodes, "Send Follow-up Prompt")
    if send_node:
        send_node["name"] = "Send Recap"
        # Update jsonBody references
        if "jsonBody" in send_node.get("parameters", {}):
            send_node["parameters"]["jsonBody"] = send_node["parameters"]["jsonBody"].replace(
                "Build Follow-up Prompt", "Build Recap Blocks"
            )
        print("  Renamed 'Send Follow-up Prompt' → 'Send Recap'")
    else:
        print("  WARNING: Could not find 'Send Follow-up Prompt' node")

    # Update SplitInBatches output 1 → Build Recap Context
    split_conns = connections.get("Split In Batches", {}).get("main", [[], []])
    if len(split_conns) > 1:
        split_conns[1] = [{"node": "Build Recap Context", "type": "main", "index": 0}]

    # New chain: Build Recap Context → Recap Agent → Parse Recap Output → Build Recap Blocks → Open Bot DM → Send Recap → Prepare Log Data
    connections["Build Recap Context"] = {"main": [[{"node": "Recap Agent", "type": "main", "index": 0}]]}
    connections["Recap Agent"] = {"main": [[{"node": "Parse Recap Output", "type": "main", "index": 0}]]}
    connections["Parse Recap Output"] = {"main": [[{"node": "Build Recap Blocks", "type": "main", "index": 0}]]}
    connections["Build Recap Blocks"] = {"main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]}
    connections["Open Bot DM"] = {"main": [[{"node": "Send Recap", "type": "main", "index": 0}]]}
    connections["Send Recap"] = {"main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]}

    # Remove old connection keys
    if "Build Follow-up Prompt" in connections:
        del connections["Build Follow-up Prompt"]
    if "Send Follow-up Prompt" in connections:
        del connections["Send Follow-up Prompt"]
    print("  Rewired all connections")

    # ── Step 7: Update Prepare Log Data ───────────────────────────────────
    log_node = find_node(nodes, "Prepare Log Data")
    if log_node:
        log_node["parameters"]["jsCode"] = r"""// Log recap delivery for dedup
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
        print("  Updated Prepare Log Data for meeting_recap message_type")
    else:
        print("  WARNING: Could not find 'Prepare Log Data' node")

    # ── Step 8: Update Compute Dedup Window ───────────────────────────────
    dedup_node = find_node(nodes, "Compute Dedup Window")
    if dedup_node:
        code = dedup_node["parameters"]["jsCode"]
        if "message_type=eq.followup_prompt" in code:
            code = code.replace(
                "message_type=eq.followup_prompt",
                "message_type=in.(followup_prompt,meeting_recap)"
            )
            dedup_node["parameters"]["jsCode"] = code
            print("  Updated Compute Dedup Window for meeting_recap dedup")
        else:
            print("  WARNING: Could not find 'message_type=eq.followup_prompt' in Compute Dedup Window")
    else:
        print("  WARNING: Could not find 'Compute Dedup Window' node")

    # ── Step 9: Push and sync ─────────────────────────────────────────────
    print(f"\n=== Pushing workflow ({len(nodes)} nodes) ===")
    result = push_workflow(FOLLOWUP_CRON_ID, wf)
    print(f"Pushed Follow-up Cron: {len(result['nodes'])} nodes")
    sync_local(result, "Follow-up Cron.json")
    print("\nDone!")


INTERACTIVE_ID = "JgVjCqoT6ZwGuDL1"


def build_interactive_handler():
    """Add recap action routes to the Interactive Events Handler workflow."""
    wf = fetch_workflow(INTERACTIVE_ID)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"Fetched Interactive Handler: {len(nodes)} nodes")

    # ── Step 1: Add 3 new routes to Route Action switch ───────────────────
    route_node = find_node(nodes, "Route Action")
    if not route_node:
        print("ERROR: Could not find 'Route Action' node")
        return
    rules = route_node["parameters"]["rules"]["values"]

    # recap_create_task route (contains match for recap_create_task_*)
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

    # recap_save_activity route (equals match)
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

    # recap_draft_followup route (equals match)
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
    print("  Added 3 new routes to Route Action: recap_create_task, recap_save_activity, recap_draft_followup")

    # ── Step 2: Add Build Task Payload node ───────────────────────────────
    ref_node = find_node(nodes, "Build Followup Context")
    if not ref_node:
        print("ERROR: Could not find 'Build Followup Context' node")
        return
    ref_pos = ref_node["position"]

    build_task_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": r"""// Build Workato webhook payload for SF Task creation
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
      Description: 'From meeting: ' + (context.meeting_subject || '') + ' with ' + (context.account_name || '') + '\nAssigned to: ' + (context.task_owner || 'TBD'),
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
    print("  Added Build Task Payload")

    # ── Step 3: Add Send Task to Workato node ─────────────────────────────
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
    print("  Added Send Task to Workato")

    # ── Step 4: Add Confirm Task Created node ─────────────────────────────
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
    print("  Added Confirm Task Created")

    # ── Step 5: Add Build Activity Payload node ───────────────────────────
    build_activity_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": r"""// Build Workato webhook payload for SF Activity log
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const taskList = (context.tasks || []).map(t =>
  '- ' + t.description + (t.owner ? ' (' + t.owner + ')' : '')
).join('\n');
const decisionList = (context.key_decisions || []).map(d => '- ' + d).join('\n');

const description = [
  'Meeting: ' + (context.meeting_subject || ''),
  'Account: ' + (context.account_name || ''),
  '',
  'Summary:',
  context.summary || '',
  '',
  decisionList ? 'Key Decisions:\n' + decisionList : '',
  '',
  taskList ? 'Action Items:\n' + taskList : '',
].filter(Boolean).join('\n');

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
    print("  Added Build Activity Payload")

    # ── Step 6: Add Send Activity to Workato node ─────────────────────────
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
    print("  Added Send Activity to Workato")

    # ── Step 7: Add Confirm Activity Saved node ───────────────────────────
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
    print("  Added Confirm Activity Saved")

    # ── Step 8: Add Bridge Recap to Draft node ────────────────────────────
    bridge_id = str(uuid.uuid4())
    nodes.append({
        "parameters": {
            "jsCode": r"""// Bridge recap draft request to existing followup flow
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
    print("  Added Bridge Recap to Draft")

    # ── Step 9: Wire all new connections ───────────────────────────────────
    # Get the output index for each new route
    num_existing_rules = len(rules) - 3  # we added 3 rules
    recap_task_output = num_existing_rules
    recap_activity_output = num_existing_rules + 1
    recap_draft_output = num_existing_rules + 2

    # Wire Route Action new outputs
    route_conns = connections.get("Route Action", {}).get("main", [])
    while len(route_conns) <= recap_draft_output:
        route_conns.append([])
    route_conns[recap_task_output] = [{"node": "Build Task Payload", "type": "main", "index": 0}]
    route_conns[recap_activity_output] = [{"node": "Build Activity Payload", "type": "main", "index": 0}]
    route_conns[recap_draft_output] = [{"node": "Bridge Recap to Draft", "type": "main", "index": 0}]
    connections["Route Action"]["main"] = route_conns

    # Task flow chain
    connections["Build Task Payload"] = {"main": [[{"node": "Send Task to Workato", "type": "main", "index": 0}]]}
    connections["Send Task to Workato"] = {"main": [[{"node": "Confirm Task Created", "type": "main", "index": 0}]]}

    # Activity flow chain
    connections["Build Activity Payload"] = {"main": [[{"node": "Send Activity to Workato", "type": "main", "index": 0}]]}
    connections["Send Activity to Workato"] = {"main": [[{"node": "Confirm Activity Saved", "type": "main", "index": 0}]]}

    # Draft bridge → existing Update Msg - Drafting (which feeds into Build Followup Context)
    connections["Bridge Recap to Draft"] = {"main": [[{"node": "Update Msg - Drafting", "type": "main", "index": 0}]]}
    print("  Wired all new connections")

    # ── Step 10: Enrich Build Followup Context with recap data ────────────
    followup_ctx = find_node(nodes, "Build Followup Context")
    if followup_ctx:
        code = followup_ctx["parameters"]["jsCode"]
        old_latency = "## CRITICAL: DATA LATENCY PROTOCOL"
        new_latency = r"""## MEETING RECAP CONTEXT (from AI-generated recap):
${context.recapContext ? context.recapContext : '[No recap context available — research from scratch]'}

Use this recap context to anchor your follow-up email. The recap was generated from transcript data and is more reliable than generic account context.

## CRITICAL: DATA LATENCY PROTOCOL"""
        if old_latency in code:
            code = code.replace(old_latency, new_latency)
            followup_ctx["parameters"]["jsCode"] = code
            print("  Enriched Build Followup Context with recapContext injection")
        else:
            print("  WARNING: Could not find DATA LATENCY PROTOCOL section in Build Followup Context")
    else:
        print("  WARNING: Could not find 'Build Followup Context' node")

    # ── Step 11: Push and sync ────────────────────────────────────────────
    print(f"\n=== Pushing workflow ({len(nodes)} nodes) ===")
    result = push_workflow(INTERACTIVE_ID, wf)
    print(f"Pushed Interactive Handler: {len(result['nodes'])} nodes")
    sync_local(result, "Interactive Events Handler.json")
    print("\nDone!")


if __name__ == "__main__":
    build_recap_cron()
    build_interactive_handler()
