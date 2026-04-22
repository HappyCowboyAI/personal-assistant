#!/usr/bin/env python3
"""
Update Filter User Opps to narrow close date focus:
- my_deals (IC): current fiscal year (unchanged)
- team_deals (Manager): current + next quarter only
- top_pipeline (Exec): current + next quarter only
Also update Resolve Identity prompts to reflect the date window.
"""

import json
import os
import requests

N8N_BASE_URL = os.getenv("N8N_BASE_URL", "https://scottai.trackslife.com")
N8N_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiZmExNjNjMS1iZDUzLTRjMGYtYjBiYS04ZGMzNjI2ZjdjNzkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiM2VlZWQ1MWYtODg2NC00NzQwLWIxMzAtNWZjN2M5ZGMyNzk2IiwiaWF0IjoxNzcxODkwOTY0fQ.ZBr6HmgMNfOD7CwMFuSxGUvxk40_d0wc59M6Y2JuwlA"

SALES_DIGEST_ID = "7sinwSgjkEA40zDj"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Content-Type": "application/json"}


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


# Updated Filter User Opps with date window logic
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

// Date window helpers
function getCurrentAndNextQuarterEnd() {
  const now = new Date();
  const month = now.getMonth(); // 0-11
  const year = now.getFullYear();

  // Current quarter end
  const currentQ = Math.floor(month / 3);
  // Next quarter end (2 quarters from start of current)
  const nextQEnd = currentQ + 2;

  let endMonth, endYear;
  if (nextQEnd <= 3) {
    endMonth = nextQEnd * 3; // 0-based month after last month of quarter
    endYear = year;
  } else {
    endMonth = (nextQEnd - 4) * 3;
    endYear = year + 1;
  }

  // Last day of the end month (month is 0-based, so endMonth is the first day of next month)
  return new Date(endYear, endMonth, 0, 23, 59, 59);
}

function getFiscalYearEnd() {
  // Backstory fiscal year: Feb 1 - Jan 31
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  // If we're in Jan, FY ends this Jan 31
  // If Feb-Dec, FY ends next Jan 31
  if (month === 0) {
    return new Date(year, 0, 31, 23, 59, 59);
  }
  return new Date(year + 1, 0, 31, 23, 59, 59);
}

// Filter by close date window
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

// Format date labels for scope descriptions
const qEndLabel = twoQuarterEnd.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

let userOpps = [];
let scopeLabel = '';

if (digestScope === 'my_deals') {
  // IC view: filter by owner name, full fiscal year
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return owners.includes(repLower);
  });
  userOpps = filterByDateWindow(userOpps, fyEnd);
  scopeLabel = repName + "'s OPEN OPPORTUNITIES";

} else if (digestScope === 'team_deals') {
  // Manager view: own deals + all direct reports' deals
  // Date window: current + next quarter only
  const managerToReports = hierarchyData.managerToReports || {};
  let reportNames = [repLower];

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

  // Narrow to current + next quarter
  userOpps = filterByDateWindow(userOpps, twoQuarterEnd);

  // Sort by close date ascending (nearest first)
  userOpps.sort((a, b) => new Date(a.closeDate) - new Date(b.closeDate));
  scopeLabel = repName + "'s TEAM PIPELINE through " + qEndLabel + " (" + reportNames.length + " reps)";

} else if (digestScope === 'top_pipeline') {
  // Exec view: all opps closing current + next quarter, sorted by amount, top 25
  userOpps = filterByDateWindow([...allOpps], twoQuarterEnd);

  const totalInWindow = userOpps.length;

  userOpps.sort((a, b) => {
    const amtA = parseFloat((a.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    const amtB = parseFloat((b.amount || '0').replace(/[^0-9.]/g, '')) || 0;
    return amtB - amtA;
  });
  userOpps = userOpps.slice(0, 25);
  scopeLabel = "TOP PIPELINE through " + qEndLabel + " (" + totalInWindow + " deals in window, showing top 25 by amount)";
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
    dateWindowEnd: qEndLabel
  }
}];
"""

# Updated Resolve Identity with date window references in prompts
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
const dateWindowEnd = user.dateWindowEnd || '';

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

You DO have access to Backstory MCP tools. Use them ONLY for:
- Revenue stories and engagement analysis on specific deals
- Recent activity details (emails, meetings, calls) on key accounts
- Engagement score trends and changes`;

  briefingStructure = `Write a 60-second morning briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Brief — ${assistantName}"
2. The Lead (1-2 sentences) — the single most important thing today
3. Today's Priorities (2-4 items) — specific actions with account names and reasons, use emoji status indicators
4. Pipeline Pulse — two-column engagement score grid using section fields
5. One Thing I'm Watching — one forward-looking observation
6. Context footer — "Backstory intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the morning sales briefing for ${repName}. Their ${oppCount} open opportunities are already loaded in your system prompt — do NOT use MCP to search for opportunities.

Instead, use the Backstory MCP tools to investigate revenue stories and engagement patterns on the top 3-5 most important deals (highest amount, closest close date, or biggest engagement changes). Look for recent activity, meeting patterns, and risk signals.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`;

} else if (digestScope === 'team_deals') {
  roleContext = `You are ${assistantName}, a sales management assistant for ${repName}. You help them lead their team and stay ahead of pipeline risks.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} (${oppCount} deals closing through ${dateWindowEnd}) ━━━

${oppTable}

Do NOT use MCP to search for or list opportunities — they are already provided above. The table contains all team deals closing between now and end of ${dateWindowEnd}.

You DO have access to Backstory MCP tools. Use them ONLY for:
- Revenue stories and engagement analysis on specific deals
- Recent activity details to identify which reps are active vs. going dark
- Engagement score trends and coaching signals`;

  briefingStructure = `Write a 90-second team pipeline briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Team Brief — ${assistantName}"
2. Team Pulse (2-3 sentences) — overall pipeline health for the current and next quarter: total pipeline value, deals closing this quarter and next, biggest risks
3. Reps Who Need Attention (2-3 items) — which reps have deals at risk, declining engagement, or upcoming close dates with no recent activity. Be specific: name the rep and the deal.
4. Top Coaching Moments — 1-2 deals where manager intervention could change the outcome. What should ${repName} do?
5. Team Pipeline Snapshot — two-column grid: rep name + their key metric (pipeline total, deal count, or engagement trend)
6. One Signal to Watch — a forward-looking team-level pattern
7. Context footer — "Backstory team intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the team pipeline briefing for ${repName} (sales manager). Their team's ${oppCount} open deals closing through ${dateWindowEnd} are already loaded in your system prompt — do NOT use MCP to search for opportunities.

Instead, use the Backstory MCP tools to investigate team engagement patterns: identify which reps have deals with declining engagement, spot coaching opportunities, and find deals where manager intervention could help. Focus on 3-5 highest-risk or highest-value deals across the team.

Then write the briefing as a Block Kit JSON object following the format in your system instructions. Remember: output ONLY the JSON object, nothing else.`;

} else if (digestScope === 'top_pipeline') {
  roleContext = `You are ${assistantName}, an executive sales intelligence assistant for ${repName}. You provide pipeline visibility and strategic signals at the leadership level.

Your personality: ${assistantPersona}

Today is ${currentDate}. ${repName} is in ${timezone}.

━━━ ${scopeLabel} ━━━

${oppTable}

Do NOT use MCP to search for or list opportunities — they are already provided above. The table shows the top deals by amount closing between now and end of ${dateWindowEnd} (${totalOppCount} total open deals org-wide).

You DO have access to Backstory MCP tools. Use them ONLY for:
- Revenue stories on the largest deals
- Deal velocity trends and forecast signals
- Executive-level engagement patterns`;

  briefingStructure = `Write a 90-second executive pipeline briefing following this structure:

1. Header — "${assistantEmoji.replace(/:/g, '')} ${currentDate.split(',')[0]} Pipeline Brief — ${assistantName}"
2. Pipeline at a Glance (2-3 sentences) — total pipeline value closing this quarter and next, number of deals in the window, weighted forecast if calculable, deals closing this month
3. Top Deals to Watch (3-4 items) — the highest-value or highest-risk deals with brief status. Focus on what executives care about: deal size, stage progression, risk of slip.
4. Forecast Signals — patterns that affect the number: are deals accelerating or stalling? Are close dates being pushed? Pipeline generation vs. close rate?
5. Key Numbers — two-column grid: metric name + value (pipeline in window, avg deal size, deals closing this quarter, avg engagement score)
6. Strategic Signal — one forward-looking observation about pipeline health or competitive dynamics
7. Context footer — "Backstory executive intelligence • ${currentDate} • ${timeStr} PT"`;

  agentPrompt = `Generate the executive pipeline briefing for ${repName} (sales executive). The top ${oppCount} deals by amount closing through ${dateWindowEnd} are already loaded in your system prompt (out of ${totalOppCount} total open deals org-wide) — do NOT use MCP to search for opportunities.

Instead, use the Backstory MCP tools to analyze pipeline health: investigate the top 3-5 largest deals for velocity, engagement trends, and risk signals. Look for forecast-impacting patterns.

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


def upgrade(wf):
    print("\n=== Updating date filtering ===")
    for node in wf["nodes"]:
        if node["name"] == "Filter User Opps":
            node["parameters"]["jsCode"] = FILTER_USER_OPPS_CODE
            print("  Updated Filter User Opps (added quarter-based date windows)")
        elif node["name"] == "Resolve Identity":
            node["parameters"]["jsCode"] = RESOLVE_IDENTITY_CODE
            print("  Updated Resolve Identity (prompts reference date window)")
    return wf


def main():
    print("Fetching Sales Digest workflow...")
    wf = fetch_workflow(SALES_DIGEST_ID)
    print(f"  {len(wf['nodes'])} nodes")

    wf = upgrade(wf)

    print("\n=== Pushing workflow ===")
    result = push_workflow(SALES_DIGEST_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local file ===")
    sync_local(result, "Sales Digest.json")

    print("\nDone! Date filtering updated:")
    print("  - my_deals: full fiscal year (Feb 1 - Jan 31)")
    print("  - team_deals: current + next quarter")
    print("  - top_pipeline: current + next quarter, top 25 by amount")


if __name__ == "__main__":
    main()
