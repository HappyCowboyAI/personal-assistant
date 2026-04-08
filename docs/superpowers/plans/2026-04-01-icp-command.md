# ICP Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `icp`, `icp targets`, and `icp <company>` commands to the People.ai Personal Assistant, porting the ICP calibration workflow from the accountinsights project as a sub-workflow.

**Architecture:** The Slack Events Handler routes `icp` commands to a new sub-workflow ("ICP Analysis") via Execute Workflow. The sub-workflow branches by mode (calibrate/targets/compare) and posts results to the user's DM. The calibrate mode is ported from `icp_calibration_v1.json` with credential remapping. All three modes use Claude + People.ai MCP.

**Tech Stack:** n8n workflows (API-managed via Python), People.ai Insights API + MCP, Claude Sonnet 4.5, Slack Block Kit

**Spec:** `docs/superpowers/specs/2026-04-01-icp-command-design.md`

**Source workflow:** `/Users/scottmetcalf/projects/accountinsights/n8n/workflows/icp_calibration_v1.json`

---

## File Structure

| File | Purpose |
|------|---------|
| `scripts/add_icp_command.py` | Python script to create sub-workflow + modify Events Handler |
| `n8n/workflows/ICP Analysis.json` | New sub-workflow (synced after creation) |
| `n8n/workflows/Slack Events Handler.json` | Modified (new route + nodes) |

---

### Task 1: Create the ICP Analysis sub-workflow with calibrate mode

**Files:**
- Create: `scripts/add_icp_command.py`
- Synced: `n8n/workflows/ICP Analysis.json`

This task creates the sub-workflow via the n8n API with all calibrate-mode nodes. The workflow receives input via `executeWorkflowTrigger` and branches by mode.

- [ ] **Step 1: Create script skeleton with imports and helpers**

Create `scripts/add_icp_command.py`:

```python
#!/usr/bin/env python3
"""Add ICP command: create ICP Analysis sub-workflow + route in Events Handler."""

import sys, os, json, uuid, requests
sys.path.insert(0, os.path.dirname(__file__))
from n8n_helpers import fetch_workflow, push_workflow, sync_local, find_node

WF_EVENTS_HANDLER = "QuQbIaWetunUOFUW"
N8N_BASE = "https://scottai.trackslife.com"

def make_node(name, node_type, position, parameters, credentials=None):
    """Create an n8n node dict."""
    node = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": node_type,
        "typeVersion": 2 if node_type == "n8n-nodes-base.code" else 4.2 if node_type == "n8n-nodes-base.httpRequest" else 1,
        "position": position,
        "parameters": parameters,
    }
    if credentials:
        node["credentials"] = credentials
    return node

def create_workflow(payload):
    """Create a new workflow via n8n API."""
    headers = {"X-N8N-API-KEY": os.getenv("N8N_API_KEY"), "Content-Type": "application/json"}
    resp = requests.post(f"{N8N_BASE}/api/v1/workflows", headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

# Credential IDs for oppassistant
ANTHROPIC_CRED = {"anthropicApi": {"id": "rlAz7ZSl4y6AwRUq", "name": "Anthropic account 2"}}
SLACK_CRED = {"httpHeaderAuth": {"id": "LluVuiMJ8NUbAiG7", "name": "Slackbot Auth Token"}}
MCP_CRED = {"httpMultipleHeadersAuth": {"id": "wvV5pwBeIL7f2vLG", "name": "People.ai MCP Multi-Header"}}

# People.ai OAuth (same as Silence Contract Monitor)
PEOPLEAI_AUTH_BODY = "client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&grant_type=client_credentials"
```

- [ ] **Step 2: Add the sub-workflow node definitions**

Add the calibrate-mode nodes. These are ported from `icp_calibration_v1.json` with credential remapping. The key nodes:

1. **Workflow Input Trigger** — `executeWorkflowTrigger` with `inputSource: "passthrough"`
2. **Route by Mode** — Code node that reads `$json.mode` and sets `isCalibrate`, `isTargets`, `isCompare`
3. **Mode Switch** — IF node that branches on mode
4. **Get Auth Token (ICP)** — POST to `https://api.people.ai/v3/auth/tokens`
5. **Fetch Winners** — POST to `https://api.people.ai/v3/beta/insights/export` with closed_won filter
6. **Fetch Losers** — Same endpoint with closed_lost filter
7. **Parse Winners CSV** — Code node parsing CSV response
8. **Parse Losers CSV** — Same logic
9. **Extract Winner Metrics** — Code node computing derived ratios (meetingRatio, execRatio, etc.)
10. **Extract Loser Metrics** — Same logic for losers
11. **Select Top 15 Winners** — Code node stratifying by revenue tier
12. **Loop Deep Dives** — SplitInBatches (batchSize: 1)
13. **Deep Dive Agent** — Claude agent with People.ai MCP tools
14. **Anthropic Chat Model (Deep Dive)** — Claude Sonnet 4.5
15. **People.ai MCP (Deep Dive)** — MCP client tool
16. **Parse Deep Dive Results** — Code node extracting JSON
17. **Aggregate Deep Dives** — Code node collecting results
18. **Merge All Data** — Code node combining winners + losers + deep dives
19. **Generate Fingerprint Agent** — Claude agent for analysis
20. **Anthropic Chat Model (Fingerprint)** — Claude Sonnet 4.5
21. **Format Calibrate Output** — Code node building Slack blocks
22. **Send Calibrate Result** — HTTP Request posting to DM

Add the following Python code to the script. Each node is defined with its full parameters, code, and connections.

```python
def build_icp_workflow():
    """Build the ICP Analysis sub-workflow."""
    nodes = []
    connections = {}

    # ── Node 1: Workflow Input Trigger ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Workflow Input Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
        "parameters": {"inputSource": "passthrough"},
    })

    # ── Node 2: Route by Mode ──
    ROUTE_MODE_CODE = r"""
const input = $input.first().json;
const mode = (input.mode || 'calibrate').toLowerCase();
return [{
  json: {
    ...input,
    isCalibrate: mode === 'calibrate',
    isTargets: mode === 'targets',
    isCompare: mode === 'compare',
  }
}];
"""
    nodes.append(make_node("Route by Mode", "n8n-nodes-base.code", [200, 0],
        {"jsCode": ROUTE_MODE_CODE}))

    # ── Node 3: Is Calibrate? ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Is Calibrate?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [400, 0],
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [{
                    "id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.isCalibrate }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"},
                }],
            },
            "options": {},
        },
    })

    # ── Node 4: Get Auth Token (ICP) ──
    nodes.append(make_node("Get Auth Token (ICP)", "n8n-nodes-base.httpRequest", [600, -200], {
        "method": "POST",
        "url": "https://api.people.ai/v3/auth/tokens",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/x-www-form-urlencoded"}]},
        "sendBody": True,
        "specifyBody": "string",
        "body": PEOPLEAI_AUTH_BODY,
        "options": {},
    }))

    # ── Insights API columns (shared by winners & losers) ──
    INSIGHTS_COLUMNS = json.dumps([
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

    # ── Node 5: Fetch Winners ──
    WINNERS_BODY = '={{ JSON.stringify({ object: "account", columns: ' + INSIGHTS_COLUMNS + ', filter: { "$and": [{ attribute: { slug: "ootb_account_closed_won_opportunities", variation_id: "ootb_account_closed_won_opportunities_last_fyear" }, clause: { "$gt": 0 } }] } }) }}'
    nodes.append(make_node("Fetch Winners", "n8n-nodes-base.httpRequest", [800, -400], {
        "method": "POST",
        "url": "https://api.people.ai/v3/beta/insights/export",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Authorization", "value": '=Bearer {{ $node["Get Auth Token (ICP)"].json.access_token }}'},
            {"name": "Content-Type", "value": "application/json"},
        ]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": WINNERS_BODY,
        "options": {},
    }))

    # ── Node 6: Fetch Losers ──
    LOSERS_BODY = '={{ JSON.stringify({ object: "account", columns: ' + INSIGHTS_COLUMNS + ', filter: { "$and": [{ attribute: { slug: "ootb_account_closed_lost_opportunities", variation_id: "ootb_account_closed_lost_opportunities_last_fyear" }, clause: { "$gt": 0 } }, { attribute: { slug: "ootb_account_closed_won_opportunities", variation_id: "ootb_account_closed_won_opportunities_last_fyear" }, clause: { "$eq": 0 } }] } }) }}'
    nodes.append(make_node("Fetch Losers", "n8n-nodes-base.httpRequest", [800, 0], {
        "method": "POST",
        "url": "https://api.people.ai/v3/beta/insights/export",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Authorization", "value": '=Bearer {{ $node["Get Auth Token (ICP)"].json.access_token }}'},
            {"name": "Content-Type", "value": "application/json"},
        ]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": LOSERS_BODY,
        "options": {},
    }))

    # ── Node 7: Parse Winners CSV ──
    PARSE_CSV_CODE = r"""
const csvData = $json.data || '';
if (!csvData || csvData.trim().length === 0) {
  return [{ json: { accounts: [], _empty: true } }];
}
function parseLine(line) {
  const vals = []; let inQ = false, cur = '';
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (c === '"' && (i === 0 || line[i-1] !== '\\')) { inQ = !inQ; continue; }
    if (c === ',' && !inQ) { vals.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  vals.push(cur.trim());
  return vals;
}
const lines = csvData.trim().split(/\r?\n/);
const headers = parseLine(lines[0]);
const accounts = [];
for (let i = 1; i < lines.length; i++) {
  const vals = parseLine(lines[i]);
  if (vals.length < headers.length) continue;
  const acct = {};
  headers.forEach((h, idx) => { acct[h] = vals[idx] || ''; });
  accounts.push(acct);
}
return [{ json: { accounts, count: accounts.length } }];
"""
    nodes.append(make_node("Parse Winners CSV", "n8n-nodes-base.code", [1000, -400],
        {"jsCode": PARSE_CSV_CODE}))

    # ── Node 8: Parse Losers CSV ──
    nodes.append(make_node("Parse Losers CSV", "n8n-nodes-base.code", [1000, 0],
        {"jsCode": PARSE_CSV_CODE}))

    # ── Node 9: Extract Winner Metrics ──
    EXTRACT_METRICS_CODE = r"""
const data = $input.first().json;
const accounts = data.accounts || [];
const SAMPLE = 30;
function num(v) { const n = parseFloat(v); return isNaN(n) ? 0 : n; }
function getField(acct, ...names) {
  for (const n of names) {
    for (const k of Object.keys(acct)) {
      if (k.toLowerCase().includes(n.toLowerCase()) && acct[k]) return acct[k];
    }
  }
  return '';
}
const enriched = accounts.map(a => {
  const meetings = num(getField(a, 'Meetings'));
  const emails = num(getField(a, 'Emails (Last 30'));
  const emailsSent = num(getField(a, 'Emails Sent'));
  const emailsRecv = num(getField(a, 'Emails Received'));
  const people30 = num(getField(a, 'People Contacted (Last 30'));
  const people7 = num(getField(a, 'People Contacted (Last 7'));
  const execs = num(getField(a, 'Engaged Executives'));
  const closedWon = num(getField(a, 'Closed Won'));
  const closedLost = num(getField(a, 'Closed Lost'));
  const revenue = num(getField(a, 'Annual Revenue'));
  const total = meetings + emails;
  return {
    accountId: getField(a, 'Account ID'),
    accountName: getField(a, 'Account Name'),
    owner: getField(a, 'Account Owner'),
    domain: getField(a, 'Domain'),
    industry: getField(a, 'Industry'),
    annualRevenue: revenue,
    engagementLevel: getField(a, 'Engagement Level'),
    meetings30d: meetings,
    emails30d: emails,
    emailsSent30d: emailsSent,
    emailsReceived30d: emailsRecv,
    peopleContacted30d: people30,
    peopleContacted7d: people7,
    execsEngaged30d: execs,
    closedWon,
    closedLost,
    meetingRatio: total > 0 ? +(meetings / total).toFixed(3) : 0,
    execRatio: people30 > 0 ? +(execs / people30).toFixed(3) : 0,
    emailResponsiveness: emailsSent > 0 ? +(emailsRecv / emailsSent).toFixed(3) : 0,
    contactVelocityProxy: people30 > 0 ? +((people7 / people30) * 4.286).toFixed(3) : 0,
    stakeholderBreadth: +(people30 / 4.3).toFixed(3),
  };
});
enriched.sort((a, b) => b.closedWon - a.closedWon);
const top = enriched.slice(0, SAMPLE);
return [{ json: { winners: top, winnerCount: top.length } }];
"""
    nodes.append(make_node("Extract Winner Metrics", "n8n-nodes-base.code", [1200, -400],
        {"jsCode": EXTRACT_METRICS_CODE}))

    # ── Node 10: Extract Loser Metrics ──
    EXTRACT_LOSER_CODE = EXTRACT_METRICS_CODE.replace(
        "enriched.sort((a, b) => b.closedWon - a.closedWon);",
        "enriched.sort((a, b) => b.closedLost - a.closedLost);"
    ).replace(
        "return [{ json: { winners: top, winnerCount: top.length } }];",
        "return [{ json: { losers: top, loserCount: top.length } }];"
    )
    nodes.append(make_node("Extract Loser Metrics", "n8n-nodes-base.code", [1200, 0],
        {"jsCode": EXTRACT_LOSER_CODE}))

    # ── Node 11: Select Top 15 Winners ──
    SELECT_TOP_CODE = r"""
const data = $('Extract Winner Metrics').first().json;
const winners = data.winners || [];
const sorted = [...winners].sort((a, b) => b.annualRevenue - a.annualRevenue);
const top5 = sorted.slice(0, 5);
const mid5 = sorted.slice(Math.floor(sorted.length / 3), Math.floor(sorted.length / 3) + 5);
const bot5 = sorted.slice(-5);
const selected = [...top5, ...mid5, ...bot5];
// Deduplicate by accountId
const seen = new Set();
const unique = selected.filter(a => {
  if (seen.has(a.accountId)) return false;
  seen.add(a.accountId);
  return true;
}).slice(0, 15);
return unique.map(a => ({ json: a }));
"""
    nodes.append(make_node("Select Top 15 Winners", "n8n-nodes-base.code", [1400, -400],
        {"jsCode": SELECT_TOP_CODE}))

    # ── Node 12: Loop Deep Dives ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Loop Deep Dives",
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3.1,
        "position": [1600, -400],
        "parameters": {"batchSize": 1, "options": {}},
    })

    # ── Node 13: Deep Dive Agent ──
    DEEP_DIVE_SYSTEM = "You are a sales engagement analyst specializing in activity pattern recognition. Analyze People.ai data to extract structured behavioral patterns. Always output valid JSON."
    DEEP_DIVE_PROMPT = r"""Analyze the account "{{ $json.accountName }}" (People.ai ID: {{ $json.accountId }}).

Use the People.ai MCP tools to:
1. Call get_recent_account_activity to get the 90-day activity timeline
2. Call get_engaged_people to get stakeholder details

Then extract this EXACT JSON structure (no markdown, no explanation, just JSON):
{
  "account_name": "{{ $json.accountName }}",
  "meetings_90d": <number>,
  "meeting_cadence": "weekly|biweekly|sporadic|declining",
  "meeting_ratio": <0.0-1.0>,
  "unique_contacts": <number>,
  "exec_contacts": <number>,
  "exec_ratio": <0.0-1.0>,
  "committee_formed": <true|false>,
  "new_stakeholders_last_30d": <number>,
  "email_responsiveness": <0.0-n>,
  "exec_entry_timing": "early|mid|late|never",
  "engagement_arc": "accelerating|steady|front-loaded|sporadic"
}"""
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Deep Dive Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [1800, -400],
        "parameters": {
            "promptType": "define",
            "text": DEEP_DIVE_PROMPT,
            "options": {"systemMessage": DEEP_DIVE_SYSTEM, "maxIterations": 5},
        },
        "continueOnFail": True,
    })

    # ── Node 14: Anthropic Chat Model (Deep Dive) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Anthropic Chat Model (Deep Dive)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [1800, -200],
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-5-20250929", "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "credentials": ANTHROPIC_CRED,
    })

    # ── Node 15: People.ai MCP (Deep Dive) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "People.ai MCP (Deep Dive)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [2000, -200],
        "parameters": {"endpointUrl": "https://mcp.people.ai/mcp", "authentication": "multipleHeadersAuth"},
        "credentials": MCP_CRED,
    })

    # ── Node 16: Parse Deep Dive Results ──
    PARSE_DD_CODE = r"""
const output = $json.output || $json.text || '';
let result = null;
try {
  const match = output.match(/\{[\s\S]*\}/);
  if (match) result = JSON.parse(match[0]);
} catch(e) {}
if (!result) {
  result = { account_name: 'parse_error', error: true };
}
return [{ json: result }];
"""
    nodes.append(make_node("Parse Deep Dive Results", "n8n-nodes-base.code", [2000, -400],
        {"jsCode": PARSE_DD_CODE}))

    # ── Node 17: Aggregate Deep Dives ──
    AGG_CODE = r"""
const allItems = $('Parse Deep Dive Results').all();
const results = allItems.map(i => i.json).filter(r => !r.error);
return [{ json: { deepDiveResults: results, deepDiveCount: results.length } }];
"""
    nodes.append(make_node("Aggregate Deep Dives", "n8n-nodes-base.code", [2200, -400],
        {"jsCode": AGG_CODE}))

    # ── Node 18: Merge All Data ──
    MERGE_CODE = r"""
const input = $('Workflow Input Trigger').first().json;
const winners = $('Extract Winner Metrics').first().json.winners || [];
const losers = $('Extract Loser Metrics').first().json.losers || [];
const deepDives = $('Aggregate Deep Dives').first().json.deepDiveResults || [];
const todayStr = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
return [{
  json: {
    ...input,
    winners: JSON.stringify(winners),
    losers: JSON.stringify(losers),
    deepDiveResults: JSON.stringify(deepDives),
    winnerCount: winners.length,
    loserCount: losers.length,
    deepDiveCount: deepDives.length,
    todayStr,
  }
}];
"""
    nodes.append(make_node("Merge All Data", "n8n-nodes-base.code", [2400, -200],
        {"jsCode": MERGE_CODE}))

    # ── Node 19: Generate Fingerprint Agent ──
    FP_SYSTEM = "You are a world-class ICP analyst for sales teams. Be precise, data-driven, and specific. Use actual numbers from the data. Every claim must be backed by cohort comparison data. Output in Slack mrkdwn format."
    FP_PROMPT = r"""You are {{ $json.assistantName }}, preparing an ICP Win Pattern Fingerprint for {{ $json.repName }}.

WINNER ACCOUNTS ({{ $json.winnerCount }} accounts with closed-won deals):
{{ $json.winners }}

LOSER ACCOUNTS ({{ $json.loserCount }} accounts with closed-lost, no wins):
{{ $json.losers }}

DEEP DIVE ACTIVITY TIMELINES ({{ $json.deepDiveCount }} winner accounts analyzed via People.ai):
{{ $json.deepDiveResults }}

Analyze this data and generate a Win Pattern Fingerprint in Slack mrkdwn format:

:dart: *WIN PATTERN FINGERPRINT*
Calibrated: {{ $json.todayStr }}
Based on: {{ $json.winnerCount }} winners vs {{ $json.loserCount }} losers (last 12 months)
Deep dive: {{ $json.deepDiveCount }} winner activity timelines analyzed

Include these sections:
1. :bar_chart: *BEHAVIORAL BENCHMARKS* — Table comparing winner vs loser medians with gap and signal strength for: Meeting Quality, Executive Coverage, Email Responsiveness, Contact Velocity, Stakeholder Breadth
2. :trophy: *TOP DIFFERENTIATORS* — Ranked by signal strength (largest gap = strongest)
3. :scales: *RECOMMENDED ICP SCORING WEIGHTS* — Percentages based on gap analysis
4. :chart_with_upwards_trend: *WINNER ENGAGEMENT ARC* — Timeline pattern from deep dives (weeks 1-2, 3-4, 5-8, 8-12)
5. :no_entry_sign: *ANTI-PATTERNS* — What losing accounts look like, with numbers
6. :dart: *SCORING THRESHOLDS* — Strong Fit (>0.70), Moderate Fit (0.40-0.70), Weak Fit (<0.40) with specific criteria

Use Slack mrkdwn: *bold*, bullet points with •, no markdown headers (##), no markdown links."""
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Generate Fingerprint Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [2600, -200],
        "parameters": {
            "promptType": "define",
            "text": FP_PROMPT,
            "options": {"systemMessage": FP_SYSTEM, "maxIterations": 3},
        },
    })

    # ── Node 20: Anthropic Chat Model (Fingerprint) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Anthropic Chat Model (Fingerprint)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [2600, 0],
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-5-20250929", "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "credentials": ANTHROPIC_CRED,
    })

    # ── Node 21: Send Calibrate Result ──
    SEND_CALIBRATE_CODE = r"""
const input = $('Merge All Data').first().json;
const output = $json.output || $json.text || 'No fingerprint generated.';
const text = `:dart: *ICP Calibration Complete*\nRequested by ${input.repName} • ${input.todayStr}\n\n${output}`;
return [{
  json: {
    channel: input.channelId,
    text,
    username: input.assistantName || 'Aria',
    icon_emoji: input.assistantEmoji || ':robot_face:',
  }
}];
"""
    nodes.append(make_node("Format Calibrate Output", "n8n-nodes-base.code", [2800, -200],
        {"jsCode": SEND_CALIBRATE_CODE}))

    nodes.append(make_node("Send Calibrate Result", "n8n-nodes-base.httpRequest", [3000, -200], {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji, unfurl_links: false, unfurl_media: false }) }}',
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Connections for calibrate mode ──
    connections = {
        "Workflow Input Trigger": {"main": [[{"node": "Route by Mode", "type": "main", "index": 0}]]},
        "Route by Mode": {"main": [[{"node": "Is Calibrate?", "type": "main", "index": 0}]]},
        "Is Calibrate?": {"main": [
            [{"node": "Get Auth Token (ICP)", "type": "main", "index": 0}],  # true
            [],  # false → targets/compare (Task 2)
        ]},
        "Get Auth Token (ICP)": {"main": [[
            {"node": "Fetch Winners", "type": "main", "index": 0},
            {"node": "Fetch Losers", "type": "main", "index": 0},
        ]]},
        "Fetch Winners": {"main": [[{"node": "Parse Winners CSV", "type": "main", "index": 0}]]},
        "Fetch Losers": {"main": [[{"node": "Parse Losers CSV", "type": "main", "index": 0}]]},
        "Parse Winners CSV": {"main": [[{"node": "Extract Winner Metrics", "type": "main", "index": 0}]]},
        "Parse Losers CSV": {"main": [[{"node": "Extract Loser Metrics", "type": "main", "index": 0}]]},
        "Extract Winner Metrics": {"main": [[{"node": "Select Top 15 Winners", "type": "main", "index": 0}]]},
        "Select Top 15 Winners": {"main": [[{"node": "Loop Deep Dives", "type": "main", "index": 0}]]},
        "Loop Deep Dives": {"main": [
            [{"node": "Aggregate Deep Dives", "type": "main", "index": 0}],  # done
            [{"node": "Deep Dive Agent", "type": "main", "index": 0}],  # loop
        ]},
        "Deep Dive Agent": {"main": [[{"node": "Parse Deep Dive Results", "type": "main", "index": 0}]]},
        "Anthropic Chat Model (Deep Dive)": {"ai_languageModel": [[{"node": "Deep Dive Agent", "type": "ai_languageModel", "index": 0}]]},
        "People.ai MCP (Deep Dive)": {"ai_tool": [[{"node": "Deep Dive Agent", "type": "ai_tool", "index": 0}]]},
        "Parse Deep Dive Results": {"main": [[{"node": "Loop Deep Dives", "type": "main", "index": 0}]]},
        "Aggregate Deep Dives": {"main": [[{"node": "Merge All Data", "type": "main", "index": 0}]]},
        "Merge All Data": {"main": [[{"node": "Generate Fingerprint Agent", "type": "main", "index": 0}]]},
        "Generate Fingerprint Agent": {"main": [[{"node": "Format Calibrate Output", "type": "main", "index": 0}]]},
        "Anthropic Chat Model (Fingerprint)": {"ai_languageModel": [[{"node": "Generate Fingerprint Agent", "type": "ai_languageModel", "index": 0}]]},
        "Format Calibrate Output": {"main": [[{"node": "Send Calibrate Result", "type": "main", "index": 0}]]},
    }

    return nodes, connections
```

- [ ] **Step 3: Add targets and compare mode nodes**

Add these nodes to the `build_icp_workflow` function, branching from the `Is Calibrate?` false output:

```python
    # ── Node: Is Targets? ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Is Targets?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [600, 400],
        "parameters": {
            "conditions": {
                "options": {"version": 2, "caseSensitive": True, "typeValidation": "loose"},
                "combinator": "and",
                "conditions": [{
                    "id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.isTargets }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"},
                }],
            },
            "options": {},
        },
    })

    # ── Targets Agent ──
    TARGETS_SYSTEM = r"""You are {{ $json.assistantName }}, a personal sales assistant for {{ $json.repName }}.
You have access to People.ai MCP tools. Use them to find accounts that match the ICP winning pattern but have low current engagement.

ICP WINNING PATTERN BENCHMARKS:
- Meeting Quality Ratio > 0.35 (meetings as % of total touchpoints)
- Executive Coverage > 0.20 (exec contacts as % of total contacts)
- Email Responsiveness > 0.40 (received/sent ratio)
- Contact Velocity > 1.0 (weekly new contact rate)
- Stakeholder Breadth > 2.0 contacts/week

ROLE CONTEXT:
- Digest scope: {{ $json.digestScope }}
- User email: {{ $json.email }}
- If scope is "my_deals", focus ONLY on accounts owned by {{ $json.repName }}
- If scope is "team_deals", include team accounts
- If scope is "top_pipeline", scan broadly

Find accounts where firmographics suggest ICP fit but engagement metrics are weak — these are the opportunities. Use top_records and ask_sales_ai_about_account tools.

Output in Slack mrkdwn format. List up to 10 target accounts ranked by ICP fit potential. For each: account name, estimated ICP score, one-line reason for the fit, and one-line gap to address."""

    TARGETS_PROMPT = r"""Find ICP target accounts for {{ $json.repName }}.

Use People.ai MCP tools to:
1. Get the top accounts (use top_records tool)
2. For promising but low-engagement accounts, check their status with get_account_status
3. Score them against the ICP benchmarks in your instructions

Format as:
:dart: *ICP Target Accounts*
X accounts match your winning pattern but need engagement:

:large_green_circle: *AccountName* — ICP Score: X.XX (Strong/Moderate Fit)
   One-line reason + one-line gap

Keep it concise — max 10 accounts."""

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Targets Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [800, 300],
        "parameters": {
            "promptType": "define",
            "text": TARGETS_PROMPT,
            "options": {"systemMessage": TARGETS_SYSTEM, "maxIterations": 10},
        },
        "continueOnFail": True,
    })

    # ── Anthropic Chat Model (Targets) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Anthropic Chat Model (Targets)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [800, 500],
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-5-20250929", "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "credentials": ANTHROPIC_CRED,
    })

    # ── People.ai MCP (Targets) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "People.ai MCP (Targets)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [1000, 500],
        "parameters": {"endpointUrl": "https://mcp.people.ai/mcp", "authentication": "multipleHeadersAuth"},
        "credentials": MCP_CRED,
    })

    # ── Format Targets Output ──
    FORMAT_TARGETS_CODE = r"""
const input = $('Route by Mode').first().json;
const output = $json.output || $json.text || 'Could not find target accounts.';
return [{
  json: {
    channel: input.channelId,
    text: output,
    username: input.assistantName || 'Aria',
    icon_emoji: input.assistantEmoji || ':robot_face:',
  }
}];
"""
    nodes.append(make_node("Format Targets Output", "n8n-nodes-base.code", [1000, 300],
        {"jsCode": FORMAT_TARGETS_CODE}))

    # ── Send Targets Result ──
    nodes.append(make_node("Send Targets Result", "n8n-nodes-base.httpRequest", [1200, 300], {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji, unfurl_links: false, unfurl_media: false }) }}',
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Compare Agent ──
    COMPARE_SYSTEM = r"""You are {{ $json.assistantName }}, a personal sales assistant for {{ $json.repName }}.
You have access to People.ai MCP tools. Use them to analyze a specific account against ICP benchmarks.

ICP WINNING PATTERN BENCHMARKS (from calibration analysis):
- Meeting Quality Ratio benchmark: 0.42 (winner median). Scoring: >0.35 strong, 0.20-0.35 moderate, <0.20 weak
- Executive Coverage benchmark: 0.24. Scoring: >0.20 strong, 0.10-0.20 moderate, <0.10 weak
- Email Responsiveness benchmark: 0.52. Scoring: >0.40 strong, 0.20-0.40 moderate, <0.20 weak
- Contact Velocity benchmark: 1.3. Scoring: >1.0 strong, 0.6-1.0 moderate, <0.6 weak
- Stakeholder Breadth benchmark: 3.1/week. Scoring: >2.0 strong, 1.0-2.0 moderate, <1.0 weak

Scoring weights: Meeting Quality 30%, Exec Coverage 25%, Email Responsiveness 20%, Contact Velocity 15%, Stakeholder Breadth 10%

Use the MCP tools to:
1. find_account to locate the account
2. get_account_status for engagement metrics
3. get_engaged_people for stakeholder details
4. get_recent_account_activity for timeline

Then score each dimension and compute a weighted overall ICP Fit Score (0.0-1.0).

Output in Slack mrkdwn format."""

    COMPARE_PROMPT = r"""Analyze *{{ $json.companyName }}* against the ICP winning pattern for {{ $json.repName }}.

Use People.ai MCP tools to research this account, then produce:

:dart: *ICP Fit Report — {{ $json.companyName }}*

*Overall Score:* X.XX (Strong/Moderate/Weak Fit)

Score each dimension with emoji indicator:
:white_check_mark: = at or above benchmark
:warning: = below benchmark
:red_circle: = significantly below

Then add a :bulb: *Recommendation* section with 1-2 specific actions to improve fit.

Keep it concise."""

    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Compare Agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 1.7,
        "position": [800, 700],
        "parameters": {
            "promptType": "define",
            "text": COMPARE_PROMPT,
            "options": {"systemMessage": COMPARE_SYSTEM, "maxIterations": 10},
        },
        "continueOnFail": True,
    })

    # ── Anthropic Chat Model (Compare) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Anthropic Chat Model (Compare)",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": [800, 900],
        "parameters": {
            "model": {"__rl": True, "mode": "list", "value": "claude-sonnet-4-5-20250929", "cachedResultName": "Claude Sonnet 4.5"},
            "options": {},
        },
        "credentials": ANTHROPIC_CRED,
    })

    # ── People.ai MCP (Compare) ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "People.ai MCP (Compare)",
        "type": "@n8n/n8n-nodes-langchain.mcpClientTool",
        "typeVersion": 1.2,
        "position": [1000, 900],
        "parameters": {"endpointUrl": "https://mcp.people.ai/mcp", "authentication": "multipleHeadersAuth"},
        "credentials": MCP_CRED,
    })

    # ── Format Compare Output ──
    FORMAT_COMPARE_CODE = r"""
const input = $('Route by Mode').first().json;
const output = $json.output || $json.text || 'Could not analyze this account.';
return [{
  json: {
    channel: input.channelId,
    text: output,
    username: input.assistantName || 'Aria',
    icon_emoji: input.assistantEmoji || ':robot_face:',
  }
}];
"""
    nodes.append(make_node("Format Compare Output", "n8n-nodes-base.code", [1000, 700],
        {"jsCode": FORMAT_COMPARE_CODE}))

    # ── Send Compare Result ──
    nodes.append(make_node("Send Compare Result", "n8n-nodes-base.httpRequest", [1200, 700], {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji, unfurl_links: false, unfurl_media: false }) }}',
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Add targets/compare connections ──
    connections["Is Calibrate?"]["main"][1] = [{"node": "Is Targets?", "type": "main", "index": 0}]
    connections["Is Targets?"] = {"main": [
        [{"node": "Targets Agent", "type": "main", "index": 0}],  # true
        [{"node": "Compare Agent", "type": "main", "index": 0}],  # false = compare
    ]}
    connections["Targets Agent"] = {"main": [[{"node": "Format Targets Output", "type": "main", "index": 0}]]}
    connections["Anthropic Chat Model (Targets)"] = {"ai_languageModel": [[{"node": "Targets Agent", "type": "ai_languageModel", "index": 0}]]}
    connections["People.ai MCP (Targets)"] = {"ai_tool": [[{"node": "Targets Agent", "type": "ai_tool", "index": 0}]]}
    connections["Format Targets Output"] = {"main": [[{"node": "Send Targets Result", "type": "main", "index": 0}]]}
    connections["Compare Agent"] = {"main": [[{"node": "Format Compare Output", "type": "main", "index": 0}]]}
    connections["Anthropic Chat Model (Compare)"] = {"ai_languageModel": [[{"node": "Compare Agent", "type": "ai_languageModel", "index": 0}]]}
    connections["People.ai MCP (Compare)"] = {"ai_tool": [[{"node": "Compare Agent", "type": "ai_tool", "index": 0}]]}
    connections["Format Compare Output"] = {"main": [[{"node": "Send Compare Result", "type": "main", "index": 0}]]}

    return nodes, connections
```

- [ ] **Step 4: Add create_workflow call and push**

```python
def create_icp_sub_workflow():
    """Create the ICP Analysis sub-workflow on n8n."""
    nodes, connections = build_icp_workflow()
    payload = {
        "name": "ICP Analysis",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }
    result = create_workflow(payload)
    wf_id = result["id"]
    print(f"Created ICP Analysis workflow: {wf_id} ({len(result['nodes'])} nodes)")

    # Activate
    import requests, os
    headers = {"X-N8N-API-KEY": os.getenv("N8N_API_KEY"), "Content-Type": "application/json"}
    base = "https://scottai.trackslife.com"
    resp = requests.post(f"{base}/api/v1/workflows/{wf_id}/activate", headers=headers)
    print(f"Activated: {resp.status_code}")

    # Sync local
    sync_local(fetch_workflow(wf_id), "ICP Analysis.json")
    return wf_id
```

- [ ] **Step 5: Run and verify sub-workflow creation**

```bash
cd scripts && python3 -c "from add_icp_command import create_icp_sub_workflow; create_icp_sub_workflow()"
```

Expected: `Created ICP Analysis workflow: <id> (XX nodes)` + `Activated: 200`

- [ ] **Step 6: Commit**

```bash
git add scripts/add_icp_command.py n8n/workflows/ICP\ Analysis.json
git commit -m "feat: create ICP Analysis sub-workflow with calibrate/targets/compare modes"
```

---

### Task 2: Add ICP routing to the Slack Events Handler

**Files:**
- Modify: `scripts/add_icp_command.py` (add Events Handler modification)
- Synced: `n8n/workflows/Slack Events Handler.json`

This task adds the `cmd_icp` route to the Events Handler, plus the thinking message, input preparation, and Execute Workflow nodes.

- [ ] **Step 1: Add the Events Handler modification function**

Add to `scripts/add_icp_command.py`:

```python
def add_icp_route(icp_workflow_id):
    """Add cmd_icp route to the Slack Events Handler."""
    wf = fetch_workflow(WF_EVENTS_HANDLER)
    nodes = wf["nodes"]
    connections = wf["connections"]

    # ── Step A: Update Route by State code to add icp routing ──
    route_node = find_node(nodes, "Route by State")
    code = route_node["parameters"]["jsCode"]

    # Insert icp routing before the catch-all
    icp_route = """
  else if (lower === 'icp') {
    route = 'cmd_icp'; subRoute = 'calibrate';
  } else if (lower === 'icp targets') {
    route = 'cmd_icp'; subRoute = 'targets';
  } else if (lower.startsWith('icp ')) {
    route = 'cmd_icp'; subRoute = 'compare';
  }"""

    # Insert before the line with cmd_insights
    code = code.replace(
        "else if (lower === 'insights'",
        icp_route + "\n  else if (lower === 'insights'"
    )
    route_node["parameters"]["jsCode"] = code

    # ── Step B: Add Switch Route output for cmd_icp ──
    switch_node = find_node(nodes, "Switch Route")
    rules = switch_node["parameters"]["rules"]["values"]
    rules.append({
        "conditions": {
            "options": {"version": 2, "caseSensitive": True, "typeValidation": "strict"},
            "combinator": "and",
            "conditions": [{
                "id": str(uuid.uuid4()),
                "operator": {"name": "filter.operator.equals", "type": "string", "operation": "equals"},
                "leftValue": "={{ $json.route }}",
                "rightValue": "cmd_icp",
            }],
        },
        "renameOutput": True,
        "outputKey": "cmd_icp",
    })
    icp_output_idx = len(rules) - 1

    # ── Step C: Add Open Bot DM (ICP) node ──
    # Find a good position near other cmd nodes
    nodes.append(make_node("Open Bot DM (ICP)", "n8n-nodes-base.httpRequest", [3200, 2800], {
        "method": "POST",
        "url": "https://slack.com/api/conversations.open",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ users: $json.slackUserId }) }}',
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Step D: Add Send ICP Thinking node ──
    THINKING_CODE = r"""
const data = $('Route by State').first().json;
const dmChannel = $json.channel?.id || $json.channel;
const sub = data.subRoute || 'calibrate';
const companyName = data.companyName || '';
const name = data.assistantName || 'Aria';
let thinkingText = '';
if (sub === 'calibrate') {
  thinkingText = ':mag: Running ICP calibration \u2014 analyzing won vs lost patterns... this takes 3-5 minutes.';
} else if (sub === 'targets') {
  thinkingText = ':mag: Finding target accounts matching your ICP... give me about 30 seconds.';
} else {
  thinkingText = ':mag: Comparing *' + companyName + '* against your winning pattern... give me about 30 seconds.';
}
return [{
  json: {
    channel: dmChannel,
    text: thinkingText,
    username: name,
    icon_emoji: data.assistantEmoji || ':robot_face:',
  }
}];
"""
    nodes.append(make_node("Build ICP Thinking", "n8n-nodes-base.code", [3400, 2800],
        {"jsCode": THINKING_CODE}))

    nodes.append(make_node("Send ICP Thinking", "n8n-nodes-base.httpRequest", [3600, 2800], {
        "method": "POST",
        "url": "https://slack.com/api/chat.postMessage",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ channel: $json.channel, text: $json.text, username: $json.username, icon_emoji: $json.icon_emoji }) }}',
        "options": {},
    }, credentials=SLACK_CRED))

    # ── Step E: Add Prepare ICP Input node ──
    PREPARE_CODE = r"""
const data = $('Route by State').first().json;
const user = $('Lookup User').first().json;
const dmChannel = $('Open Bot DM (ICP)').first().json.channel?.id || $('Open Bot DM (ICP)').first().json.channel;
const sub = data.subRoute || 'calibrate';
const lower = (data.messageText || '').toLowerCase().trim();

let mode = 'calibrate';
let companyName = '';
if (sub === 'targets') {
  mode = 'targets';
} else if (sub === 'compare') {
  mode = 'compare';
  // Extract company name: everything after "icp "
  companyName = (data.messageText || '').replace(/^icp\s+/i, '').trim();
}

const repName = (user.email || '').split('@')[0]
  .replace(/\./g, ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

return [{
  json: {
    mode,
    companyName,
    userId: user.id,
    slackUserId: user.slack_user_id || data.slackUserId,
    email: user.email,
    channelId: dmChannel,
    assistantName: user.assistant_name || 'Aria',
    assistantEmoji: user.assistant_emoji || ':robot_face:',
    assistantPersona: user.assistant_persona || '',
    digestScope: user.digest_scope || 'my_deals',
    repName,
  }
}];
"""
    nodes.append(make_node("Prepare ICP Input", "n8n-nodes-base.code", [3800, 2800],
        {"jsCode": PREPARE_CODE}))

    # ── Step F: Add Execute ICP Workflow node ──
    nodes.append({
        "id": str(uuid.uuid4()),
        "name": "Execute ICP Workflow",
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1.2,
        "position": [4000, 2800],
        "parameters": {
            "workflowId": {"__rl": True, "mode": "id", "value": icp_workflow_id},
            "options": {"waitForSubWorkflow": True},
        },
    })

    # ── Step G: Wire it all up ──
    # Switch Route output → Open Bot DM (ICP)
    main = connections["Switch Route"]["main"]
    while len(main) <= icp_output_idx:
        main.append([])
    main[icp_output_idx] = [{"node": "Open Bot DM (ICP)", "type": "main", "index": 0}]

    connections["Open Bot DM (ICP)"] = {"main": [[{"node": "Build ICP Thinking", "type": "main", "index": 0}]]}
    connections["Build ICP Thinking"] = {"main": [[{"node": "Send ICP Thinking", "type": "main", "index": 0}]]}
    connections["Send ICP Thinking"] = {"main": [[{"node": "Prepare ICP Input", "type": "main", "index": 0}]]}
    connections["Prepare ICP Input"] = {"main": [[{"node": "Execute ICP Workflow", "type": "main", "index": 0}]]}

    # Push
    result = push_workflow(WF_EVENTS_HANDLER, wf)
    print(f"Pushed Events Handler: {len(result['nodes'])} nodes")
    sync_local(fetch_workflow(WF_EVENTS_HANDLER), "Slack Events Handler.json")
```

- [ ] **Step 2: Add main() and run**

```python
def main():
    print("=== Creating ICP Analysis sub-workflow ===")
    icp_workflow_id = create_icp_sub_workflow()

    print(f"\n=== Adding ICP route to Events Handler ===")
    add_icp_route(icp_workflow_id)

    print(f"\n=== Done! ===")
    print(f"ICP Analysis workflow ID: {icp_workflow_id}")
    print("Commands: icp | icp targets | icp <company>")

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script**

```bash
cd scripts && python3 add_icp_command.py
```

Expected:
```
=== Creating ICP Analysis sub-workflow ===
Created ICP Analysis workflow: <id> (XX nodes)
Activated: 200
=== Adding ICP route to Events Handler ===
Pushed Events Handler: XXX nodes
=== Done! ===
```

- [ ] **Step 4: Commit**

```bash
git add scripts/add_icp_command.py n8n/workflows/
git commit -m "feat: add icp command routing to Events Handler"
```

---

### Task 3: Test all three modes

- [ ] **Step 1: Test calibrate mode**

DM the bot: `icp`

Expected: Thinking message appears immediately, then 3-5 minutes later the Win Pattern Fingerprint posts with behavioral benchmarks, differentiators, anti-patterns, and scoring thresholds.

- [ ] **Step 2: Test targets mode**

DM the bot: `icp targets`

Expected: Thinking message, then ~30 seconds later a ranked list of target accounts with ICP scores.

- [ ] **Step 3: Test compare mode**

DM the bot: `icp flexera`

Expected: Thinking message, then ~30 seconds later an ICP Fit Report for Flexera with dimension scores and recommendations.

- [ ] **Step 4: Verify assistant identity**

All responses should use the user's personalized assistant name/emoji (e.g., "Pikachu" with `:pikachu:`), not the default "Aria".

- [ ] **Step 5: Fix any issues and commit**

```bash
git add -A && git commit -m "fix: address ICP command testing issues"
```

---

### Task 4: Update MEMORY.md with ICP Analysis workflow ID

- [ ] **Step 1: Add workflow ID to memory**

After creation, note the workflow ID and update memory with the new workflow reference.

- [ ] **Step 2: Commit**

```bash
git add .claude/ && git commit -m "chore: update memory with ICP Analysis workflow ID"
```
