#!/usr/bin/env python3
"""
Add daily themes to Sales Digest:
- Monday: Full Pipeline Brief (current behavior)
- Tuesday: Engagement Shifts (who went hot/cold)
- Wednesday: At-Risk Deals (stalled, declining engagement)
- Thursday: Momentum & Wins (advancing deals, rising engagement)
- Friday: Week in Review + Next Week Preview

Modifies Filter User Opps and Resolve Identity nodes.
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


# ============================================================
# FILTER USER OPPS — with theme-aware filtering
# ============================================================
FILTER_USER_OPPS_CODE = r"""// Filter pre-fetched opps based on user's role/digest_scope and daily theme
const user = $('Split In Batches').first().json;
const allOpps = $('Parse Opps CSV').first().json.opps;
const hierarchyData = $('Parse Hierarchy').first().json;

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
  // Weekend: no scheduled digest, but if on-demand, default to full pipeline
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

// === Scope-based filtering (same as before) ===
if (digestScope === 'my_deals') {
  userOpps = allOpps.filter(opp => {
    const owners = (opp.owners || '').toLowerCase();
    return owners.includes(repLower);
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
  // Filter to deals showing risk signals
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
  // Sort by engagement descending to surface high-momentum deals first
  userOpps.sort((a, b) => {
    const engA = parseFloat((a.engagement || '0').replace(/[^0-9.]/g, '')) || 0;
    const engB = parseFloat((b.engagement || '0').replace(/[^0-9.]/g, '')) || 0;
    return engB - engA;
  });
  themeNote = `Sorted by engagement score to surface momentum. ${userOpps.length} deals in scope.`;
}

// === Build formatted table ===
let oppTable = '';
if (userOpps.length > 0) {
  if (digestScope === 'my_deals') {
    oppTable = '| Opportunity | Account | Stage | Close Date | Amount | Engagement |\n';
    oppTable += '|---|---|---|---|---|---|\n';
    for (const opp of userOpps) {
      oppTable += '| ' + opp.name + ' | ' + opp.account + ' | ' + opp.stage + ' | ' + opp.closeDate + ' | ' + opp.amount + ' | ' + opp.engagement + ' |\n';
    }
  } else {
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
    dateWindowEnd: qEndLabel,
    theme,
    themeLabel: themeLabels[theme] || 'Brief',
    themeNote
  }
}];
"""

# ============================================================
# RESOLVE IDENTITY — with 5 themes × 3 scopes
# ============================================================
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
const theme = user.theme || 'full_pipeline';
const themeLabel = user.themeLabel || 'Brief';
const themeNote = user.themeNote || '';

const dayLabel = currentDate.split(',')[0]; // "Monday", "Tuesday", etc.
const emojiClean = assistantEmoji.replace(/:/g, '');

// === Shared Block Kit formatting rules ===
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

// === Role context by scope (data + identity — same for all themes) ===
function buildRoleContext(scope) {
  const mcpRules = `Do NOT use MCP to search for or list opportunities — they are already provided above.

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
  if (scope === 'team_deals') return `People.ai team intelligence • ${currentDate} • ${timeStr} PT`;
  if (scope === 'top_pipeline') return `People.ai executive intelligence • ${currentDate} • ${timeStr} PT`;
  return `People.ai intelligence • ${currentDate} • ${timeStr} PT`;
}

// === Theme-specific briefing structure and agent prompt ===
function buildThemePrompts(theme, scope) {
  // Scope-aware title modifiers
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

  // Fallback to full_pipeline if theme not recognized
  return buildThemePrompts('full_pipeline', scope);
}

// === Build the prompts ===
const roleContext = buildRoleContext(digestScope);
const { briefingStructure, agentPrompt } = buildThemePrompts(theme, digestScope);

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
    agentPrompt
  }
}];
"""


def upgrade(wf):
    print("\n=== Adding daily themes ===")
    for node in wf["nodes"]:
        if node["name"] == "Filter User Opps":
            node["parameters"]["jsCode"] = FILTER_USER_OPPS_CODE
            print("  Updated Filter User Opps (theme-aware filtering)")
        elif node["name"] == "Resolve Identity":
            node["parameters"]["jsCode"] = RESOLVE_IDENTITY_CODE
            print("  Updated Resolve Identity (5 themes × 3 scopes)")
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

    print("\nDone! Daily themes active (weekdays only):")
    print("  Monday    → Full Pipeline Brief")
    print("  Tuesday   → Engagement Shifts")
    print("  Wednesday → At-Risk Deals")
    print("  Thursday  → Momentum & Wins")
    print("  Friday    → Week in Review")
    print("  Sat/Sun   → No scheduled digest (on-demand falls back to Full Pipeline)")


if __name__ == "__main__":
    main()
