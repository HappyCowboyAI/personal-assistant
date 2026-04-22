#!/usr/bin/env python3
"""
Create the Follow-up Cron workflow.

Polls every 15 minutes for recently ended customer meetings. For each
user whose meeting ended ~30 minutes ago, sends a Slack DM with
interactive buttons: [Draft Follow-up] [Skip].

When "Draft Follow-up" is clicked, the Interactive Events Handler
triggers the follow-up agent to draft an email.

Modeled after the Meeting Prep Cron pattern:
1. Fetch today's meetings from Backstory
2. Match meetings that ended within the follow-up window
3. Dedup against already-offered follow-ups
4. Send interactive prompt via Slack

The follow-up delay is configurable per user (default 30 min) via
users.followup_delay_minutes column (migration 007).
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SUPABASE_URL = "https://rhrlnkbphxntxxxcrgvv.supabase.co"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

# Credential references
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}

# Backstory client credentials (same as Meeting Prep Cron)
PEOPLEAI_CLIENT_ID = "YOUR_CLIENT_ID"
PEOPLEAI_CLIENT_SECRET = "YOUR_CLIENT_SECRET"


def uid():
    return str(uuid.uuid4())


# ── Build Query code (construct Backstory export for today's meetings) ──

BUILD_QUERY_CODE = r"""// Build Backstory export query for today's external meetings
// Same pattern as Meeting Prep Cron, but we look for meetings that already happened
const now = Date.now();
const startOfDay = new Date();
startOfDay.setHours(0, 0, 0, 0);
const endOfDay = new Date();
endOfDay.setHours(23, 59, 59, 999);

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": startOfDay.getTime() } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": now } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account_name" },
    { slug: "ootb_activity_account_id" },
    { slug: "ootb_activity_opportunity_name" },
    { slug: "ootb_activity_participants" }
  ],
  sort: [{ attribute: { slug: "ootb_activity_timestamp" }, direction: "desc" }]
};

return [{ json: { query: JSON.stringify(query) } }];
"""


# ── Parse Meetings code ──

PARSE_MEETINGS_CODE = r"""// Parse CSV response from Backstory meetings export
const raw = $('Fetch Today Meetings').first().json.data || '';
if (!raw || raw.trim().length === 0) {
  return [{ json: { meetings: [], meetingCount: 0 } }];
}

const lines = raw.split('\n');
if (lines.length < 2) {
  return [{ json: { meetings: [], meetingCount: 0 } }];
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

// Parse CSV rows
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

function getVal(row, name) {
  const idx = headers.findIndex(h => h.toLowerCase().includes(name.toLowerCase()));
  return idx >= 0 ? (row[idx] || '') : '';
}

const meetings = [];
for (let i = 1; i < lines.length; i++) {
  if (!lines[i].trim()) continue;
  const row = parseCSVRow(lines[i]);

  const tsRaw = getVal(row, 'timestamp');
  let tsMs = 0;
  if (tsRaw) {
    // Could be ISO string or epoch ms
    const num = Number(tsRaw);
    if (!isNaN(num) && num > 1e12) { tsMs = num; }
    else { tsMs = new Date(tsRaw).getTime(); }
  }
  if (!tsMs || isNaN(tsMs)) continue;

  meetings.push({
    activityUid: getVal(row, 'uid') || getVal(row, 'activity_uid'),
    timestamp: tsMs,
    subject: getVal(row, 'subject'),
    originator: getVal(row, 'originator'),
    accountName: getVal(row, 'account_name') || getVal(row, 'account'),
    accountId: getVal(row, 'account_id'),
    opportunityName: getVal(row, 'opportunity_name') || getVal(row, 'opportunity'),
    participants: getVal(row, 'participants'),
  });
}

return [{ json: { meetings, meetingCount: meetings.length, headers } }];
"""


# ── Match Users to Ended Meetings code ──

MATCH_CODE = r"""// Match users to meetings that ended within their follow-up window
const meetings = $('Parse Meetings').first().json.meetings || [];
const usersAll = $('Get Followup Users').all().map(i => i.json);
const sentAll = $('Check Sent Followups').all().map(i => i.json);

// Filter valid users
const users = usersAll.filter(u => u && u.id && u.onboarding_state === 'complete');

// Build dedup set: userId:activityUid
const sentSet = new Set();
for (const msg of sentAll) {
  if (msg && msg.metadata) {
    try {
      const meta = typeof msg.metadata === 'string' ? JSON.parse(msg.metadata) : msg.metadata;
      if (meta.activity_uid && msg.user_id) {
        sentSet.add(msg.user_id + ':' + meta.activity_uid);
      }
    } catch(e) {}
  }
}

const now = Date.now();
const output = [];

// Assume meetings last ~60 minutes
const MEETING_DURATION_MS = 60 * 60 * 1000;

for (const user of users) {
  const delayMs = (user.followup_delay_minutes || 30) * 60 * 1000;
  const followupEnabled = user.followup_enabled !== false;
  if (!followupEnabled) continue;

  // Derive rep name from email
  const repName = user.email
    ? user.email.split('@')[0].split('.').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
    : 'there';

  for (const meeting of meetings) {
    // Estimated end time = meeting start + 60 min
    const estimatedEnd = meeting.timestamp + MEETING_DURATION_MS;
    const timeSinceEnd = now - estimatedEnd;

    // Follow-up window: delay ± 15 min
    // e.g., 30 min delay → send between 15 and 45 min after meeting ends
    const windowStart = delayMs - 15 * 60 * 1000;
    const windowEnd = delayMs + 15 * 60 * 1000;

    if (timeSinceEnd < windowStart || timeSinceEnd > windowEnd) continue;

    // Skip if already sent
    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentSet.has(dedupKey)) continue;

    // Skip meetings without account context
    if (!meeting.accountName) continue;

    output.push({
      json: {
        userId: user.id,
        slackUserId: user.slack_user_id,
        email: user.email,
        repName,
        assistantName: user.assistant_name || 'Aria',
        assistantEmoji: user.assistant_emoji || ':robot_face:',
        organizationId: user.organization_id,
        meetingSubject: meeting.subject,
        accountName: meeting.accountName,
        accountId: meeting.accountId,
        opportunityName: meeting.opportunityName,
        participants: meeting.participants,
        activityUid: meeting.activityUid,
        meetingTimestamp: meeting.timestamp,
        minutesSinceEnd: Math.round(timeSinceEnd / 60000),
      }
    });
  }
}

if (output.length === 0) {
  return [{ json: { noMatches: true } }];
}

return output;
"""


# ── Build Follow-up Prompt code (for interactive message) ──

BUILD_PROMPT_CODE = r"""const data = $input.first().json;

const timeAgo = data.minutesSinceEnd < 60
  ? `${data.minutesSinceEnd} minutes ago`
  : `${Math.round(data.minutesSinceEnd / 60)} hours ago`;

const text = `You met with *${data.accountName}* ${timeAgo}` +
  (data.meetingSubject ? ` — _${data.meetingSubject}_` : '') +
  `\n\nWant me to draft a follow-up?`;

// Interactive blocks with buttons
const blocks = [
  {
    type: "section",
    text: { type: "mrkdwn", text: text }
  },
  {
    type: "actions",
    elements: [
      {
        type: "button",
        text: { type: "plain_text", text: ":email:  Draft Follow-up", emoji: true },
        style: "primary",
        action_id: "followup_draft",
        value: JSON.stringify({
          accountName: data.accountName,
          accountId: data.accountId,
          activityUid: data.activityUid,
          meetingSubject: data.meetingSubject,
          participants: data.participants,
          userId: data.userId,
          dbUserId: data.userId,
          slackUserId: data.slackUserId,
          organizationId: data.organizationId,
          assistantName: data.assistantName,
          assistantEmoji: data.assistantEmoji,
          repName: data.repName,
        })
      },
      {
        type: "button",
        text: { type: "plain_text", text: "Skip", emoji: true },
        action_id: "followup_skip",
        value: JSON.stringify({ activityUid: data.activityUid })
      }
    ]
  }
];

return [{
  json: {
    ...data,
    promptText: text,
    blocks: JSON.stringify(blocks)
  }
}];
"""


# ── Log Follow-up Prompt code ──

LOG_PROMPT_CODE = r"""const data = $('Build Follow-up Prompt').first().json;
const sendResult = $('Send Follow-up Prompt').first().json;

return [{
  json: {
    user_id: data.userId,
    message_type: 'followup_prompt',
    channel: 'slack',
    direction: 'outbound',
    content: data.promptText,
    metadata: JSON.stringify({
      activity_uid: data.activityUid,
      account_name: data.accountName,
      meeting_subject: data.meetingSubject,
      slack_ts: sendResult.ts || null,
      slack_channel: sendResult.channel || null
    }),
  }
}];
"""


def build_workflow():
    nodes = []
    connections = {}

    # ── 1. Schedule Trigger ───────────────────────────────────────────
    nodes.append({
        "parameters": {
            "rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]},
        },
        "id": uid(),
        "name": "Every 15 Minutes",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1.2,
        "position": [250, 300],
    })

    # ── 2. Get Auth Token ─────────────────────────────────────────────
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/auth/tokens",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/x-www-form-urlencoded"}
                ]
            },
            "sendBody": True,
            "specifyBody": "string",
            "body": f"client_id={PEOPLEAI_CLIENT_ID}&client_secret={PEOPLEAI_CLIENT_SECRET}&grant_type=client_credentials",
            "options": {},
        },
        "id": uid(),
        "name": "Get Auth Token",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [500, 300],
    })
    connections["Every 15 Minutes"] = {
        "main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]
    }

    # ── 3. Build Query ────────────────────────────────────────────────
    nodes.append({
        "parameters": {"jsCode": BUILD_QUERY_CODE},
        "id": uid(),
        "name": "Build Query",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [750, 300],
    })
    connections["Get Auth Token"] = {
        "main": [[{"node": "Build Query", "type": "main", "index": 0}]]
    }

    # ── 4. Fetch Today Meetings ───────────────────────────────────────
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.query }}",
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Today Meetings",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1000, 300],
        "continueOnFail": True,
    })
    connections["Build Query"] = {
        "main": [[{"node": "Fetch Today Meetings", "type": "main", "index": 0}]]
    }

    # ── 5. Parse Meetings ─────────────────────────────────────────────
    nodes.append({
        "parameters": {"jsCode": PARSE_MEETINGS_CODE},
        "id": uid(),
        "name": "Parse Meetings",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1250, 300],
    })
    connections["Fetch Today Meetings"] = {
        "main": [[{"node": "Parse Meetings", "type": "main", "index": 0}]]
    }

    # ── 6. Get Followup Users ─────────────────────────────────────────
    nodes.append({
        "parameters": {
            "method": "GET",
            "url": f"{SUPABASE_URL}/rest/v1/users?onboarding_state=eq.complete&select=id,slack_user_id,email,assistant_name,assistant_emoji,organization_id,onboarding_state,followup_delay_minutes,followup_enabled",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": uid(),
        "name": "Get Followup Users",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1500, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    })
    connections["Parse Meetings"] = {
        "main": [[{"node": "Get Followup Users", "type": "main", "index": 0}]]
    }

    # ── 7. Check Sent Followups ───────────────────────────────────────
    nodes.append({
        "parameters": {
            "method": "GET",
            "url": f"{SUPABASE_URL}/rest/v1/messages?message_type=eq.followup_prompt&sent_at=gte.{{ new Date(new Date().setHours(0,0,0,0)).toISOString() }}&select=user_id,metadata",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "options": {},
        },
        "id": uid(),
        "name": "Check Sent Followups",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1750, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
        "alwaysOutputData": True,
    })
    connections["Get Followup Users"] = {
        "main": [[{"node": "Check Sent Followups", "type": "main", "index": 0}]]
    }

    # ── 8. Match Users to Ended Meetings ──────────────────────────────
    nodes.append({
        "parameters": {"jsCode": MATCH_CODE},
        "id": uid(),
        "name": "Match Users to Ended Meetings",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2000, 300],
    })
    connections["Check Sent Followups"] = {
        "main": [[{"node": "Match Users to Ended Meetings", "type": "main", "index": 0}]]
    }

    # ── 9. Has Matches? ──────────────────────────────────────────────
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.noMatches }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "notEquals"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Has Matches?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2250, 300],
    })
    connections["Match Users to Ended Meetings"] = {
        "main": [[{"node": "Has Matches?", "type": "main", "index": 0}]]
    }

    # ── 10. Split In Batches ──────────────────────────────────────────
    nodes.append({
        "parameters": {"options": {}},
        "id": uid(),
        "name": "Split In Batches",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [2500, 300],
    })

    # ── 11. Build Follow-up Prompt ────────────────────────────────────
    nodes.append({
        "parameters": {"jsCode": BUILD_PROMPT_CODE},
        "id": uid(),
        "name": "Build Follow-up Prompt",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2750, 300],
    })

    # ── 12. Open Bot DM ──────────────────────────────────────────────
    nodes.append({
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
            "jsonBody": '={{ JSON.stringify({ users: $json.slackUserId }) }}',
            "options": {},
        },
        "id": uid(),
        "name": "Open Bot DM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3000, 300],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ── 13. Send Follow-up Prompt ─────────────────────────────────────
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
            "jsonBody": '={{ JSON.stringify({ channel: $json.channel.id, text: $("Build Follow-up Prompt").first().json.promptText, blocks: JSON.parse($("Build Follow-up Prompt").first().json.blocks), username: $("Build Follow-up Prompt").first().json.assistantName, icon_emoji: $("Build Follow-up Prompt").first().json.assistantEmoji }) }}',
            "options": {},
        },
        "id": uid(),
        "name": "Send Follow-up Prompt",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3250, 300],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ── 14. Prepare Log Data ──────────────────────────────────────────
    nodes.append({
        "parameters": {"jsCode": LOG_PROMPT_CODE},
        "id": uid(),
        "name": "Prepare Log Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3500, 300],
    })

    # ── 15. Log Follow-up Prompt ──────────────────────────────────────
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": f"{SUPABASE_URL}/rest/v1/messages",
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
            "jsonBody": '={{ JSON.stringify($json) }}',
            "options": {},
        },
        "id": uid(),
        "name": "Log Follow-up Prompt",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3750, 300],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    })

    # ── Wire connections ──────────────────────────────────────────────

    # Has Matches? true (output 0) → Split In Batches
    # Has Matches? false (output 1) → nothing (end)
    connections["Has Matches?"] = {
        "main": [
            [{"node": "Split In Batches", "type": "main", "index": 0}],
            [],
        ]
    }

    # Split output 1 (loop) → Build Follow-up Prompt
    connections["Split In Batches"] = {
        "main": [
            [],  # output 0 = done
            [{"node": "Build Follow-up Prompt", "type": "main", "index": 0}],
        ]
    }

    connections["Build Follow-up Prompt"] = {
        "main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]
    }
    connections["Open Bot DM"] = {
        "main": [[{"node": "Send Follow-up Prompt", "type": "main", "index": 0}]]
    }
    connections["Send Follow-up Prompt"] = {
        "main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]
    }
    connections["Prepare Log Data"] = {
        "main": [[{"node": "Log Follow-up Prompt", "type": "main", "index": 0}]]
    }
    connections["Log Follow-up Prompt"] = {
        "main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]
    }

    return {
        "name": "Follow-up Cron",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


def main():
    print("Building Follow-up Cron workflow...")
    workflow = build_workflow()
    print(f"  {len(workflow['nodes'])} nodes")

    # Check for existing
    print("\nChecking for existing workflow...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS)
    resp.raise_for_status()
    existing_wf = None
    for wf in resp.json().get("data", []):
        if wf["name"] == "Follow-up Cron":
            existing_wf = wf
            break

    if existing_wf:
        wf_id = existing_wf["id"]
        print(f"  Found existing: {wf_id}, updating...")
        payload = {
            "name": workflow["name"],
            "nodes": workflow["nodes"],
            "connections": workflow["connections"],
            "settings": workflow["settings"],
            "staticData": workflow["staticData"],
        }
        resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS, json=payload)
        resp.raise_for_status()
    else:
        print("  Creating new workflow...")
        resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
        resp.raise_for_status()
        wf_id = resp.json()["id"]
        print(f"  Created: {wf_id}")

    # Activate
    print("\nActivating...")
    requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS).raise_for_status()
    print("  Active")

    # Sync local
    print("\nSyncing local file...")
    final = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS).json()
    path = os.path.join(REPO_ROOT, "n8n", "workflows", "Follow-up Cron.json")
    with open(path, "w") as f:
        json.dump(final, f, indent=4)
    print(f"  Synced to {path}")

    print(f"\nDone! Follow-up Cron workflow created.")
    print(f"  Workflow ID: {wf_id}")
    print(f"  Schedule: Every 15 minutes")
    print(f"  Nodes: {len(final['nodes'])}")
    print(f"  Default delay: 30 min after meeting end")
    print(f"\n  IMPORTANT: Run 007_followup_config.sql migration in Supabase!")
    print(f"  IMPORTANT: Add followup_draft/followup_skip button handling to Interactive Events Handler!")


if __name__ == "__main__":
    main()
