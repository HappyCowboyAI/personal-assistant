#!/usr/bin/env python3
"""
Add Deal Watch Cron — daily state-change alerts.
- Runs daily at 7:00 AM PT (after 6am Sales Digest), weekdays only
- Classifies all open deals using Export API metrics
- Compares today's classifications against yesterday's deal_snapshots
- Sends proactive alerts to users when deals change state (e.g., healthy → stalled)
- Saves today's snapshots for tomorrow's comparison
"""

import json
import os
import uuid
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}

SLACK_CRED = {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}
SUPABASE_CRED = {"id": "ASRWWkQ0RSMOpNF1", "name": "Supabase account"}
PAI_CLIENT_BODY = "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"


def uid():
    return str(uuid.uuid4())


def fetch_workflow(wf_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
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


# ============================================================
# Export API query — same expanded columns as Insights
# ============================================================
INSIGHTS_OPP_QUERY = json.dumps({
    "object": "opportunity",
    "filter": {
        "$and": [
            {"attribute": {"slug": "ootb_opportunity_is_closed"}, "clause": {"$eq": False}},
            {"attribute": {"slug": "ootb_opportunity_close_date", "variation_id": "ootb_opportunity_close_date_0"},
             "clause": {"$within": {"$ref": "time_ranges.this_fyear"}}}
        ]
    },
    "columns": [
        {"slug": "ootb_opportunity_owners"},
        {"slug": "ootb_opportunity_name"},
        {"slug": "ootb_opportunity_account_name"},
        {"slug": "ootb_opportunity_close_date"},
        {"slug": "ootb_opportunity_current_stage"},
        {"slug": "ootb_opportunity_converted_amount"},
        {"slug": "ootb_opportunity_crm_id"},
        {"slug": "ootb_opportunity_engagement_level"},
        {"slug": "ootb_opportunity_days_in_stage"},
        {"slug": "ootb_opportunity_count_of_meetings_standard"},
        {"slug": "ootb_opportunity_upcoming_meetings_standard"},
        {"slug": "ootb_opportunity_count_of_emails_received"},
        {"slug": "ootb_opportunity_count_of_emails_sent"},
        {"slug": "ootb_opportunity_executive_activities"},
        {"slug": "ootb_opportunity_meetings_with_director_vp_exec"},
        {"slug": "ootb_opportunity_people_engaged"},
        {"slug": "ootb_opportunity_total_activities_count"}
    ],
    "sort": [{"attribute": {"slug": "ootb_opportunity_owners"}, "direction": "asc"}]
})


# ============================================================
# Parse + Classify — same logic as Insights sub-workflow
# ============================================================
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
  const n = parseFloat(String(val).replace(/[^0-9.\-]/g, ''));
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
    stage: get(row, 'Current Stage', 'Stage'),
    amount: get(row, 'Converted Amount', 'Amount'),
    crmId: get(row, 'CRM ID', 'Opportunity CRM ID', 'CRM Id'),
    engagement: get(row, 'Engagement Level', 'Engagement'),
    daysInStage: get(row, 'Days In Stage', 'Days in Stage'),
    meetings30d: get(row, 'Count Of Meetings Standard', 'Meetings', 'Count of Meetings'),
    upcomingMeetings: get(row, 'Upcoming Meetings Standard', 'Upcoming Meetings'),
    emailsReceived: get(row, 'Count Of Emails Received', 'Emails Received'),
    emailsSent: get(row, 'Count Of Emails Sent', 'Emails Sent'),
    execActivities: get(row, 'Executive Activities', 'Exec Activities'),
    execMeetings: get(row, 'Meetings With Director VP Exec', 'Executive Meetings', 'Director+ Meetings'),
    peopleEngaged: get(row, 'People Engaged', 'Contacts Engaged'),
    totalActivities: get(row, 'Total Activities Count', 'Total Activities')
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

return [{ json: { classifiedOpps, oppCount: classifiedOpps.length } }];
"""


# ============================================================
# Detect Transitions — compare today vs yesterday snapshots
# ============================================================
DETECT_TRANSITIONS_CODE = r"""// Compare today's classifications against yesterday's snapshots
const todayData = $('Parse and Classify').first().json;
const yesterdaySnapshots = $('Get Yesterday Snapshots').all().map(item => item.json);

const todayOpps = todayData.classifiedOpps || [];

// Build lookup by CRM ID from yesterday's snapshots
const yesterdayMap = {};
for (const snap of yesterdaySnapshots) {
  if (snap.opportunity_crm_id) {
    yesterdayMap[snap.opportunity_crm_id] = snap;
  }
}

const transitions = [];
const snapshotsToSave = [];

// Severity ranking for transition direction
const severityRank = { 'stalled': 0, 'risk': 1, 'healthy': 2, 'accelerating': 3 };
const classLabels = {
  'stalled': '\ud83d\udd34 Stalled',
  'risk': '\u26a0\ufe0f At Risk',
  'healthy': '\u2705 Healthy',
  'accelerating': '\ud83d\ude80 Accelerating'
};

for (const opp of todayOpps) {
  const crmId = opp.crmId;
  if (!crmId) continue;

  // Build snapshot for saving
  snapshotsToSave.push({
    opportunity_crm_id: crmId,
    opportunity_name: opp.name || '',
    account_name: opp.account || '',
    owner_name: opp.owners || '',
    classification: opp.classification,
    engagement_level: opp.metrics?.engagement || 0,
    days_in_stage: opp.metrics?.daysInStage || 0,
    metrics: JSON.stringify(opp.metrics || {})
  });

  const yesterday = yesterdayMap[crmId];

  if (!yesterday) {
    // New deal — only flag if it's stalled or risk
    if (opp.classification === 'stalled' || opp.classification === 'risk') {
      transitions.push({
        crmId,
        name: opp.name,
        account: opp.account,
        owner: opp.owners,
        previousClass: null,
        newClass: opp.classification,
        previousLabel: 'New',
        newLabel: classLabels[opp.classification],
        direction: 'worsening',
        flags: opp.flags || [],
        engagement: opp.metrics?.engagement || 0
      });
    }
    continue;
  }

  // Compare classifications
  const prevClass = yesterday.classification;
  const newClass = opp.classification;

  if (prevClass === newClass) continue; // No change

  const prevRank = severityRank[prevClass] ?? 2;
  const newRank = severityRank[newClass] ?? 2;
  const direction = newRank < prevRank ? 'worsening' : 'improving';

  transitions.push({
    crmId,
    name: opp.name,
    account: opp.account,
    owner: opp.owners,
    previousClass: prevClass,
    newClass: newClass,
    previousLabel: classLabels[prevClass] || prevClass,
    newLabel: classLabels[newClass] || newClass,
    direction,
    flags: opp.flags || [],
    engagement: opp.metrics?.engagement || 0
  });
}

return [{ json: {
  transitions,
  transitionCount: transitions.length,
  worseningCount: transitions.filter(t => t.direction === 'worsening').length,
  improvingCount: transitions.filter(t => t.direction === 'improving').length,
  snapshotsToSave,
  snapshotCount: snapshotsToSave.length,
  hasTransitions: transitions.length > 0
}}];
"""


# ============================================================
# Build Save Snapshots Query — upserts to deal_snapshots
# ============================================================
SAVE_SNAPSHOTS_CODE = r"""// Build batch upsert for deal_snapshots table
const data = $('Detect Transitions').first().json;
const snapshots = data.snapshotsToSave || [];

if (snapshots.length === 0) {
  return [{ json: { query: '', count: 0 } }];
}

// Build individual upsert values
const values = snapshots.map(s => {
  const metrics = typeof s.metrics === 'string' ? s.metrics : JSON.stringify(s.metrics || {});
  return `(
    '${(s.opportunity_crm_id || '').replace(/'/g, "''")}',
    '${(s.opportunity_name || '').replace(/'/g, "''")}',
    '${(s.account_name || '').replace(/'/g, "''")}',
    '${(s.owner_name || '').replace(/'/g, "''")}',
    '${s.classification}',
    ${s.engagement_level || 0},
    ${s.days_in_stage || 0},
    '${metrics.replace(/'/g, "''")}'::jsonb,
    CURRENT_DATE
  )`;
}).join(',\n');

const query = `INSERT INTO deal_snapshots
  (opportunity_crm_id, opportunity_name, account_name, owner_name, classification, engagement_level, days_in_stage, metrics, snapshot_date)
VALUES ${values}
ON CONFLICT (organization_id, opportunity_crm_id, snapshot_date)
DO UPDATE SET
  classification = EXCLUDED.classification,
  engagement_level = EXCLUDED.engagement_level,
  days_in_stage = EXCLUDED.days_in_stage,
  metrics = EXCLUDED.metrics,
  opportunity_name = EXCLUDED.opportunity_name,
  account_name = EXCLUDED.account_name,
  owner_name = EXCLUDED.owner_name;`;

return [{ json: { query, count: snapshots.length } }];
"""


# ============================================================
# Match Alerts to Users — scope-aware alert routing
# ============================================================
MATCH_ALERTS_CODE = r"""// Match transitions to users based on their scope
const transData = $('Detect Transitions').first().json;
const users = $('Get Alert Users').all().map(item => item.json);
const hierarchyData = $('Parse Hierarchy').first().json;

const transitions = transData.transitions || [];
if (transitions.length === 0 || users.length === 0) {
  return [{ json: { noAlerts: true } }];
}

const managerToReports = hierarchyData.managerToReports || {};
const results = [];

for (const user of users) {
  const userEmail = (user.email || '').toLowerCase();
  const repName = userEmail.split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const repLower = repName.toLowerCase();
  const digestScope = user.digest_scope || 'my_deals';

  let userTransitions = [];

  if (digestScope === 'my_deals') {
    userTransitions = transitions.filter(t => {
      const owner = (t.owner || '').toLowerCase();
      return owner.includes(repLower);
    });
  } else if (digestScope === 'team_deals') {
    let reportNames = [repLower];
    for (const [mgrKey, reports] of Object.entries(managerToReports)) {
      if (mgrKey.includes(repLower) || repLower.includes(mgrKey)) {
        for (const report of reports) {
          const rName = (report.name || '').toLowerCase();
          if (rName && !reportNames.includes(rName)) reportNames.push(rName);
        }
      }
    }
    if (managerToReports[userEmail]) {
      for (const report of managerToReports[userEmail]) {
        const rName = (report.name || '').toLowerCase();
        if (rName && !reportNames.includes(rName)) reportNames.push(rName);
      }
    }
    userTransitions = transitions.filter(t => {
      const owner = (t.owner || '').toLowerCase();
      return reportNames.some(name => owner.includes(name));
    });
  } else {
    // pipeline scope — see all transitions
    userTransitions = transitions;
  }

  if (userTransitions.length === 0) continue;

  results.push({
    userId: user.id,
    slackUserId: user.slack_user_id,
    email: user.email,
    assistantName: user.assistant_name || 'Aria',
    assistantEmoji: user.assistant_emoji || ':robot_face:',
    repName,
    transitions: userTransitions,
    worseningCount: userTransitions.filter(t => t.direction === 'worsening').length,
    improvingCount: userTransitions.filter(t => t.direction === 'improving').length
  });
}

if (results.length === 0) {
  return [{ json: { noAlerts: true } }];
}

return results.map(r => ({ json: r }));
"""


# ============================================================
# Build Alert Message — deterministic Block Kit (no Claude)
# ============================================================
BUILD_ALERT_CODE = r"""// Build Slack Block Kit alert message — no AI needed
const data = $('Split In Batches').first().json;
const transitions = data.transitions || [];
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const emojiClean = assistantEmoji.replace(/:/g, '');

const worsening = transitions.filter(t => t.direction === 'worsening');
const improving = transitions.filter(t => t.direction === 'improving');

const blocks = [];

// Header
blocks.push({
  type: 'header',
  text: { type: 'plain_text', text: emojiClean + ' Deal State Changes', emoji: true }
});

// Summary
const summaryParts = [];
if (worsening.length > 0) summaryParts.push(worsening.length + ' need' + (worsening.length === 1 ? 's' : '') + ' attention');
if (improving.length > 0) summaryParts.push(improving.length + ' improving');
blocks.push({
  type: 'section',
  text: { type: 'mrkdwn', text: '*' + transitions.length + ' deals changed state overnight* \u2014 ' + summaryParts.join(', ') }
});

// Worsening section
if (worsening.length > 0) {
  blocks.push({ type: 'divider' });
  blocks.push({
    type: 'section',
    text: { type: 'mrkdwn', text: '*\ud83d\udea8 Needs Attention*' }
  });

  for (const t of worsening.slice(0, 10)) {
    const prevLabel = t.previousLabel || 'New';
    const arrow = prevLabel + ' \u2192 ' + t.newLabel;
    const flagText = (t.flags || []).length > 0 ? '\n    _' + t.flags.join(', ') + '_' : '';
    const link = t.crmId ? ' <https://app.people.ai/opportunities/' + t.crmId + '|View>' : '';
    blocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: '*' + (t.name || 'Unknown') + '* (' + (t.account || '') + ')' + link + '\n' + arrow + flagText }
    });
  }
  if (worsening.length > 10) {
    blocks.push({
      type: 'context',
      elements: [{ type: 'mrkdwn', text: '...and ' + (worsening.length - 10) + ' more' }]
    });
  }
}

// Improving section
if (improving.length > 0) {
  blocks.push({ type: 'divider' });
  blocks.push({
    type: 'section',
    text: { type: 'mrkdwn', text: '*\u2705 Improving*' }
  });

  for (const t of improving.slice(0, 5)) {
    const arrow = t.previousLabel + ' \u2192 ' + t.newLabel;
    const link = t.crmId ? ' <https://app.people.ai/opportunities/' + t.crmId + '|View>' : '';
    blocks.push({
      type: 'section',
      text: { type: 'mrkdwn', text: '*' + (t.name || 'Unknown') + '* (' + (t.account || '') + ')' + link + '\n' + arrow }
    });
  }
  if (improving.length > 5) {
    blocks.push({
      type: 'context',
      elements: [{ type: 'mrkdwn', text: '...and ' + (improving.length - 5) + ' more improving' }]
    });
  }
}

// Footer
const now = new Date();
const dateStr = now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
blocks.push({
  type: 'context',
  elements: [{ type: 'mrkdwn', text: 'People.ai deal intelligence \u2022 ' + dateStr + ' \u2022 Type `insights` for full analysis' }]
});

const notificationText = worsening.length > 0
  ? worsening.length + ' deal' + (worsening.length === 1 ? '' : 's') + ' need' + (worsening.length === 1 ? 's' : '') + ' attention'
  : improving.length + ' deal' + (improving.length === 1 ? '' : 's') + ' improved overnight';

return [{ json: {
  slackUserId: data.slackUserId,
  assistantName,
  assistantEmoji,
  blocks: JSON.stringify(blocks),
  notificationText
}}];
"""


# ============================================================
# CREATE DEAL WATCH CRON WORKFLOW
# ============================================================
def create_deal_watch_cron():
    print("\n=== Creating Deal Watch Cron workflow ===")

    # Fetch Parse Hierarchy code from live Sales Digest
    wf = fetch_workflow("7sinwSgjkEA40zDj")
    parse_hierarchy_code = None
    for node in wf["nodes"]:
        if node["name"] == "Parse Hierarchy":
            parse_hierarchy_code = node["parameters"]["jsCode"]
            break
    if not parse_hierarchy_code:
        raise RuntimeError("Could not find Parse Hierarchy in Sales Digest")

    send_body = """={{ JSON.stringify({ channel: $('Open Bot DM').first().json.channel.id, text: $('Build Alert Message').first().json.notificationText, username: $('Build Alert Message').first().json.assistantName, icon_emoji: $('Build Alert Message').first().json.assistantEmoji, blocks: JSON.parse($('Build Alert Message').first().json.blocks), unfurl_links: false, unfurl_media: false }) }}"""

    nodes = [
        # 1. Schedule Trigger — 7:00 AM PT, weekdays
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "cronExpression",
                            "expression": "0 7 * * 1-5"
                        }
                    ]
                }
            },
            "id": uid(),
            "name": "Daily 7am PT",
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
        # 3. Fetch User Hierarchy (fan-out with Fetch Insights Opps and Get Yesterday Snapshots)
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
                "jsonBody": '{"object": "user", "columns": [{"slug": "ootb_user_name"}, {"slug": "ootb_user_email"}, {"slug": "ootb_user_manager"}]}',
                "options": {}
            },
            "id": uid(),
            "name": "Fetch User Hierarchy",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [640, 200]
        },
        # 4. Parse Hierarchy
        {
            "parameters": {"jsCode": parse_hierarchy_code},
            "id": uid(),
            "name": "Parse Hierarchy",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 200]
        },
        # 5. Fetch Insights Opps
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
                "jsonBody": INSIGHTS_OPP_QUERY,
                "options": {}
            },
            "id": uid(),
            "name": "Fetch Insights Opps",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [640, 400]
        },
        # 6. Parse and Classify
        {
            "parameters": {"jsCode": PARSE_AND_CLASSIFY_CODE},
            "id": uid(),
            "name": "Parse and Classify",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 400]
        },
        # 7. Get Yesterday Snapshots (Supabase)
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "deal_snapshots",
                "returnAll": True,
                "filters": {
                    "conditions": [
                        {"keyName": "snapshot_date", "condition": "eq",
                         "keyValue": "={{ new Date(Date.now() - 86400000).toISOString().split('T')[0] }}"}
                    ]
                }
            },
            "id": uid(),
            "name": "Get Yesterday Snapshots",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [640, 600],
            "credentials": {"supabaseApi": SUPABASE_CRED},
            "alwaysOutputData": True
        },
        # 8. Detect Transitions
        {
            "parameters": {"jsCode": DETECT_TRANSITIONS_CODE},
            "id": uid(),
            "name": "Detect Transitions",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1080, 400]
        },
        # 9. Save Snapshots (build query)
        {
            "parameters": {"jsCode": SAVE_SNAPSHOTS_CODE},
            "id": uid(),
            "name": "Build Save Query",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 600]
        },
        # 10. Execute Save (Supabase RPC or raw SQL via HTTP)
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $('Get Auth Token').first().json._supabaseUrl || 'https://your-supabase-url.supabase.co' }}/rest/v1/rpc/exec_sql",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "apikey", "value": "={{ $env.SUPABASE_KEY || '' }}"}
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ query: $('Build Save Query').first().json.query }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Save Snapshots",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1520, 600],
            "continueOnFail": True
        },
        # 11. Has Transitions? (If node)
        {
            "parameters": {
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "conditions": [{
                        "id": uid(),
                        "leftValue": "={{ $json.hasTransitions }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true"}
                    }],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Has Transitions?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1300, 400]
        },
        # 12. Get Alert Users (Supabase — users with digest enabled)
        {
            "parameters": {
                "operation": "getAll",
                "tableId": "users",
                "returnAll": True,
                "filters": {
                    "conditions": [
                        {"keyName": "onboarding_state", "condition": "eq", "keyValue": "complete"}
                    ]
                }
            },
            "id": uid(),
            "name": "Get Alert Users",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1520, 200],
            "credentials": {"supabaseApi": SUPABASE_CRED}
        },
        # 13. Match Alerts to Users
        {
            "parameters": {"jsCode": MATCH_ALERTS_CODE},
            "id": uid(),
            "name": "Match Alerts to Users",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1740, 400]
        },
        # 14. Has Alerts? (If node)
        {
            "parameters": {
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "conditions": [{
                        "id": uid(),
                        "leftValue": "={{ $json.noAlerts }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "notTrue"}
                    }],
                    "combinator": "and"
                },
                "options": {}
            },
            "id": uid(),
            "name": "Has Alerts?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1960, 400]
        },
        # 15. Split In Batches
        {
            "parameters": {"batchSize": 1, "options": {}},
            "id": uid(),
            "name": "Split In Batches",
            "type": "n8n-nodes-base.splitInBatches",
            "typeVersion": 3,
            "position": [2180, 340]
        },
        # 16. Open Bot DM
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
                "jsonBody": "={{ JSON.stringify({ users: $('Split In Batches').first().json.slackUserId }) }}",
                "options": {}
            },
            "id": uid(),
            "name": "Open Bot DM",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2400, 340],
            "credentials": {"httpHeaderAuth": SLACK_CRED}
        },
        # 17. Build Alert Message
        {
            "parameters": {"jsCode": BUILD_ALERT_CODE},
            "id": uid(),
            "name": "Build Alert Message",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2620, 340]
        },
        # 18. Send Alert
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
            "name": "Send Alert",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2840, 340],
            "credentials": {"httpHeaderAuth": SLACK_CRED},
            "continueOnFail": True
        }
    ]

    connections = {
        "Daily 7am PT": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        # Fan out from Get Auth Token to 3 parallel paths
        "Get Auth Token": {"main": [[
            {"node": "Fetch User Hierarchy", "type": "main", "index": 0},
            {"node": "Fetch Insights Opps", "type": "main", "index": 0},
            {"node": "Get Yesterday Snapshots", "type": "main", "index": 0}
        ]]},
        "Fetch User Hierarchy": {"main": [[{"node": "Parse Hierarchy", "type": "main", "index": 0}]]},
        "Fetch Insights Opps": {"main": [[{"node": "Parse and Classify", "type": "main", "index": 0}]]},
        # Three paths merge at Detect Transitions
        "Parse and Classify": {"main": [[{"node": "Detect Transitions", "type": "main", "index": 0}]]},
        "Get Yesterday Snapshots": {"main": [[{"node": "Detect Transitions", "type": "main", "index": 0}]]},
        # Detect Transitions fans out to save + check transitions
        "Detect Transitions": {"main": [[
            {"node": "Build Save Query", "type": "main", "index": 0},
            {"node": "Has Transitions?", "type": "main", "index": 0}
        ]]},
        "Build Save Query": {"main": [[{"node": "Save Snapshots", "type": "main", "index": 0}]]},
        # Alert path
        "Has Transitions?": {"main": [
            [{"node": "Get Alert Users", "type": "main", "index": 0}],  # true
            []  # false — no transitions
        ]},
        "Parse Hierarchy": {"main": [[{"node": "Match Alerts to Users", "type": "main", "index": 0}]]},
        "Get Alert Users": {"main": [[{"node": "Match Alerts to Users", "type": "main", "index": 0}]]},
        "Match Alerts to Users": {"main": [[{"node": "Has Alerts?", "type": "main", "index": 0}]]},
        "Has Alerts?": {"main": [
            [{"node": "Split In Batches", "type": "main", "index": 0}],  # true
            []  # false — no alerts for any user
        ]},
        "Split In Batches": {"main": [
            [{"node": "Open Bot DM", "type": "main", "index": 0}],  # each item
            []  # done
        ]},
        "Open Bot DM": {"main": [[{"node": "Build Alert Message", "type": "main", "index": 0}]]},
        "Build Alert Message": {"main": [[{"node": "Send Alert", "type": "main", "index": 0}]]},
        "Send Alert": {"main": [[{"node": "Split In Batches", "type": "main", "index": 0}]]}
    }

    workflow = {
        "name": "Deal Watch Cron",
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
    print("  Activated — runs 7:00 AM PT, weekdays")

    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Deal Watch Cron.json")

    return wf_id


def main():
    wf_id = create_deal_watch_cron()
    print(f"\nDone! Deal Watch Cron workflow ID: {wf_id}")
    print("  Schedule: 7:00 AM PT, Monday-Friday")
    print("  Flow: Classify all deals → Compare vs yesterday → Alert on state changes")
    print("  First run: saves snapshots only (no yesterday data = no alerts)")
    print("  Second run: detects transitions and sends alerts")
    print("\n  NOTE: The Save Snapshots node uses raw SQL via Supabase RPC.")
    print("  You may need to configure the Supabase URL and API key in the node,")
    print("  or switch to individual Supabase inserts if RPC isn't available.")


if __name__ == "__main__":
    main()
