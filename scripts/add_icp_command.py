#!/usr/bin/env python3
"""
Create the ICP Analysis sub-workflow with three modes: calibrate, targets, compare.

Sub-workflow flow:
  Workflow Input Trigger (passthrough)
    → Route Mode (Code: reads mode field)
    → IF Is Calibrate
      TRUE → calibrate pipeline (3-5 min)
      FALSE → IF Is Targets
        TRUE → Targets Agent (Claude + MCP, ~30s)
        FALSE → Compare Agent (Claude + MCP, ~30s)

Calibrate pipeline:
  Get Auth Token → [parallel] Fetch Winners + Fetch Losers
    → Parse Winners CSV + Parse Losers CSV
    → Extract Winner Metrics + Extract Loser Metrics
    → Select Top 15 Winners
    → Loop Deep Dives (SplitInBatches → Deep Dive Agent)
    → Aggregate Deep Dives
    → Merge All Data
    → Generate Fingerprint Agent
    → Format + Send to Slack DM

Targets mode:
  Targets Agent (Claude + MCP) → Send Targets

Compare mode:
  Compare Agent (Claude + MCP) → Send Compare
"""

import json
import sys
from n8n_helpers import (
    uid, find_node, fetch_workflow, push_workflow, sync_local, activate_workflow,
    create_or_update_workflow, make_code_node, make_slack_http_node, make_agent_trio,
    N8N_BASE_URL, HEADERS, REPO_ROOT,
    ANTHROPIC_CRED, MCP_CRED, SLACK_CRED,
    NODE_HTTP_REQUEST, NODE_CODE, NODE_IF, NODE_SPLIT_IN_BATCHES,
    NODE_AGENT, NODE_ANTHROPIC_CHAT, NODE_MCP_CLIENT,
    MODEL_SONNET, PEOPLEAI_MCP_URL,
    WF_EVENTS_HANDLER,
)
import requests

PAI_CLIENT_BODY = "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"

# ── Insights API column specs ──
ACCOUNT_COLUMNS = json.dumps([
    {"slug": "ootb_account_id"},
    {"slug": "ootb_account_name"},
    {"slug": "ootb_account_original_owner"},
    {"slug": "ootb_account_domain"},
    {"slug": "ootb_account_engagement_level"},
    {"slug": "ootb_account_annual_revenue", "variation_id": "ootb_account_annual_revenue_any_time"},
    {"slug": "ootb_account_industry"},
    {"slug": "ootb_account_count_of_meetings_standard", "variation_id": "ootb_account_count_of_meetings_standard_last_30_days"},
    {"slug": "ootb_account_count_of_emails", "variation_id": "ootb_account_count_of_emails_last_30_days"},
    {"slug": "ootb_account_count_of_emails_sent", "variation_id": "ootb_account_count_of_emails_sent_last_30_days"},
    {"slug": "ootb_account_count_of_emails_received", "variation_id": "ootb_account_count_of_emails_received_last_30_days"},
    {"slug": "ootb_account_count_of_external_people_contacted", "variation_id": "ootb_account_count_of_external_people_contacted_last_30_days"},
    {"slug": "ootb_account_count_of_external_people_contacted", "variation_id": "ootb_account_count_of_external_people_contacted_last_7_days"},
    {"slug": "ootb_account_count_of_engaged_executives_external", "variation_id": "ootb_account_count_of_engaged_executives_external_last_30_days"},
    {"slug": "ootb_account_executive_activities", "variation_id": "ootb_account_executive_activities_last_30_days"},
    {"slug": "ootb_account_people_engaged", "variation_id": "ootb_account_people_engaged_last_30_days"},
    {"slug": "ootb_account_closed_won_opportunities", "variation_id": "ootb_account_closed_won_opportunities_last_fyear"},
])

WINNERS_QUERY = json.dumps({
    "object": "account",
    "filter": {"$and": [
        {"attribute": {"slug": "ootb_account_closed_won_opportunities", "variation_id": "ootb_account_closed_won_opportunities_last_fyear"},
         "clause": {"$gt": 0}},
    ]},
    "columns": json.loads(ACCOUNT_COLUMNS),
    "sort": [{"attribute": {"slug": "ootb_account_annual_revenue", "variation_id": "ootb_account_annual_revenue_any_time"}, "direction": "desc"}],
    "limit": 30,
})

LOSERS_QUERY = json.dumps({
    "object": "account",
    "filter": {"$and": [
        {"attribute": {"slug": "ootb_account_closed_won_opportunities", "variation_id": "ootb_account_closed_won_opportunities_last_fyear"},
         "clause": {"$eq": 0}},
    ]},
    "columns": json.loads(ACCOUNT_COLUMNS),
    "sort": [{"attribute": {"slug": "ootb_account_annual_revenue", "variation_id": "ootb_account_annual_revenue_any_time"}, "direction": "desc"}],
    "limit": 30,
})


# ── CSV parser (reusable JS) ──
CSV_PARSER_JS = r"""function parseCsvLine(line) {
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

function csvToObjects(csvData) {
  if (!csvData) return [];
  const lines = csvData.split('\n').filter(l => l.trim());
  if (lines.length < 2) return [];
  const headers = parseCsvLine(lines[0]);
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = parseCsvLine(lines[i]);
    const obj = {};
    headers.forEach((h, idx) => { obj[h] = vals[idx] || ''; });
    rows.push(obj);
  }
  return rows;
}"""


def create_icp_sub_workflow():
    """Create and activate the ICP Analysis sub-workflow. Returns the workflow ID."""
    print("=== Creating ICP Analysis sub-workflow ===\n")

    nodes = []
    connections = {}

    # ── 1. Trigger ──
    nodes.append({
        "parameters": {"inputSource": "passthrough"},
        "id": uid(),
        "name": "Workflow Input Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 600],
    })

    # ── 2. Route Mode (Code) ──
    nodes.append(make_code_node("Route Mode", r"""// Pass through input with mode extracted
const input = $input.first().json;
const mode = (input.mode || 'calibrate').toLowerCase().trim();
return [{ json: { ...input, mode } }];
""", [240, 600]))

    # ── 3. IF Is Calibrate ──
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                    "leftValue": "={{ $json.mode }}",
                    "rightValue": "calibrate",
                }],
            },
        },
        "id": uid(),
        "name": "IF Is Calibrate",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [480, 600],
    })

    # ── 4. IF Is Targets (false branch of calibrate) ──
    nodes.append({
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                    "leftValue": "={{ $json.mode }}",
                    "rightValue": "targets",
                }],
            },
        },
        "id": uid(),
        "name": "IF Is Targets",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [480, 1000],
    })

    # ════════════════════════════════════════════════════
    # CALIBRATE PATH (top — true branch of IF Is Calibrate)
    # ════════════════════════════════════════════════════

    # 5. Send Calibrating Message
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": '={\n  "channel": "{{ $json.channelId }}",\n  "text": ":microscope: Starting ICP calibration — analyzing your closed-won and closed-lost accounts. This takes 3-5 minutes...",\n  "username": "{{ $json.assistantName }}",\n  "icon_emoji": "{{ $json.assistantEmoji }}"\n}',
            "options": {},
        },
        "id": uid(),
        "name": "Send Calibrating Msg",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [760, 400],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # 6. Get Auth Token
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/auth/tokens",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Content-Type", "value": "application/x-www-form-urlencoded"},
            ]},
            "sendBody": True,
            "specifyBody": "string",
            "body": PAI_CLIENT_BODY,
            "options": {},
        },
        "id": uid(),
        "name": "Get Auth Token",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1000, 400],
    })

    # 7. Fetch Winners
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Authorization", "value": "=Bearer {{ $json.access_token }}"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": WINNERS_QUERY,
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Winners",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1260, 300],
    })

    # 8. Fetch Losers
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"},
                {"name": "Content-Type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": LOSERS_QUERY,
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Losers",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1260, 520],
    })

    # 9. Parse Winners CSV
    nodes.append(make_code_node("Parse Winners CSV", CSV_PARSER_JS + r"""
const csvData = $('Fetch Winners').first().json.data;
const rows = csvToObjects(csvData);
return [{ json: { winners: rows, winnerCount: rows.length } }];
""", [1520, 300]))

    # 10. Parse Losers CSV
    nodes.append(make_code_node("Parse Losers CSV", CSV_PARSER_JS + r"""
const csvData = $('Fetch Losers').first().json.data;
const rows = csvToObjects(csvData);
return [{ json: { losers: rows, loserCount: rows.length } }];
""", [1520, 520]))

    # 11. Extract Winner Metrics
    nodes.append(make_code_node("Extract Winner Metrics", r"""// Compute engagement metrics for winner accounts
const winners = $('Parse Winners CSV').first().json.winners || [];

function num(v) { return parseFloat(v) || 0; }

const metrics = winners.map(w => {
  const meetings = num(w['Meetings (Last 30 Days)'] || w['Meetings'] || 0);
  const emailsSent = num(w['Emails Sent (Last 30 Days)'] || w['Emails Sent'] || 0);
  const emailsRecv = num(w['Emails Received (Last 30 Days)'] || w['Emails Received'] || 0);
  const totalEmails = num(w['Emails (Last 30 Days)'] || w['Emails'] || 0);
  const contacts30 = num(w['External People Contacted (Last 30 Days)'] || 0);
  const contacts7 = num(w['External People Contacted (Last 7 Days)'] || 0);
  const execActivities = num(w['Executive Activities (Last 30 Days)'] || 0);
  const engagedExecs = num(w['Engaged Executives External (Last 30 Days)'] || 0);
  const peopleEngaged = num(w['People Engaged (Last 30 Days)'] || 0);
  const revenue = num(w['Annual Revenue'] || 0);

  return {
    accountName: w['Account Name'] || w['Name'] || '',
    accountId: w['Account ID'] || w['Record ID'] || '',
    domain: w['Domain'] || '',
    industry: w['Industry'] || '',
    revenue,
    engagementLevel: w['Engagement Level'] || '',
    meetings, emailsSent, emailsRecv, totalEmails,
    contacts30, contacts7, execActivities, engagedExecs, peopleEngaged,
    meetingRatio: meetings > 0 ? meetings / Math.max(totalEmails, 1) : 0,
    execRatio: execActivities > 0 ? execActivities / Math.max(meetings + totalEmails, 1) : 0,
    emailResponsiveness: emailsSent > 0 ? emailsRecv / emailsSent : 0,
    contactVelocityProxy: contacts7 > 0 && contacts30 > 0 ? contacts7 / contacts30 : 0,
    stakeholderBreadth: peopleEngaged,
    closedWon: num(w['Closed Won Opportunities (Last FYear)'] || 0),
  };
});

return [{ json: { winnerMetrics: metrics, winnerCount: metrics.length } }];
""", [1780, 300]))

    # 12. Extract Loser Metrics
    nodes.append(make_code_node("Extract Loser Metrics", r"""// Compute engagement metrics for loser accounts
const losers = $('Parse Losers CSV').first().json.losers || [];

function num(v) { return parseFloat(v) || 0; }

const metrics = losers.map(w => {
  const meetings = num(w['Meetings (Last 30 Days)'] || w['Meetings'] || 0);
  const emailsSent = num(w['Emails Sent (Last 30 Days)'] || w['Emails Sent'] || 0);
  const emailsRecv = num(w['Emails Received (Last 30 Days)'] || w['Emails Received'] || 0);
  const totalEmails = num(w['Emails (Last 30 Days)'] || w['Emails'] || 0);
  const contacts30 = num(w['External People Contacted (Last 30 Days)'] || 0);
  const contacts7 = num(w['External People Contacted (Last 7 Days)'] || 0);
  const execActivities = num(w['Executive Activities (Last 30 Days)'] || 0);
  const engagedExecs = num(w['Engaged Executives External (Last 30 Days)'] || 0);
  const peopleEngaged = num(w['People Engaged (Last 30 Days)'] || 0);
  const revenue = num(w['Annual Revenue'] || 0);

  return {
    accountName: w['Account Name'] || w['Name'] || '',
    accountId: w['Account ID'] || w['Record ID'] || '',
    domain: w['Domain'] || '',
    industry: w['Industry'] || '',
    revenue,
    engagementLevel: w['Engagement Level'] || '',
    meetings, emailsSent, emailsRecv, totalEmails,
    contacts30, contacts7, execActivities, engagedExecs, peopleEngaged,
    meetingRatio: meetings > 0 ? meetings / Math.max(totalEmails, 1) : 0,
    execRatio: execActivities > 0 ? execActivities / Math.max(meetings + totalEmails, 1) : 0,
    emailResponsiveness: emailsSent > 0 ? emailsRecv / emailsSent : 0,
    contactVelocityProxy: contacts7 > 0 && contacts30 > 0 ? contacts7 / contacts30 : 0,
    stakeholderBreadth: peopleEngaged,
  };
});

return [{ json: { loserMetrics: metrics, loserCount: metrics.length } }];
""", [1780, 520]))

    # 13. Select Top 15 Winners (stratified by revenue tier)
    nodes.append(make_code_node("Select Top 15 Winners", r"""// Stratified selection: 5 top revenue, 5 mid, 5 bottom
const metrics = $('Extract Winner Metrics').first().json.winnerMetrics || [];
const sorted = [...metrics].sort((a, b) => b.revenue - a.revenue);

const n = sorted.length;
if (n <= 15) {
  // Return all if 15 or fewer — emit one item per account for SplitInBatches
  const items = sorted.map(m => ({ json: { account: m } }));
  return items.length > 0 ? items : [{ json: { account: null } }];
}

const tierSize = 5;
const top = sorted.slice(0, tierSize);
const third = Math.floor(n / 3);
const twoThird = Math.floor(2 * n / 3);
const mid = sorted.slice(third, third + tierSize);
const bottom = sorted.slice(Math.max(twoThird, n - tierSize), Math.max(twoThird, n - tierSize) + tierSize);

const selected = [...top, ...mid, ...bottom];
// Deduplicate by accountName
const seen = new Set();
const unique = selected.filter(m => {
  if (seen.has(m.accountName)) return false;
  seen.add(m.accountName);
  return true;
}).slice(0, 15);

return unique.map(m => ({ json: { account: m } }));
""", [2060, 300]))

    # 14. Loop Deep Dives (SplitInBatches)
    nodes.append({
        "parameters": {"batchSize": 1, "options": {}},
        "id": uid(),
        "name": "Loop Deep Dives",
        "type": NODE_SPLIT_IN_BATCHES,
        "typeVersion": 3.1,
        "position": [2320, 300],
    })

    # 15. Deep Dive Agent
    deep_dive_system = (
        "You are an account research analyst. Given an account name, use People.ai tools to gather:\n"
        "1. Recent meeting activity and who attended\n"
        "2. Stakeholder map — which titles/roles are engaged\n"
        "3. Deal progression pattern — how deals moved through stages\n"
        "4. Executive engagement level\n\n"
        "Return a structured JSON (no extra text):\n"
        "```json\n"
        "{\n"
        '  "account_name": "...",\n'
        '  "key_stakeholders": [{"name": "...", "title": "...", "engagement": "high/medium/low"}],\n'
        '  "deal_pattern": "description of how deals progressed",\n'
        '  "exec_engagement": "high/medium/low/none",\n'
        '  "avg_deal_cycle_days": null,\n'
        '  "multi_threaded": true/false,\n'
        '  "champion_identified": true/false,\n'
        '  "win_factors": ["factor1", "factor2"]\n'
        "}\n"
        "```"
    )
    deep_dive_agent_nodes = make_agent_trio(
        "Deep Dive Agent", "DeepDive",
        deep_dive_system,
        '={{ "Research this account and return the structured JSON analysis: " + $json.account.accountName }}',
        [2580, 300],
        connections,
    )
    nodes.extend(deep_dive_agent_nodes)

    # 16. Collect Deep Dive (appends to static data array)
    nodes.append(make_code_node("Collect Deep Dive", r"""// Append deep dive result to accumulator
const agentOutput = $('Deep Dive Agent').first().json.output || '';
const accountData = $('Loop Deep Dives').first().json.account || {};

let deepDive = { accountName: accountData.accountName || 'Unknown', raw: agentOutput };

// Try to parse JSON from agent output
const jsonMatch = agentOutput.match(/```json\s*([\s\S]*?)\s*```/);
if (jsonMatch) {
  try { deepDive = { ...deepDive, ...JSON.parse(jsonMatch[1]) }; } catch(e) {}
} else {
  try { deepDive = { ...deepDive, ...JSON.parse(agentOutput) }; } catch(e) {}
}

// Get existing accumulated results from workflow static data
const existingItems = $('Collect Deep Dive').all();
const accumulated = [];
for (const item of existingItems) {
  if (item.json.deepDives) {
    accumulated.push(...item.json.deepDives);
  }
}
accumulated.push(deepDive);

return [{ json: { deepDive, deepDives: accumulated, count: accumulated.length } }];
""", [2840, 300]))

    # 17. Aggregate Deep Dives (runs after SplitInBatches "done" output)
    nodes.append(make_code_node("Aggregate Deep Dives", r"""// Collect all deep dives from loop iterations
const allItems = $('Collect Deep Dive').all();
const deepDives = [];
const seen = new Set();

for (const item of allItems) {
  const dd = item.json.deepDive;
  if (dd && dd.accountName && !seen.has(dd.accountName)) {
    seen.add(dd.accountName);
    deepDives.push(dd);
  }
}

// Also pass through the input data from earlier nodes
const inputData = $('Route Mode').first().json;

return [{ json: { ...inputData, deepDives, deepDiveCount: deepDives.length } }];
""", [2320, 100]))

    # 18. Merge All Data
    nodes.append(make_code_node("Merge All Data", r"""// Combine winner metrics + loser metrics + deep dives into one payload
const inputData = $('Aggregate Deep Dives').first().json;
const winnerMetrics = $('Extract Winner Metrics').first().json.winnerMetrics || [];
const loserMetrics = $('Extract Loser Metrics').first().json.loserMetrics || [];
const deepDives = inputData.deepDives || [];

// Compute aggregate benchmarks from winners
function avg(arr, key) {
  const vals = arr.map(a => a[key]).filter(v => v > 0);
  return vals.length > 0 ? vals.reduce((s, v) => s + v, 0) / vals.length : 0;
}

const winnerBenchmarks = {
  avgMeetingRatio: avg(winnerMetrics, 'meetingRatio'),
  avgExecRatio: avg(winnerMetrics, 'execRatio'),
  avgEmailResponsiveness: avg(winnerMetrics, 'emailResponsiveness'),
  avgContactVelocity: avg(winnerMetrics, 'contactVelocityProxy'),
  avgStakeholderBreadth: avg(winnerMetrics, 'stakeholderBreadth'),
  avgMeetings: avg(winnerMetrics, 'meetings'),
  avgEmails: avg(winnerMetrics, 'totalEmails'),
  avgExecActivities: avg(winnerMetrics, 'execActivities'),
  avgPeopleEngaged: avg(winnerMetrics, 'peopleEngaged'),
  topIndustries: [...new Set(winnerMetrics.map(w => w.industry).filter(Boolean))].slice(0, 5),
  avgRevenue: avg(winnerMetrics, 'revenue'),
};

const loserBenchmarks = {
  avgMeetingRatio: avg(loserMetrics, 'meetingRatio'),
  avgExecRatio: avg(loserMetrics, 'execRatio'),
  avgEmailResponsiveness: avg(loserMetrics, 'emailResponsiveness'),
  avgContactVelocity: avg(loserMetrics, 'contactVelocityProxy'),
  avgStakeholderBreadth: avg(loserMetrics, 'stakeholderBreadth'),
};

return [{ json: {
  ...inputData,
  winnerMetrics, loserMetrics, deepDives,
  winnerBenchmarks, loserBenchmarks,
  winnerCount: winnerMetrics.length,
  loserCount: loserMetrics.length,
} }];
""", [2580, 100]))

    # 19. Generate Fingerprint Agent
    fingerprint_system = r"""You are an ICP (Ideal Customer Profile) analysis expert for a B2B sales team. You have been given:

1. **Winner Accounts** — accounts that closed deals in the last fiscal year, with engagement metrics
2. **Loser Accounts** — accounts that lost deals (closed-lost, no closed-won), with engagement metrics
3. **Deep Dive Data** — detailed behavioral analysis of top winner accounts

Your job: synthesize all this data into an *ICP Fingerprint* — a clear, actionable profile of what winning accounts look like.

FORMAT YOUR RESPONSE IN SLACK MRKDWN (not markdown). Use *bold*, _italic_, bullet points with •.

Structure your response as:

*:dna: ICP Fingerprint — Calibration Results*

*Engagement Benchmarks (Winners vs Losers):*
• Meeting-to-email ratio: [winner avg] vs [loser avg]
• Executive engagement ratio: [winner avg] vs [loser avg]
• Email responsiveness: [winner avg] vs [loser avg]
• Stakeholder breadth: [winner avg] vs [loser avg]
• Contact velocity: [winner avg] vs [loser avg]

*Behavioral Patterns (from deep dives):*
• Multi-threading: [% of winners that are multi-threaded]
• Champion identification: [pattern]
• Executive access: [pattern]
• Deal velocity: [pattern]

*ICP Profile Summary:*
• Industry sweet spots: [list]
• Revenue range: [range]
• Key signals that predict a win: [3-5 bullets]
• Red flags that predict a loss: [3-5 bullets]

*Quick Reference Scorecard:*
A simple framework reps can use to score any prospect (list 5-7 criteria with point values).

Keep it under 2500 characters total for Slack limits. Be specific with numbers, not vague."""

    fingerprint_nodes = make_agent_trio(
        "Generate Fingerprint Agent", "Fingerprint",
        fingerprint_system,
        '={{ "Analyze this ICP data and generate the fingerprint:\\n\\nWinner Benchmarks: " + JSON.stringify($json.winnerBenchmarks) + "\\n\\nLoser Benchmarks: " + JSON.stringify($json.loserBenchmarks) + "\\n\\nDeep Dives (" + ($json.deepDiveCount || 0) + " accounts): " + JSON.stringify($json.deepDives || []).slice(0, 3000) + "\\n\\nWinner Count: " + ($json.winnerCount || 0) + ", Loser Count: " + ($json.loserCount || 0) }}',
        [2840, 100],
        connections,
    )
    nodes.extend(fingerprint_nodes)

    # 20. Send Fingerprint
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={\n  \"channel\": \"{{ $json.channelId }}\",\n  \"text\": \"ICP Fingerprint generated\",\n  \"blocks\": [{\"type\": \"section\", \"text\": {\"type\": \"mrkdwn\", \"text\": {{ JSON.stringify($('Generate Fingerprint Agent').first().json.output || 'No results generated').slice(0, 3000) }} }}],\n  \"username\": \"{{ $json.assistantName }}\",\n  \"icon_emoji\": \"{{ $json.assistantEmoji }}\"\n}",
            "options": {},
        },
        "id": uid(),
        "name": "Send Fingerprint",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [3100, 100],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ════════════════════════════════════════════════════
    # TARGETS PATH
    # ════════════════════════════════════════════════════

    targets_system = r"""You are a sales targeting expert. Using People.ai tools, identify and rank the user's best-fit prospects.

Apply these ICP benchmarks when evaluating accounts:
• High meeting-to-email ratio (>0.3) = strong fit
• Executive engagement present = strong fit
• Multi-threaded (3+ stakeholders engaged) = strong fit
• Email responsiveness ratio > 0.5 = strong fit
• Growing contact velocity (7-day contacts > 25% of 30-day) = momentum signal

ROLE-BASED FILTERING:
- If the user's digestScope is "my_deals": only show accounts owned by or assigned to the user
- If "team_deals": show the user's team accounts
- If "top_pipeline": show top accounts across the org

Use People.ai tools to:
1. Get the user's accounts with engagement data
2. Score each against the ICP benchmarks
3. Rank by fit score (highest first)

FORMAT IN SLACK MRKDWN (not markdown). Structure as:

*:dart: ICP Target List*

For each account (top 10):
• *Account Name* — Fit Score: X/10
  Strengths: [what matches ICP]
  Gaps: [what's missing]
  Next action: [specific recommendation]

Keep under 2500 characters."""

    targets_agent_nodes = make_agent_trio(
        "Targets Agent", "Targets",
        targets_system,
        '={{ "Find and rank my best ICP-fit prospects. My name is " + $json.repName + ". My digest scope is " + $json.digestScope + ". My email is " + $json.email + "." }}',
        [760, 900],
        connections,
    )
    nodes.extend(targets_agent_nodes)

    # Send Targets
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={\n  \"channel\": \"{{ $json.channelId }}\",\n  \"text\": \"ICP Target List\",\n  \"blocks\": [{\"type\": \"section\", \"text\": {\"type\": \"mrkdwn\", \"text\": {{ JSON.stringify($('Targets Agent').first().json.output || 'No results').slice(0, 3000) }} }}],\n  \"username\": \"{{ $json.assistantName }}\",\n  \"icon_emoji\": \"{{ $json.assistantEmoji }}\"\n}",
            "options": {},
        },
        "id": uid(),
        "name": "Send Targets",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1040, 900],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ════════════════════════════════════════════════════
    # COMPARE PATH
    # ════════════════════════════════════════════════════

    compare_system = r"""You are an ICP fit analyst. The user wants to evaluate a specific account against their Ideal Customer Profile.

Apply these ICP benchmarks:
• Meeting-to-email ratio benchmark: >0.3 = strong
• Executive engagement: present = strong signal
• Multi-threading: 3+ stakeholders = strong
• Email responsiveness: >0.5 reply ratio = healthy
• Contact velocity: 7-day > 25% of 30-day = momentum

Using People.ai tools:
1. Look up the specified account
2. Get engagement metrics, stakeholder data, activity history
3. Score the account on each ICP dimension (1-10 scale)
4. Compute overall ICP fit score
5. Identify gaps and recommend actions

FORMAT IN SLACK MRKDWN (not markdown). Structure as:

*:bar_chart: ICP Fit Report — [Account Name]*

*Overall Fit Score: X/10*

*Dimension Scores:*
• Meeting engagement: X/10
• Executive access: X/10
• Multi-threading: X/10
• Email responsiveness: X/10
• Contact velocity: X/10
• Stakeholder breadth: X/10

*Strengths:*
• [what matches ICP well]

*Gaps:*
• [where it falls short]

*Recommendations:*
• [specific next steps to improve fit]

Keep under 2500 characters."""

    compare_agent_nodes = make_agent_trio(
        "Compare Agent", "Compare",
        compare_system,
        '={{ "Evaluate this account against our ICP: " + ($json.companyName || "unknown company") + ". My name is " + $json.repName + ". My email is " + $json.email + "." }}',
        [760, 1200],
        connections,
    )
    nodes.extend(compare_agent_nodes)

    # Send Compare
    nodes.append({
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/chat.postMessage",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={\n  \"channel\": \"{{ $json.channelId }}\",\n  \"text\": \"ICP Fit Report\",\n  \"blocks\": [{\"type\": \"section\", \"text\": {\"type\": \"mrkdwn\", \"text\": {{ JSON.stringify($('Compare Agent').first().json.output || 'No results').slice(0, 3000) }} }}],\n  \"username\": \"{{ $json.assistantName }}\",\n  \"icon_emoji\": \"{{ $json.assistantEmoji }}\"\n}",
            "options": {},
        },
        "id": uid(),
        "name": "Send Compare",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1040, 1200],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    })

    # ════════════════════════════════════════════════════
    # CONNECTIONS
    # ════════════════════════════════════════════════════

    connections.update({
        "Workflow Input Trigger": {"main": [[{"node": "Route Mode", "type": "main", "index": 0}]]},
        "Route Mode": {"main": [[{"node": "IF Is Calibrate", "type": "main", "index": 0}]]},
        # IF Is Calibrate: true (index 0) → calibrate path, false (index 1) → IF Is Targets
        "IF Is Calibrate": {"main": [
            [{"node": "Send Calibrating Msg", "type": "main", "index": 0}],
            [{"node": "IF Is Targets", "type": "main", "index": 0}],
        ]},
        # IF Is Targets: true (index 0) → targets, false (index 1) → compare
        "IF Is Targets": {"main": [
            [{"node": "Targets Agent", "type": "main", "index": 0}],
            [{"node": "Compare Agent", "type": "main", "index": 0}],
        ]},
        # Calibrate path
        "Send Calibrating Msg": {"main": [[{"node": "Get Auth Token", "type": "main", "index": 0}]]},
        "Get Auth Token": {"main": [
            [
                {"node": "Fetch Winners", "type": "main", "index": 0},
                {"node": "Fetch Losers", "type": "main", "index": 0},
            ]
        ]},
        "Fetch Winners": {"main": [[{"node": "Parse Winners CSV", "type": "main", "index": 0}]]},
        "Fetch Losers": {"main": [[{"node": "Parse Losers CSV", "type": "main", "index": 0}]]},
        "Parse Winners CSV": {"main": [[{"node": "Extract Winner Metrics", "type": "main", "index": 0}]]},
        "Parse Losers CSV": {"main": [[{"node": "Extract Loser Metrics", "type": "main", "index": 0}]]},
        "Extract Winner Metrics": {"main": [[{"node": "Select Top 15 Winners", "type": "main", "index": 0}]]},
        "Select Top 15 Winners": {"main": [[{"node": "Loop Deep Dives", "type": "main", "index": 0}]]},
        # SplitInBatches: output 0 = done, output 1 = loop
        "Loop Deep Dives": {"main": [
            [{"node": "Aggregate Deep Dives", "type": "main", "index": 0}],
            [{"node": "Deep Dive Agent", "type": "main", "index": 0}],
        ]},
        "Deep Dive Agent": {"main": [[{"node": "Collect Deep Dive", "type": "main", "index": 0}]]},
        "Collect Deep Dive": {"main": [[{"node": "Loop Deep Dives", "type": "main", "index": 0}]]},
        "Aggregate Deep Dives": {"main": [[{"node": "Merge All Data", "type": "main", "index": 0}]]},
        "Merge All Data": {"main": [[{"node": "Generate Fingerprint Agent", "type": "main", "index": 0}]]},
        "Generate Fingerprint Agent": {"main": [[{"node": "Send Fingerprint", "type": "main", "index": 0}]]},
        # Targets path
        "Targets Agent": {"main": [[{"node": "Send Targets", "type": "main", "index": 0}]]},
        # Compare path
        "Compare Agent": {"main": [[{"node": "Send Compare", "type": "main", "index": 0}]]},
    })

    # ════════════════════════════════════════════════════
    # BUILD AND PUSH
    # ════════════════════════════════════════════════════

    workflow = {
        "name": "ICP Analysis",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "saveManualExecutions": True,
            "callerPolicy": "workflowsFromSameOwner",
        },
    }

    print(f"  Built workflow with {len(nodes)} nodes")

    # Check if already exists
    name = workflow["name"]
    print(f"Looking for existing '{name}' workflow...")
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows", headers=HEADERS)
    resp.raise_for_status()
    existing = None
    for w in resp.json().get("data", []):
        if w["name"] == name:
            existing = w
            break

    if existing:
        wf_id = existing["id"]
        print(f"  Found existing: {wf_id} — updating")
        result = push_workflow(wf_id, workflow)
    else:
        print("  Not found — creating new workflow")
        resp = requests.post(
            f"{N8N_BASE_URL}/api/v1/workflows",
            headers=HEADERS,
            json=workflow,
        )
        resp.raise_for_status()
        result = resp.json()
        wf_id = result["id"]
        print(f"  Created: {wf_id}")

    # Sub-workflows don't need activation — they're called via executeWorkflow
    # Re-fetch canonical version and sync locally
    final = fetch_workflow(wf_id)
    print("\n=== Syncing ===")
    sync_local(final, "ICP Analysis.json")

    print(f"\n=== ICP Analysis workflow ready ===")
    print(f"  ID: {wf_id}")
    print(f"  Nodes: {len(final['nodes'])}")

    return wf_id


def add_icp_route(icp_workflow_id):
    """Add 'icp' command routing to the Slack Events Handler workflow."""
    print(f"\n=== Adding ICP route to Slack Events Handler (sub-wf: {icp_workflow_id}) ===\n")

    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    conns = wf.get("connections", {})
    print(f"  Fetched: {len(nodes)} nodes")

    # Guard: skip if already added
    node_names = [n["name"] for n in nodes]
    if "Build ICP Thinking" in node_names:
        print("  Build ICP Thinking already exists — skipping")
        return wf

    # ── 1. Update Route by State — add ICP command detection ──
    route_node = find_node(nodes, "Route by State")
    if not route_node:
        raise ValueError("Route by State node not found")
    route_code = route_node["parameters"]["jsCode"]

    # Insert ICP routes BEFORE the insights line
    old_insights = "else if (lower === 'insights' || lower.startsWith('insights ')) route = 'cmd_insights';"
    icp_routes = (
        "else if (lower === 'icp') { route = 'cmd_icp'; subRoute = 'calibrate'; }\n"
        "  else if (lower === 'icp targets') { route = 'cmd_icp'; subRoute = 'targets'; }\n"
        "  else if (lower.startsWith('icp ')) { route = 'cmd_icp'; subRoute = 'compare'; }\n"
        "  " + old_insights
    )
    new_code = route_code.replace(old_insights, icp_routes)
    if new_code == route_code:
        print("  WARNING: Could not find insights route line — trying alternate insertion")
        # Try inserting after brief
        old_brief = "else if (lower === 'brief' || lower.startsWith('brief ')) route = 'cmd_brief';"
        new_code = route_code.replace(
            old_brief,
            old_brief + "\n"
            "  else if (lower === 'icp') { route = 'cmd_icp'; subRoute = 'calibrate'; }\n"
            "  else if (lower === 'icp targets') { route = 'cmd_icp'; subRoute = 'targets'; }\n"
            "  else if (lower.startsWith('icp ')) { route = 'cmd_icp'; subRoute = 'compare'; }"
        )

    # Add companyName to return statement
    # Find messageText in the return and add companyName after it
    if "companyName:" not in new_code:
        new_code = new_code.replace(
            "messageText: text,",
            "messageText: text,\n    companyName: lower.startsWith('icp ') && subRoute === 'compare' ? text.replace(/^icp\\s+/i, '').trim() : '',"
        )
        # If that didn't work, try messageText without trailing comma
        if "companyName:" not in new_code:
            new_code = new_code.replace(
                "messageText: text",
                "messageText: text,\n    companyName: lower.startsWith('icp ') && subRoute === 'compare' ? text.replace(/^icp\\s+/i, '').trim() : ''"
            )

    route_node["parameters"]["jsCode"] = new_code
    print("  Updated Route by State with ICP command routes + companyName output")

    # ── 2. Add Switch Route output for cmd_icp ──
    switch_node = find_node(nodes, "Switch Route")
    if not switch_node:
        raise ValueError("Switch Route node not found")
    rules = switch_node["parameters"]["rules"]["values"]
    new_rule = {
        "conditions": {
            "options": {
                "version": 2,
                "leftValue": "",
                "caseSensitive": True,
                "typeValidation": "strict",
            },
            "combinator": "and",
            "conditions": [{
                "id": uid(),
                "operator": {
                    "name": "filter.operator.equals",
                    "type": "string",
                    "operation": "equals",
                },
                "leftValue": "={{ $json.route }}",
                "rightValue": "cmd_icp",
            }],
        },
        "renameOutput": True,
        "outputKey": "cmd_icp",
    }
    new_output_index = len(rules)
    rules.append(new_rule)
    print(f"  Added Switch Route output {new_output_index} for cmd_icp")

    # ── 3. Add new nodes ──
    # Position them below existing nodes to avoid overlap
    base_x = 2180
    base_y = 3200

    # Open Bot DM (ICP)
    open_dm_node = {
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
            "jsonBody": "={{ JSON.stringify({ users: $json.slackUserId }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Open Bot DM (ICP)",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x, base_y],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(open_dm_node)
    print(f"  Added Open Bot DM (ICP)")

    # Build ICP Thinking
    build_thinking_code = r"""const data = $('Route by State').first().json;
const dmChannel = $json.channel?.id || $json.channel;
const sub = data.subRoute || 'calibrate';
const companyName = data.companyName || '';
const name = data.assistantName || data.assistant_name || 'Aria';
const emoji = data.assistantEmoji || data.assistant_emoji || ':robot_face:';
let text = '';
if (sub === 'calibrate') {
  text = ':mag: Running ICP calibration \u2014 analyzing won vs lost patterns... this takes 3-5 minutes.';
} else if (sub === 'targets') {
  text = ':mag: Finding target accounts matching your ICP... give me about 30 seconds.';
} else {
  text = ':mag: Comparing *' + companyName + '* against your winning pattern... give me about 30 seconds.';
}
return [{ json: { channel: dmChannel, text, username: name, icon_emoji: emoji } }];"""
    build_thinking_node = make_code_node("Build ICP Thinking", build_thinking_code, [base_x + 240, base_y])
    nodes.append(build_thinking_node)
    print(f"  Added Build ICP Thinking")

    # Send ICP Thinking
    send_thinking_node = {
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
            "jsonBody": "={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji, unfurl_links: false, unfurl_media: false }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Send ICP Thinking",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [base_x + 480, base_y],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(send_thinking_node)
    print(f"  Added Send ICP Thinking")

    # Prepare ICP Input
    prepare_input_code = r"""const data = $('Route by State').first().json;
const user = $('Lookup User').first().json;
const dmChannel = $('Open Bot DM (ICP)').first().json.channel?.id || $('Open Bot DM (ICP)').first().json.channel;
const sub = data.subRoute || 'calibrate';
let mode = sub === 'targets' ? 'targets' : sub === 'compare' ? 'compare' : 'calibrate';
let companyName = data.companyName || '';
const repName = (user.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase());
return [{ json: {
  mode, companyName, userId: user.id,
  slackUserId: user.slack_user_id || data.slackUserId,
  email: user.email, channelId: dmChannel,
  assistantName: user.assistant_name || 'Aria',
  assistantEmoji: user.assistant_emoji || ':robot_face:',
  assistantPersona: user.assistant_persona || '',
  digestScope: user.digest_scope || 'my_deals',
  repName,
} }];"""
    prepare_input_node = make_code_node("Prepare ICP Input", prepare_input_code, [base_x + 720, base_y])
    nodes.append(prepare_input_node)
    print(f"  Added Prepare ICP Input")

    # Execute ICP Workflow
    execute_icp_node = {
        "parameters": {
            "workflowId": {
                "__rl": True,
                "mode": "id",
                "value": icp_workflow_id,
            },
            "options": {},
        },
        "id": uid(),
        "name": "Execute ICP Workflow",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [base_x + 960, base_y],
    }
    nodes.append(execute_icp_node)
    print(f"  Added Execute ICP Workflow")

    # ── 4. Wire connections ──
    # Switch Route output → Open Bot DM (ICP)
    if "Switch Route" not in conns:
        conns["Switch Route"] = {"main": []}
    sr_outputs = conns["Switch Route"]["main"]
    while len(sr_outputs) <= new_output_index:
        sr_outputs.append([])
    sr_outputs[new_output_index] = [{"node": "Open Bot DM (ICP)", "type": "main", "index": 0}]
    print(f"  Wired: Switch Route[{new_output_index}] → Open Bot DM (ICP)")

    conns["Open Bot DM (ICP)"] = {
        "main": [[{"node": "Build ICP Thinking", "type": "main", "index": 0}]]
    }
    conns["Build ICP Thinking"] = {
        "main": [[{"node": "Send ICP Thinking", "type": "main", "index": 0}]]
    }
    conns["Send ICP Thinking"] = {
        "main": [[{"node": "Prepare ICP Input", "type": "main", "index": 0}]]
    }
    conns["Prepare ICP Input"] = {
        "main": [[{"node": "Execute ICP Workflow", "type": "main", "index": 0}]]
    }
    print("  Wired: Open Bot DM → Build ICP Thinking → Send ICP Thinking → Prepare ICP Input → Execute ICP Workflow")

    # ── 5. Update help text ──
    icp_help_lines = (
        '"`icp` \\u2014 ICP calibration: analyze won vs lost engagement patterns\\n" +\n'
        '    "`icp targets` \\u2014 Surface unengaged accounts matching your ICP\\n" +\n'
        '    "`icp` _<company>_ \\u2014 Compare a specific account against your winning pattern\\n\\n" +\n'
    )

    # Look for Build Help Response node
    for node in nodes:
        if node["name"] == "Build Help Response":
            old_help = node["parameters"]["jsCode"]

            # Try inserting before "Pause or restart"
            pause_marker = '"*Pause or restart:*'
            if pause_marker in old_help:
                icp_section = (
                    '"*ICP analysis:*\\n" +\n'
                    '    ' + icp_help_lines +
                    '    ' + pause_marker
                )
                new_help = old_help.replace(pause_marker, icp_section)
                node["parameters"]["jsCode"] = new_help
                print("  Updated Build Help Response with ICP commands")
            else:
                print("  WARNING: Could not find 'Pause or restart' marker in Build Help Response")
            break

    # Also look for a "more" help node or fallback help text
    for node in nodes:
        name = node.get("name", "")
        if "parameters" in node and "jsCode" in node.get("parameters", {}):
            code = node["parameters"]["jsCode"]
            # Look for nodes that have help text with existing commands listed
            if "insights" in code and ("brief" in code or "silence" in code) and "icp" not in code:
                # Check if this is a help/more dialog node
                if "`insights`" in code or "insights —" in code or "insights \\u2014" in code:
                    # Insert ICP after insights mention
                    old_insights_help = '"`insights`'
                    if old_insights_help in code:
                        # Find the full insights line and add ICP after its block
                        # Try to find end of insights section
                        insights_block_end = None
                        for marker in ['\\n\\n" +', '\\n" +\n    "*']:
                            if marker in code[code.index(old_insights_help):]:
                                insights_block_end = marker
                                break

                        if insights_block_end:
                            # Find the position after the insights block
                            idx = code.index(old_insights_help)
                            block_end = code.index(insights_block_end, idx) + len(insights_block_end)
                            icp_insert = (
                                '\n    "`icp` \\u2014 ICP calibration\\n" +\n'
                                '    "`icp targets` \\u2014 accounts matching your ICP\\n" +\n'
                                '    "`icp` _<company>_ \\u2014 compare account vs ICP\\n'
                            )
                            new_code = code[:block_end] + icp_insert + code[block_end:]
                            node["parameters"]["jsCode"] = new_code
                            print(f"  Updated '{name}' with ICP commands in help text")

    print(f"  Total nodes: {len(nodes)}")

    # ── 6. Push and sync ──
    print("\n=== Pushing Slack Events Handler ===")
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, "Slack Events Handler.json")

    return result


def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--route-only":
        # Just add the route, using the known workflow ID
        icp_wf_id = sys.argv[2] if len(sys.argv) > 2 else "2lWTeRVCrjx1NtmJ"
        add_icp_route(icp_wf_id)
    else:
        wf_id = create_icp_sub_workflow()
        print(f"\nICP Analysis workflow ID: {wf_id}")
        add_icp_route(wf_id)

    print("\nDone! Users can now type:")
    print("  icp            — ICP calibration (won vs lost patterns)")
    print("  icp targets    — Surface unengaged accounts matching ICP")
    print("  icp <company>  — Compare a specific account against winning pattern")


if __name__ == "__main__":
    main()
