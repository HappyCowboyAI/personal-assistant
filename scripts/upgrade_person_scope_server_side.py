#!/usr/bin/env python3
"""
Upgrade On-Demand Digest to use server-side OR filter for person-scope requests.

Changes:
1. Fetch User Hierarchy  — add ootb_user_id column
2. Parse Hierarchy       — extract peopleAiId for each user
3. NEW Build Opp Query   — builds person-specific OR filter or standard query
4. Fetch Open Opps       — use dynamic query body from Build Opp Query
5. Parse Opps CSV        — add CSM Owner and Lead SE columns
6. Filter User Opps      — person-scope uses server-side filtered data + role detection
7. Resolve Identity      — remove MCP-only fallback for person-scope (use real data)

Usage:  python scripts/upgrade_person_scope_server_side.py <N8N_API_KEY>
"""

import requests
import json
import uuid
import sys
import os

N8N_BASE_URL = "https://scottai.trackslife.com"
WORKFLOW_ID = "vxGajBdXFBaOCdkG"  # On-Demand Digest

# ============================================================
# JavaScript code for each updated/new node
# ============================================================

PARSE_HIERARCHY_CODE = r"""// Parse CSV from People.ai User hierarchy export
const csvData = $('Fetch User Hierarchy').first().json.data;

if (!csvData) {
  return [{ json: { hierarchy: {}, managerToReports: {}, userCount: 0, error: 'No hierarchy data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { hierarchy: {}, managerToReports: {}, userCount: 0, error: 'Hierarchy CSV has no data rows' } }];
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

const hierarchy = {};
const managerToReports = {};

for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < headers.length) continue;

  const name       = getField(row, 'User Name', 'ootb_user_name', 'Name');
  const email      = getField(row, 'User Email', 'ootb_user_email', 'Email').toLowerCase();
  const manager    = getField(row, 'User Manager', 'ootb_user_manager', 'Manager');
  const peopleAiId = getField(row, 'User ID', 'ootb_user_id', 'ID');

  if (email) {
    hierarchy[email] = { name, email, manager, peopleAiId };
  }

  if (manager) {
    const mgrLower = manager.toLowerCase();
    if (!managerToReports[mgrLower]) {
      managerToReports[mgrLower] = [];
    }
    managerToReports[mgrLower].push({ name, email });
  }
}

return [{ json: { hierarchy, managerToReports, userCount: Object.keys(hierarchy).length } }];
"""

BUILD_OPP_QUERY_CODE = r"""// Build the People.ai Query API request body based on scope.
// For person: scope — OR filter across AE/CSM/SE owner fields using the person's numeric People.ai ID.
// For all other scopes — standard all-open-opps query.

const user = $('Workflow Input Trigger').first().json;
const hierarchyData = $('Parse Hierarchy').first().json;
const digestScope = user.digest_scope || 'my_deals';

const baseColumns = [
  { slug: 'ootb_opportunity_id' },
  { slug: 'ootb_opportunity_crm_id' },
  { slug: 'ootb_opportunity_name' },
  { slug: 'ootb_opportunity_account_name' },
  { slug: 'ootb_opportunity_original_owner' },
  { slug: 'opportunity_csm_owner__c_user' },
  { slug: 'opportunity_lead_sales_engineer__c_user' },
  { slug: 'ootb_opportunity_current_stage' },
  { slug: 'ootb_opportunity_close_date' },
  { slug: 'ootb_opportunity_engagement_level' }
];

const sort = [{ attribute: { slug: 'ootb_opportunity_close_date' }, direction: 'asc' }];

let filter;
let personPeopleAiId = null;
let targetEmail = null;

if (digestScope.startsWith('person:')) {
  targetEmail = digestScope.replace('person:', '').toLowerCase();
  const hierarchyEntry = (hierarchyData.hierarchy || {})[targetEmail];

  if (hierarchyEntry && hierarchyEntry.peopleAiId) {
    const parsed = parseInt(hierarchyEntry.peopleAiId, 10);
    if (!isNaN(parsed)) {
      personPeopleAiId = parsed;
    }
  }

  if (personPeopleAiId !== null) {
    // Server-side OR filter: AE owner OR CSM owner OR Lead SE owner
    filter = {
      '$and': [
        { attribute: { slug: 'ootb_opportunity_is_closed' }, clause: { '$eq': false } },
        {
          '$or': [
            { attribute: { slug: 'ootb_opportunity_original_owner' }, clause: { '$eq': personPeopleAiId } },
            { attribute: { slug: 'opportunity_csm_owner__c_user' },   clause: { '$eq': personPeopleAiId } },
            { attribute: { slug: 'opportunity_lead_sales_engineer__c_user' }, clause: { '$eq': personPeopleAiId } }
          ]
        }
      ]
    };
  } else {
    // Person not found in hierarchy — fetch all opps, filter client-side by name
    filter = {
      '$and': [
        { attribute: { slug: 'ootb_opportunity_is_closed' }, clause: { '$eq': false } }
      ]
    };
  }
} else {
  // Standard: all open opps (client-side filtering by role/team happens in Filter User Opps)
  filter = {
    '$and': [
      { attribute: { slug: 'ootb_opportunity_is_closed' }, clause: { '$eq': false } }
    ]
  };
}

const queryBody = JSON.stringify({
  object: 'opportunity',
  filter,
  columns: baseColumns.map(c => ({ slug: c.slug })),
  sort
});

return [{ json: { queryBody, personPeopleAiId, targetEmail } }];
"""

PARSE_OPPS_CSV_CODE = r"""// Parse CSV from People.ai Query API export
const csvData = $('Fetch Open Opps').first().json.data;

if (!csvData) {
  return [{ json: { opps: [], oppCount: 0, error: 'No CSV data returned' } }];
}

const lines = csvData.split('\n').filter(l => l.trim());
if (lines.length < 2) {
  return [{ json: { opps: [], oppCount: 0, error: 'CSV has no data rows' } }];
}

function parseCsvLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') { current += '"'; i++; }
      else { inQuotes = !inQuotes; }
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
headers.forEach((h, i) => {
  headerMap[h] = i;
  headerMap[h.toLowerCase()] = i;
});

function getField(row, ...names) {
  for (const name of names) {
    const idx = headerMap[name] ?? headerMap[name.toLowerCase()];
    if (idx !== undefined && row[idx] !== undefined && row[idx] !== '') {
      return row[idx];
    }
  }
  return '';
}

const opps = [];
for (let i = 1; i < lines.length; i++) {
  const row = parseCsvLine(lines[i]);
  if (row.length < 2) continue;

  opps.push({
    peopleAiId:  getField(row, 'Opportunity ID', 'ootb_opportunity_id', 'ID', 'Id'),
    owners:      getField(row, 'Opportunity Owner (name)', 'Opportunity Owner', 'Opportunity Owners'),
    ownerId:     getField(row, 'Opportunity Owner (id)'),
    csmOwner:    getField(row, 'CSM Owner (name)'),
    csmOwnerId:  getField(row, 'CSM Owner (id)'),
    leadSe:      getField(row, 'Lead Sales Engineer (name)'),
    leadSeId:    getField(row, 'Lead Sales Engineer (id)'),
    name:        getField(row, 'Opportunity Name',         'ootb_opportunity_name'),
    account:     getField(row, 'Account Name',             'ootb_opportunity_account_name'),
    closeDate:   getField(row, 'Close Date',               'ootb_opportunity_close_date'),
    stage:       getField(row, 'Stage',                    'ootb_opportunity_current_stage', 'Current Stage'),
    amount:      '',
    crmId:       getField(row, 'Record ID',                'ootb_opportunity_crm_id', 'CRM ID'),
    engagement:  getField(row, 'Opportunity Engagement Level', 'ootb_opportunity_engagement_level', 'Engagement Level')
  });
}

return [{ json: { opps, oppCount: opps.length, headers } }];
"""

FILTER_USER_OPPS_CODE = r"""// Filter pre-fetched opps based on user's role/digest_scope and daily theme
const user = $('Workflow Input Trigger').first().json;
const allOpps = $('Parse Opps CSV').first().json.opps;
const debugHeaders = ($('Parse Opps CSV').first().json.headers || []).join('|');
const debugSampleOwners = allOpps.length > 0 ? (allOpps[0].owners || '(empty)') : '(no opps)';
const hierarchyData = $('Parse Hierarchy').first().json;
const buildQueryData = $('Build Opp Query').first().json;

// Derive rep name from email
const repName = (user.email || '').split('@')[0]
  .replace(/\./g, ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

const repLower = repName.toLowerCase();
const digestScope = user.digest_scope || 'my_deals';
const userEmail = (user.email || '').toLowerCase();

// === Theme resolution ===
function resolveTheme(override) {
  if (override) return override;
  const dayOfWeek = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    timeZone: 'America/Los_Angeles'
  }).toLowerCase();
  const dayMap = {
    'monday': 'full_pipeline',
    'tuesday': 'engagement_shifts',
    'wednesday': 'at_risk',
    'thursday': 'momentum',
    'friday': 'week_review'
  };
  return dayMap[dayOfWeek] || 'full_pipeline';
}

const theme = resolveTheme(user.themeOverride || null);

// === Date window helpers ===
function getCurrentAndNextQuarterEnd() {
  const now = new Date();
  const month = now.getMonth();
  const year = now.getFullYear();
  const currentQ = Math.floor(month / 3);
  const nextQEnd = currentQ + 2;
  let endMonth, endYear;
  if (nextQEnd <= 3) {
    endMonth = nextQEnd * 3;
    endYear = year;
  } else {
    endMonth = (nextQEnd - 4) * 3;
    endYear = year + 1;
  }
  return new Date(endYear, endMonth, 0, 23, 59, 59);
}

function getFiscalYearEnd() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  if (month === 0) return new Date(year, 0, 31, 23, 59, 59);
  return new Date(year + 1, 0, 31, 23, 59, 59);
}

function filterByDateWindow(opps, endDate) {
  const now = new Date();
  return opps.filter(opp => {
    if (!opp.closeDate) return false;
    const close = new Date(opp.closeDate);
    return close >= now && close <= endDate;
  });
}

const twoQuarterEnd = getCurrentAndNextQuarterEnd();
const fyEnd = getFiscalYearEnd();
const qEndLabel = twoQuarterEnd.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

let userOpps = [];
let scopeLabel = '';

// === Scope-based filtering ===
if (digestScope === 'my_deals') {
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return owners.includes(repLower) || owners.includes(userEmail);
  });
  userOpps = filterByDateWindow(userOpps, fyEnd);
  scopeLabel = repName + "'s OPEN OPPORTUNITIES";

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

  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return reportNames.some(name => owners.includes(name));
  });
  userOpps = filterByDateWindow(userOpps, twoQuarterEnd);
  userOpps.sort((a, b) => new Date(a.closeDate) - new Date(b.closeDate));
  scopeLabel = repName + "'s TEAM PIPELINE through " + qEndLabel + " (" + reportNames.length + " reps)";

} else if (digestScope === 'top_pipeline') {
  userOpps = filterByDateWindow([...allOpps], twoQuarterEnd);
  const totalInWindow = userOpps.length;
  userOpps.sort((a, b) => {
    const amtA = parseFloat((a.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    const amtB = parseFloat((b.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    return amtB - amtA;
  });
  userOpps = userOpps.slice(0, 25);
  scopeLabel = "TOP PIPELINE through " + qEndLabel + " (" + totalInWindow + " deals in window, showing top 25 by amount)";

} else if (digestScope.startsWith('person:')) {
  const targetEmail = digestScope.replace('person:', '').toLowerCase();
  const hierarchyEntry = (hierarchyData.hierarchy || {})[targetEmail];
  const emailDerivedName = targetEmail.split('@')[0].replace(/\./g, ' ');
  const displayName = hierarchyEntry && hierarchyEntry.name
    ? hierarchyEntry.name
    : emailDerivedName.replace(/\b\w/g, c => c.toUpperCase());

  const personPeopleAiId = buildQueryData.personPeopleAiId;
  const hadServerFilter = (personPeopleAiId !== null && personPeopleAiId !== undefined);

  if (hadServerFilter) {
    // All returned opps already belong to this person (AE, CSM, or SE)
    userOpps = filterByDateWindow(allOpps, fyEnd);
  } else {
    // Fallback: client-side name/email matching
    const targetName = displayName.toLowerCase();
    const emailPrefix = targetEmail.split('@')[0].toLowerCase();
    userOpps = allOpps.filter(opp => {
      const owners = (opp.owners || '').toLowerCase();
      return owners.includes(targetName) || owners.includes(targetEmail) || owners.includes(emailPrefix);
    });
    userOpps = filterByDateWindow(userOpps, fyEnd);
  }

  scopeLabel = displayName + "'s OPEN OPPORTUNITIES";
}

// === Theme-based additional filtering ===
const themeLabels = {
  'full_pipeline': 'Full Pipeline Brief',
  'engagement_shifts': 'Engagement Shifts',
  'at_risk': 'At-Risk Deals',
  'momentum': 'Momentum & Wins',
  'week_review': 'Week in Review'
};

let themeNote = '';

if (theme === 'at_risk') {
  const riskOpps = userOpps.filter(opp => {
    const eng = (opp.engagement || '').toLowerCase();
    const isLowEngagement = !eng || eng === 'low' || eng === 'none' || eng === '0' || eng === '';
    const closeDate = new Date(opp.closeDate);
    const daysToClose = (closeDate - new Date()) / (1000 * 60 * 60 * 24);
    const isClosingSoon = daysToClose >= 0 && daysToClose <= 45;
    const lateStages = ['closed won', 'closed lost', 'negotiation', 'contract'];
    const stage = (opp.stage || '').toLowerCase();
    const isNotLateStage = !lateStages.some(s => stage.includes(s));
    return isLowEngagement || (isClosingSoon && isNotLateStage);
  });
  if (riskOpps.length > 0) {
    themeNote = `Filtered to ${riskOpps.length} deals showing risk signals (low/no engagement or closing soon in early stage). Full pipeline has ${userOpps.length} deals.`;
    userOpps = riskOpps;
  } else {
    themeNote = `No obvious risk signals detected across ${userOpps.length} deals — all deals shown for review.`;
  }
} else if (theme === 'momentum') {
  userOpps.sort((a, b) => {
    const engA = parseFloat((a.engagement || '0').replace(/[^0-9.]/g, '')) || 0;
    const engB = parseFloat((b.engagement || '0').replace(/[^0-9.]/g, '')) || 0;
    return engB - engA;
  });
  themeNote = `Sorted by engagement score to surface momentum. ${userOpps.length} deals in scope.`;
}

// === Helper: determine a person's role on a deal ===
function getRoleOnDeal(opp, peopleAiId) {
  if (!peopleAiId) return '';
  const idStr = String(peopleAiId);
  if (opp.ownerId && String(opp.ownerId) === idStr) return 'AE';
  if (opp.csmOwnerId && String(opp.csmOwnerId) === idStr) return 'CSM';
  if (opp.leadSeId && String(opp.leadSeId) === idStr) return 'SE';
  return '';
}

// === Build formatted table ===
// Always include peopleAiId so the agent can build deep links.
let oppTable = '';
if (userOpps.length > 0) {
  if (digestScope.startsWith('person:')) {
    const personPeopleAiId = buildQueryData.personPeopleAiId;
    oppTable = '| peopleAiId | Opportunity | Account | Role | Stage | Close Date | Engagement | CRM ID |\n';
    oppTable += '|---|---|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      const role = getRoleOnDeal(opp, personPeopleAiId);
      oppTable += `| ${opp.peopleAiId} | ${opp.name} | ${opp.account} | ${role} | ${opp.stage} | ${opp.closeDate} | ${opp.engagement} | ${opp.crmId || ''} |\n`;
    }
  } else if (digestScope === 'my_deals') {
    oppTable = '| peopleAiId | Opportunity | Account | Stage | Close Date | Engagement | CRM ID |\n';
    oppTable += '|---|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      oppTable += `| ${opp.peopleAiId} | ${opp.name} | ${opp.account} | ${opp.stage} | ${opp.closeDate} | ${opp.engagement} | ${opp.crmId || ''} |\n`;
    }
  } else {
    oppTable = '| peopleAiId | Opportunity | Account | Owner | Stage | Close Date | Engagement | CRM ID |\n';
    oppTable += '|---|---|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      oppTable += `| ${opp.peopleAiId} | ${opp.name} | ${opp.account} | ${opp.owners} | ${opp.stage} | ${opp.closeDate} | ${opp.engagement} | ${opp.crmId || ''} |\n`;
    }
  }
} else {
  oppTable = '(No open opportunities found in the date window)';
}

return [{
  json: {
    ...user,
    userOpps,
    userOppCount: userOpps.length,
    totalOppCount: allOpps.length,
    oppTable,
    repName,
    digestScope,
    scopeLabel,
    debugHeaders,
    debugSampleOwners,
    dateWindowEnd: qEndLabel,
    theme,
    themeLabel: themeLabels[theme] || 'Brief',
    themeNote
  }
}];
"""

RESOLVE_IDENTITY_CODE = r"""const user = $('Filter User Opps').first().json;

const assistantName    = user.assistant_name    || 'Aria';
const assistantEmoji   = user.assistant_emoji   || ':robot_face:';
const assistantPersona = user.assistant_persona || 'direct, action-oriented, and conversational';
const repName    = user.repName || (user.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Rep';
const timezone   = user.timezone || 'America/Los_Angeles';
const currentDate = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
const timeStr     = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: timezone });

const oppTable       = user.oppTable || '(No opportunity data available)';
const oppCount       = user.userOppCount || 0;
const totalOppCount  = user.totalOppCount || oppCount;
const digestScope    = user.digestScope || 'my_deals';
const scopeLabel     = user.scopeLabel  || (repName + "'s OPEN OPPORTUNITIES");
const isPersonScope  = digestScope.startsWith('person:');
const subjectName    = isPersonScope
  ? scopeLabel.replace(/'s OPEN OPPORTUNITIES$/, '').trim()
  : repName;
const dateWindowEnd  = user.dateWindowEnd || '';
const theme          = user.theme          || 'full_pipeline';
const themeLabel     = user.themeLabel     || 'Brief';
const themeNote      = user.themeNote      || '';

const dayLabel   = currentDate.split(',')[0];
const emojiClean = assistantEmoji.replace(/:/g, '');

// === Shared Block Kit formatting rules ===
const blockKitRules = `OUTPUT FORMAT — CRITICAL:
Respond with ONLY a valid JSON object. Your ENTIRE response must be the JSON object and nothing else. No prose before or after. No explanation. No markdown code fences (no backticks). No "let me" or "here is" preamble. Start your response with { and end with }.

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
  - If you have more than 10 data points, split into multiple section blocks
- Use "context" block at the bottom for timestamp and data source
- Maximum 50 blocks per message

MRKDWN RULES (inside all text fields):
- Bold: *text* — single asterisks only
- Line break: \\n
- Blank line: \\n\\n
- Top-level bullets: use the • character (e.g. • Main point)
- Sub-bullets under a numbered item or heading: indent with 4 spaces before the bullet (e.g.     • Sub-point)
- This creates visual hierarchy — numbered deals at top level, details indented beneath
- NO ## headers — use *bold text* on its own line instead
- NO **double asterisks**
- NO standard markdown links [text](url) — use <https://url|text>
- NO dash bullets (-)

EMOJI STATUS INDICATORS — use these consistently:
🚀 Acceleration / strong momentum
⚠️ Risk pattern detected
💎 Hidden upside opportunity
🔴 Stalled / critical risk
✅ Healthy / on track
📈 Engagement rising
📉 Engagement falling
➡️ Engagement stable
🔥 High engagement (80+)`;

// === Role context by scope (data + identity) ===
function buildRoleContext(scope) {
  const mcpRules = `DEEP LINKS — make each deal name a clickable link using the peopleAiId column from the data table:
<https://app.people.ai/opportunity/PEOPLEAIID|Deal Name Here> (replace PEOPLEAIID with the peopleAiId value and Deal Name with the actual deal name)
Do NOT add a separate "View in People.ai" line — the deal name itself is the link.
Example: <https://app.people.ai/opportunity/5479658708|HPE AI Forensics Pilot>
If the peopleAiId is empty, omit the link and just use plain bold text for the deal name.

Do NOT use MCP to search for or list opportunities — they are already provided above.

You DO have access to People.ai MCP tools. Use them ONLY for:
- Revenue stories and engagement analysis on specific deals
- Recent activity details (emails, meetings, calls) on key accounts
- Engagement score trends and changes`;

  if (scope === 'my_deals') {
    return `You are ${assistantName}, a personal sales assistant for ${repName}. You work exclusively for them and know their pipeline intimately.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals) ━━━
${themeNote ? '\n' + themeNote + '\n' : ''}
${oppTable}

${mcpRules}`;
  } else if (scope === 'team_deals') {
    return `You are ${assistantName}, a sales management assistant for ${repName}. You help them lead their team and stay ahead of pipeline risks.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals closing through ${dateWindowEnd}) ━━━
${themeNote ? '\n' + themeNote + '\n' : ''}
${oppTable}

${mcpRules}`;
  } else if (scope.startsWith('person:')) {
    return `You are ${assistantName}, a personal sales assistant for ${repName}. They have asked you to review ${subjectName}'s pipeline.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals) ━━━
${themeNote ? '\n' + themeNote + '\n' : ''}
${oppTable}

${mcpRules}

IMPORTANT — PERSON SCOPE:
- This brief is about *${subjectName}'s* pipeline, not ${repName}'s.
- Address ${repName} as the reader (e.g. "Here's ${subjectName}'s pipeline for you to review...").
- Wherever the briefing structure says "your deals" or "your pipeline", treat that as "${subjectName}'s deals" / "${subjectName}'s pipeline".
- Never say "${repName}, your pipeline..." — say "${subjectName} has X deals..." or "Here's ${subjectName}'s pipeline...".
- The Role column shows whether ${subjectName} is the AE, CSM, or SE on each deal.`;
  } else {
    return `You are ${assistantName}, an executive sales intelligence assistant for ${repName}. You provide pipeline visibility and strategic signals at the leadership level.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} ━━━
${themeNote ? '\n' + themeNote + '\n' : ''}
${oppTable}

${mcpRules}`;
  }
}

// === Scope-aware footer ===
function footer(scope) {
  if (scope === 'team_deals')   return `Backstory team intelligence • ${currentDate} • ${timeStr} PT`;
  if (scope === 'top_pipeline') return `Backstory executive intelligence • ${currentDate} • ${timeStr} PT`;
  return `Backstory intelligence • ${currentDate} • ${timeStr} PT`;
}

// === Theme-specific briefing structure and agent prompt ===
function buildThemePrompts(theme, scope) {
  const scopeTitle = scope === 'team_deals' ? ' Team' : scope === 'top_pipeline' ? ' Pipeline' : '';

  // ── FULL PIPELINE (Monday) ──
  if (theme === 'full_pipeline') {
    if (scope === 'my_deals') {
      return {
        briefingStructure: `Write a 60-second morning briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Brief — ${assistantName}"
2. The Lead (1-2 sentences) — the single most important thing today
3. Today's Priorities (2-4 items) — specific actions with account names and reasons, use emoji status indicators
4. Pipeline Pulse — two-column engagement score grid using section fields
5. One Thing I'm Watching — one forward-looking observation
6. Context footer — "${footer(scope)}"`,

        agentPrompt: `Generate the morning sales briefing for ${repName}. Their ${oppCount} open opportunities are already loaded in your system prompt — do NOT use MCP to search for opportunities.

Instead, use the People.ai MCP tools to investigate revenue stories and engagement patterns on the top 3-5 most important deals (highest amount, closest close date, or biggest engagement changes). Look for recent activity, meeting patterns, and risk signals.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`
      };
    } else if (scope === 'team_deals') {
      return {
        briefingStructure: `Write a 90-second team pipeline briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Team Brief — ${assistantName}"
2. Team Pulse (2-3 sentences) — overall pipeline health: total pipeline value, deals closing this quarter and next, biggest risks
3. Reps Who Need Attention (2-3 items) — which reps have deals at risk, declining engagement, or upcoming close dates with no recent activity
4. Top Coaching Moments — 1-2 deals where manager intervention could change the outcome
5. Team Pipeline Snapshot — two-column grid: rep name + key metric
6. One Signal to Watch — a forward-looking team-level pattern
7. Context footer — "${footer(scope)}"`,

        agentPrompt: `Generate the team pipeline briefing for ${repName} (sales manager). Their team's ${oppCount} open deals closing through ${dateWindowEnd} are already loaded — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to investigate team engagement patterns: identify reps with declining engagement, spot coaching opportunities, and find deals where manager intervention could help. Focus on 3-5 highest-risk or highest-value deals.

Output ONLY the Block Kit JSON object, nothing else.`
      };
    } else {
      return {
        briefingStructure: `Write a 90-second executive pipeline briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Pipeline Brief — ${assistantName}"
2. Pipeline at a Glance (2-3 sentences) — total pipeline value, deal count, weighted forecast, deals closing this month
3. Top Deals to Watch (3-4 items) — highest-value or highest-risk deals with status
4. Forecast Signals — deal acceleration/stalling patterns, close date movements
5. Key Numbers — two-column grid: metric name + value
6. Strategic Signal — one forward-looking observation
7. Context footer — "${footer(scope)}"`,

        agentPrompt: `Generate the executive pipeline briefing for ${repName}. Top ${oppCount} deals by amount closing through ${dateWindowEnd} are loaded (${totalOppCount} total org-wide) — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to analyze pipeline health on the top 3-5 largest deals: velocity, engagement trends, risk signals, forecast-impacting patterns.

Output ONLY the Block Kit JSON object, nothing else.`
      };
    }
  }

  // ── ENGAGEMENT SHIFTS (Tuesday) ──
  if (theme === 'engagement_shifts') {
    const scopeWho = scope === 'my_deals' ? 'your deals' : scope === 'team_deals' ? "your team's deals" : 'deals across the organization';
    return {
      briefingStructure: `Write a 60-second engagement shift briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Engagement Shifts${scopeTitle} — ${assistantName}"
2. The Shift (1-2 sentences) — summarize the biggest engagement movements across ${scopeWho}
3. Going Hot (2-3 deals) — deals with the highest engagement scores or most recent activity. What's driving the engagement? Use 📈 🔥 indicators.
4. Going Cold (2-3 deals) — deals with low or declining engagement, accounts going quiet. Use 📉 🔴 indicators.${scope !== 'my_deals' ? '\n5. Rep Activity Pulse — which reps are most/least active this week (two-column grid)' : '\n5. Activity Snapshot — two-column grid of engagement scores by deal'}
6. One Pattern — one insight about what's driving engagement up or down
7. Context footer — "${footer(scope)}"`,

      agentPrompt: `Generate an engagement shifts briefing for ${repName}. ${oppCount} deals are loaded — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to investigate engagement patterns: pull engagement score histories, recent activity timelines, and meeting/email cadence on the 3-5 deals with the most notable engagement movement (both positive and negative). Look for accounts going dark and accounts heating up.

Output ONLY the Block Kit JSON object, nothing else.`
    };
  }

  // ── AT-RISK DEALS (Wednesday) ──
  if (theme === 'at_risk') {
    const scopeWho = scope === 'my_deals' ? 'your pipeline' : scope === 'team_deals' ? "your team's pipeline" : 'the org pipeline';
    return {
      briefingStructure: `Write a 60-second at-risk deals briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} At-Risk Deals${scopeTitle} — ${assistantName}"
2. Risk Summary (1-2 sentences) — how many deals are showing risk signals in ${scopeWho}, total value at risk
3. Critical Risks (2-3 deals) — deals most likely to slip or stall. For each: what's wrong, how long it's been, and what to do about it. Use 🔴 ⚠️ indicators.
4. Going Dark (1-2 deals) — accounts with zero or minimal recent engagement. These need outreach now. Use 📉 indicators.${scope === 'team_deals' ? '\n5. Reps to Check In With — which reps have the most at-risk deals, who needs coaching or support' : scope === 'top_pipeline' ? '\n5. Forecast Impact — total dollar value at risk, potential slip from forecast' : '\n5. Risk vs. Healthy — two-column comparison grid'}
6. Fix-It Actions — 2-3 concrete next steps to address the biggest risks this week
7. Context footer — "${footer(scope)}"`,

      agentPrompt: `Generate an at-risk deals briefing for ${repName}. ${oppCount} deals flagged with risk signals are loaded — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to investigate the riskiest deals: look for missing activity, declining engagement trends, silent stakeholders, and deals where the close date is approaching without stage progression. Focus on the 3-5 highest-value deals at risk.

Output ONLY the Block Kit JSON object, nothing else.`
    };
  }

  // ── MOMENTUM & WINS (Thursday) ──
  if (theme === 'momentum') {
    const scopeWho = scope === 'my_deals' ? 'your deals' : scope === 'team_deals' ? "your team" : 'the organization';
    return {
      briefingStructure: `Write a 60-second momentum briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Momentum & Wins${scopeTitle} — ${assistantName}"
2. Momentum Check (1-2 sentences) — what's working across ${scopeWho} right now
3. Deals on Fire (2-3 deals) — highest engagement, most active, advancing fastest. What's fueling it? Use 🚀 🔥 ✅ indicators.
4. Hidden Upside (1-2 deals) — deals quietly outperforming expectations or with untapped expansion potential. Use 💎 indicators.${scope === 'team_deals' ? '\n5. Rep Wins — which reps are crushing it, what can others learn from their approach' : scope === 'top_pipeline' ? '\n5. Pipeline Acceleration — deals that advanced stages, new pipeline created, forecast upside' : '\n5. Engagement Leaders — two-column grid of your hottest deals by engagement'}
6. Keep It Going — 1-2 actions to maintain or amplify the momentum
7. Context footer — "${footer(scope)}"`,

      agentPrompt: `Generate a momentum and wins briefing for ${repName}. ${oppCount} deals are loaded (sorted by engagement) — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to validate positive signals: check deal velocity, recent meetings, rising engagement scores, and multithreading on the top 3-5 highest-engagement deals. Celebrate what's working and identify patterns to replicate.

Output ONLY the Block Kit JSON object, nothing else.`
    };
  }

  // ── WEEK IN REVIEW (Friday) ──
  if (theme === 'week_review') {
    const scopeWho = scope === 'my_deals' ? 'your pipeline' : scope === 'team_deals' ? "your team" : 'the organization';
    return {
      briefingStructure: `Write a 90-second week in review briefing following this structure:

1. Header — "${emojiClean} ${dayLabel} Week in Review${scopeTitle} — ${assistantName}"
2. This Week's Moves (2-3 sentences) — what changed in ${scopeWho} this week: deals that advanced, engagement shifts, notable activity
3. Wins & Progress (2-3 items) — deals that moved forward, positive engagement trends, meetings completed. Use ✅ 🚀 indicators.
4. Missed or Slipping (1-2 items) — deals that stalled or slipped this week, close dates pushed. Use ⚠️ 🔴 indicators.${scope === 'team_deals' ? '\n5. Team Scorecard — two-column grid: rep name + their week (active/quiet/strong)' : scope === 'top_pipeline' ? '\n5. Weekly Pipeline Delta — key numbers: pipeline added vs. closed, forecast movement' : '\n5. Week by the Numbers — two-column grid: key pipeline metrics this week vs. last'}
6. Next Week Preview — deals closing next week, meetings on the calendar, actions to set up for Monday
7. Context footer — "${footer(scope)}"`,

      agentPrompt: `Generate a week in review briefing for ${repName}. ${oppCount} deals are loaded — do NOT use MCP to search for opportunities.

Use People.ai MCP tools to compare this week's activity with previous patterns: look for deals that had new meetings, emails, or engagement changes this week. Identify what moved forward and what went quiet. Also check for meetings or close dates coming up next week.

Output ONLY the Block Kit JSON object, nothing else.`
    };
  }

  return buildThemePrompts('full_pipeline', scope);
}

// === Build the prompts ===
const roleContext = buildRoleContext(digestScope);
const effectiveScope = isPersonScope ? 'my_deals' : digestScope;
const { briefingStructure, agentPrompt } = buildThemePrompts(theme, effectiveScope);

// For person-scope: use a customised agent prompt that references the pre-fetched data
let finalAgentPrompt = agentPrompt;
if (isPersonScope) {
  finalAgentPrompt = `Generate a ${themeLabel} briefing for ${repName} covering ${subjectName}'s open pipeline.

${subjectName}'s ${oppCount} open opportunities are already loaded in your system prompt — do NOT use MCP to search for opportunities. The Role column shows whether ${subjectName} is the AE, CSM, or SE on each deal.

Instead, use the People.ai MCP tools to investigate revenue stories and engagement patterns on ${subjectName}'s top 3-5 most important deals. Look for recent activity, meeting patterns, and risk signals.

Address the briefing to ${repName}. Reference ${subjectName}'s pipeline, not ${repName}'s.
Output ONLY the Block Kit JSON object, nothing else.`;
}

const systemPrompt = roleContext + '\n\n' + briefingStructure + '\n\n' + blockKitRules;

return [{
  json: {
    userId: user.id,
    slackUserId: user.slack_user_id,
    assistantName,
    assistantEmoji,
    repName,
    digestScope,
    theme,
    themeLabel,
    systemPrompt,
    agentPrompt: finalAgentPrompt
  }
}];
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/upgrade_person_scope_server_side.py <N8N_API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]
    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    # ── Fetch live workflow ──────────────────────────────────────
    print(f"Fetching live workflow {WORKFLOW_ID}...")
    r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}", headers=headers)
    r.raise_for_status()
    workflow = r.json()

    nodes = workflow["nodes"]
    connections = workflow["connections"]

    def find_node(name):
        for n in nodes:
            if n["name"] == name:
                return n
        return None

    # ── 1. Fetch User Hierarchy: add ootb_user_id ───────────────
    fetch_hierarchy = find_node("Fetch User Hierarchy")
    if not fetch_hierarchy:
        print("ERROR: 'Fetch User Hierarchy' node not found"); sys.exit(1)

    fetch_hierarchy["parameters"]["jsonBody"] = json.dumps({
        "object": "user",
        "columns": [
            {"slug": "ootb_user_name"},
            {"slug": "ootb_user_email"},
            {"slug": "ootb_user_manager"},
            {"slug": "ootb_user_id"}
        ]
    })
    print("✓ Updated Fetch User Hierarchy (added ootb_user_id)")

    # ── 2. Parse Hierarchy: extract peopleAiId ──────────────────
    parse_hierarchy = find_node("Parse Hierarchy")
    if not parse_hierarchy:
        print("ERROR: 'Parse Hierarchy' node not found"); sys.exit(1)

    parse_hierarchy["parameters"]["jsCode"] = PARSE_HIERARCHY_CODE
    print("✓ Updated Parse Hierarchy (extracts peopleAiId)")

    # ── 3. Insert new 'Build Opp Query' node ────────────────────
    # Position it between Parse Hierarchy and Fetch Open Opps
    ph_pos = parse_hierarchy["position"]
    fo_pos = find_node("Fetch Open Opps")["position"] if find_node("Fetch Open Opps") else [ph_pos[0]+224, ph_pos[1]]

    build_opp_query_node = {
        "parameters": {
            "jsCode": BUILD_OPP_QUERY_CODE
        },
        "id": str(uuid.uuid4()),
        "name": "Build Opp Query",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [
            (ph_pos[0] + fo_pos[0]) // 2,
            ph_pos[1]
        ]
    }
    nodes.append(build_opp_query_node)
    print("✓ Added 'Build Opp Query' node")

    # ── 4. Fetch Open Opps: dynamic body from Build Opp Query ───
    fetch_opps = find_node("Fetch Open Opps")
    if not fetch_opps:
        print("ERROR: 'Fetch Open Opps' node not found"); sys.exit(1)

    # Switch from static jsonBody to expression-based string body
    fetch_opps["parameters"]["specifyBody"] = "string"
    fetch_opps["parameters"].pop("jsonBody", None)
    fetch_opps["parameters"]["body"] = "={{ $('Build Opp Query').first().json.queryBody }}"
    print("✓ Updated Fetch Open Opps (dynamic body from Build Opp Query)")

    # ── 5. Parse Opps CSV: add CSM Owner + Lead SE columns ──────
    parse_opps = find_node("Parse Opps CSV")
    if not parse_opps:
        print("ERROR: 'Parse Opps CSV' node not found"); sys.exit(1)

    parse_opps["parameters"]["jsCode"] = PARSE_OPPS_CSV_CODE
    print("✓ Updated Parse Opps CSV (added csmOwner, leadSe columns)")

    # ── 6. Filter User Opps: server-side person-scope handling ──
    filter_opps = find_node("Filter User Opps")
    if not filter_opps:
        print("ERROR: 'Filter User Opps' node not found"); sys.exit(1)

    filter_opps["parameters"]["jsCode"] = FILTER_USER_OPPS_CODE
    print("✓ Updated Filter User Opps (server-side person-scope + role detection)")

    # ── 7. Resolve Identity: remove MCP-only fallback ───────────
    resolve_identity = find_node("Resolve Identity")
    if not resolve_identity:
        print("ERROR: 'Resolve Identity' node not found"); sys.exit(1)

    resolve_identity["parameters"]["jsCode"] = RESOLVE_IDENTITY_CODE
    print("✓ Updated Resolve Identity (data-driven person-scope prompt)")

    # ── Update connections ───────────────────────────────────────
    # Parse Hierarchy → Build Opp Query
    connections["Parse Hierarchy"] = {
        "main": [[{"node": "Build Opp Query", "type": "main", "index": 0}]]
    }
    # Build Opp Query → Fetch Open Opps
    connections["Build Opp Query"] = {
        "main": [[{"node": "Fetch Open Opps", "type": "main", "index": 0}]]
    }
    print("✓ Updated connections: Parse Hierarchy → Build Opp Query → Fetch Open Opps")

    # ── Push to n8n ──────────────────────────────────────────────
    payload = {
        "name": workflow["name"],
        "nodes": nodes,
        "connections": connections,
        "settings": workflow.get("settings", {}),
        "staticData": workflow.get("staticData")
    }

    print("\nPushing updated workflow to n8n...")
    r = requests.put(
        f"{N8N_BASE_URL}/api/v1/workflows/{WORKFLOW_ID}",
        headers=headers,
        json=payload
    )

    if r.status_code == 200:
        print(f"✓ Workflow updated successfully!")
        updated = r.json()
        out_path = os.path.join(os.path.dirname(__file__), "..", "n8n", "workflows", "On-Demand Digest.json")
        with open(out_path, "w") as f:
            json.dump(updated, f, indent=2)
        print(f"✓ Saved to n8n/workflows/On-Demand Digest.json")
        print(f"\nNew node count: {len(updated.get('nodes', []))}")
    else:
        print(f"✗ Push failed: HTTP {r.status_code}")
        print(r.text[:1000])
        sys.exit(1)


if __name__ == "__main__":
    main()
