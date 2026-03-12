#!/usr/bin/env python3
"""
Add 'insights' command to Slack Events Handler + create Opportunity Insights sub-workflow.
- Two-layer pattern: Export API (quantitative classification) → MCP (qualitative story)
- Types: stalled, risk, hidden, accelerating, all
- Scope-aware: my_deals, team_deals, top_pipeline
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


def sync_local(wf, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(wf, f, indent=4)
    print(f"  Synced {path}")


def get_live_code():
    """Fetch reusable code from live Sales Digest."""
    wf = fetch_workflow("7sinwSgjkEA40zDj")
    parse_hierarchy_code = None
    parse_blocks_code = None
    for node in wf["nodes"]:
        if node["name"] == "Parse Hierarchy":
            parse_hierarchy_code = node["parameters"]["jsCode"]
        elif node["name"] == "Parse Blocks":
            parse_blocks_code = node["parameters"]["jsCode"]
    if not parse_hierarchy_code or not parse_blocks_code:
        raise RuntimeError("Could not find Parse Hierarchy or Parse Blocks in Sales Digest")
    return parse_hierarchy_code, parse_blocks_code


# ============================================================
# Export API queries
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

INSIGHTS_ACCOUNT_QUERY = json.dumps({
    "object": "account",
    "columns": [
        {"slug": "ootb_account_name"},
        {"slug": "ootb_account_original_owner"},
        {"slug": "ootb_account_engagement_level"},
        {"slug": "ootb_account_open_opportunities"},
        {"slug": "ootb_account_count_of_meetings_standard"},
        {"slug": "ootb_account_people_engaged"},
        {"slug": "ootb_account_executive_engaged"},
        {"slug": "ootb_account_executive_activities"},
        {"slug": "ootb_account_crm_id"}
    ]
})


# ============================================================
# Parse Insights CSV — expanded opportunity columns
# ============================================================
PARSE_INSIGHTS_CSV_CODE = r"""const csvData = $('Fetch Insights Opps').first().json.data;

if (!csvData) {
  return [{ json: { opps: [], oppCount: 0, error: 'No opportunity data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { opps: [], oppCount: 0 } }];
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

const opps = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;

  opps.push({
    owners: get(row, 'Owners', 'Owner'),
    name: get(row, 'Opportunity Name', 'Name'),
    account: get(row, 'Account Name', 'Account'),
    closeDate: get(row, 'Close Date'),
    stage: get(row, 'Current Stage', 'Stage'),
    amount: get(row, 'Converted Amount', 'Amount'),
    crmId: get(row, 'CRM ID', 'Opportunity CRM ID', 'CRM Id'),
    engagement: get(row, 'Engagement Level', 'Engagement'),
    daysInStage: get(row, 'Days In Stage', 'Days in Stage'),
    meetings30d: get(row, 'Count Of Meetings Standard', 'Meetings', 'Count of Meetings', 'Count Of Meetings'),
    upcomingMeetings: get(row, 'Upcoming Meetings Standard', 'Upcoming Meetings'),
    emailsReceived: get(row, 'Count Of Emails Received', 'Emails Received', 'Count of Emails Received'),
    emailsSent: get(row, 'Count Of Emails Sent', 'Emails Sent', 'Count of Emails Sent'),
    execActivities: get(row, 'Executive Activities', 'Exec Activities'),
    execMeetings: get(row, 'Meetings With Director VP Exec', 'Executive Meetings', 'Director+ Meetings',
                       'Meetings With Director Vp Exec', 'Meetings with Director/VP/Exec'),
    peopleEngaged: get(row, 'People Engaged', 'Contacts Engaged'),
    totalActivities: get(row, 'Total Activities Count', 'Total Activities')
  });
}

return [{ json: { opps, oppCount: opps.length, headers: headers } }];
"""


# ============================================================
# Parse Account CSV — for Hidden Opportunity detection
# ============================================================
PARSE_ACCOUNT_CSV_CODE = r"""// Parse account data for Hidden Opp classification
// Handles cases where API query might fail or return no data
const input = $('Fetch Account Data').first().json;
const csvData = input.data;

if (!csvData) {
  return [{ json: { accounts: [], accountCount: 0, error: input.error || 'No account data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { accounts: [], accountCount: 0 } }];
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

const allAccounts = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;

  allAccounts.push({
    name: get(row, 'Account Name', 'Name', 'Account'),
    owner: get(row, 'Original Owner', 'Owner'),
    engagement: get(row, 'Engagement Level', 'Engagement'),
    openOpps: get(row, 'Open Opportunities', 'Open Opps'),
    meetings: get(row, 'Count Of Meetings Standard', 'Meetings', 'Count of Meetings'),
    peopleEngaged: get(row, 'People Engaged', 'Contacts Engaged'),
    execEngaged: get(row, 'Executive Engaged', 'Exec Engaged'),
    execActivities: get(row, 'Executive Activities', 'Exec Activities'),
    crmId: get(row, 'CRM ID', 'Account CRM ID', 'CRM Id')
  });
}

// Filter to accounts with zero open opportunities
const hiddenCandidates = allAccounts.filter(a => {
  const openOpps = parseInt(a.openOpps) || 0;
  return openOpps === 0;
});

return [{ json: { accounts: hiddenCandidates, accountCount: hiddenCandidates.length, totalAccounts: allAccounts.length } }];
"""


# ============================================================
# Classify Deals — apply Opportunity Insights formulas
# ============================================================
CLASSIFY_DEALS_CODE = r"""// Apply classification formulas from Opportunity Insights spec
// Merges data from Parse Insights CSV and Parse Account CSV
const oppsData = $('Parse Insights CSV').first().json;
const accountsData = $('Parse Account CSV').first().json;

const opps = oppsData.opps || [];
const accounts = accountsData.accounts || [];

// Null-safe numeric helper
function num(val) {
  if (val === null || val === undefined || val === '') return null;
  const n = parseFloat(String(val).replace(/[^0-9.\-]/g, ''));
  return isNaN(n) ? null : n;
}
function n(val) { return num(val) || 0; }

// Classify each opportunity
const classifiedOpps = opps.map(opp => {
  const engagement = n(opp.engagement);
  const daysInStage = n(opp.daysInStage);
  const meetings30d = n(opp.meetings30d);
  const upcomingMeetings = n(opp.upcomingMeetings);
  const emailsReceived = n(opp.emailsReceived);
  const emailsSent = n(opp.emailsSent);
  const execActivities = n(opp.execActivities);
  const execMeetings = n(opp.execMeetings);
  const peopleEngaged = n(opp.peopleEngaged);
  const totalActivities = n(opp.totalActivities);

  // Derived metrics
  const emailResponsiveness = emailsSent > 0 ? emailsReceived / emailsSent : 0;
  const totalMeetings = meetings30d + (n(opp.execMeetings) || 0);
  const execCoverage = totalMeetings > 0 ? 100 * execMeetings / totalMeetings : 0;
  const stakeholderBreadth = daysInStage > 7 ? peopleEngaged / (daysInStage / 7) : peopleEngaged;

  let classification = 'healthy';
  let flags = [];

  // === STALLED check ===
  const isStalled = engagement < 25 ||
    (engagement < 50 && daysInStage > 45 && meetings30d === 0);

  if (isStalled) {
    classification = 'stalled';
    if (engagement < 25) flags.push('Very low engagement (' + engagement + ')');
    if (daysInStage > 45) flags.push('Stuck in stage ' + daysInStage + ' days');
    if (meetings30d === 0) flags.push('No meetings in 30 days');
  }

  // === RISK check (only if not stalled) ===
  if (classification === 'healthy') {
    let riskSignals = 0;
    let riskFlags = [];
    if (execActivities === 0) { riskSignals++; riskFlags.push('No exec engagement'); }
    if (emailResponsiveness < 0.3 && emailsSent > 0) { riskSignals++; riskFlags.push('Low email response (' + emailResponsiveness.toFixed(2) + ')'); }
    if (peopleEngaged < 3) { riskSignals++; riskFlags.push('Single-threaded (' + peopleEngaged + ' contacts)'); }
    if (execCoverage < 10 && totalMeetings > 0) { riskSignals++; riskFlags.push('Below power line (' + execCoverage.toFixed(0) + '% exec)'); }

    if (riskSignals >= 2) {
      classification = 'risk';
      flags = riskFlags;
    }
  }

  // === ACCELERATING check (only if still healthy) ===
  if (classification === 'healthy') {
    let accelSignals = 0;
    let accelFlags = [];
    if (upcomingMeetings >= 2) { accelSignals++; accelFlags.push(upcomingMeetings + ' upcoming meetings'); }
    if (execActivities >= 3) { accelSignals++; accelFlags.push(execActivities + ' exec activities'); }
    if (meetings30d >= 4) { accelSignals++; accelFlags.push(meetings30d + ' meetings in 30d'); }

    if (engagement >= 70 && accelSignals >= 2) {
      classification = 'accelerating';
      flags = accelFlags;
    }
  }

  return {
    ...opp,
    classification,
    flags,
    derivedMetrics: {
      engagement, daysInStage, meetings30d, upcomingMeetings,
      emailResponsiveness: emailResponsiveness.toFixed(2),
      execCoverage: execCoverage.toFixed(1),
      stakeholderBreadth: stakeholderBreadth.toFixed(2),
      execActivities, peopleEngaged, totalActivities
    }
  };
});

// Classify accounts for Hidden Opps
const hiddenAccounts = accounts.filter(acct => {
  const engagement = n(acct.engagement);
  const meetings = n(acct.meetings);
  return engagement >= 50 && meetings > 0;
}).map(acct => ({
  ...acct,
  classification: 'hidden',
  flags: ['High engagement (' + n(acct.engagement) + ') with ' + n(acct.meetings) + ' meetings but no open opportunity']
}));

const counts = {
  stalled: classifiedOpps.filter(o => o.classification === 'stalled').length,
  risk: classifiedOpps.filter(o => o.classification === 'risk').length,
  healthy: classifiedOpps.filter(o => o.classification === 'healthy').length,
  accelerating: classifiedOpps.filter(o => o.classification === 'accelerating').length,
  hidden: hiddenAccounts.length,
  total: classifiedOpps.length
};

return [{ json: { classifiedOpps, hiddenAccounts, counts } }];
"""


# ============================================================
# Filter by Scope — scope filtering + build tables per classification
# ============================================================
FILTER_INSIGHTS_SCOPE_CODE = r"""const data = $('Classify Deals').first().json;
const input = $('Workflow Input Trigger').first().json;
const hierarchyData = $('Parse Hierarchy').first().json;

const classifiedOpps = data.classifiedOpps || [];
const hiddenAccounts = data.hiddenAccounts || [];

// Support both passthrough (camelCase/nested) and explicit inputData (snake_case/flat)
const ur = input.userRecord || {};
const userEmail = (ur.email || input.email || '').toLowerCase();
const repName = userEmail.split('@')[0]
  .replace(/\./g, ' ')
  .replace(/\b\w/g, c => c.toUpperCase());
const repLower = repName.toLowerCase();
const digestScope = ur.digest_scope || input.digest_scope || 'my_deals';
const insightType = input.insightType || 'all';

let filteredOpps = classifiedOpps;
let filteredAccounts = hiddenAccounts;
let scopeLabel = '';

// === Scope-based filtering ===
if (digestScope === 'my_deals') {
  filteredOpps = classifiedOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return owners.includes(repLower);
  });
  filteredAccounts = hiddenAccounts.filter(acct => {
    const owner = (acct.owner || '').toLowerCase();
    return owner.includes(repLower);
  });
  scopeLabel = repName + "'s deals";

} else if (digestScope === 'team_deals') {
  const managerToReports = hierarchyData.managerToReports || {};
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

  filteredOpps = classifiedOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return reportNames.some(name => owners.includes(name));
  });
  filteredAccounts = hiddenAccounts.filter(acct => {
    const owner = (acct.owner || '').toLowerCase();
    return reportNames.some(name => owner.includes(name));
  });
  scopeLabel = repName + "'s team (" + reportNames.length + " reps)";

} else {
  scopeLabel = "Full pipeline";
}

// === Build tables per classification ===
function buildOppTable(opps, includeFlags) {
  if (opps.length === 0) return '(none)';
  let table = '| Opportunity | Account | Owner | Stage | Engagement | CRM ID |' + (includeFlags ? ' Flags |' : '') + '\n';
  table += '|---|---|---|---|---|---|' + (includeFlags ? '---|' : '') + '\n';
  for (const opp of opps) {
    table += '| ' + (opp.name || '') + ' | ' + (opp.account || '') + ' | ' + (opp.owners || '') +
      ' | ' + (opp.stage || '') + ' | ' + (opp.engagement || '') + ' | ' + (opp.crmId || '') +
      (includeFlags ? ' | ' + (opp.flags || []).join('; ') : '') + ' |\n';
  }
  return table;
}

function buildAccountTable(accounts) {
  if (accounts.length === 0) return '(none)';
  let table = '| Account | Owner | Engagement | Meetings | People Engaged | CRM ID | Flags |\n';
  table += '|---|---|---|---|---|---|---|\n';
  for (const acct of accounts) {
    table += '| ' + (acct.name || '') + ' | ' + (acct.owner || '') + ' | ' + (acct.engagement || '') +
      ' | ' + (acct.meetings || '') + ' | ' + (acct.peopleEngaged || '') + ' | ' + (acct.crmId || '') +
      ' | ' + (acct.flags || []).join('; ') + ' |\n';
  }
  return table;
}

const stalledDeals = filteredOpps.filter(o => o.classification === 'stalled');
const riskDeals = filteredOpps.filter(o => o.classification === 'risk');
const acceleratingDeals = filteredOpps.filter(o => o.classification === 'accelerating');
const healthyDeals = filteredOpps.filter(o => o.classification === 'healthy');

const stalledTable = buildOppTable(stalledDeals, true);
const riskTable = buildOppTable(riskDeals, true);
const acceleratingTable = buildOppTable(acceleratingDeals, true);
const hiddenTable = buildAccountTable(filteredAccounts);

const scopedCounts = {
  stalled: stalledDeals.length,
  risk: riskDeals.length,
  healthy: healthyDeals.length,
  accelerating: acceleratingDeals.length,
  hidden: filteredAccounts.length,
  total: filteredOpps.length
};

const summaryLine = 'Pipeline: ' + scopedCounts.total + ' deals (' +
  scopedCounts.stalled + ' stalled, ' +
  scopedCounts.risk + ' at risk, ' +
  scopedCounts.healthy + ' healthy, ' +
  scopedCounts.accelerating + ' accelerating) + ' +
  scopedCounts.hidden + ' hidden opportunity accounts';

return [{ json: {
  insightType,
  repName,
  scopeLabel,
  digestScope,
  stalledTable, stalledCount: stalledDeals.length,
  riskTable, riskCount: riskDeals.length,
  acceleratingTable, acceleratingCount: acceleratingDeals.length,
  hiddenTable, hiddenCount: filteredAccounts.length,
  healthyCount: healthyDeals.length,
  totalOppCount: filteredOpps.length,
  summaryLine,
  // Pass top deals for MCP investigation hints
  topStalled: stalledDeals.slice(0, 5).map(d => d.name),
  topRisk: riskDeals.slice(0, 5).map(d => d.name),
  topAccel: acceleratingDeals.slice(0, 5).map(d => d.name),
  topHidden: filteredAccounts.slice(0, 5).map(d => d.name)
}}];
"""


# ============================================================
# Resolve Insights Identity — build prompts per insight type
# ============================================================
RESOLVE_INSIGHTS_IDENTITY_CODE = r"""const data = $('Filter by Scope').first().json;
const input = $('Workflow Input Trigger').first().json;

// Support both passthrough (camelCase/nested) and explicit inputData (snake_case/flat)
const ur = input.userRecord || {};
const assistantName = input.assistantName || ur.assistant_name || input.assistant_name || 'Aria';
const assistantEmoji = input.assistantEmoji || ur.assistant_emoji || input.assistant_emoji || ':robot_face:';
const assistantPersona = ur.assistant_persona || input.assistant_persona || 'direct, action-oriented, and conversational';
const repName = data.repName || 'Rep';
const timezone = ur.timezone || input.timezone || 'America/Los_Angeles';
const currentDate = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
const timeStr = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: timezone });
const emojiClean = assistantEmoji.replace(/:/g, '');

const insightType = data.insightType || 'all';
const scopeLabel = data.scopeLabel || '';
const digestScope = data.digestScope || 'my_deals';
const summaryLine = data.summaryLine || '';

// === Block Kit formatting rules ===
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
- Use "divider" blocks between major sections (maximum 3 per message)
- Use "section" with "fields" for two-column data
  - MAXIMUM 10 fields per section block (Slack API hard limit)
  - If you have more than 10 data points, split into multiple section blocks
- Use "context" block at the bottom for timestamp and data source
- Maximum 50 blocks per message

MRKDWN RULES (inside all text fields):
- Bold: *text* — single asterisks only
- Line break: \n
- Blank line: \n\n
- Bullet points: use the \u2022 character on its own line
- NO ## headers — use *bold text* on its own line instead
- NO **double asterisks**
- NO standard markdown links [text](url) — use <https://url|text>
- NO dash bullets (-)

DEEP LINKS — make the deal or account NAME itself a clickable link. Do NOT add a separate "View in People.ai" line.
- For opportunities: <https://app.people.ai/opportunities/CRMID|Deal Name Here> (replace CRMID with the CRM ID from the data table, and "Deal Name Here" with the actual opportunity name)
- For accounts: <https://app.people.ai/accounts/CRMID|Account Name Here>
- Example: *<https://app.people.ai/opportunities/006abc123|PwC - ClosePlan Pilot>* | Closes May 31

EMOJI STATUS INDICATORS — use these consistently:
\ud83d\ude80 Acceleration / strong momentum
\u26a0\ufe0f Risk pattern detected
\ud83d\udc8e Hidden upside opportunity
\ud83d\udd34 Stalled / critical risk
\u2705 Healthy / on track
\ud83d\udcc8 Engagement rising
\ud83d\udcc9 Engagement falling`;

// === Scope-aware role intro ===
function buildRoleIntro() {
  if (digestScope === 'my_deals') {
    return `You are ${assistantName}, a personal sales intelligence analyst for ${repName}. You help them see what's really happening in their pipeline using quantitative signals.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.
Scope: ${scopeLabel}`;
  } else if (digestScope === 'team_deals') {
    return `You are ${assistantName}, a sales management intelligence analyst for ${repName}. You help them lead their team by surfacing pipeline risks and opportunities using quantitative signals.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.
Scope: ${scopeLabel}`;
  } else {
    return `You are ${assistantName}, an executive pipeline intelligence analyst for ${repName}. You provide strategic pipeline visibility using quantitative classification signals.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.
Scope: ${scopeLabel}`;
  }
}

const footer = digestScope === 'team_deals'
  ? `People.ai team intelligence \u2022 ${currentDate} \u2022 ${timeStr} PT`
  : digestScope === 'top_pipeline'
    ? `People.ai executive intelligence \u2022 ${currentDate} \u2022 ${timeStr} PT`
    : `People.ai pipeline intelligence \u2022 ${currentDate} \u2022 ${timeStr} PT`;

// === Build type-specific prompts ===
function buildPrompts(type) {
  const roleIntro = buildRoleIntro();

  if (type === 'stalled') {
    const systemPrompt = roleIntro + `

\u2501\u2501\u2501 CLASSIFICATION SUMMARY \u2501\u2501\u2501
${summaryLine}

\u2501\u2501\u2501 STALLED DEALS (${data.stalledCount}) \u2501\u2501\u2501
Classification: engagement < 25, OR (engagement < 50 AND days_in_stage > 45 AND no meetings in 30d)
${data.stalledTable}

You have access to People.ai MCP tools. Use them ONLY for qualitative context on the top 3-5 stalled deals:
- Recent activity timeline (when did engagement drop?)
- Stakeholder analysis (who is/isn't engaged?)
- Historical patterns (has this account gone cold before?)

Do NOT use MCP to list or search for opportunities \u2014 they are already classified above.

Write a pipeline intelligence briefing as a recovery specialist:

1. Header \u2014 "${emojiClean} Stalled Deals \u2014 ${assistantName}"
2. Stall Summary (2-3 sentences) \u2014 how many deals are stalled, total value at risk, common patterns
3. Recovery Priority (top 3-5 deals) \u2014 for each: what stalled, how long, recommended recovery action. Make the deal name a clickable People.ai link. Use \ud83d\udd34 \u26a0\ufe0f indicators.
4. Patterns \u2014 common stall signals across deals (single-threaded, no exec, dark accounts)
5. Recovery Playbook \u2014 2-3 concrete actions to revive the highest-value stalled deals this week
6. Context footer \u2014 "${footer}"

${blockKitRules}`;

    const agentPrompt = `Generate a stalled deals intelligence report for ${repName}. ${data.stalledCount} stalled deals are loaded in your system prompt.

Use People.ai MCP tools to investigate the top ${Math.min(data.stalledCount, 5)} stalled deals: look for when engagement dropped, who the last contacts were, and any signals of life.

Output ONLY the Block Kit JSON object, nothing else.`;

    return { systemPrompt, agentPrompt };
  }

  if (type === 'risk') {
    const systemPrompt = roleIntro + `

\u2501\u2501\u2501 CLASSIFICATION SUMMARY \u2501\u2501\u2501
${summaryLine}

\u2501\u2501\u2501 AT-RISK DEALS (${data.riskCount}) \u2501\u2501\u2501
Classification: 2+ risk signals from (no exec engagement, email responsiveness < 0.3, < 3 people engaged, exec coverage < 10%)
${data.riskTable}

You have access to People.ai MCP tools. Use them ONLY for qualitative context on the top 3-5 at-risk deals:
- Risk signal validation (confirm the quantitative flags with activity data)
- Stakeholder map (who should be engaged but isn't?)
- Competitive signals or deal blockers

Do NOT use MCP to list or search for opportunities.

Write a pipeline intelligence briefing as a risk analyst:

1. Header \u2014 "${emojiClean} At-Risk Deals \u2014 ${assistantName}"
2. Risk Summary (2-3 sentences) \u2014 how many deals at risk, total value exposed, most common risk signals
3. Critical Risks (top 3-5 deals) \u2014 for each: specific risk signals, severity, recommended mitigation. Make the deal name a clickable People.ai link. Use \u26a0\ufe0f \ud83d\udd34 indicators.
4. Risk Patterns \u2014 systemic issues across at-risk deals (e.g., exec engagement gap, single-threading)
5. Mitigation Plan \u2014 2-3 prioritized actions to address the biggest risks this week
6. Context footer \u2014 "${footer}"

${blockKitRules}`;

    const agentPrompt = `Generate an at-risk deals intelligence report for ${repName}. ${data.riskCount} at-risk deals are loaded.

Use People.ai MCP tools to validate risk signals on the top ${Math.min(data.riskCount, 5)} at-risk deals: check activity gaps, stakeholder coverage, and engagement trends.

Output ONLY the Block Kit JSON object, nothing else.`;

    return { systemPrompt, agentPrompt };
  }

  if (type === 'hidden') {
    const systemPrompt = roleIntro + `

\u2501\u2501\u2501 CLASSIFICATION SUMMARY \u2501\u2501\u2501
${summaryLine}

\u2501\u2501\u2501 HIDDEN OPPORTUNITY ACCOUNTS (${data.hiddenCount}) \u2501\u2501\u2501
Classification: engagement >= 50 AND meetings > 0 AND zero open opportunities
These are accounts showing buying signals but with no opportunity created in CRM.
${data.hiddenTable}

You have access to People.ai MCP tools. Use them ONLY for qualitative context on the top 3-5 hidden opportunity accounts:
- Recent activity details (who is meeting with whom?)
- Account history (any past opportunities, closed-lost deals?)
- Engagement trajectory (rising or stable?)

Do NOT use MCP to list or search for opportunities.

Write a pipeline intelligence briefing as a pipeline advisor:

1. Header \u2014 "${emojiClean} Hidden Opportunities \u2014 ${assistantName}"
2. Discovery Summary (2-3 sentences) \u2014 how many hidden opp accounts found, what engagement signals suggest
3. Top Discoveries (top 3-5 accounts) \u2014 for each: engagement level, who is active, what suggests an opportunity. Make the deal name a clickable People.ai link. Use \ud83d\udc8e \ud83d\udcc8 indicators.
4. Why These Matter \u2014 what the engagement data tells us about buying intent
5. Next Steps \u2014 2-3 actions to qualify and convert the highest-potential hidden opportunities
6. Context footer \u2014 "${footer}"

${blockKitRules}`;

    const agentPrompt = `Generate a hidden opportunities intelligence report for ${repName}. ${data.hiddenCount} accounts with high engagement but no open opportunities are loaded.

Use People.ai MCP tools to investigate the top ${Math.min(data.hiddenCount, 5)} accounts: look for recent meeting activity, past deal history, and engagement patterns that suggest buying intent.

Output ONLY the Block Kit JSON object, nothing else.`;

    return { systemPrompt, agentPrompt };
  }

  if (type === 'accelerating') {
    const systemPrompt = roleIntro + `

\u2501\u2501\u2501 CLASSIFICATION SUMMARY \u2501\u2501\u2501
${summaryLine}

\u2501\u2501\u2501 ACCELERATING DEALS (${data.acceleratingCount}) \u2501\u2501\u2501
Classification: engagement >= 70 AND 2+ acceleration signals (upcoming meetings >= 2, exec activities >= 3, meetings in 30d >= 4)
${data.acceleratingTable}

You have access to People.ai MCP tools. Use them ONLY for qualitative context on the top 3-5 accelerating deals:
- Momentum validation (confirm velocity with activity data)
- Stakeholder engagement depth (multithreaded? exec sponsor?)
- Close readiness signals (what needs to happen to close?)

Do NOT use MCP to list or search for opportunities.

Write a pipeline intelligence briefing as a close specialist:

1. Header \u2014 "${emojiClean} Accelerating Deals \u2014 ${assistantName}"
2. Momentum Summary (2-3 sentences) \u2014 how many deals accelerating, total value in motion, key drivers
3. Top Movers (top 3-5 deals) \u2014 for each: acceleration signals, engagement strength, what to do to maintain momentum. Make the deal name a clickable People.ai link. Use \ud83d\ude80 \ud83d\udd25 \u2705 indicators.
4. Acceleration Patterns \u2014 what's working across these deals (exec engagement, meeting cadence, multithreading)
5. Close Playbook \u2014 2-3 actions to keep momentum and accelerate toward close
6. Context footer \u2014 "${footer}"

${blockKitRules}`;

    const agentPrompt = `Generate an accelerating deals intelligence report for ${repName}. ${data.acceleratingCount} accelerating deals are loaded.

Use People.ai MCP tools to validate momentum on the top ${Math.min(data.acceleratingCount, 5)} deals: check recent activity cadence, stakeholder depth, and close readiness.

Output ONLY the Block Kit JSON object, nothing else.`;

    return { systemPrompt, agentPrompt };
  }

  // === ALL — comprehensive intelligence report ===
  const systemPrompt = roleIntro + `

\u2501\u2501\u2501 PIPELINE CLASSIFICATION \u2501\u2501\u2501
${summaryLine}

\u2501\u2501\u2501 STALLED (${data.stalledCount}) \u2501\u2501\u2501
${data.stalledTable}

\u2501\u2501\u2501 AT RISK (${data.riskCount}) \u2501\u2501\u2501
${data.riskTable}

\u2501\u2501\u2501 ACCELERATING (${data.acceleratingCount}) \u2501\u2501\u2501
${data.acceleratingTable}

\u2501\u2501\u2501 HIDDEN OPPORTUNITIES (${data.hiddenCount}) \u2501\u2501\u2501
${data.hiddenTable}

Healthy deals: ${data.healthyCount} (not shown \u2014 no action needed)

You have access to People.ai MCP tools. Use them to investigate the top 2-3 deals in each category for qualitative context.
Do NOT use MCP to list or search for opportunities \u2014 they are already classified above.

Write a comprehensive pipeline intelligence briefing:

1. Header \u2014 "${emojiClean} Pipeline Intelligence \u2014 ${assistantName}"
2. Pipeline Pulse (2-3 sentences) \u2014 overall health, biggest risks, biggest opportunities
3. \ud83d\udd34 Stalled Deals \u2014 top 2-3 stalled deals with recovery recommendations. Make deal names clickable People.ai links.
4. \u26a0\ufe0f At-Risk Deals \u2014 top 2-3 at-risk deals with mitigation steps. Include deep links.
5. \ud83d\ude80 Accelerating Deals \u2014 top 2-3 deals with momentum. What to do to close. Include deep links.
6. \ud83d\udc8e Hidden Opportunities \u2014 top 2-3 accounts with no opp but high engagement. Include deep links.
7. This Week's Actions \u2014 3-5 prioritized actions across all categories
8. Context footer \u2014 "${footer}"

${blockKitRules}`;

  const agentPrompt = `Generate a comprehensive pipeline intelligence report for ${repName}. All deals are classified and loaded above across 4 categories.

Use People.ai MCP tools to investigate the top 2-3 deals in each category: validate signals, get recent activity context, and assess deal/account health.

Output ONLY the Block Kit JSON object, nothing else.`;

  return { systemPrompt, agentPrompt };
}

const { systemPrompt, agentPrompt } = buildPrompts(insightType);

return [{ json: {
  userId: input.dbUserId || input.id,
  slackUserId: input.userId || input.slack_user_id,
  channelId: input.channelId,
  assistantName,
  assistantEmoji,
  repName,
  insightType,
  systemPrompt,
  agentPrompt
}}];
"""


# ============================================================
# Parse Insights Command — Events Handler routing
# ============================================================
PARSE_INSIGHTS_CMD_CODE = r"""const data = $('Route by State').first().json;
const text = (data.text || '').toLowerCase().trim();
const insightArg = text.replace(/^insights?\s*/, '').trim();

const typeAliases = {
  'stalled': 'stalled', 'stall': 'stalled', 'stuck': 'stalled',
  'risk': 'risk', 'risks': 'risk', 'at-risk': 'risk', 'at risk': 'risk',
  'hidden': 'hidden', 'ghost': 'hidden', 'ghosts': 'hidden',
  'accelerating': 'accelerating', 'accel': 'accelerating', 'fast': 'accelerating', 'hot': 'accelerating',
  'all': 'all', '': 'all'
};

const typeLabels = {
  'stalled': 'Stalled Deals',
  'risk': 'At-Risk Deals',
  'hidden': 'Hidden Opportunities',
  'accelerating': 'Accelerating Deals',
  'all': 'Full Pipeline Intelligence'
};

let insightType = typeAliases[insightArg] || null;
let responseText = '';

if (!insightType) {
  responseText = data.assistantEmoji + " I didn\u2019t recognize that insight type. Try:\n\n" +
    "\u2022 `insights` \u2014 full pipeline intelligence\n" +
    "\u2022 `insights stalled` \u2014 deals losing momentum\n" +
    "\u2022 `insights risk` \u2014 emerging threats\n" +
    "\u2022 `insights hidden` \u2014 accounts without opportunities\n" +
    "\u2022 `insights accelerating` \u2014 deals ready to close";
}

return [{
  json: {
    ...data,
    insightType,
    insightLabel: insightType ? typeLabels[insightType] : null,
    isValid: !!insightType,
    responseText
  }
}];
"""


# ============================================================
# CREATE OPPORTUNITY INSIGHTS SUB-WORKFLOW
# ============================================================
def create_insights_workflow():
    print("\n=== Creating Opportunity Insights workflow ===")

    parse_hierarchy_code, parse_blocks_code = get_live_code()

    # Fix agent name reference — Sales Digest uses "Digest Agent", we use "Insights Agent"
    parse_blocks_code = parse_blocks_code.replace("Digest Agent", "Insights Agent")

    send_body = """={{ JSON.stringify({ channel: $('Workflow Input Trigger').first().json.channelId, text: $('Parse Blocks').first().json.notificationText, username: $('Resolve Insights Identity').first().json.assistantName, icon_emoji: $('Resolve Insights Identity').first().json.assistantEmoji, blocks: JSON.parse($('Parse Blocks').first().json.blocks), unfurl_links: false, unfurl_media: false }) }}"""

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
        # 3. Fetch User Hierarchy (fan-out path 1)
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
        # 5. Fetch Insights Opps (fan-out path 2 — expanded columns)
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
        # 6. Parse Insights CSV
        {
            "parameters": {"jsCode": PARSE_INSIGHTS_CSV_CODE},
            "id": uid(),
            "name": "Parse Insights CSV",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 400]
        },
        # 7. Fetch Account Data (fan-out path 3 — for Hidden Opps)
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
                "jsonBody": INSIGHTS_ACCOUNT_QUERY,
                "options": {}
            },
            "id": uid(),
            "name": "Fetch Account Data",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [640, 600],
            "continueOnFail": True
        },
        # 8. Parse Account CSV
        {
            "parameters": {"jsCode": PARSE_ACCOUNT_CSV_CODE},
            "id": uid(),
            "name": "Parse Account CSV",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [860, 600]
        },
        # 9. Classify Deals
        {
            "parameters": {"jsCode": CLASSIFY_DEALS_CODE},
            "id": uid(),
            "name": "Classify Deals",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1080, 400]
        },
        # 10. Filter by Scope
        {
            "parameters": {"jsCode": FILTER_INSIGHTS_SCOPE_CODE},
            "id": uid(),
            "name": "Filter by Scope",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1300, 400]
        },
        # 11. Resolve Insights Identity
        {
            "parameters": {"jsCode": RESOLVE_INSIGHTS_IDENTITY_CODE},
            "id": uid(),
            "name": "Resolve Insights Identity",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1520, 400]
        },
        # 12. Insights Agent
        {
            "parameters": {
                "promptType": "define",
                "text": "={{ $('Resolve Insights Identity').first().json.agentPrompt }}",
                "options": {
                    "systemMessage": "={{ $('Resolve Insights Identity').first().json.systemPrompt }}",
                    "maxIterations": 20
                }
            },
            "id": uid(),
            "name": "Insights Agent",
            "type": "@n8n/n8n-nodes-langchain.agent",
            "typeVersion": 1.7,
            "position": [1740, 400],
            "continueOnFail": True
        },
        # 13. Anthropic Chat Model (sub-node of Insights Agent)
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
            "position": [1748, 624],
            "credentials": {"anthropicApi": ANTHROPIC_CRED}
        },
        # 14. People.ai MCP (sub-node of Insights Agent)
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
            "position": [1876, 624],
            "credentials": {"httpMultipleHeadersAuth": MCP_CRED}
        },
        # 15. Parse Blocks
        {
            "parameters": {"jsCode": parse_blocks_code},
            "id": uid(),
            "name": "Parse Blocks",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1960, 400]
        },
        # 16. Send Insights
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
            "name": "Send Insights",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2180, 400],
            "credentials": {"httpHeaderAuth": SLACK_CRED},
            "continueOnFail": True
        }
    ]

    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        # Sequential: Auth → Hierarchy → Parse → Opps → Parse → Accounts → Parse → Classify
        # All prior nodes accessible via $('NodeName') in Code nodes
        "Get Auth Token": {"main": [[{"node": "Fetch User Hierarchy", "type": "main", "index": 0}]]},
        "Fetch User Hierarchy": {"main": [[{"node": "Parse Hierarchy", "type": "main", "index": 0}]]},
        "Parse Hierarchy": {"main": [[{"node": "Fetch Insights Opps", "type": "main", "index": 0}]]},
        "Fetch Insights Opps": {"main": [[{"node": "Parse Insights CSV", "type": "main", "index": 0}]]},
        "Parse Insights CSV": {"main": [[{"node": "Fetch Account Data", "type": "main", "index": 0}]]},
        "Fetch Account Data": {"main": [[{"node": "Parse Account CSV", "type": "main", "index": 0}]]},
        "Parse Account CSV": {"main": [[{"node": "Classify Deals", "type": "main", "index": 0}]]},
        # Main pipeline continues
        "Classify Deals": {"main": [[{"node": "Filter by Scope", "type": "main", "index": 0}]]},
        "Filter by Scope": {"main": [[{"node": "Resolve Insights Identity", "type": "main", "index": 0}]]},
        "Resolve Insights Identity": {"main": [[{"node": "Insights Agent", "type": "main", "index": 0}]]},
        "Insights Agent": {"main": [[{"node": "Parse Blocks", "type": "main", "index": 0}]]},
        # Sub-node connections
        "Anthropic Chat Model": {"ai_languageModel": [[{"node": "Insights Agent", "type": "ai_languageModel", "index": 0}]]},
        "People.ai MCP": {"ai_tool": [[{"node": "Insights Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Blocks": {"main": [[{"node": "Send Insights", "type": "main", "index": 0}]]}
    }

    workflow = {
        "name": "Opportunity Insights",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"}
    }

    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS, json=workflow)
    resp.raise_for_status()
    result = resp.json()
    wf_id = result["id"]
    print(f"  Created: ID={wf_id}, {len(result['nodes'])} nodes")
    print("  (Sub-workflow — no activation needed, called via Execute Workflow)")

    resp3 = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}", headers=HEADERS)
    resp3.raise_for_status()
    sync_local(resp3.json(), "Opportunity Insights.json")

    return wf_id


# ============================================================
# ADD INSIGHTS COMMAND TO SLACK EVENTS HANDLER
# ============================================================
def upgrade_events_handler(wf, insights_wf_id):
    print(f"\n=== Adding insights command (Insights WF ID: {insights_wf_id}) ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    node_names = [n["name"] for n in nodes]
    if "Parse Insights" in node_names:
        print("  Parse Insights already exists — skipping")
        return wf

    # --- 1. Update Route by State to recognize "insights" command ---
    for node in nodes:
        if node["name"] == "Route by State":
            old_code = node["parameters"]["jsCode"]
            # Insert after the last command detection
            new_code = old_code.replace(
                "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';",
                "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';\n  else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';"
            )
            if new_code == old_code:
                # Try inserting after scope command if brief isn't there yet
                new_code = old_code.replace(
                    "else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';",
                    "else if (lower === 'scope' || lower.startsWith('scope ')) route = 'cmd_scope';\n  else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';"
                )
            node["parameters"]["jsCode"] = new_code
            print("  Updated Route by State with 'insights' command")
            break

    # --- 2. Add "Insights" output to Switch Route ---
    for node in nodes:
        if node["name"] == "Switch Route":
            node["parameters"]["rules"]["values"].append({
                "outputKey": "Insights",
                "conditions": {
                    "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                    "combinator": "and",
                    "conditions": [{
                        "id": uid(),
                        "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                        "leftValue": "={{ $json.route }}",
                        "rightValue": "cmd_insights"
                    }]
                },
                "renameOutput": True
            })
            output_idx = len(node["parameters"]["rules"]["values"]) - 1
            print(f"  Added 'Insights' output to Switch Route (output {output_idx})")
            break
    else:
        output_idx = 10

    # --- 3. Add Parse Insights node ---
    parse_insights_id = uid()
    nodes.append({
        "parameters": {"jsCode": PARSE_INSIGHTS_CMD_CODE},
        "id": parse_insights_id,
        "name": "Parse Insights",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2180, 2320]
    })
    print(f"  Added Parse Insights (id={parse_insights_id})")

    # --- 4. Add Is Valid Insight? (If node) ---
    is_valid_id = uid()
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "leftValue": "", "caseSensitive": True, "typeValidation": "strict"},
                "conditions": [{
                    "id": uid(),
                    "leftValue": "={{ $json.isValid }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"}
                }],
                "combinator": "and"
            },
            "options": {}
        },
        "id": is_valid_id,
        "name": "Is Valid Insight?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2420, 2320]
    })
    print(f"  Added Is Valid Insight? (id={is_valid_id})")

    # --- 5. Add Send Generating Msg ---
    send_gen_id = uid()
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
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.assistantEmoji + ' Analyzing your pipeline for *' + $json.insightLabel + '*... this takes about 45 seconds.', username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_gen_id,
        "name": "Send Insights Generating",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 2220],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added Send Insights Generating (id={send_gen_id})")

    # --- 6. Add Prepare Insights Input ---
    # Restores original data from Is Valid Insight? after Send Generating
    # (Send Generating outputs Slack API response, not user data)
    prepare_id = uid()
    nodes.append({
        "parameters": {
            "jsCode": "// Restore original data from Is Valid Insight? (Send Generating outputs Slack API response)\nreturn [{ json: $('Is Valid Insight?').first().json }];"
        },
        "id": prepare_id,
        "name": "Prepare Insights Input",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2900, 2220]
    })
    print(f"  Added Prepare Insights Input (id={prepare_id})")

    # --- 7. Add Execute Insights ---
    exec_insights_id = uid()
    nodes.append({
        "parameters": {
            "workflowId": {"__rl": True, "mode": "id", "value": insights_wf_id},
            "options": {}
        },
        "id": exec_insights_id,
        "name": "Execute Insights",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [3140, 2220]
    })
    print(f"  Added Execute Insights (id={exec_insights_id})")

    # --- 7. Add Send Insights Error ---
    send_error_id = uid()
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
            "jsonBody": "={{ JSON.stringify({ channel: $json.channelId, text: $json.responseText, username: $json.assistantName, icon_emoji: $json.assistantEmoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {}
        },
        "id": send_error_id,
        "name": "Send Insights Error",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2660, 2420],
        "credentials": {"httpHeaderAuth": SLACK_CRED}
    })
    print(f"  Added Send Insights Error (id={send_error_id})")

    # --- 8. Wire connections ---
    if "Switch Route" not in connections:
        connections["Switch Route"] = {"main": []}
    switch_outputs = connections["Switch Route"]["main"]
    while len(switch_outputs) <= output_idx:
        switch_outputs.append([])
    switch_outputs[output_idx] = [{"node": "Parse Insights", "type": "main", "index": 0}]

    connections["Parse Insights"] = {
        "main": [[{"node": "Is Valid Insight?", "type": "main", "index": 0}]]
    }
    # Sequential: Is Valid Insight? → Send Generating → Prepare Input → Execute Insights
    # Prepare Input restores data from Is Valid Insight? since Send Generating
    # outputs a Slack API response. Sequential ensures "generating" message appears first.
    connections["Is Valid Insight?"] = {
        "main": [
            [{"node": "Send Insights Generating", "type": "main", "index": 0}],  # true
            [{"node": "Send Insights Error", "type": "main", "index": 0}]         # false
        ]
    }
    connections["Send Insights Generating"] = {
        "main": [[{"node": "Prepare Insights Input", "type": "main", "index": 0}]]
    }
    connections["Prepare Insights Input"] = {
        "main": [[{"node": "Execute Insights", "type": "main", "index": 0}]]
    }

    print(f"  Wired: Switch[{output_idx}] → Parse Insights → Is Valid? → [yes: Generating → Prepare → Execute] [no: Error]")

    # --- 9. Update Build Help Response — add insights section ---
    for node in nodes:
        if node["name"] == "Build Help Response":
            old_code = node["parameters"]["jsCode"]

            # Insert insights section before "Pause or restart"
            old_marker = '"*Pause or restart:*'
            insights_section = (
                '"*Pipeline intelligence:*\\n" +\n'
                '    "`insights` \\u2014 full pipeline analysis\\n" +\n'
                '    "`insights stalled` \\u2014 deals losing momentum\\n" +\n'
                '    "`insights risk` \\u2014 emerging threats\\n" +\n'
                '    "`insights hidden` \\u2014 accounts without opportunities\\n" +\n'
                '    "`insights accelerating` \\u2014 deals ready to close\\n\\n" +\n'
                '    "*Pause or restart:*'
            )
            new_code = old_code.replace(old_marker, insights_section)

            if new_code == old_code:
                print("  WARNING: Could not find 'Pause or restart' marker in Build Help Response")
            else:
                print("  Updated Build Help Response — added insights section")

            # Also add insights to the fallback text
            fallback_old = '"`brief risk` \\u2014 deals that need attention\\n" +\n    "`/bs'
            fallback_new = '"`brief risk` \\u2014 deals that need attention\\n" +\n    "`insights` \\u2014 pipeline intelligence\\n" +\n    "`/bs'
            new_code = new_code.replace(fallback_old, fallback_new)

            node["parameters"]["jsCode"] = new_code
            break

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ============================================================
# MAIN
# ============================================================
def activate_workflow(wf_id):
    resp = requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}/activate", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def main():
    # Step 1: Create Opportunity Insights sub-workflow
    insights_wf_id = create_insights_workflow()

    # Step 1b: Activate sub-workflow (required for Execute Workflow references)
    print("\n=== Activating Opportunity Insights ===")
    activate_workflow(insights_wf_id)
    print(f"  Activated: {insights_wf_id}")

    # Step 2: Update Slack Events Handler
    print("\nFetching Slack Events Handler...")
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  {len(events_wf['nodes'])} nodes")

    events_wf = upgrade_events_handler(events_wf, insights_wf_id)

    print("\n=== Pushing Slack Events Handler ===")
    result = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Slack Events Handler.json")

    print(f"\nDone! Opportunity Insights workflow ID: {insights_wf_id}")
    print("Users can now type:")
    print("  insights       — full pipeline intelligence")
    print("  insights stalled  — deals losing momentum")
    print("  insights risk     — emerging threats")
    print("  insights hidden   — accounts without opportunities")
    print("  insights accel    — deals ready to close")


if __name__ == "__main__":
    main()
