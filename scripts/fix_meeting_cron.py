#!/usr/bin/env python3
"""
Fix Meeting Prep Cron:
- Export API doesn't return participant emails — match via account→opp owner instead
- CSV column names are display names, not slugs (e.g., "Activity date" not "ootb_activity_timestamp")
- Timestamps are ISO format, not epoch ms
- Add Fetch Open Opps + Parse Opps CSV steps to get account→owner mapping
- Rewrite matching logic
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

CRON_ID = "Of1U4T6x07aVqBYD"
MEETING_BRIEF_ID = "Cj4HcHfbzy9OZhwE"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
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


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def get_sales_digest_code():
    """Fetch Parse Opps CSV code from Sales Digest."""
    wf = fetch_workflow("7sinwSgjkEA40zDj")
    parse_opps_code = None
    for node in wf["nodes"]:
        if node["name"] == "Parse Opps CSV":
            parse_opps_code = node["parameters"]["jsCode"]
    return parse_opps_code


# ============================================================
# UPDATED CODE NODES
# ============================================================

# Build Query — use correct timestamp format for People.ai
CRON_BUILD_QUERY_CODE = r"""// Build People.ai activity export query for today's upcoming external meetings
const tz = 'America/Los_Angeles';
const now = new Date();

// Query from now forward through end of today + buffer
// This ensures we catch meetings happening in the next few hours
const windowStart = now.getTime();

// End of today in PT (roughly midnight + 1 day as safety margin)
const todayStr = now.toLocaleDateString('en-US', { timeZone: tz });
const parts = todayStr.split('/');
const todayMidnight = new Date(parts[2] + '-' + parts[0].padStart(2, '0') + '-' + parts[1].padStart(2, '0') + 'T00:00:00-08:00');
const tomorrowEnd = new Date(todayMidnight.getTime() + 48 * 3600000);

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": windowStart } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$lte": tomorrowEnd.getTime() } }
    ]
  },
  columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" }
  ],
  sort: [
    { attribute: { slug: "ootb_activity_timestamp" }, direction: "asc" }
  ]
};

return [{ json: { query: JSON.stringify(query) } }];
"""

# Parse Meetings — handle actual CSV column names (display names, not slugs)
CRON_PARSE_MEETINGS_CODE = r"""// Parse CSV from People.ai activity export
// API returns display names: "Activity", "Activity date", "Subject", "Account (name)", etc.
// Timestamps are ISO format (e.g., "2026-02-24 16:00:00+00:00"), not epoch ms
const raw = $('Fetch Today Meetings').first().json;

// n8n HTTP Request may return the CSV in .data or as the response body
const csvData = typeof raw === 'string' ? raw : (raw.data || raw.body || '');

if (!csvData || typeof csvData !== 'string') {
  return [{ json: { meetings: [], meetingCount: 0, error: 'No CSV data' } }];
}

const lines = csvData.split(/\r?\n/).filter(l => l.trim());
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
headers.forEach((h, i) => { headerMap[h.toLowerCase()] = i; });

function getField(row, ...names) {
  for (const name of names) {
    const idx = headerMap[name.toLowerCase()];
    if (idx !== undefined && row[idx]) {
      return row[idx];
    }
  }
  return '';
}

const meetings = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;

  const activityUid = getField(row, 'Activity', 'ootb_activity_uid');
  const timestampStr = getField(row, 'Activity date', 'ootb_activity_timestamp');
  const subject = getField(row, 'Subject', 'ootb_activity_subject');
  const accountName = getField(row, 'Account (name)', 'Account', 'ootb_activity_account');
  const accountId = getField(row, 'Account (id)');
  const oppName = getField(row, 'Opportunity (name)', 'Opportunity', 'ootb_activity_opportunity');
  const oppId = getField(row, 'Opportunity (id)');

  // Parse ISO timestamp to epoch ms
  let timestampMs = 0;
  if (timestampStr) {
    const parsed = new Date(timestampStr);
    if (!isNaN(parsed.getTime())) {
      timestampMs = parsed.getTime();
    }
  }

  if (!activityUid) continue;

  meetings.push({
    activityUid,
    timestampMs,
    timestampStr,
    subject: subject || 'Customer Meeting',
    accountName: accountName || '',
    accountId,
    oppName: oppName || '',
    oppId
  });
}

return [{ json: { meetings, meetingCount: meetings.length } }];
"""

# Match Users to Meetings — via account→opp owner chain
CRON_MATCH_USERS_CODE = r"""// Match meetings to users via account ownership (opp owner → user email)
// The export API doesn't return participant lists, so we match through:
// 1. Meeting has an account name
// 2. User owns an opportunity with that account
// 3. → user gets the meeting brief
const meetingsData = $('Parse Meetings').first().json;
const meetings = meetingsData.meetings || [];
const users = $('Get Prep Users').all().map(item => item.json);
const sentBriefs = $('Check Sent Briefs').all().map(item => item.json);
const oppsData = $('Parse Opps CSV').first().json;
const allOpps = oppsData.opps || [];

// Build set of already-sent briefs: key = "userId:activityUid"
const sentKeys = new Set();
for (const brief of sentBriefs) {
  const meta = typeof brief.metadata === 'string' ? JSON.parse(brief.metadata || '{}') : (brief.metadata || {});
  if (meta.activity_uid && brief.user_id) {
    sentKeys.add(brief.user_id + ':' + meta.activity_uid);
  }
}

// Build account→owners map from opportunities
// owners field contains names like "Scott Metcalf", match to user emails
const accountOwners = {}; // accountName (lower) → Set of owner name fragments (lower)
const accountOppInfo = {}; // accountName (lower) → {oppName, stage, amount, closeDate, engagement}

for (const opp of allOpps) {
  const acct = (opp.account || '').toLowerCase().trim();
  if (!acct) continue;

  if (!accountOwners[acct]) accountOwners[acct] = new Set();

  const owners = (opp.owners || '').toLowerCase();
  // Owner names could be comma-separated or semicolon-separated
  const ownerList = owners.split(/[,;]/).map(o => o.trim()).filter(o => o);
  for (const owner of ownerList) {
    accountOwners[acct].add(owner);
  }

  // Keep the highest-value opp info for context
  if (!accountOppInfo[acct] ||
      (parseFloat((opp.amount || '0').replace(/[^0-9.]/g, '')) >
       parseFloat((accountOppInfo[acct].amount || '0').replace(/[^0-9.]/g, '')))) {
    accountOppInfo[acct] = {
      oppName: opp.name,
      stage: opp.stage,
      amount: opp.amount,
      closeDate: opp.closeDate,
      engagement: opp.engagement
    };
  }
}

const now = Date.now();
const results = [];

for (const user of users) {
  const userEmail = (user.email || '').toLowerCase();
  const prepMinutes = user.meeting_prep_minutes_before || 120;
  const prepWindowMs = prepMinutes * 60 * 1000;
  const tooLateMs = 15 * 60 * 1000;

  // Derive user's name from email for matching against opp owners
  const userName = userEmail.split('@')[0].replace(/\./g, ' ').toLowerCase();

  for (const meeting of meetings) {
    if (!meeting.accountName) continue;

    const meetingAcct = meeting.accountName.toLowerCase().trim();

    // Check timing: meeting should be between 15 min and prepMinutes from now
    const timeUntil = meeting.timestampMs - now;
    if (timeUntil < tooLateMs || timeUntil > prepWindowMs) continue;

    // Check if user owns an opp with this account
    const owners = accountOwners[meetingAcct];
    if (!owners) continue;

    let isOwner = false;
    for (const owner of owners) {
      if (owner.includes(userName) || userName.includes(owner)) {
        isOwner = true;
        break;
      }
    }
    if (!isOwner) continue;

    // Dedup check
    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentKeys.has(dedupKey)) continue;

    // Get opp context if available
    const oppInfo = accountOppInfo[meetingAcct] || {};

    results.push({
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistant_name: user.assistant_name,
      assistant_emoji: user.assistant_emoji,
      assistant_persona: user.assistant_persona,
      timezone: user.timezone || 'America/Los_Angeles',
      repName: userEmail.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      accountName: meeting.accountName,
      meetingSubject: meeting.subject,
      meetingTime: String(meeting.timestampMs),
      participants: '',
      opportunityName: meeting.oppName || oppInfo.oppName || '',
      opportunityStage: oppInfo.stage || '',
      opportunityAmount: oppInfo.amount || '',
      opportunityCloseDate: oppInfo.closeDate || '',
      opportunityEngagement: oppInfo.engagement || '',
      activityUid: meeting.activityUid
    });
  }
}

if (results.length === 0) {
  return [{ json: { matches: [], matchCount: 0, noMatches: true } }];
}

return results.map(r => ({ json: r }));
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


def upgrade_cron(wf):
    print(f"\n=== Updating Meeting Prep Cron ({len(wf['nodes'])} nodes) ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Get parse opps code from Sales Digest
    parse_opps_code = get_sales_digest_code()
    if not parse_opps_code:
        raise RuntimeError("Could not get Parse Opps CSV code from Sales Digest")
    print("  Got Parse Opps CSV code from Sales Digest")

    # --- Update existing code nodes ---
    for node in nodes:
        if node["name"] == "Build Query":
            node["parameters"]["jsCode"] = CRON_BUILD_QUERY_CODE
            print("  Updated Build Query")
        elif node["name"] == "Parse Meetings":
            node["parameters"]["jsCode"] = CRON_PARSE_MEETINGS_CODE
            print("  Updated Parse Meetings")
        elif node["name"] == "Match Users to Meetings":
            node["parameters"]["jsCode"] = CRON_MATCH_USERS_CODE
            print("  Updated Match Users to Meetings (account-based matching)")
        elif node["name"] == "Log Meeting Brief":
            node["parameters"]["jsCode"] = LOG_MEETING_BRIEF_CODE
            print("  Updated Log Meeting Brief")

    # --- Add Fetch Open Opps node ---
    node_names = [n["name"] for n in nodes]
    if "Fetch Open Opps" not in node_names:
        fetch_opps_id = uid()
        nodes.append({
            "parameters": {
                "method": "POST",
                "url": "https://api.people.ai/v3/beta/insights/export",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Authorization",
                         "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '{"object": "opportunity", "filter": {"$and": [{"attribute": {"slug": "ootb_opportunity_is_closed"}, "clause": {"$eq": false}}]}, "columns": [{"slug": "ootb_opportunity_owners"}, {"slug": "ootb_opportunity_name"}, {"slug": "ootb_opportunity_account_name"}, {"slug": "ootb_opportunity_close_date"}, {"slug": "ootb_opportunity_current_stage"}, {"slug": "ootb_opportunity_converted_amount"}, {"slug": "ootb_opportunity_crm_id"}, {"slug": "ootb_opportunity_engagement_level"}], "sort": [{"attribute": {"slug": "ootb_opportunity_owners"}, "direction": "asc"}]}',
                "options": {}
            },
            "id": fetch_opps_id,
            "name": "Fetch Open Opps",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [640, 620]
        })
        print(f"  Added Fetch Open Opps (id={fetch_opps_id})")

    if "Parse Opps CSV" not in node_names:
        parse_opps_id = uid()
        nodes.append({
            "parameters": {"jsCode": parse_opps_code},
            "id": parse_opps_id,
            "name": "Parse Opps CSV",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 620]
        })
        print(f"  Added Parse Opps CSV (id={parse_opps_id})")

    # --- Rewire connections ---
    # Get Auth Token fans out to: Build Query, Get Prep Users, Check Sent Briefs, AND Fetch Open Opps
    auth_targets = connections.get("Get Auth Token", {}).get("main", [[]])[0]
    if not any(t["node"] == "Fetch Open Opps" for t in auth_targets):
        auth_targets.append({"node": "Fetch Open Opps", "type": "main", "index": 0})
        print("  Wired Get Auth Token → Fetch Open Opps")

    # Fetch Open Opps → Parse Opps CSV
    connections["Fetch Open Opps"] = {
        "main": [[{"node": "Parse Opps CSV", "type": "main", "index": 0}]]
    }
    print("  Wired Fetch Open Opps → Parse Opps CSV")

    # Parse Opps CSV → Match Users to Meetings
    connections["Parse Opps CSV"] = {
        "main": [[{"node": "Match Users to Meetings", "type": "main", "index": 0}]]
    }
    print("  Wired Parse Opps CSV → Match Users to Meetings")

    print(f"  Total nodes: {len(nodes)}")
    return wf


def main():
    print("Fetching Meeting Prep Cron...")
    wf = fetch_workflow(CRON_ID)
    print(f"  {len(wf['nodes'])} nodes")

    wf = upgrade_cron(wf)

    print("\n=== Pushing workflow ===")
    result = push_workflow(CRON_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{CRON_ID}", headers=HEADERS)
    resp.raise_for_status()
    sync_local(resp.json(), "Meeting Prep Cron.json")

    print("\nDone! Meeting Prep Cron now matches via account→opp owner.")
    print("  Meetings matched to users who own opps with the meeting's account.")
    print("  Export API column names handled (display names, ISO timestamps).")


if __name__ == "__main__":
    main()
