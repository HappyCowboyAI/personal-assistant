#!/usr/bin/env python3
"""
Add Meeting Brief feature:
1. Creates a Meeting Brief sub-workflow (Claude agent generates prep brief)
2. Creates a Meeting Prep Cron workflow (polls People.ai every 15 min for upcoming external meetings)
3. Updates help text in Slack Events Handler
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
ANTHROPIC_CRED = {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}
MCP_CRED = {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}
PAI_CLIENT_BODY = "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"


def uid():
    return str(uuid.uuid4())


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wf_id, wf):
    payload = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": wf.get("settings", {}), "staticData": wf.get("staticData")}
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def activate_workflow(wf_id):
    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def get_parse_blocks_code():
    """Fetch Parse Blocks code from the live Sales Digest."""
    wf = fetch_workflow("7sinwSgjkEA40zDj")
    for node in wf["nodes"]:
        if node["name"] == "Parse Blocks":
            return node["parameters"]["jsCode"]
    raise RuntimeError("Parse Blocks node not found in Sales Digest")


# ============================================================
# MEETING BRIEF RESOLVE IDENTITY CODE
# ============================================================
MEETING_RESOLVE_CODE = r"""const input = $('Workflow Input Trigger').first().json;

const assistantName = input.assistant_name || 'Aria';
const assistantEmoji = input.assistant_emoji || ':robot_face:';
const assistantPersona = input.assistant_persona || 'direct, action-oriented, and conversational';
const repName = input.repName || (input.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Rep';
const timezone = input.timezone || 'America/Los_Angeles';

const accountName = input.accountName || 'Unknown Account';
const meetingSubject = input.meetingSubject || 'Customer Meeting';
const meetingTime = input.meetingTime || '';
const participants = input.participants || '';
const opportunityName = input.opportunityName || '';
const opportunityStage = input.opportunityStage || '';
const opportunityAmount = input.opportunityAmount || '';
const opportunityCloseDate = input.opportunityCloseDate || '';
const opportunityEngagement = input.opportunityEngagement || '';
const hasOpportunity = !!(opportunityName && opportunityName !== 'N/A' && opportunityName.trim());

const currentDate = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
const timeStr = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: timezone });
const emojiClean = assistantEmoji.replace(/:/g, '');

// Calculate minutes until meeting
let minutesUntil = '';
if (meetingTime) {
  const meetingMs = parseInt(meetingTime);
  if (!isNaN(meetingMs)) {
    const diffMin = Math.round((meetingMs - Date.now()) / 60000);
    if (diffMin > 0) minutesUntil = diffMin + ' minutes';
    else minutesUntil = 'starting now';
  }
}

// Build context about the opportunity if available
let dealContext = '';
if (hasOpportunity) {
  dealContext = `\n━━━ DEAL CONTEXT ━━━
Opportunity: ${opportunityName}
Stage: ${opportunityStage}
Amount: ${opportunityAmount}
Close Date: ${opportunityCloseDate}
Engagement: ${opportunityEngagement}
`;
}

const blockKitRules = `OUTPUT FORMAT — CRITICAL:
Respond with ONLY a valid JSON object. No prose. No explanation. No markdown code fences (no backticks).

Your response must have exactly this shape:
{
  "notification_text": "string — one sentence, shown in push notifications",
  "blocks": [ array of valid Slack Block Kit blocks ]
}

BLOCK KIT STRUCTURE RULES:
- Use a "header" block for the message title (plain_text only, emoji: true)
- Use "section" blocks with "mrkdwn" text for all body content
- Use "divider" blocks between major sections (maximum 2 per message)
- Use "section" with "fields" for two-column data (engagement scores, metrics)
  - MAXIMUM 10 fields per section block (Slack API hard limit)
- Use "context" block at the bottom for timestamp and data source
- Maximum 50 blocks per message

MRKDWN RULES (inside all text fields):
- Bold: *text* — single asterisks only
- Line break: \\n
- Blank line: \\n\\n
- Bullet points: use the • character on its own line
- NO ## headers — use *bold text* on its own line instead
- NO **double asterisks**
- NO standard markdown links [text](url) — use <https://url|text>
- NO dash bullets (-)

EMOJI STATUS INDICATORS:
🚀 Acceleration / strong momentum
⚠️ Risk pattern detected
💎 Hidden upside opportunity
🔴 Stalled / critical risk
✅ Healthy / on track
📈 Engagement rising
📉 Engagement falling
🤝 Meeting / relationship building`;

const systemPrompt = `You are ${assistantName}, a personal sales assistant for ${repName}. You are preparing them for an upcoming customer meeting.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ MEETING DETAILS ━━━
Subject: ${meetingSubject}
Account: ${accountName}
Time: ${minutesUntil ? 'In ' + minutesUntil : 'Today'}
Participants: ${participants || 'Not available'}
${dealContext}

You have access to People.ai MCP tools. Use them to research:
- The account's engagement history and recent activity (emails, meetings, calls)
- Each participant's role, title, and recent touchpoints
- ${hasOpportunity ? 'Deal progression, engagement trends, and risk signals for this opportunity' : 'Any open opportunities or past deals with this account'}
- Recent account news or changes

Prepare a 90-second meeting prep briefing following this structure:

1. Header — "${emojiClean} Meeting Prep — ${accountName} — ${assistantName}"
2. Account Snapshot (2-3 sentences) — engagement trend, ${hasOpportunity ? 'deal stage, amount, how the deal is progressing' : 'relationship status, any open opportunities or history'}. Use status indicators.
3. People in the Room — for each external participant: who they are, their role, last touchpoint, any signals. If you can't find info, say so briefly.
4. What to Ask About (2-3 items) — specific questions based on recent activity, deal status, or engagement patterns. Make these actionable and conversation-ready.
5. Watch Out For (1-2 items) — risks, sensitivities, or things that could derail the meeting. Missing activity, declining engagement, competitor signals, etc.
${hasOpportunity ? '6. Deal Status — two-column fields: key deal metrics (stage, amount, close date, engagement)' : '6. Account Intel — two-column fields: key account metrics from People.ai'}
7. Context footer — "People.ai meeting intelligence • ${currentDate} • ${timeStr} PT"

Keep it tight — they're reading this before walking into the meeting.

${blockKitRules}`;

const agentPrompt = `Prepare a meeting brief for ${repName} who has a meeting with ${accountName}${minutesUntil ? ' in ' + minutesUntil : ' today'}.

Meeting subject: ${meetingSubject}
Participants: ${participants || 'Unknown — research the account contacts'}

Use the People.ai MCP tools to research:
1. The account "${accountName}" — engagement history, recent activity
2. Each participant listed — role, title, recent touchpoints, engagement
3. ${hasOpportunity ? 'The opportunity "' + opportunityName + '" — deal health, progression, risks' : 'Any open opportunities or past deals with "' + accountName + '"'}
4. Recent emails, meetings, and calls with this account

Then generate the meeting prep briefing as a Block Kit JSON object following the format in your system instructions. Output ONLY the JSON object, nothing else.`;

return [{
  json: {
    userId: input.userId,
    slackUserId: input.slackUserId,
    channelId: input.channelId,
    assistantName,
    assistantEmoji,
    repName,
    accountName,
    systemPrompt,
    agentPrompt
  }
}];
"""


# ============================================================
# MEETING PREP CRON — main orchestration code
# ============================================================
CRON_PARSE_MEETINGS_CODE = r"""// Parse CSV from People.ai activity export into meeting objects
const csvData = $('Fetch Today Meetings').first().json.data;

if (!csvData) {
  return [{ json: { meetings: [], error: 'No meeting data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { meetings: [], meetingCount: 0 } }];
}

function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

const headers = parseCsvLine(lines[0]);
const headerMap = {};
headers.forEach((h, i) => { headerMap[h] = i; });

function getField(row, ...names) {
  for (const name of names) {
    if (headerMap[name] !== undefined && row[headerMap[name]]) {
      return row[headerMap[name]];
    }
  }
  return '';
}

const meetings = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < headers.length) continue;

  const activityUid = getField(row, 'ootb_activity_uid', 'Activity UID');
  const activityType = getField(row, 'ootb_activity_type', 'Activity Type');
  const timestamp = getField(row, 'ootb_activity_timestamp', 'Activity Timestamp');
  const subject = getField(row, 'ootb_activity_subject', 'Activity Subject');
  const participants = getField(row, 'ootb_activity_participants', 'Participants');
  const originator = getField(row, 'ootb_activity_originator', 'Originator');
  const account = getField(row, 'ootb_activity_account', 'Account');
  const opportunity = getField(row, 'ootb_activity_opportunity', 'Opportunity');
  const matchResult = getField(row, 'ootb_activity_match_result', 'Match Result');

  meetings.push({
    activityUid,
    activityType,
    timestamp,
    subject,
    participants,
    originator,
    account,
    opportunity,
    matchResult
  });
}

return [{ json: { meetings, meetingCount: meetings.length } }];
"""

CRON_MATCH_USERS_CODE = r"""// Match meetings to users and filter to upcoming meetings within prep window
const meetings = $('Parse Meetings').first().json.meetings || [];
const users = $('Get Prep Users').all().map(item => item.json);
const sentBriefs = $('Check Sent Briefs').all().map(item => item.json);

// Build set of already-sent briefs: key = "userId:activityUid"
const sentKeys = new Set();
for (const brief of sentBriefs) {
  const meta = brief.metadata || {};
  if (meta.activity_uid && brief.user_id) {
    sentKeys.add(brief.user_id + ':' + meta.activity_uid);
  }
}

const now = Date.now();
const results = [];

for (const user of users) {
  const userEmail = (user.email || '').toLowerCase();
  const prepMinutes = user.meeting_prep_minutes_before || 120;
  const prepWindowMs = prepMinutes * 60 * 1000;
  // Buffer: don't send brief if meeting is < 15 min away (too late)
  const tooLateMs = 15 * 60 * 1000;

  for (const meeting of meetings) {
    // Check if user is a participant
    const participantStr = (meeting.participants || '').toLowerCase();
    const originatorStr = (meeting.originator || '').toLowerCase();

    const isParticipant = participantStr.includes(userEmail) || originatorStr.includes(userEmail);
    if (!isParticipant) continue;

    // Check timing: meeting should be between 15 min and prepMinutes from now
    const meetingTs = parseInt(meeting.timestamp);
    if (isNaN(meetingTs)) continue;

    const timeUntil = meetingTs - now;
    if (timeUntil < tooLateMs || timeUntil > prepWindowMs) continue;

    // Check dedup
    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentKeys.has(dedupKey)) continue;

    // Parse opportunity info if available
    const oppParts = (meeting.opportunity || '').split('|').map(s => s.trim());

    results.push({
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistant_name: user.assistant_name,
      assistant_emoji: user.assistant_emoji,
      assistant_persona: user.assistant_persona,
      timezone: user.timezone || 'America/Los_Angeles',
      repName: (user.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      accountName: meeting.account || 'Unknown Account',
      meetingSubject: meeting.subject || 'Customer Meeting',
      meetingTime: meeting.timestamp,
      participants: meeting.participants || '',
      opportunityName: oppParts[0] || '',
      opportunityStage: '',
      opportunityAmount: '',
      opportunityCloseDate: '',
      opportunityEngagement: '',
      activityUid: meeting.activityUid
    });
  }
}

if (results.length === 0) {
  return [{ json: { matches: [], matchCount: 0, noMatches: true } }];
}

return results.map(r => ({ json: r }));
"""

CRON_BUILD_QUERY_CODE = r"""// Build the People.ai activity export query for today's external meetings
// Uses millisecond epoch timestamps
const tz = 'America/Los_Angeles';
const now = new Date();

// Get today's start and end in the org timezone
// We query from now to now + 3 hours to cover the prep window
const windowStart = now.getTime();
const windowEnd = windowStart + (3 * 60 * 60 * 1000); // 3 hours from now

// But also get meetings that already started today (for first run catchup)
// Start from beginning of today in PT
const todayStr = now.toLocaleDateString('en-US', { timeZone: tz });
const todayStart = new Date(todayStr + ' 00:00:00 GMT-0800').getTime();

// End of today
const todayEnd = todayStart + (24 * 60 * 60 * 1000);

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": windowStart } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": todayEnd } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_type" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_participants" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" },
    { slug: "ootb_activity_match_result" }
  ],
  sort: [
    { attribute: { slug: "ootb_activity_timestamp" }, direction: "asc" }
  ]
};

return [{ json: { query: JSON.stringify(query) } }];
"""

LOG_MEETING_BRIEF_CODE = r"""// Log sent meeting brief to messages table for dedup
const input = $('Split In Batches').first().json;
return [{
  json: {
    user_id: input.userId,
    message_type: 'meeting_prep',
    channel: 'slack',
    direction: 'outbound',
    content: 'Meeting brief for ' + (input.accountName || 'unknown account'),
    metadata: JSON.stringify({
      activity_uid: input.activityUid,
      account_name: input.accountName,
      meeting_subject: input.meetingSubject
    }),
    sent_at: new Date().toISOString()
  }
}];
"""


# ============================================================
# CREATE MEETING BRIEF SUB-WORKFLOW
# ============================================================
def create_meeting_brief_workflow():
    print("\n=== Creating Meeting Brief sub-workflow ===")

    parse_blocks_code = get_parse_blocks_code()

    send_body = """={{ JSON.stringify({ channel: $('Resolve Meeting Identity').first().json.channelId, text: $('Parse Blocks').first().json.notificationText, username: $('Resolve Meeting Identity').first().json.assistantName, icon_emoji: $('Resolve Meeting Identity').first().json.assistantEmoji, blocks: JSON.parse($('Parse Blocks').first().json.blocks), unfurl_links: false, unfurl_media: false }) }}"""

    nodes = [
        # 1. Workflow Input Trigger
        {
            "parameters": {"inputSource": "passthrough"},
            "id": uid(),
            "name": "Workflow Input Trigger",
            "type": "n8n-nodes-base.executeWorkflowTrigger",
            "typeVersion": 1.1,
            "position": [200, 400]
        },
        # 2. Open Bot DM (get channel for this user)
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/conversations.open",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/json"}]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ users: $('Workflow Input Trigger').first().json.slackUserId }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Open Bot DM",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 400],
            "credentials": {"httpHeaderAuth": SLACK_CRED}
        },
        # 3. Set Channel ID
        {
            "parameters": {
                "jsCode": """const input = $('Workflow Input Trigger').first().json;
const dmChannel = $('Open Bot DM').first().json.channel?.id || '';
return [{ json: { ...input, channelId: dmChannel } }];"""
            },
            "id": uid(),
            "name": "Set Channel ID",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [640, 400]
        },
        # 4. Resolve Meeting Identity
        {
            "parameters": {"jsCode": MEETING_RESOLVE_CODE},
            "id": uid(),
            "name": "Resolve Meeting Identity",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 400]
        },
        # 5. Meeting Brief Agent
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $('Resolve Meeting Identity').first().json.agentPrompt }}",
                "options": {
                    "systemMessage": "={{ $('Resolve Meeting Identity').first().json.systemPrompt }}"
                }
            },
            "id": uid(),
            "name": "Meeting Brief Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [1080, 400],
            "continueOnFail": True
        },
        # 6. Anthropic Chat Model (sub-node)
        {
            "parameters": {
                "model": {
                    "__rl": True,
                    "mode": "list",
                    "value": "claude-sonnet-4-5-20250929",
                    "cachedResultName": "Claude Sonnet 4.5"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Anthropic Chat Model",
            "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
            "typeVersion": 1.3,
            "position": [1088, 624],
            "credentials": {"anthropicApi": ANTHROPIC_CRED}
        },
        # 7. People.ai MCP (sub-node)
        {
            "parameters": {
                "endpointUrl": "https://mcp-canary.people.ai/mcp",
                "authentication": "multipleHeadersAuth",
                "options": {}
            },
            "id": uid(),
            "name": "People.ai MCP",
            "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
            "typeVersion": 1.2,
            "position": [1216, 624],
            "credentials": {"httpMultipleHeadersAuth": MCP_CRED}
        },
        # 8. Parse Blocks
        {
            "parameters": {"jsCode": parse_blocks_code},
            "id": uid(),
            "name": "Parse Blocks",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 400]
        },
        # 9. Send Meeting Brief
        {
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
                "jsonBody": send_body,
                "options": {}
            },
            "id": uid(),
            "name": "Send Meeting Brief",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1520, 400],
            "credentials": {"httpHeaderAuth": SLACK_CRED},
            "continueOnFail": True
        }
    ]

    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]},
        "Open Bot DM": {"main": [[{"node": "Set Channel ID", "type": "main", "index": 0}]]},
        "Set Channel ID": {"main": [[{"node": "Resolve Meeting Identity", "type": "main", "index": 0}]]},
        "Resolve Meeting Identity": {"main": [[{"node": "Meeting Brief Agent", "type": "main", "index": 0}]]},
        "Meeting Brief Agent": {"main": [[{"node": "Parse Blocks", "type": "main", "index": 0}]]},
        "Anthropic Chat Model": {"ai_languageModel": [[{"node": "Meeting Brief Agent", "type": "ai_languageModel", "index": 0}]]},
        "People.ai MCP": {"ai_tool": [[{"node": "Meeting Brief Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Blocks": {"main": [[{"node": "Send Meeting Brief", "type": "main", "index": 0}]]}
    }

    workflow = {
        "name": "Meeting Brief",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"}
    }

    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")
    print("  (Sub-workflow — called via Execute Workflow)")

    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Meeting Brief.json")

    return wf_id


# ============================================================
# CREATE MEETING PREP CRON WORKFLOW
# ============================================================
def create_meeting_prep_cron(meeting_brief_wf_id):
    print(f"\n=== Creating Meeting Prep Cron (brief WF: {meeting_brief_wf_id}) ===")

    nodes = [
        # 1. Schedule Trigger — every 15 minutes
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {"field": "minutes", "minutesInterval": 15}
                    ]
                }
            },
            "id": uid(),
            "name": "Every 15 Minutes",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [200, 400]
        },
        # 2. Get Auth Token
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/auth/tokens",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [{"name": "Content-Type", "value": "application/x-www-form-urlencoded"}]
                },
                "sendBody": True,
                "specifyBody": "string",
                "body": PAI_CLIENT_BODY,
                "options": {}
            },
            "id": uid(),
            "name": "Get Auth Token",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 400]
        },
        # 3. Build Query
        {
            "parameters": {"jsCode": CRON_BUILD_QUERY_CODE},
            "id": uid(),
            "name": "Build Query",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [640, 400]
        },
        # 4. Fetch Today Meetings
        {
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ $('Build Query').first().json.query }}",
                "options": {}
            },
            "id": uid(),
            "name": "Fetch Today Meetings",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [860, 400]
        },
        # 5. Parse Meetings
        {
            "parameters": {"jsCode": CRON_PARSE_MEETINGS_CODE},
            "id": uid(),
            "name": "Parse Meetings",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1080, 400]
        },
        # 6. Get Prep Users (Supabase)
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "users",
                "returnAll": True,
                "filters": {
                    "conditions": [
                        {"keyName": "meeting_prep_enabled", "condition": "eq", "keyValue": "true"},
                        {"keyName": "onboarding_state", "condition": "eq", "keyValue": "complete"}
                    ]
                }
            },
            "id": uid(),
            "name": "Get Prep Users",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1080, 620],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # 7. Check Sent Briefs (Supabase — recent meeting_prep messages)
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "messages",
                "returnAll": True,
                "filters": {
                    "conditions": [
                        {"keyName": "message_type", "condition": "eq", "keyValue": "meeting_prep"},
                        {"keyName": "sent_at", "condition": "gt", "keyValue": "={{ new Date(Date.now() - 24*60*60*1000).toISOString() }}"}
                    ]
                }
            },
            "id": uid(),
            "name": "Check Sent Briefs",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1080, 840],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # 8. Match Users to Meetings
        {
            "parameters": {"jsCode": CRON_MATCH_USERS_CODE},
            "id": uid(),
            "name": "Match Users to Meetings",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 400]
        },
        # 9. Has Matches? (If node)
        {
            "parameters": {
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "conditions": [{
                        "id": uid(),
                        "leftValue": "={{ $json.noMatches }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "notTrue"}
                    }],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Has Matches?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1520, 400]
        },
        # 10. Split In Batches
        {
            "parameters": {"batchSize": 1, "options": {}},
            "id": uid(),
            "name": "Split In Batches",
            "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3,
            "position": [1740, 340]
        },
        # 11. Execute Meeting Brief
        {
            "parameters": {
                "workflowId": {"__rl": True, "mode": "id", "value": meeting_brief_wf_id},
                "options": {}
            },
            "id": uid(),
            "name": "Execute Meeting Brief",
            "type": "n8n-nodes-base.executeWorkflow",
            "typeVersion": 1.2,
            "position": [1960, 340]
        },
        # 12. Log Meeting Brief
        {
            "parameters": {"jsCode": LOG_MEETING_BRIEF_CODE},
            "id": uid(),
            "name": "Log Meeting Brief",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2180, 340]
        },
        # 13. Save to Messages (Supabase)
        {
            "parameters": {
                "tableId": "messages",
                "fieldsUi": {
                    "fieldValues": [
                        {"fieldName": "user_id", "fieldValue": "={{ $json.user_id }}"},
                        {"fieldName": "message_type", "fieldValue": "={{ $json.message_type }}"},
                        {"fieldName": "channel", "fieldValue": "={{ $json.channel }}"},
                        {"fieldName": "direction", "fieldValue": "={{ $json.direction }}"},
                        {"fieldName": "content", "fieldValue": "={{ $json.content }}"},
                        {"fieldName": "metadata", "fieldValue": "={{ $json.metadata }}"},
                        {"fieldName": "sent_at", "fieldValue": "={{ $json.sent_at }}"}
                    ]
                }
            },
            "id": uid(),
            "name": "Save to Messages",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [2400, 340],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        }
    ]

    connections = {
        "Every 15 Minutes": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        "Get Auth Token": {"main": [[
            {"node": "Build Query", "type": "main", "index": 0},
            {"node": "Get Prep Users", "type": "main", "index": 0},
            {"node": "Check Sent Briefs", "type": "main", "index": 0}
        ]]},
        "Build Query": {"main": [[{"node": "Fetch Today Meetings", "type": "main", "index": 0}]]},
        "Fetch Today Meetings": {"main": [[{"node": "Parse Meetings", "type": "main", "index": 0}]]},
        "Parse Meetings": {"main": [[{"node": "Match Users to Meetings", "type": "main", "index": 0}]]},
        "Get Prep Users": {"main": [[{"node": "Match Users to Meetings", "type": "main", "index": 0}]]},
        "Check Sent Briefs": {"main": [[{"node": "Match Users to Meetings", "type": "main", "index": 0}]]},
        "Match Users to Meetings": {"main": [[{"node": "Has Matches?", "type": "main", "index": 0}]]},
        "Has Matches?": {"main": [
            [{"node": "Split In Batches", "type": "main", "index": 0}],  # true
            []  # false — do nothing
        ]},
        "Split In Batches": {"main": [
            [{"node": "Execute Meeting Brief", "type": "main", "index": 0}],  # each item
            []  # done
        ]},
        "Execute Meeting Brief": {"main": [[{"node": "Log Meeting Brief", "type": "main", "index": 0}]]},
        "Log Meeting Brief": {"main": [[{"node": "Save to Messages", "type": "main", "index": 0}]]},
        "Save to Messages": {"main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]}
    }

    workflow = {
        "name": "Meeting Prep Cron",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"}
    }

    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")

    # Activate the cron
    print("  Activating cron...")
    activate_workflow(wf_id)
    print("  Activated — running every 15 minutes")

    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Meeting Prep Cron.json")

    return wf_id


# ============================================================
# UPDATE HELP TEXT
# ============================================================
def update_help_text(wf):
    print("\n=== Updating help text ===")
    for node in wf["nodes"]:
        if node["name"] == "Build Help Response":
            old_code = node["parameters"]["jsCode"]
            # Add meeting prep info to help text
            new_code = old_code.replace(
                r"*Automatic*\n\u2022 Morning briefing \u2014 your daily pipeline pulse\n\u2022 Meeting prep 2 hours before customer calls\n\u2022 Alerts when deals need attention",
                r"*Automatic*\n\u2022 Morning briefing \u2014 themed daily pipeline digest (Mon\u2013Fri)\n\u2022 Meeting prep \u2014 auto-delivered ~2hrs before external meetings\n\u2022 Alerts when deals need attention"
            )
            if new_code == old_code:
                # Try alternate existing text
                new_code = old_code.replace(
                    r"\u2022 Meeting prep 2 hours before customer calls",
                    r"\u2022 Meeting prep \u2014 auto-delivered ~2hrs before external meetings"
                )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Build Help Response — meeting prep description")
            return wf
    print("  WARNING: Build Help Response not found")
    return wf


# ============================================================
# MAIN
# ============================================================
def main():
    # Step 1: Create Meeting Brief sub-workflow
    meeting_brief_id = create_meeting_brief_workflow()

    # Step 2: Create Meeting Prep Cron
    cron_id = create_meeting_prep_cron(meeting_brief_id)

    # Step 3: Update help text in Events Handler
    print("\nFetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes")

    events_wf = update_help_text(events_wf)

    print("\n=== Pushing Slack Events Handler ===")
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Slack Events Handler.json")

    print(f"\nDone!")
    print(f"  Meeting Brief workflow: {meeting_brief_id}")
    print(f"  Meeting Prep Cron: {cron_id} (active, every 15 min)")
    print(f"  Flow: Cron polls People.ai → matches meetings to users → fires Meeting Brief sub-workflow")
    print(f"  Dedup: logs to messages table with activity_uid, skips already-sent briefs")


if __name__ == "__main__":
    main()
