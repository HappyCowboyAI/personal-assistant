"""
Fix: Follow-up Cron's Parse Meetings can't find CSV columns because the
Backstory Query API returns human-readable headers (e.g., "Activity date")
but the parser looks for slug-based names (e.g., "timestamp").

Also the Build Query is missing participant email variation columns, so
no participant data comes back.

Fixes:
1. Build Query: add participant email variation column
2. Parse Meetings: match actual API header names ("Activity date", "Activity", etc.)

Usage:
    N8N_API_KEY=... python3 scripts/fix_followup_cron_parse.py
"""

from n8n_helpers import (
    find_node, fetch_workflow, push_workflow, sync_local,
    WF_FOLLOWUP_CRON,
)


NEW_BUILD_QUERY = r"""// Build Backstory export query for meetings in the last 24 hours
// At 9am: catches yesterday afternoon meetings (4h+ delay means they're ready)
// At 3pm: catches this morning's meetings (ended by 11am, 4h+ elapsed)
const now = Date.now();
const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000;

const query = {
  object: "activity",
  filter: {
    "$and": [
      { attribute: { slug: "ootb_activity_type" }, clause: { "$eq": "meeting" } },
      { attribute: { slug: "ootb_activity_external" }, clause: { "$eq": true } },
      { attribute: { slug: "ootb_activity_timestamp" }, clause: { "$gte": twentyFourHoursAgo } },
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

return [{ json: { query: JSON.stringify(query) } }];
"""


NEW_PARSE_MEETINGS = r"""// Parse CSV response from Backstory meetings export
// API returns human-readable headers: "Activity", "Activity date", "Subject",
// "Account Name", "Opportunity Name", "Activity Participants (Email)", etc.
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

// Flexible header matching: check multiple possible names
function getVal(row, ...names) {
  for (const name of names) {
    const idx = headers.findIndex(h => h.toLowerCase().includes(name.toLowerCase()));
    if (idx >= 0 && row[idx]) return row[idx];
  }
  return '';
}

// Parse bracket-delimited list: "[a;b;c]" → ["a","b","c"]
function parseList(val) {
  if (!val) return [];
  return val.replace(/^\[/, '').replace(/\]$/, '').trim()
    .split(';').map(s => s.trim()).filter(Boolean);
}

const meetings = [];
for (let i = 1; i < lines.length; i++) {
  if (!lines[i].trim()) continue;
  const row = parseCSVRow(lines[i]);

  // Match actual API headers: "Activity date", "Activity", "Subject", etc.
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
  if (!tsMs || isNaN(tsMs)) continue;

  const activityUid = getVal(row, 'Activity') || '';
  // Skip if no UID (first column "Activity" contains the UID)
  if (!activityUid) continue;

  const participantEmails = parseList(getVal(row, 'Participants (Email)', 'Participants'));
  const participantNames = parseList(getVal(row, 'Participants (Name)'));

  meetings.push({
    activityUid,
    timestamp: tsMs,
    subject: getVal(row, 'Subject'),
    originator: getVal(row, 'Originator'),
    accountName: getVal(row, 'Account Name', 'Account'),
    accountId: '',
    opportunityName: getVal(row, 'Opportunity Name', 'Opportunity'),
    participants: participantEmails.join('; '),
    participantEmails,
    participantNames,
  });
}

return [{ json: { meetings, meetingCount: meetings.length, headers } }];
"""


def main():
    print(f"Fetching Follow-up Cron {WF_FOLLOWUP_CRON}...")
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    nodes = wf["nodes"]
    print(f"  {len(nodes)} nodes")

    # Fix Build Query: add participant email columns
    bq = find_node(nodes, "Build Query")
    if bq:
        bq["parameters"]["jsCode"] = NEW_BUILD_QUERY
        print("  Build Query: added participant email/name variation columns")
    else:
        print("  ERROR: Build Query not found")
        return

    # Fix Parse Meetings: match actual API headers
    pm = find_node(nodes, "Parse Meetings")
    if pm:
        pm["parameters"]["jsCode"] = NEW_PARSE_MEETINGS
        print("  Parse Meetings: fixed header matching (Activity date, Activity, etc.)")
    else:
        print("  ERROR: Parse Meetings not found")
        return

    print(f"\n=== Pushing Follow-up Cron ===")
    result = push_workflow(WF_FOLLOWUP_CRON, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")
    sync_local(result, "Follow-up Cron.json")

    print("\nDone! Follow-up Cron can now parse meetings from Query API response.")
    print("  Fixed: 'Activity date' header match (was looking for 'timestamp')")
    print("  Fixed: 'Activity' header match for UID (was looking for 'uid')")
    print("  Fixed: Added participant email/name columns to query")
    print("  Fixed: Flexible getVal with multiple header name fallbacks")


if __name__ == "__main__":
    main()
