#!/usr/bin/env python3
"""
Add participant-based filtering to Meeting Prep Cron.

Currently: sends ALL external meetings to ALL prep-enabled users.
After: sends each meeting ONLY to internal participants found in our users table.

Changes:
1. Build Query: add variation_id columns for participant email + external flag
2. Parse Meetings: extract internal participant emails from CSV
3. Match Users to Meetings: only match users whose email is in meeting's internal participants
"""

import json
import os
import requests

N8N_BASE_URL = "https://scottai.trackslife.com"
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

WORKFLOW_ID = "Of1U4T6x07aVqBYD"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(wid):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(wid, wf):
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
        "staticData": wf.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{wid}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def find_node(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
    raise ValueError(f"Node '{name}' not found")


def main():
    print("Fetching live Meeting Prep Cron workflow...")
    wf = fetch_workflow(WORKFLOW_ID)
    nodes = wf["nodes"]

    # ── 1. Update Build Query to include participant variation_id columns ──
    print("\n1. Updating Build Query columns...")
    build_query = find_node(nodes, "Build Query")
    old_columns = """columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_originator" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" }
  ],"""

    new_columns = """columns: [
    { slug: "ootb_activity_uid" },
    { slug: "ootb_activity_timestamp" },
    { slug: "ootb_activity_subject" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_email" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_name" },
    { slug: "ootb_activity_participants", variation_id: "ootb_activity_participants_external" },
    { slug: "ootb_activity_account" },
    { slug: "ootb_activity_opportunity" }
  ],"""

    code = build_query["parameters"]["jsCode"]
    if old_columns in code:
        code = code.replace(old_columns, new_columns)
        build_query["parameters"]["jsCode"] = code
        print("   Updated columns with participant variation_id fields")
    else:
        print("   WARNING: Could not find columns block. Current code:")
        print(code[:500])
        return

    # ── 2. Update Parse Meetings to extract participant data ──
    print("\n2. Updating Parse Meetings to extract participant emails...")
    parse_meetings = find_node(nodes, "Parse Meetings")

    new_parse_code = r"""// Parse CSV from Backstory activity export
// Headers include: Activity, Activity date, Subject,
// Activity Participants (Email), Activity Participants (Name),
// Activity Participants (External), Account (id), Account (name), etc.
const raw = $('Fetch Today Meetings').first().json;

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
  let inBrackets = 0;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '[') inBrackets++;
    else if (ch === ']') inBrackets--;

    if (ch === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes && inBrackets === 0) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

// Parse bracket-delimited list: "[a;b;c]" → ["a", "b", "c"]
function parseList(val) {
  if (!val) return [];
  const trimmed = val.replace(/^\[/, '').replace(/\]$/, '').trim();
  if (!trimmed) return [];
  return trimmed.split(';').map(s => s.trim());
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

  // Parse participant data
  const emails = parseList(getField(row, 'Activity Participants (Email)'));
  const names = parseList(getField(row, 'Activity Participants (Name)'));
  const externals = parseList(getField(row, 'Activity Participants (External)'));

  // Build internal participant email list
  const internalEmails = [];
  for (let p = 0; p < emails.length; p++) {
    const isExternal = (externals[p] || '').toLowerCase() === 'true';
    if (!isExternal && emails[p]) {
      internalEmails.push(emails[p].toLowerCase());
    }
  }

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
    oppId,
    internalEmails,
    participantCount: emails.length,
    internalCount: internalEmails.length,
    externalCount: emails.length - internalEmails.length
  });
}

return [{ json: { meetings, meetingCount: meetings.length } }];
"""
    parse_meetings["parameters"]["jsCode"] = new_parse_code
    print("   Updated Parse Meetings with participant extraction")

    # ── 3. Update Match Users to Meetings to filter by participant email ──
    print("\n3. Updating Match Users to Meetings for participant filtering...")
    match_node = find_node(nodes, "Match Users to Meetings")

    new_match_code = r"""// Match meetings to users based on PARTICIPANT EMAIL
// Only users who are internal participants of a meeting get the brief for that meeting
const meetingsData = $('Parse Meetings').first().json;
const meetings = meetingsData.meetings || [];
const users = $('Filter Prep Users').all().map(item => item.json);
const sentBriefs = $('Check Sent Briefs').all().map(item => item.json);

// Build dedup set: "userId:activityUid"
const sentKeys = new Set();
for (const brief of sentBriefs) {
  let meta = brief.metadata || {};
  if (typeof meta === 'string') {
    try { meta = JSON.parse(meta); } catch(e) { meta = {}; }
  }
  if (meta.activity_uid && brief.user_id) {
    sentKeys.add(brief.user_id + ':' + meta.activity_uid);
  }
}

// Build email → user lookup
const emailToUser = {};
for (const user of users) {
  const email = (user.email || '').toLowerCase();
  if (email) emailToUser[email] = user;
}

const now = Date.now();
const results = [];

for (const meeting of meetings) {
  if (!meeting.accountName) continue;

  const timeUntil = meeting.timestampMs - now;
  // Default: 2hr prep window, 15min too-late cutoff
  const tooLateMs = 15 * 60 * 1000;

  // For each internal participant email, check if they're in our users table
  for (const email of (meeting.internalEmails || [])) {
    const user = emailToUser[email];
    if (!user) continue; // Not in our system

    const prepMinutes = user.meeting_prep_minutes_before || 120;
    const prepWindowMs = prepMinutes * 60 * 1000;
    if (timeUntil < tooLateMs || timeUntil > prepWindowMs) continue;

    const dedupKey = user.id + ':' + meeting.activityUid;
    if (sentKeys.has(dedupKey)) continue;

    const repName = email.split('@')[0]
      .replace(/\./g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());

    results.push({
      userId: user.id,
      slackUserId: user.slack_user_id,
      email: user.email,
      assistant_name: user.assistant_name,
      assistant_emoji: user.assistant_emoji,
      assistant_persona: user.assistant_persona,
      timezone: user.timezone || 'America/Los_Angeles',
      repName,
      accountName: meeting.accountName,
      meetingSubject: meeting.subject,
      meetingTime: String(meeting.timestampMs),
      participants: '',
      opportunityName: meeting.oppName || '',
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

// Sort by meeting time (nearest first) and cap at 5 per cycle
results.sort((a, b) => parseInt(a.meetingTime) - parseInt(b.meetingTime));
const maxPerCycle = 5;
const capped = results.slice(0, maxPerCycle);
return capped.map(r => ({ json: r }));
"""
    match_node["parameters"]["jsCode"] = new_match_code
    print("   Updated Match Users to Meetings with participant email filtering")

    # ── Push ──
    print("\nPushing updated workflow...")
    result = push_workflow(WORKFLOW_ID, wf)
    print(f"  ✓ Pushed (updatedAt: {result.get('updatedAt', '?')})")

    # Sync local
    print("\nSyncing local file...")
    live = fetch_workflow(WORKFLOW_ID)
    local_path = os.path.join(REPO_ROOT, "n8n", "workflows", "Meeting Prep Cron.json")
    with open(local_path, "w") as f:
        json.dump(live, f, indent=2)
    print(f"  ✓ Saved to {local_path}")

    print("\nDone! Meeting Prep Cron now filters by participant email:")
    print("  1. Build Query exports participant email + external flag via variation_id")
    print("  2. Parse Meetings extracts internal participant emails per meeting")
    print("  3. Match Users to Meetings only sends briefs to users who are meeting participants")


if __name__ == "__main__":
    main()
