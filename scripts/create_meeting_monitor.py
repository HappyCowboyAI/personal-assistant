"""
Create: Meeting Data Monitor workflow.

Polls Backstory every 30 min (5am-8pm PT weekdays) for today's meetings
involving Scott Metcalf and Shreyas Gore. Reports what data is available
for each meeting so we can observe ingestion latency.

Usage:
    N8N_API_KEY=... python scripts/create_meeting_monitor.py
"""

import json
from n8n_helpers import (
    uid, fetch_workflow, push_workflow, sync_local,
    SLACK_CRED, HEADERS, N8N_BASE_URL,
)
import requests

WF_NAME = "Meeting Data Monitor"
SCOTT_EMAIL = "scott.metcalf@people.ai"
SHREYAS_EMAIL = "shreyas.gore@people.ai"
SCOTT_SLACK_ID = "U061WJ6RMJS"

# ── Node definitions ──

schedule_trigger = {
    "parameters": {
        "rule": {
            "interval": [
                {
                    "field": "cronExpression",
                    "expression": "*/30 5-20 * * 1-5"  # Every 30 min, 5am-8pm, Mon-Fri
                }
            ]
        }
    },
    "id": uid(),
    "name": "Every 30 Min (Weekdays 5am-8pm)",
    "type": "n8n-nodes-base.scheduleTrigger",
    "typeVersion": 1.2,
    "position": [0, 0],
}

get_auth_token = {
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
        "contentType": "raw",
        "rawContentType": "application/x-www-form-urlencoded",
        "body": "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials",
        "options": {},
    },
    "id": uid(),
    "name": "Get Auth Token",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [220, 0],
}

build_query = {
    "parameters": {
        "jsCode": """// Build Backstory activity export query for today's meetings
const tz = 'America/Los_Angeles';
const now = new Date();

// Start of today in PT
const todayStr = now.toLocaleDateString('en-US', { timeZone: tz });
const parts = todayStr.split('/');
const todayMidnight = new Date(parts[2] + '-' + parts[0].padStart(2, '0') + '-' + parts[1].padStart(2, '0') + 'T00:00:00-08:00');
const tomorrowMidnight = new Date(todayMidnight.getTime() + 24 * 3600000);

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": todayMidnight.getTime() } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": tomorrowMidnight.getTime() } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_created_at" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_email" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_name" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_external" },
    { slug: "ootb_activity_duration" },
    { slug: "ootb_activity_sentiment" },
    { slug: "ootb_activity_action_items" },
    { slug: "ootb_activity_key_topics" },
    { slug: "ootb_activity_summary" },
    { slug: "ootb_activity_transcript_status" },
  ],
  sort: [
    { attribute: { slug: "ootb_activity_timestamp" }, direction: "asc" }
  ]
};

return [{ json: { query: JSON.stringify(query) } }];
"""
    },
    "id": uid(),
    "name": "Build Query",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [440, 0],
}

fetch_meetings = {
    "parameters": {
        "method": "POST",
        "url": "https://api.people.ai/v3/beta/insights/export",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"},
                {"name": "Content-Type", "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ $('Build Query').first().json.query }}",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch Today Meetings",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [660, 0],
}

parse_and_filter = {
    "parameters": {
        "jsCode": """// Parse CSV and filter for Scott + Shreyas meetings
const csvText = $input.first().json.data || $input.first().json.body || '';
const WATCH_EMAILS = ['""" + SCOTT_EMAIL + """', '""" + SHREYAS_EMAIL + """'];

// Parse CSV
const lines = csvText.trim().split('\\n');
if (lines.length < 2) {
  return [{ json: { meetings: [], summary: 'No meetings found for today.', meetingCount: 0 } }];
}

const headers = [];
let inQuotes = false;
let current = '';
for (const ch of lines[0]) {
  if (ch === '"') { inQuotes = !inQuotes; continue; }
  if (ch === ',' && !inQuotes) { headers.push(current.trim()); current = ''; continue; }
  current += ch;
}
headers.push(current.trim());

function parseRow(line) {
  const vals = [];
  let inQ = false, cur = '';
  for (const ch of line) {
    if (ch === '"') { inQ = !inQ; continue; }
    if (ch === ',' && !inQ) { vals.push(cur.trim()); cur = ''; continue; }
    cur += ch;
  }
  vals.push(cur.trim());
  const obj = {};
  headers.forEach((h, i) => obj[h] = vals[i] || '');
  return obj;
}

const now = new Date();
const tz = 'America/Los_Angeles';
const meetings = [];

for (let i = 1; i < lines.length; i++) {
  if (!lines[i].trim()) continue;
  const row = parseRow(lines[i]);

  // Check if Scott or Shreyas is a participant
  const emails = (row['Activity Participants (Email)'] || '').toLowerCase();
  const isOurs = WATCH_EMAILS.some(e => emails.includes(e));
  if (!isOurs) continue;

  const meetingTime = new Date(row['Activity date'] || '');
  const elapsed = (now - meetingTime) / 3600000; // hours since meeting
  const hasEnded = elapsed > 0;

  // Check what data is available
  const subject = row['Subject'] || '[no subject]';
  const account = row['Account (name)'] || '';
  const opp = row['Opportunity (name)'] || '';
  const duration = row['Duration'] || row['Activity Duration'] || '';
  const sentiment = row['Sentiment'] || row['Activity Sentiment'] || '';
  const actionItems = row['Action Items'] || row['Activity Action Items'] || '';
  const keyTopics = row['Key Topics'] || row['Activity Key Topics'] || '';
  const summary = row['Summary'] || row['Activity Summary'] || '';
  const transcriptStatus = row['Transcript Status'] || row['Activity Transcript Status'] || '';

  // Build data availability flags
  const flags = [];
  if (account) flags.push(':white_check_mark: Account');
  else flags.push(':x: Account');
  if (duration) flags.push(':white_check_mark: Duration');
  if (sentiment) flags.push(':white_check_mark: Sentiment');
  if (actionItems) flags.push(':white_check_mark: Actions');
  if (keyTopics) flags.push(':white_check_mark: Topics');
  if (summary) flags.push(':white_check_mark: Summary');
  if (transcriptStatus) flags.push(':memo: Transcript: ' + transcriptStatus);

  // Determine overall status
  let status;
  if (!hasEnded) {
    status = ':calendar: Upcoming';
  } else if (summary || actionItems || keyTopics) {
    status = ':green_circle: Enriched';
  } else if (account) {
    status = ':yellow_circle: Basic';
  } else {
    status = ':red_circle: Minimal';
  }

  // Who from our team
  const names = (row['Activity Participants (Name)'] || '').split(';').map(n => n.trim());
  const emailList = (row['Activity Participants (Email)'] || '').split(';').map(e => e.trim());
  const ourPeople = [];
  emailList.forEach((e, idx) => {
    if (WATCH_EMAILS.includes(e.toLowerCase())) {
      ourPeople.push(names[idx] || e);
    }
  });

  const meetingPT = meetingTime.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });

  meetings.push({
    time: meetingPT,
    elapsed: hasEnded ? elapsed.toFixed(1) + 'h ago' : 'upcoming',
    subject: subject.length > 50 ? subject.substring(0, 47) + '...' : subject,
    account: account || '[unmatched]',
    status,
    flags: flags.join(' | '),
    rep: ourPeople.join(', '),
    raw: row,
  });
}

// Sort by time
meetings.sort((a, b) => {
  const ta = new Date(a.raw['Activity date'] || 0);
  const tb = new Date(b.raw['Activity date'] || 0);
  return ta - tb;
});

// Build Slack summary
const nowPT = now.toLocaleTimeString('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
const datePT = now.toLocaleDateString('en-US', { timeZone: tz, weekday: 'long', month: 'short', day: 'numeric' });

let summary = `:mag: *Meeting Data Monitor* — ${datePT} at ${nowPT} PT\\n`;
summary += `_Tracking: Scott Metcalf, Shreyas Gore | ${meetings.length} meetings today_\\n\\n`;

if (meetings.length === 0) {
  summary += 'No external meetings found for today.';
} else {
  // Status legend
  summary += ':green_circle: = enriched (transcript data)  :yellow_circle: = basic (calendar only)  :red_circle: = minimal  :calendar: = upcoming\\n\\n';

  for (const m of meetings) {
    summary += `${m.status} *${m.time}* — ${m.subject}\\n`;
    summary += `    _${m.account}_ | ${m.rep} | ${m.elapsed}\\n`;
    if (m.flags) {
      summary += `    ${m.flags}\\n`;
    }
    summary += '\\n';
  }

  // Stats
  const enriched = meetings.filter(m => m.status.includes('green')).length;
  const basic = meetings.filter(m => m.status.includes('yellow')).length;
  const minimal = meetings.filter(m => m.status.includes('red')).length;
  const upcoming = meetings.filter(m => m.status.includes('calendar')).length;

  summary += `---\\n_Enriched: ${enriched} | Basic: ${basic} | Minimal: ${minimal} | Upcoming: ${upcoming}_`;
}

return [{ json: { summary, meetingCount: meetings.length, meetings } }];
"""
    },
    "id": uid(),
    "name": "Parse & Filter Meetings",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [880, 0],
}

open_dm = {
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
        "jsonBody": '={"users": "' + SCOTT_SLACK_ID + '"}',
        "options": {},
    },
    "id": uid(),
    "name": "Open DM",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [1100, 0],
    "credentials": {"httpHeaderAuth": SLACK_CRED},
}

post_report = {
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
        "jsonBody": (
            '={{ JSON.stringify({'
            ' channel: $("Open DM").first().json.channel.id,'
            ' text: $("Parse & Filter Meetings").first().json.summary,'
            ' username: "Meeting Monitor",'
            ' icon_emoji: ":mag:"'
            '}) }}'
        ),
        "options": {},
    },
    "id": uid(),
    "name": "Post Report",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [1320, 0],
    "credentials": {"httpHeaderAuth": SLACK_CRED},
}

# ── Assemble workflow ──

nodes = [
    schedule_trigger,
    get_auth_token,
    build_query,
    fetch_meetings,
    parse_and_filter,
    open_dm,
    post_report,
]

connections = {
    "Every 30 Min (Weekdays 5am-8pm)": {
        "main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]
    },
    "Get Auth Token": {
        "main": [[{"node": "Build Query", "type": "main", "index": 0}]]
    },
    "Build Query": {
        "main": [[{"node": "Fetch Today Meetings", "type": "main", "index": 0}]]
    },
    "Fetch Today Meetings": {
        "main": [[{"node": "Parse & Filter Meetings", "type": "main", "index": 0}]]
    },
    "Parse & Filter Meetings": {
        "main": [[{"node": "Open DM", "type": "main", "index": 0}]]
    },
    "Open DM": {
        "main": [[{"node": "Post Report", "type": "main", "index": 0}]]
    },
}

workflow = {
    "name": WF_NAME,
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
        "timezone": "America/Los_Angeles",
    },
}


def main():
    print(f"Creating workflow: {WF_NAME}")

    # Create the workflow
    resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows",
        json=workflow,
        headers=HEADERS,
    )
    if resp.status_code not in (200, 201):
        print(f"  ERROR: HTTP {resp.status_code}")
        print(f"  {resp.text[:500]}")
        return

    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID {wf_id}, {len(result['nodes'])} nodes")

    # Activate it
    activate_resp = requests.post(
        f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate",
        headers=HEADERS,
    )
    if activate_resp.status_code == 200:
        print(f"  Activated!")
    else:
        print(f"  Activation: HTTP {activate_resp.status_code}")

    # Sync local
    sync_local(result, "Meeting Data Monitor.json")
    print(f"\nDone! Workflow ID: {wf_id}")
    print(f"Schedule: Every 30 min, 5am-8pm PT, Mon-Fri")
    print(f"Tracking: {SCOTT_EMAIL}, {SHREYAS_EMAIL}")


if __name__ == "__main__":
    main()
