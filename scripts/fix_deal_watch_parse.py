#!/usr/bin/env python3
"""
Fix Deal Watch Cron: Parse and Classify CSV header mismatches.

The People.ai Insights API returns different column headers than expected:
  - "Record ID" not "CRM ID"
  - "Amount (Converted)" not "Converted Amount"
  - "Opportunity Engagement Level" not "Engagement Level"
  - "Meetings (Last 7 Days)" not "Count Of Meetings Standard"
  - "Days in Stage" returns HH:MM:SS format, not number of days
  - "Owners" column missing from API response
"""

from n8n_helpers import find_node, modify_workflow, WF_DEAL_WATCH_CRON


PARSE_AND_CLASSIFY_CODE = r"""// Parse CSV and classify deals — combined for Deal Watch
const csvData = $('Fetch Insights Opps').first().json.data;

if (!csvData) {
  return [{ json: { classifiedOpps: [], error: 'No data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { classifiedOpps: [], oppCount: 0 } }];
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

function get(row, ...names) {
  for (const name of names) {
    const idx = headerMap[name.toLowerCase()];
    if (idx !== undefined && row[idx] !== undefined && row[idx] !== '') return row[idx];
  }
  return '';
}

function num(val) {
  if (val === null || val === undefined || val === '') return null;
  const s = String(val);
  // Handle HH:MM:SS duration format (Days in Stage) — convert to days
  if (/^\d+:\d+:\d+$/.test(s)) {
    const parts = s.split(':');
    const hours = parseInt(parts[0], 10);
    return Math.round(hours / 24);
  }
  const n = parseFloat(s.replace(/[^0-9.\-]/g, ''));
  return isNaN(n) ? null : n;
}
function n(val) { return num(val) || 0; }

const classifiedOpps = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;

  const opp = {
    owners: get(row, 'Owners', 'Owner'),
    name: get(row, 'Opportunity Name', 'Name'),
    account: get(row, 'Account Name', 'Account'),
    closeDate: get(row, 'Close Date'),
    stage: get(row, 'Stage', 'Current Stage'),
    amount: get(row, 'Amount (Converted)', 'Converted Amount', 'Amount'),
    crmId: get(row, 'Record ID', 'CRM ID', 'Opportunity CRM ID', 'CRM Id'),
    engagement: get(row, 'Opportunity Engagement Level', 'Engagement Level', 'Engagement'),
    daysInStage: get(row, 'Days in Stage', 'Days In Stage'),
    meetings30d: get(row, 'Meetings (Last 7 Days)', 'Count Of Meetings Standard', 'Meetings', 'Count of Meetings'),
    upcomingMeetings: get(row, 'Upcoming Meetings (Next 7 Days)', 'Upcoming Meetings Standard', 'Upcoming Meetings'),
    emailsReceived: get(row, 'Emails Received (Last 7 Days)', 'Count Of Emails Received', 'Emails Received'),
    emailsSent: get(row, 'Emails Sent (Last 7 Days)', 'Count Of Emails Sent', 'Emails Sent'),
    execActivities: get(row, 'Activities with Executives (Last 7 Days)', 'Executive Activities', 'Exec Activities'),
    execMeetings: get(row, 'Meetings with a Director, VP, or Executive (Last 7 Days)', 'Meetings With Director VP Exec', 'Executive Meetings', 'Director+ Meetings'),
    peopleEngaged: get(row, 'People Engaged (Last 7 Days)', 'People Engaged', 'Contacts Engaged'),
    totalActivities: get(row, 'Total Activities (Last 7 Days)', 'Total Activities Count', 'Total Activities')
  };

  const engagement = n(opp.engagement);
  const daysInStage = n(opp.daysInStage);
  const meetings30d = n(opp.meetings30d);
  const upcomingMeetings = n(opp.upcomingMeetings);
  const emailsReceived = n(opp.emailsReceived);
  const emailsSent = n(opp.emailsSent);
  const execActivities = n(opp.execActivities);
  const execMeetings = n(opp.execMeetings);
  const peopleEngaged = n(opp.peopleEngaged);

  const emailResponsiveness = emailsSent > 0 ? emailsReceived / emailsSent : 0;
  const totalMeetings = meetings30d + execMeetings;
  const execCoverage = totalMeetings > 0 ? 100 * execMeetings / totalMeetings : 0;

  let classification = 'healthy';
  let flags = [];

  // Stalled
  if (engagement < 25 || (engagement < 50 && daysInStage > 45 && meetings30d === 0)) {
    classification = 'stalled';
    if (engagement < 25) flags.push('Very low engagement');
    if (daysInStage > 45) flags.push('Stuck ' + daysInStage + 'd');
    if (meetings30d === 0) flags.push('No meetings 30d');
  }

  // Risk
  if (classification === 'healthy') {
    let riskSignals = 0;
    let riskFlags = [];
    if (execActivities === 0) { riskSignals++; riskFlags.push('No exec'); }
    if (emailResponsiveness < 0.3 && emailsSent > 0) { riskSignals++; riskFlags.push('Low email response'); }
    if (peopleEngaged < 3) { riskSignals++; riskFlags.push('Single-threaded'); }
    if (execCoverage < 10 && totalMeetings > 0) { riskSignals++; riskFlags.push('Low exec coverage'); }
    if (riskSignals >= 2) {
      classification = 'risk';
      flags = riskFlags;
    }
  }

  // Accelerating
  if (classification === 'healthy') {
    let accelSignals = 0;
    let accelFlags = [];
    if (upcomingMeetings >= 2) { accelSignals++; accelFlags.push(upcomingMeetings + ' upcoming mtgs'); }
    if (execActivities >= 3) { accelSignals++; accelFlags.push(execActivities + ' exec activities'); }
    if (meetings30d >= 4) { accelSignals++; accelFlags.push(meetings30d + ' mtgs 30d'); }
    if (engagement >= 70 && accelSignals >= 2) {
      classification = 'accelerating';
      flags = accelFlags;
    }
  }

  classifiedOpps.push({
    ...opp,
    classification,
    flags,
    metrics: { engagement, daysInStage, meetings30d, execActivities, peopleEngaged }
  });
}

return [{ json: { classifiedOpps, oppCount: classifiedOpps.length } }];"""


def modify_deal_watch(nodes, connections):
    node = find_node(nodes, "Parse and Classify")
    if not node:
        print("ERROR: 'Parse and Classify' not found!")
        return 0

    code = node["parameters"]["jsCode"]
    if "Record ID" in code:
        print("  Parse and Classify: already has correct headers — skipping")
        return 0

    node["parameters"]["jsCode"] = PARSE_AND_CLASSIFY_CODE
    print("  Updated 'Parse and Classify' with correct CSV header mappings")
    print("    - Record ID → crmId")
    print("    - Amount (Converted) → amount")
    print("    - Opportunity Engagement Level → engagement")
    print("    - Meetings (Last 7 Days) → meetings30d")
    print("    - Days in Stage HH:MM:SS → converted to days")
    return 1


def main():
    print("=== Fix Deal Watch Cron: Parse and Classify ===\n")

    modify_workflow(
        WF_DEAL_WATCH_CRON,
        "Deal Watch Cron.json",
        modify_deal_watch,
    )


if __name__ == "__main__":
    main()
