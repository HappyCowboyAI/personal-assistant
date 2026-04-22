#!/usr/bin/env python3
"""
Add on-demand `recap` command to the Slack Events Handler workflow.

When a user types "recap redis" in DM, finds most recent meeting with that
account and generates a meeting recap (card + thread).

Modifies: Slack Events Handler (QuQbIaWetunUOFUW)
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.n8n_helpers import (
    fetch_workflow, push_workflow, sync_local, find_node, uid,
    make_code_node, make_slack_http_node, make_switch_condition,
    WF_EVENTS_HANDLER, SLACK_CRED, ANTHROPIC_CRED, MCP_CRED,
    NODE_HTTP_REQUEST, NODE_CODE, NODE_IF, NODE_AGENT,
    NODE_ANTHROPIC_CHAT, NODE_MCP_CLIENT, MODEL_SONNET,
)

CANARY_MCP_URL = "https://mcp-canary.people.ai/mcp"


def modify(nodes, connections):
    changes = 0

    # ── 1. Update Route by State ──────────────────────────────────────
    rbs = find_node(nodes, "Route by State")
    code = rbs["parameters"]["jsCode"]

    # Insert recap routing before the fuzzy Pass 2 block
    # Place it after the follow-up exact match block and before the `more` match
    marker = "  else if (lower.startsWith('more ') || (lower.startsWith('help ') && lower !== 'help')) {"
    recap_route = (
        "  else if (lower === 'recap' || lower.startsWith('recap ')) route = 'cmd_recap';\n"
    )
    if "cmd_recap" not in code:
        code = code.replace(marker, recap_route + marker)
        changes += 1

    # Add fuzzy matching in Pass 2 — after follow-up fuzzy match
    fuzzy_marker = "    else {\n      // --- Pass 3: Meta commands and fallback ---"
    recap_fuzzy = (
        "    else if (/\\b(recap|meeting\\s+recap)\\b/i.test(lower)) route = 'cmd_recap';\n"
    )
    if "recap|meeting" not in code:
        code = code.replace(fuzzy_marker, recap_fuzzy + fuzzy_marker)
        changes += 1

    rbs["parameters"]["jsCode"] = code

    # ── 2. Add Switch output for cmd_recap ────────────────────────────
    sw = find_node(nodes, "Switch Route")
    rules = sw["parameters"]["rules"]["values"]

    # Check if already exists
    has_recap = any(
        r.get("outputKey") == "cmd_recap"
        for r in rules
    )
    if not has_recap:
        new_rule = {
            "outputKey": "cmd_recap",
            "renameOutput": True,
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [make_switch_condition("={{ $json.route }}", "cmd_recap")],
            },
        }
        rules.append(new_rule)
        changes += 1

    recap_output_idx = next(
        i for i, r in enumerate(rules) if r.get("outputKey") == "cmd_recap"
    )

    # ── 3. Update Build Help Response ─────────────────────────────────
    help_node = find_node(nodes, "Build Help Response")
    hcode = help_node["parameters"]["jsCode"]

    # Add recap to skills list
    old_skills = "`brief` · `meet` · `insights` · `presentation` · `bbr` · `stakeholders` · `followup` · `silence`"
    new_skills = "`brief` · `meet` · `recap` · `insights` · `presentation` · `bbr` · `stakeholders` · `followup` · `silence`"
    if "`recap`" not in hcode:
        hcode = hcode.replace(old_skills, new_skills)
        changes += 1

    # Add recap to detailed help
    recap_help = (
        "    'recap': \"*`recap` \\u2014 Meeting Recap*\\n\\n\""
        " +\n      \"Get an instant recap of your most recent meeting with any account.\\n\\n\""
        " +\n      \"*Usage:*\\n\""
        " +\n      \"\\u2022 `recap Redis` \\u2014 recap your last Redis meeting\\n\""
        " +\n      \"\\u2022 `recap AMD` \\u2014 recap your last AMD meeting\\n\\n\""
        " +\n      \"Includes: summary, sentiment, key decisions, action items, and a Draft Follow-up button.\\n\\n\""
        " +\n      \"_Or just ask naturally: \\\"recap my Redis meeting\\\"_\","
    )
    if "'recap':" not in hcode:
        # Insert before 'rename' entry
        hcode = hcode.replace("    'rename':", recap_help + "\n    'rename':")
        changes += 1

    # Add recap aliases
    old_aliases_end = "'meeting prep': 'meet' }"
    new_aliases_end = "'meeting prep': 'meet', 'recaps': 'recap', 'meeting recap': 'recap', 'meeting recaps': 'recap' }"
    if "'recaps': 'recap'" not in hcode:
        hcode = hcode.replace(old_aliases_end, new_aliases_end)
        changes += 1

    # Add recap to the "Available shortcuts" fallback list
    old_avail = "Available shortcuts: `brief` · `meet` · `insights` · `presentation` · `bbr` · `stakeholders` · `followup`"
    new_avail = "Available shortcuts: `brief` · `meet` · `recap` · `insights` · `presentation` · `bbr` · `stakeholders` · `followup`"
    if new_avail not in hcode:
        hcode = hcode.replace(old_avail, new_avail)
        changes += 1

    help_node["parameters"]["jsCode"] = hcode

    # ── 4. Create all new nodes ───────────────────────────────────────
    # Position new nodes below existing ones (y ~6200+)
    base_x = 2672
    base_y = 6200

    # --- Prepare Recap Input ---
    prepare_recap_code = r"""
const data = $('Route by State').first().json;
const text = (data.text || '').trim();

// Strip command keywords to find account name
const accountArg = text
  .replace(/\b(recap|recaps|meeting\s+recap|meeting\s+recaps|my|the|a|for|with|about|on|please)\b/gi, ' ')
  .replace(/\s+/g, ' ')
  .trim();

if (!accountArg) {
  return [{ json: { ...data, hasAccount: false, responseText: 'What account should I recap? Try: `recap Redis` or `recap AMD`' } }];
}

const ur = data.userRecord || {};
const repName = (ur.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Rep';
const assistantPersona = ur.assistant_persona || 'direct, action-oriented, and conversational';

return [{ json: {
  ...data,
  hasAccount: true,
  accountArg,
  repName,
  assistantPersona,
} }];
""".strip()

    prepare_recap = make_code_node("Prepare Recap Input", prepare_recap_code, [base_x, base_y])
    nodes.append(prepare_recap)
    changes += 1

    # --- Recap Has Account? ---
    recap_has_account = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                    "leftValue": "={{ $json.hasAccount }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Recap Has Account?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [base_x + 400, base_y],
    }
    nodes.append(recap_has_account)
    changes += 1

    # --- Send Recap No Account ---
    send_no_account_body = (
        '={{ JSON.stringify({ channel: $json.channelId, '
        'text: $json.assistantEmoji + " " + $json.responseText, '
        'username: $json.assistantName, icon_emoji: $json.assistantEmoji }) }}'
    )
    send_no_account = make_slack_http_node(
        "Recap No Account", "https://slack.com/api/chat.postMessage",
        send_no_account_body, [base_x + 400, base_y + 200]
    )
    nodes.append(send_no_account)
    changes += 1

    # --- Send Recap Generating ---
    send_generating_body = (
        '={{ JSON.stringify({ channel: $json.channelId, '
        'text: $json.assistantEmoji + " Analyzing your meeting with *" + $json.accountArg + "*... give me about 30 seconds.", '
        'username: $json.assistantName, icon_emoji: $json.assistantEmoji }) }}'
    )
    send_generating = make_slack_http_node(
        "Send Recap Generating", "https://slack.com/api/chat.postMessage",
        send_generating_body, [base_x + 800, base_y]
    )
    nodes.append(send_generating)
    changes += 1

    # --- Recap Auth Token ---
    recap_auth = {
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/auth/tokens",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/x-www-form-urlencoded"}]
            },
            "sendBody": True,
            "specifyBody": "string",
            "body": "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials",
            "options": {},
        },
        "id": uid(),
        "name": "Recap Auth Token",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 1200, base_y],
    }
    nodes.append(recap_auth)
    changes += 1

    # --- Recap Build Query ---
    recap_query_code = r"""
// Build Backstory activity export query for meetings in last 7 days
const data = $('Prepare Recap Input').first().json;
const now = Date.now();
const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": sevenDaysAgo } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": now } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account_name" },
    { slug: "ootb_activity_opportunity_name" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_email" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_name" }
  ],
  sort: [{ attribute: { slug: "ootb_activity_timestamp" }, direction: "desc" }]
};

return [{ json: { meetingQuery: JSON.stringify(query) } }];
""".strip()

    recap_build_query = make_code_node("Recap Build Query", recap_query_code, [base_x + 1600, base_y])
    nodes.append(recap_build_query)
    changes += 1

    # --- Recap Fetch Meetings ---
    recap_fetch = {
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Authorization", "value": "=Bearer {{ $('Recap Auth Token').first().json.access_token }}"},
                ],
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.meetingQuery }}",
            "options": {},
        },
        "id": uid(),
        "name": "Recap Fetch Meetings",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 2000, base_y],
    }
    nodes.append(recap_fetch)
    changes += 1

    # --- Recap Parse Meetings ---
    recap_parse_code = r"""
// Parse CSV, find most recent meeting matching the account name
const prepData = $('Prepare Recap Input').first().json;
const accountArg = (prepData.accountArg || '').toLowerCase();
const raw = $('Recap Fetch Meetings').first().json.data || '';

if (!raw || raw.trim().length === 0) {
  return [{ json: { ...prepData, hasMeeting: false, responseText: "I couldn't find any recent meetings with *" + prepData.accountArg + "* in the last 7 days." } }];
}

const lines = raw.split('\n');
if (lines.length < 2) {
  return [{ json: { ...prepData, hasMeeting: false, responseText: "I couldn't find any recent meetings with *" + prepData.accountArg + "* in the last 7 days." } }];
}

// Parse CSV header
const headerLine = lines[0];
const headers = [];
let field = '';
let inQuotes = false;
for (let i = 0; i < headerLine.length; i++) {
  const c = headerLine[i];
  if (c === '"') { inQuotes = !inQuotes; }
  else if (c === ',' && !inQuotes) { headers.push(field.trim()); field = ''; }
  else { field += c; }
}
headers.push(field.trim());

function parseCSVRow(line) {
  const fields = [];
  let f = '';
  let q = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"') {
      if (q && i + 1 < line.length && line[i + 1] === '"') { f += '"'; i++; }
      else { q = !q; }
    } else if (c === ',' && !q) { fields.push(f.trim()); f = ''; }
    else { f += c; }
  }
  fields.push(f.trim());
  return fields;
}

function getVal(row, ...names) {
  for (const name of names) {
    const idx = headers.findIndex(h => h.toLowerCase().includes(name.toLowerCase()));
    if (idx >= 0 && row[idx]) return row[idx];
  }
  return '';
}

function parseList(val) {
  if (!val) return [];
  return val.replace(/^\[/, '').replace(/\]$/, '').trim()
    .split(';').map(s => s.trim()).filter(Boolean);
}

// Find meetings matching account name (case-insensitive partial match)
let bestMatch = null;
let bestTs = 0;

for (let i = 1; i < lines.length; i++) {
  if (!lines[i].trim()) continue;
  const row = parseCSVRow(lines[i]);

  const acctName = getVal(row, 'Account Name', 'Account');
  if (!acctName || !acctName.toLowerCase().includes(accountArg)) continue;

  const tsRaw = getVal(row, 'Activity date', 'date', 'timestamp');
  let tsMs = 0;
  if (tsRaw) {
    const num = Number(tsRaw);
    if (!isNaN(num) && num > 1e12) { tsMs = num; }
    else {
      const parsed = new Date(tsRaw);
      if (!isNaN(parsed.getTime())) tsMs = parsed.getTime();
    }
  }
  if (!tsMs) continue;

  // Most recent meeting wins
  if (tsMs > bestTs) {
    bestTs = tsMs;
    const activityUid = getVal(row, 'Activity') || '';
    const participantEmails = parseList(getVal(row, 'Participants (Email)', 'Participants'));
    const participantNames = parseList(getVal(row, 'Participants (Name)'));
    const dt = new Date(tsMs);
    const dayStr = dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    const timeStr = dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Los_Angeles' });

    bestMatch = {
      activityUid,
      timestamp: tsMs,
      subject: getVal(row, 'Subject'),
      accountName: acctName,
      accountId: '',
      opportunityName: getVal(row, 'Opportunity Name', 'Opportunity'),
      participants: participantNames.length > 0 ? participantNames.join('; ') : participantEmails.join('; '),
      participantEmails,
      participantNames,
      dayStr,
      timeStr,
    };
  }
}

if (!bestMatch) {
  return [{ json: { ...prepData, hasMeeting: false, responseText: "I couldn't find a recent meeting with *" + prepData.accountArg + "* in the last 7 days." } }];
}

return [{ json: { ...prepData, hasMeeting: true, meeting: bestMatch } }];
""".strip()

    recap_parse = make_code_node("Recap Parse Meetings", recap_parse_code, [base_x + 2400, base_y])
    nodes.append(recap_parse)
    changes += 1

    # --- Recap Has Meeting? ---
    recap_has_meeting = {
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "boolean", "operation": "equals"},
                    "leftValue": "={{ $json.hasMeeting }}",
                    "rightValue": True,
                }],
            },
        },
        "id": uid(),
        "name": "Recap Has Meeting?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [base_x + 2800, base_y],
    }
    nodes.append(recap_has_meeting)
    changes += 1

    # --- Recap No Meeting ---
    no_meeting_body = (
        '={{ JSON.stringify({ channel: $json.channelId, '
        'text: $json.assistantEmoji + " " + $json.responseText, '
        'username: $json.assistantName, icon_emoji: $json.assistantEmoji }) }}'
    )
    recap_no_meeting = make_slack_http_node(
        "Recap No Meeting", "https://slack.com/api/chat.postMessage",
        no_meeting_body, [base_x + 2800, base_y + 200]
    )
    nodes.append(recap_no_meeting)
    changes += 1

    # --- Recap Build Context (prepare agent prompt) ---
    recap_context_code = r"""
// Build recap context for the agent
const data = $('Recap Parse Meetings').first().json;
const m = data.meeting;
const repName = data.repName || 'Rep';
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const assistantPersona = data.assistantPersona || 'direct, action-oriented, and conversational';

const todayStr = new Date().toLocaleDateString('en-US', {
  weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
});
const tz = 'America/Los_Angeles';

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

return [{ json: {
  ...data,
  systemPrompt,
  agentPrompt,
  assistantName,
  assistantEmoji,
  repName,
} }];
""".strip()

    recap_context = make_code_node("Recap Build Context", recap_context_code, [base_x + 3200, base_y])
    nodes.append(recap_context)
    changes += 1

    # --- Recap Agent + Anthropic Chat Model + MCP ---
    agent_pos = [base_x + 3600, base_y]
    model_name = "Anthropic Chat Model (Recap OD)"
    mcp_name = "Backstory MCP (Recap OD)"
    agent_name = "Recap Agent OD"

    recap_agent = {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.agentPrompt }}",
            "options": {
                "systemMessage": "={{ $json.systemPrompt }}",
                "maxIterations": 15,
            },
        },
        "id": uid(),
        "name": agent_name,
        "type": NODE_AGENT,
        "typeVersion": 1.7,
        "position": agent_pos,
        "continueOnFail": True,
    }
    nodes.append(recap_agent)
    changes += 1

    recap_model = {
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": MODEL_SONNET, "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "id": uid(),
        "name": model_name,
        "type": NODE_ANTHROPIC_CHAT,
        "typeVersion": 1.3,
        "position": [agent_pos[0] - 50, agent_pos[1] + 200],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }
    nodes.append(recap_model)
    changes += 1

    recap_mcp = {
        "parameters": {
            "endpointUrl": CANARY_MCP_URL,
            "authentication": "multipleHeadersAuth",
            "options": {},
        },
        "id": uid(),
        "name": mcp_name,
        "type": NODE_MCP_CLIENT,
        "typeVersion": 1.2,
        "position": [agent_pos[0] + 150, agent_pos[1] + 200],
        "credentials": {"httpMultipleHeadersAuth": MCP_CRED},
    }
    nodes.append(recap_mcp)
    changes += 1

    # --- Recap Parse Output ---
    recap_parse_output_code = r"""
// Parse recap agent output into structured data
const agentOutput = $('Recap Agent OD').first().json.output || '';
const context = $('Recap Build Context').first().json;

let recap = {};
try {
  let jsonStr = agentOutput;
  const fenceMatch = jsonStr.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenceMatch) jsonStr = fenceMatch[1];
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
}}];
""".strip()

    recap_parse_output = make_code_node("Recap Parse Output OD", recap_parse_output_code, [base_x + 4000, base_y])
    nodes.append(recap_parse_output)
    changes += 1

    # --- Recap Build Card OD ---
    recap_card_code = r"""
// Build compact top-level recap card (summary + action buttons)
const data = $('Recap Parse Output OD').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const genMsg = $('Send Recap Generating').first().json;

const blocks = [];

// Header
blocks.push({
  type: "header",
  text: { type: "plain_text", text: `:clipboard: Meeting Recap \u2014 ${m.accountName}`, emoji: true }
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

blocks.push({ type: "divider" });

// Action buttons — Draft Follow-up
const truncContext = (recap.followUpContext || '').substring(0, 500);
const draftPayload = JSON.stringify({
  action: 'draft_followup',
  account_name: m.accountName,
  account_id: m.accountId || '',
  activity_uid: m.activityUid,
  meeting_subject: m.subject,
  participants: m.participants || '',
  follow_up_context: truncContext,
  user_id: data.dbUserId,
  db_user_id: data.dbUserId,
  slack_user_id: data.userId,
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
      style: "primary",
      action_id: "recap_draft_followup",
      value: draftPayload
    }
  ]
});

// Footer
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "Backstory meeting intelligence \u2022 Type `recap <account>` anytime" }
  ]
});

const promptText = `Meeting Recap \u2014 ${m.accountName}: ${subjectLine}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  generatingTs: genMsg.ts,
  generatingChannel: genMsg.channel,
}}];
""".strip()

    recap_card = make_code_node("Recap Build Card OD", recap_card_code, [base_x + 4400, base_y])
    nodes.append(recap_card)
    changes += 1

    # --- Recap Send Card OD ---
    send_card_body = (
        '={{ JSON.stringify({ channel: $json.channelId, '
        'text: $json.promptText, '
        'blocks: JSON.parse($json.blocks), '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji }) }}'
    )
    recap_send_card = make_slack_http_node(
        "Recap Send Card OD", "https://slack.com/api/chat.postMessage",
        send_card_body, [base_x + 4800, base_y]
    )
    nodes.append(recap_send_card)
    changes += 1

    # --- Recap Build Thread OD ---
    recap_thread_code = r"""
// Build detailed thread reply with decisions + tasks
const data = $('Recap Parse Output OD').first().json;
const recap = data.recap;
const m = data.meeting;
const sendResult = $('Recap Send Card OD').first().json;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Key Decisions
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `\u2022 ${d}`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\n${decisionText}` }
  });
  blocks.push({ type: "divider" });
}

// Action Items with Create Task buttons
if (recap.tasks && recap.tasks.length > 0) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Action Items*" }
  });

  for (let i = 0; i < recap.tasks.length; i++) {
    const task = recap.tasks[i];
    const taskText = `\u2022 ${task.description}` +
      (task.owner ? ` \u2014 _${task.owner}_` : '') +
      (task.due_hint ? ` (${task.due_hint})` : '');

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
      user_id: data.dbUserId,
      slack_user_id: data.userId,
      rep_name: data.repName,
      rep_email: (data.userRecord || {}).email || '',
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

// If no decisions and no tasks
if ((!recap.keyDecisions || recap.keyDecisions.length === 0) &&
    (!recap.tasks || recap.tasks.length === 0)) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "_No key decisions or action items were captured for this meeting._" }
  });
}

// Thread footer
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "Reply in this thread to discuss this meeting" }
  ]
});

return [{ json: {
  threadBlocks: JSON.stringify(blocks),
  threadTs: sendResult.ts,
  channelId: sendResult.channel,
  assistantName,
  assistantEmoji,
  generatingTs: $('Recap Build Card OD').first().json.generatingTs,
  generatingChannel: $('Recap Build Card OD').first().json.generatingChannel,
}}];
""".strip()

    recap_thread = make_code_node("Recap Build Thread OD", recap_thread_code, [base_x + 5200, base_y])
    nodes.append(recap_thread)
    changes += 1

    # --- Recap Send Thread OD ---
    send_thread_body = (
        '={{ JSON.stringify({ channel: $json.channelId, '
        'thread_ts: $json.threadTs, '
        'blocks: JSON.parse($json.threadBlocks), '
        'text: "Meeting details", '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji }) }}'
    )
    recap_send_thread = make_slack_http_node(
        "Recap Send Thread OD", "https://slack.com/api/chat.postMessage",
        send_thread_body, [base_x + 5600, base_y]
    )
    nodes.append(recap_send_thread)
    changes += 1

    # --- Recap Update Generating ---
    update_gen_body = (
        '={{ JSON.stringify({ channel: $json.generatingChannel, '
        'ts: $json.generatingTs, '
        'text: $json.assistantEmoji + " Recap ready \\u2193", '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji }) }}'
    )
    recap_update_gen = make_slack_http_node(
        "Recap Update Generating", "https://slack.com/api/chat.update",
        update_gen_body, [base_x + 6000, base_y]
    )
    nodes.append(recap_update_gen)
    changes += 1

    # --- Recap No Meeting Update Gen ---
    # When no meeting is found, also update the generating message
    # Actually, the "no meeting" path doesn't have a generating message since
    # it goes through the Has Meeting? false branch. But we DO send a generating
    # message before we know if there's a match. So we need to update it on the
    # false path too. Let me handle this differently:
    # The "Send Recap Generating" is sent BEFORE the Has Meeting check.
    # So on false path, we need to update it AND send the no-meeting text.

    # Actually, let me restructure: Send generating AFTER has account check,
    # BEFORE auth token. Then if no meeting found, we update the generating msg.

    # The flow already is: Has Account? -> [true] Send Generating -> Auth -> Query -> Fetch -> Parse -> Has Meeting?
    # On Has Meeting? false, we need to update the generating message.

    recap_no_meeting_update_code = r"""
// No meeting found — update the generating message with the error
const data = $('Recap Parse Meetings').first().json;
const genMsg = $('Send Recap Generating').first().json;

return [{ json: {
  channel: genMsg.channel,
  ts: genMsg.ts,
  text: data.assistantEmoji + ' ' + data.responseText,
  username: data.assistantName,
  icon_emoji: data.assistantEmoji,
} }];
""".strip()

    recap_no_meeting_update = make_code_node(
        "Recap No Meeting Prepare", recap_no_meeting_update_code, [base_x + 2800, base_y + 200]
    )
    # Oops, position conflict with Recap No Meeting. Let me adjust.
    recap_no_meeting_update["position"] = [base_x + 3200, base_y + 300]
    nodes.append(recap_no_meeting_update)
    changes += 1

    # Replace the simple Recap No Meeting with an update to the generating message
    # Remove the previously added simple "Recap No Meeting" and use chat.update instead
    # Actually let's just use the Recap No Meeting Prepare -> HTTP update node
    recap_no_meeting_send = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.update",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={{ JSON.stringify({ channel: $json.channel, ts: $json.ts, text: $json.text }) }}',
            "options": {},
        },
        "id": uid(),
        "name": "Recap No Meeting Send",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 3600, base_y + 300],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(recap_no_meeting_send)
    changes += 1

    # Remove the "Recap No Meeting" node we added earlier - it won't be wired
    # (it's fine to leave it, just won't be connected)

    # ── 5. Wire all connections ───────────────────────────────────────

    # Switch Route -> Prepare Recap Input
    sw_conns = connections.setdefault("Switch Route", {})
    main_outputs = sw_conns.setdefault("main", [])
    # Extend the outputs list to have enough entries
    while len(main_outputs) <= recap_output_idx:
        main_outputs.append([])
    main_outputs[recap_output_idx] = [
        {"node": "Prepare Recap Input", "type": "main", "index": 0}
    ]
    changes += 1

    # Prepare Recap Input -> Recap Has Account?
    connections["Prepare Recap Input"] = {
        "main": [[{"node": "Recap Has Account?", "type": "main", "index": 0}]]
    }

    # Recap Has Account? true (0) -> Send Recap Generating, false (1) -> Recap No Account
    connections["Recap Has Account?"] = {
        "main": [
            [{"node": "Send Recap Generating", "type": "main", "index": 0}],
            [{"node": "Recap No Account", "type": "main", "index": 0}],
        ]
    }

    # Send Recap Generating -> Recap Auth Token
    connections["Send Recap Generating"] = {
        "main": [[{"node": "Recap Auth Token", "type": "main", "index": 0}]]
    }

    # Recap Auth Token -> Recap Build Query
    connections["Recap Auth Token"] = {
        "main": [[{"node": "Recap Build Query", "type": "main", "index": 0}]]
    }

    # Recap Build Query -> Recap Fetch Meetings
    connections["Recap Build Query"] = {
        "main": [[{"node": "Recap Fetch Meetings", "type": "main", "index": 0}]]
    }

    # Recap Fetch Meetings -> Recap Parse Meetings
    connections["Recap Fetch Meetings"] = {
        "main": [[{"node": "Recap Parse Meetings", "type": "main", "index": 0}]]
    }

    # Recap Parse Meetings -> Recap Has Meeting?
    connections["Recap Parse Meetings"] = {
        "main": [[{"node": "Recap Has Meeting?", "type": "main", "index": 0}]]
    }

    # Recap Has Meeting? true (0) -> Recap Build Context, false (1) -> Recap No Meeting Prepare
    connections["Recap Has Meeting?"] = {
        "main": [
            [{"node": "Recap Build Context", "type": "main", "index": 0}],
            [{"node": "Recap No Meeting Prepare", "type": "main", "index": 0}],
        ]
    }

    # Recap No Meeting Prepare -> Recap No Meeting Send
    connections["Recap No Meeting Prepare"] = {
        "main": [[{"node": "Recap No Meeting Send", "type": "main", "index": 0}]]
    }

    # Recap Build Context -> Recap Agent OD
    connections["Recap Build Context"] = {
        "main": [[{"node": agent_name, "type": "main", "index": 0}]]
    }

    # Agent sub-node connections
    connections[model_name] = {
        "ai_languageModel": [[{"node": agent_name, "type": "ai_languageModel", "index": 0}]]
    }
    connections[mcp_name] = {
        "ai_tool": [[{"node": agent_name, "type": "ai_tool", "index": 0}]]
    }

    # Recap Agent OD -> Recap Parse Output OD
    connections[agent_name] = {
        "main": [[{"node": "Recap Parse Output OD", "type": "main", "index": 0}]]
    }

    # Recap Parse Output OD -> Recap Build Card OD
    connections["Recap Parse Output OD"] = {
        "main": [[{"node": "Recap Build Card OD", "type": "main", "index": 0}]]
    }

    # Recap Build Card OD -> Recap Send Card OD
    connections["Recap Build Card OD"] = {
        "main": [[{"node": "Recap Send Card OD", "type": "main", "index": 0}]]
    }

    # Recap Send Card OD -> Recap Build Thread OD
    connections["Recap Send Card OD"] = {
        "main": [[{"node": "Recap Build Thread OD", "type": "main", "index": 0}]]
    }

    # Recap Build Thread OD -> Recap Send Thread OD
    connections["Recap Build Thread OD"] = {
        "main": [[{"node": "Recap Send Thread OD", "type": "main", "index": 0}]]
    }

    # Recap Send Thread OD -> Recap Update Generating
    connections["Recap Send Thread OD"] = {
        "main": [[{"node": "Recap Update Generating", "type": "main", "index": 0}]]
    }

    return changes


def main():
    print("=== Adding on-demand recap command ===\n")

    print("Fetching Slack Events Handler (live)...")
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    print(f"  {len(wf['nodes'])} nodes")

    changes = modify(wf["nodes"], wf.get("connections", {}))
    print(f"\n  {changes} changes made")

    if changes == 0:
        print("\n  No changes needed")
        return

    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Slack Events Handler.json")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
