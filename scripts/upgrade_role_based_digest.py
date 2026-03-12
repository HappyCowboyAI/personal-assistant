#!/usr/bin/env python3
"""
Upgrade: Add role-based digest customization
- Modifies Sales Digest workflow (7sinwSgjkEA40zDj): adds hierarchy fetch, role-aware filtering, role-specific prompts
- Modifies Slack Events Handler workflow (QuQbIaWetunUOFUW): adds department/division/digest_scope to Create User Record
- Syncs local JSON files
"""

import json
import os
import uuid
import requests
import sys

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SALES_DIGEST_ID = "7sinwSgjkEA40zDj"
SLACK_EVENTS_ID = "QuQbIaWetunUOFUW"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


def fetch_workflow(workflow_id):
    resp = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def push_workflow(workflow_id, workflow):
    payload = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow.get("settings", {}),
        "staticData": workflow.get("staticData"),
    }
    resp = requests.put(f"{N8N_BASE_URL}/api/v1/workflows/{workflow_id}", headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def sync_local(workflow_id, workflow, filename):
    path = os.path.join(REPO_ROOT, "n8n", "workflows", filename)
    with open(path, "w") as f:
        json.dump(workflow, f, indent=4)
    print(f"  Synced {path}")


# ---------------------------------------------------------------------------
# SLACK EVENTS HANDLER — Add department/division/digest_scope to onboarding
# ---------------------------------------------------------------------------

def upgrade_slack_events(wf):
    print("\n=== Upgrading Slack Events Handler ===")
    nodes = wf["nodes"]

    # Find Create User Record node and add 3 fields
    for node in nodes:
        if node["name"] == "Create User Record":
            values = node["parameters"]["fieldsToSend"]["values"]
            existing_fields = [v["fieldId"] for v in values]

            if "department" in existing_fields:
                print("  Already has department field — skipping")
                return wf

            values.append({
                "fieldId": "department",
                "fieldValue": "={{ $('Get Slack User Info').first().json.user.profile.department || '' }}"
            })
            values.append({
                "fieldId": "division",
                "fieldValue": "={{ $('Get Slack User Info').first().json.user.profile.title || '' }}"
            })
            values.append({
                "fieldId": "digest_scope",
                "fieldValue": "={{ (() => { const t = ($('Get Slack User Info').first().json.user.profile.title || '').toLowerCase(); if (/^(vp|svp|evp|cro|chief|head of)/.test(t)) return 'top_pipeline'; if (/(manager|director)/.test(t)) return 'team_deals'; return 'my_deals'; })() }}"
            })
            print(f"  Added 3 fields to Create User Record (now {len(values)} fields)")
            break

    return wf


# ---------------------------------------------------------------------------
# SALES DIGEST — Add hierarchy nodes, role-aware filtering, role prompts
# ---------------------------------------------------------------------------

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

  const name = getField(row, 'ootb_user_name', 'User Name', 'Name');
  const email = getField(row, 'ootb_user_email', 'User Email', 'Email').toLowerCase();
  const manager = getField(row, 'ootb_user_manager', 'Manager', 'User Manager');

  if (email) {
    hierarchy[email] = { name, email, manager };
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

FILTER_USER_OPPS_CODE = r"""// Filter pre-fetched opps based on user's role/digest_scope
const user = $('Split In Batches').first().json;
const allOpps = $('Parse Opps CSV').first().json.opps;
const hierarchyData = $('Parse Hierarchy').first().json;

// Derive rep name from email: scott.metcalf@people.ai -> "Scott Metcalf"
const repName = (user.email || '').split('@')[0]
  .replace(/\./g, ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

const repLower = repName.toLowerCase();
const digestScope = user.digest_scope || 'my_deals';
const userEmail = (user.email || '').toLowerCase();

let userOpps = [];
let scopeLabel = '';

if (digestScope === 'my_deals') {
  // IC view: filter by owner name
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return owners.includes(repLower);
  });
  scopeLabel = repName + "'s OPEN OPPORTUNITIES";

} else if (digestScope === 'team_deals') {
  // Manager view: own deals + all direct reports' deals
  const managerToReports = hierarchyData.managerToReports || {};
  let reportNames = [repLower];

  // Match by manager name
  for (const [mgrKey, reports] of Object.entries(managerToReports)) {
    if (mgrKey.includes(repLower) || repLower.includes(mgrKey)) {
      for (const report of reports) {
        const rName = (report.name || '').toLowerCase();
        if (rName && !reportNames.includes(rName)) {
          reportNames.push(rName);
        }
      }
    }
  }

  // Also match by email key
  if (managerToReports[userEmail]) {
    for (const report of managerToReports[userEmail]) {
      const rName = (report.name || '').toLowerCase();
      if (rName && !reportNames.includes(rName)) {
        reportNames.push(rName);
      }
    }
  }

  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return reportNames.some(name => owners.includes(name));
  });

  // Sort by close date ascending (nearest first)
  userOpps.sort((a, b) => new Date(a.closeDate) - new Date(b.closeDate));
  scopeLabel = repName + "'s TEAM PIPELINE (" + reportNames.length + " reps)";

} else if (digestScope === 'top_pipeline') {
  // Exec view: all opps, sorted by amount, top 25
  userOpps = [...allOpps];
  userOpps.sort((a, b) => {
    const amtA = parseFloat((a.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    const amtB = parseFloat((b.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    return amtB - amtA;
  });
  userOpps = userOpps.slice(0, 25);
  scopeLabel = "TOP PIPELINE (" + allOpps.length + " total open deals, showing top 25 by amount)";
}

// Build formatted table for the system prompt
let oppTable = '';
if (userOpps.length > 0) {
  if (digestScope === 'my_deals') {
    oppTable = '| Opportunity | Account | Stage | Close Date | Amount | Engagement |\n';
    oppTable += '|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' |\n';
    }
  } else {
    // Include Owner column for team/exec views
    oppTable = '| Opportunity | Account | Owner | Stage | Close Date | Amount | Engagement |\n';
    oppTable += '|---|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.owners + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' |\n';
    }
  }
} else {
  oppTable = '(No open opportunities found)';
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
    scopeLabel
  }
}];
"""

RESOLVE_IDENTITY_CODE = r"""const user = $('Filter User Opps').first().json;

const assistantName = user.assistant_name || 'Aria';
const assistantEmoji = user.assistant_emoji || ':robot_face:';
const assistantPersona = user.assistant_persona || 'direct, action-oriented, and conversational';
const repName = user.repName || (user.email || '').split('@')[0].replace(/\./g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Rep';
const timezone = user.timezone || 'America/Los_Angeles';
const currentDate = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
const timeStr = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: timezone });

const oppTable = user.oppTable || '(No opportunity data available)';
const oppCount = user.userOppCount || 0;
const totalOppCount = user.totalOppCount || oppCount;
const digestScope = user.digestScope || 'my_deals';
const scopeLabel = user.scopeLabel || (repName + "'s OPEN OPPORTUNITIES");

// Shared Block Kit formatting rules
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
- Bullet points: use the • character on its own line
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

let roleContext = '';
let briefingStructure = '';
let agentPrompt = '';

if (digestScope === 'my_deals') {
  roleContext = `You are ${assistantName}, a personal sales assistant for ${repName}. You work exclusively for them and know their pipeline intimately.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals) ━━━

${oppTable}

Do NOT use MCP to search for or list opportunities — they are already provided above. The table above contains ALL of ${repName}'s open opportunities for this fiscal year.

You DO have access to People.ai MCP tools. Use them ONLY for:
- Revenue stories and engagement analysis on specific deals
- Recent activity details (emails, meetings, calls) on key accounts
- Engagement score trends and changes`;

  briefingStructure = `Write a 60-second morning briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Brief — ${assistantName}"
2. The Lead (1-2 sentences) — the single most important thing today
3. Today's Priorities (2-4 items) — specific actions with account names and reasons, use emoji status indicators
4. Pipeline Pulse — two-column engagement score grid using section fields
5. One Thing I'm Watching — one forward-looking observation
6. Context footer — "People.ai intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the morning sales briefing for ${repName}. Their ${oppCount} open opportunities are already loaded in your system prompt — do NOT use MCP to search for opportunities.

Instead, use the People.ai MCP tools to investigate revenue stories and engagement patterns on the top 3-5 most important deals (highest amount, closest close date, or biggest engagement changes). Look for recent activity, meeting patterns, and risk signals.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`;

} else if (digestScope === 'team_deals') {
  roleContext = `You are ${assistantName}, a sales management assistant for ${repName}. You help them lead their team and stay ahead of pipeline risks.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals) ━━━

${oppTable}

Do NOT use MCP to search for or list opportunities — they are already provided above. The table contains all open opportunities for ${repName}'s team this fiscal year.

You DO have access to People.ai MCP tools. Use them ONLY for:
- Revenue stories and engagement analysis on specific deals
- Recent activity details to identify which reps are active vs. going dark
- Engagement score trends and coaching signals`;

  briefingStructure = `Write a 90-second team pipeline briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Team Brief — ${assistantName}"
2. Team Pulse (2-3 sentences) — overall pipeline health: total pipeline value, deals closing this month, biggest risks
3. Reps Who Need Attention (2-3 items) — which reps have deals at risk, declining engagement, or upcoming close dates with no recent activity. Be specific: name the rep and the deal.
4. Top Coaching Moments — 1-2 deals where manager intervention could change the outcome. What should ${repName} do?
5. Team Pipeline Snapshot — two-column grid: rep name + their key metric (pipeline total, deal count, or engagement trend)
6. One Signal to Watch — a forward-looking team-level pattern
7. Context footer — "People.ai team intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the team pipeline briefing for ${repName} (sales manager). Their team's ${oppCount} open opportunities are already loaded in your system prompt — do NOT use MCP to search for opportunities.

Instead, use the People.ai MCP tools to investigate team engagement patterns: identify which reps have deals with declining engagement, spot coaching opportunities, and find deals where manager intervention could help. Focus on 3-5 highest-risk or highest-value deals across the team.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`;

} else if (digestScope === 'top_pipeline') {
  roleContext = `You are ${assistantName}, an executive sales intelligence assistant for ${repName}. You provide pipeline visibility and strategic signals at the leadership level.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} ━━━

${oppTable}

Do NOT use MCP to search for or list opportunities — they are already provided above. The table shows the top deals by amount across the entire organization (${totalOppCount} total open deals).

You DO have access to People.ai MCP tools. Use them ONLY for:
- Revenue stories on the largest deals
- Deal velocity trends and forecast signals
- Executive-level engagement patterns`;

  briefingStructure = `Write a 90-second executive pipeline briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Pipeline Brief — ${assistantName}"
2. Pipeline at a Glance (2-3 sentences) — total open pipeline value, number of deals, weighted forecast if calculable, deals closing this month
3. Top Deals to Watch (3-4 items) — the highest-value or highest-risk deals with brief status. Focus on what executives care about: deal size, stage progression, risk of slip.
4. Forecast Signals — patterns that affect the number: are deals accelerating or stalling? Are close dates being pushed? Pipeline generation vs. close rate?
5. Key Numbers — two-column grid: metric name + value (total pipeline, avg deal size, deals closing this month, avg engagement score)
6. Strategic Signal — one forward-looking observation about pipeline health or competitive dynamics
7. Context footer — "People.ai executive intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the executive pipeline briefing for ${repName} (sales executive). The top ${oppCount} deals by amount are already loaded in your system prompt (out of ${totalOppCount} total open deals) — do NOT use MCP to search for opportunities.

Instead, use the People.ai MCP tools to analyze pipeline health: investigate the top 3-5 largest deals for velocity, engagement trends, and risk signals. Look for forecast-impacting patterns.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`;
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
    systemPrompt,
    agentPrompt
  }
}];
"""


def upgrade_sales_digest(wf):
    print("\n=== Upgrading Sales Digest ===")
    nodes = wf["nodes"]
    connections = wf["connections"]

    # Check if already upgraded
    node_names = [n["name"] for n in nodes]
    if "Fetch User Hierarchy" in node_names:
        print("  Already has Fetch User Hierarchy — skipping")
        return wf

    # --- Shift existing node positions right by 224px (for nodes after Get Auth Token) ---
    shift_after_x = 432  # Get Auth Token is at x=432
    shift_amount = 224 * 2  # Two new nodes

    for node in nodes:
        x, y = node["position"]
        if x > shift_after_x:
            node["position"] = [x + shift_amount, y]
            print(f"  Shifted {node['name']} to [{x + shift_amount}, {y}]")

    # --- Add new node: Fetch User Hierarchy ---
    fetch_hierarchy_id = str(uuid.uuid4())
    fetch_hierarchy_node = {
        "parameters": {
            "method": "POST",
            "url": "https://api.people.ai/v3/beta/insights/export",
            "authentication": "none",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Content-Type", "value": "application/json"},
                    {"name": "Authorization", "value": "=Bearer {{ $('Get Auth Token').first().json.access_token }}"}
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json.dumps({
                "object": "user",
                "columns": [
                    {"slug": "ootb_user_name"},
                    {"slug": "ootb_user_email"},
                    {"slug": "ootb_user_manager"}
                ]
            }),
            "options": {}
        },
        "id": fetch_hierarchy_id,
        "name": "Fetch User Hierarchy",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [544, 528]
    }
    nodes.append(fetch_hierarchy_node)
    print(f"  Added Fetch User Hierarchy (id={fetch_hierarchy_id})")

    # --- Add new node: Parse Hierarchy ---
    parse_hierarchy_id = str(uuid.uuid4())
    parse_hierarchy_node = {
        "parameters": {
            "jsCode": PARSE_HIERARCHY_CODE
        },
        "id": parse_hierarchy_id,
        "name": "Parse Hierarchy",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [656, 528]
    }
    nodes.append(parse_hierarchy_node)
    print(f"  Added Parse Hierarchy (id={parse_hierarchy_id})")

    # --- Update Filter User Opps code ---
    for node in nodes:
        if node["name"] == "Filter User Opps":
            node["parameters"]["jsCode"] = FILTER_USER_OPPS_CODE
            print("  Updated Filter User Opps jsCode")
            break

    # --- Update Resolve Identity code ---
    for node in nodes:
        if node["name"] == "Resolve Identity":
            node["parameters"]["jsCode"] = RESOLVE_IDENTITY_CODE
            print("  Updated Resolve Identity jsCode")
            break

    # --- Update connections ---
    # Remove: Get Auth Token -> Fetch Open Opps
    # Add: Get Auth Token -> Fetch User Hierarchy -> Parse Hierarchy -> Fetch Open Opps
    connections["Get Auth Token"] = {
        "main": [[{"node": "Fetch User Hierarchy", "type": "main", "index": 0}]]
    }
    connections["Fetch User Hierarchy"] = {
        "main": [[{"node": "Parse Hierarchy", "type": "main", "index": 0}]]
    }
    connections["Parse Hierarchy"] = {
        "main": [[{"node": "Fetch Open Opps", "type": "main", "index": 0}]]
    }
    print("  Updated connections: Get Auth Token → Fetch User Hierarchy → Parse Hierarchy → Fetch Open Opps")

    print(f"  Total nodes: {len(nodes)}")
    return wf


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("Fetching live workflows...")
    digest_wf = fetch_workflow(SALES_DIGEST_ID)
    events_wf = fetch_workflow(SLACK_EVENTS_ID)
    print(f"  Sales Digest: {len(digest_wf['nodes'])} nodes")
    print(f"  Slack Events Handler: {len(events_wf['nodes'])} nodes")

    # Upgrade both
    events_wf = upgrade_slack_events(events_wf)
    digest_wf = upgrade_sales_digest(digest_wf)

    # Push
    print("\n=== Pushing workflows ===")
    result1 = push_workflow(SLACK_EVENTS_ID, events_wf)
    print(f"  Slack Events Handler: HTTP 200, {len(result1['nodes'])} nodes")

    result2 = push_workflow(SALES_DIGEST_ID, digest_wf)
    print(f"  Sales Digest: HTTP 200, {len(result2['nodes'])} nodes")

    # Sync local files
    print("\n=== Syncing local files ===")
    sync_local(SALES_DIGEST_ID, result2, "Sales Digest.json")
    sync_local(SLACK_EVENTS_ID, result1, "Slack Events Handler.json")

    print("\nDone! Both workflows upgraded.")


if __name__ == "__main__":
    main()
