"""
Create the Weekly Usage Report workflow.

Friday 4pm PT cron -> Supabase queries (this week + last week) -> trend analysis -> Slack Block Kit report.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from n8n_helpers import (
    uid, create_or_update_workflow,
    SUPABASE_CRED, SLACK_CRED,
    NODE_SCHEDULE_TRIGGER, NODE_CODE, NODE_HTTP_REQUEST,
    SUPABASE_URL, SLACK_CONVERSATIONS_OPEN, SLACK_CHAT_POST,
)

# ── Node 1: Schedule Trigger — Friday 4pm PT ─────────────────────────
schedule_trigger = {
    "parameters": {
        "rule": {
            "interval": [
                {
                    "field": "cronExpression",
                    "expression": "0 23 * * 5",
                }
            ]
        }
    },
    "id": uid(),
    "name": "Friday 4pm PT",
    "type": NODE_SCHEDULE_TRIGGER,
    "typeVersion": 1.2,
    "position": [0, 0],
}

# ── Node 2: Build Query — compute date ranges ────────────────────────
build_query_code = r"""
const now = new Date();
const ptNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' }));

// This week: Monday to today (Friday)
const dayOfWeek = ptNow.getDay(); // 5 = Friday
const monday = new Date(ptNow);
monday.setDate(monday.getDate() - (dayOfWeek - 1));
const mondayStr = monday.toISOString().split('T')[0];

const tomorrow = new Date(ptNow);
tomorrow.setDate(tomorrow.getDate() + 1);
const tomorrowStr = tomorrow.toISOString().split('T')[0];

// Prior week: previous Monday to previous Friday (Saturday 00:00 as upper bound)
const prevMonday = new Date(monday);
prevMonday.setDate(prevMonday.getDate() - 7);
const prevMondayStr = prevMonday.toISOString().split('T')[0];
const prevSaturday = new Date(prevMonday);
prevSaturday.setDate(prevSaturday.getDate() + 5);
const prevSaturdayStr = prevSaturday.toISOString().split('T')[0];

const base = 'https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1';

return [{ json: {
  thisWeekUrl: `${base}/messages?select=id,user_id,message_type,direction,content,sent_at,metadata&sent_at=gte.${mondayStr}T00:00:00&sent_at=lt.${tomorrowStr}T00:00:00&order=sent_at.desc&limit=10000`,
  lastWeekUrl: `${base}/messages?select=id,user_id,message_type,direction,content,sent_at,metadata&sent_at=gte.${prevMondayStr}T00:00:00&sent_at=lt.${prevSaturdayStr}T00:00:00&order=sent_at.desc&limit=10000`,
  usersUrl: `${base}/users?select=id,email,assistant_name,onboarding_state&onboarding_state=eq.complete`,
  mondayStr,
  tomorrowStr,
  prevMondayStr,
  prevSaturdayStr,
}}];
"""

build_query = {
    "parameters": {"jsCode": build_query_code},
    "id": uid(),
    "name": "Build Query",
    "type": NODE_CODE,
    "typeVersion": 2,
    "position": [224, 0],
}

# ── Node 3: Fetch Users ──────────────────────────────────────────────
fetch_users = {
    "parameters": {
        "url": "={{ $json.usersUrl }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch Users",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [448, 0],
    "credentials": {"supabaseApi": SUPABASE_CRED},
}

# ── Node 4: Fetch This Week ──────────────────────────────────────────
fetch_this_week = {
    "parameters": {
        "url": "={{ $('Build Query').first().json.thisWeekUrl }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch This Week",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [672, 0],
    "credentials": {"supabaseApi": SUPABASE_CRED},
}

# ── Node 5: Fetch Last Week ──────────────────────────────────────────
fetch_last_week = {
    "parameters": {
        "url": "={{ $('Build Query').first().json.lastWeekUrl }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch Last Week",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [896, 0],
    "credentials": {"supabaseApi": SUPABASE_CRED},
}

# ── Node 6: Build Weekly Report ──────────────────────────────────────
build_report_code = r"""
// ── Gather raw data ──────────────────────────────────────────────────
const thisWeekRaw = $('Fetch This Week').all().map(i => i.json);
const thisWeekMessages = Array.isArray(thisWeekRaw[0]) ? thisWeekRaw[0] : thisWeekRaw;
const lastWeekRaw = $('Fetch Last Week').all().map(i => i.json);
const lastWeekMessages = Array.isArray(lastWeekRaw[0]) ? lastWeekRaw[0] : lastWeekRaw;
const usersRaw = $('Fetch Users').all().map(i => i.json);
const allUsers = Array.isArray(usersRaw[0]) ? usersRaw[0] : usersRaw;
const q = $('Build Query').first().json;

// ── Deduplication (10-min window) ────────────────────────────────────
function getWindowKey(m) {
  const ts = new Date(m.sent_at || 0);
  const window = new Date(Math.floor(ts.getTime() / 600000) * 600000);
  return m.user_id + ':' + m.message_type + ':' + window.toISOString();
}

function dedup(msgs) {
  const outbound = msgs.filter(m => m.direction === 'outbound');
  const seen = new Set();
  const unique = [];
  for (const m of outbound) {
    const key = getWindowKey(m);
    if (!seen.has(key)) { seen.add(key); unique.push(m); }
  }
  return unique;
}

function dedupInbound(msgs) {
  const inbound = msgs.filter(m => m.direction === 'inbound');
  const seen = new Set();
  const unique = [];
  for (const m of inbound) {
    const key = getWindowKey(m);
    if (!seen.has(key)) { seen.add(key); unique.push(m); }
  }
  return unique;
}

const twInteractions = dedup(thisWeekMessages);
const lwInteractions = dedup(lastWeekMessages);
const twInbound = dedupInbound(thisWeekMessages);
const lwInbound = dedupInbound(lastWeekMessages);

// ── Trend helpers ────────────────────────────────────────────────────
function trend(curr, prev) {
  if (prev === 0 && curr === 0) return { pct: 0, icon: '\u27a1\ufe0f' };
  if (prev === 0) return { pct: 100, icon: '\ud83d\udcc8' };
  const pct = Math.round(((curr - prev) / prev) * 100);
  const icon = pct >= 10 ? '\ud83d\udcc8' : pct <= -10 ? '\ud83d\udcc9' : '\u27a1\ufe0f';
  return { pct, icon };
}

function fmtTrend(curr, prev, suffix) {
  const t = trend(curr, prev);
  const sign = t.pct >= 0 ? '+' : '';
  if (suffix === undefined) suffix = '';
  return `${t.icon} ${sign}${t.pct}%${suffix ? ' ' + suffix : ''}`;
}

// ── By-type counts ───────────────────────────────────────────────────
function countByType(interactions) {
  const m = {};
  for (const i of interactions) { const t = i.message_type || 'unknown'; m[t] = (m[t] || 0) + 1; }
  return m;
}

const twByType = countByType(twInteractions);
const lwByType = countByType(lwInteractions);

// ── Active users ─────────────────────────────────────────────────────
const twActiveIds = new Set(twInteractions.map(m => m.user_id).filter(Boolean));
const lwActiveIds = new Set(lwInteractions.map(m => m.user_id).filter(Boolean));
const twActiveCount = twActiveIds.size;
const lwActiveCount = lwActiveIds.size;
const totalUsers = allUsers.length;
const adoptionRate = totalUsers > 0 ? Math.round((twActiveCount / totalUsers) * 100) : 0;
const lwAdoptionRate = totalUsers > 0 ? Math.round((lwActiveCount / totalUsers) * 100) : 0;

// ── CRM actions ──────────────────────────────────────────────────────
function countCRM(msgs) {
  let saveCRM = 0, createTask = 0, draftFollowup = 0;
  for (const m of msgs) {
    const mtype = m.message_type || '';
    const content = (m.content || '').toLowerCase();
    if (mtype === 'save_to_crm' || content.includes('recap saved to salesforce') || content.includes('save_recap')) saveCRM++;
    if (mtype === 'create_task' || content.includes('task created in salesforce') || content.includes('create_task')) createTask++;
    if (mtype === 'followup_draft' || content.includes('draft follow-up') || content.includes('followup_draft')) draftFollowup++;
  }
  return { saveCRM, createTask, draftFollowup, total: saveCRM + createTask + draftFollowup };
}

const twCRM = countCRM(thisWeekMessages);
const lwCRM = countCRM(lastWeekMessages);

// ── Skill usage from inbound commands ────────────────────────────────
const skillPatterns = {
  'recap': /^(recap|followup|follow-up|follow up)\b/i,
  'brief': /^brief\b/i,
  'meet': /^(meet|prep|meeting brief|meeting prep)\b/i,
  'insights': /^insights?\b/i,
  'presentation': /^(presentation|slide|slides|deck)\b/i,
  'stakeholders': /^stakeholders?\b/i,
  'silence': /^silence\b/i,
};

function countSkills(inboundMsgs) {
  const counts = {};
  for (const m of inboundMsgs) {
    const text = (m.content || '').trim();
    for (const [skill, pattern] of Object.entries(skillPatterns)) {
      if (pattern.test(text)) { counts[skill] = (counts[skill] || 0) + 1; break; }
    }
  }
  return counts;
}

const twSkills = countSkills(twInbound);
const lwSkills = countSkills(lwInbound);

const skillLabels = {
  'recap': ':clipboard: Recap',
  'brief': ':sunrise: Brief',
  'meet': ':calendar: Meeting Prep',
  'insights': ':mag: Insights',
  'presentation': ':bar_chart: Presentation',
  'stakeholders': ':busts_in_silhouette: Stakeholders',
  'silence': ':no_bell: Silence',
};

// ── Daily breakdown (this week Mon-Fri) ──────────────────────────────
const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'];
const dailyCounts = [0, 0, 0, 0, 0];
for (const m of twInteractions) {
  const d = new Date(m.sent_at);
  const ptStr = d.toLocaleString('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short' });
  const idx = dayNames.indexOf(ptStr);
  if (idx >= 0) dailyCounts[idx]++;
}

const maxDaily = Math.max(...dailyCounts, 1);
function makeBar(count) {
  const len = Math.round((count / maxDaily) * 12);
  return '\u2588'.repeat(len);
}

const dailyLines = dayNames.map((name, i) => {
  return `${name}: ${makeBar(dailyCounts[i])} ${dailyCounts[i]}`;
}).join('\n');

// ── Most active assistants ───────────────────────────────────────────
const userCounts = {};
for (const m of twInteractions) {
  if (m.user_id) userCounts[m.user_id] = (userCounts[m.user_id] || 0) + 1;
}
const topUsers = Object.entries(userCounts)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5)
  .map(([uid, count]) => {
    const user = allUsers.find(u => u.id === uid);
    const name = user ? (user.assistant_name || user.email.split('@')[0]) : uid.substring(0, 8);
    return `${name}: ${count} interactions`;
  });

// ── Inactive / drop-off users ────────────────────────────────────────
const inactiveAll = allUsers.filter(u => !twActiveIds.has(u.id));
const droppedOff = allUsers.filter(u => lwActiveIds.has(u.id) && !twActiveIds.has(u.id));

// ── Date display ─────────────────────────────────────────────────────
const monDate = new Date(q.mondayStr + 'T12:00:00');
const friDate = new Date(monDate);
friDate.setDate(friDate.getDate() + 4);
const fmtDate = (d) => d.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
const weekNum = Math.ceil((monDate - new Date(monDate.getFullYear(), 0, 1)) / (7 * 86400000)) + 1;
const dateDisplay = `Week of ${fmtDate(monDate)}\u2013${fmtDate(friDate)}, ${monDate.getFullYear()}`;

// ── Build Block Kit ──────────────────────────────────────────────────
const twTotal = twInteractions.length;
const lwTotal = lwInteractions.length;

const blocks = [];

// Header
blocks.push({
  type: "header",
  text: { type: "plain_text", text: "\ud83d\udcca Weekly Assistant Report", emoji: true }
});
blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: dateDisplay }]
});

// Summary stats
blocks.push({ type: "divider" });
const intTrend = trend(twTotal, lwTotal);
const actTrend = trend(twActiveCount, lwActiveCount);
const crmTrend = trend(twCRM.total, lwCRM.total);
const adoptTrend = trend(adoptionRate, lwAdoptionRate);

blocks.push({
  type: "section",
  fields: [
    { type: "mrkdwn", text: `*Interactions*\n${twTotal.toLocaleString()} ${intTrend.icon} ${intTrend.pct >= 0 ? '+' : ''}${intTrend.pct}% vs last week` },
    { type: "mrkdwn", text: `*Active Users*\n${twActiveCount} of ${totalUsers} (${adoptionRate}%) ${actTrend.icon} ${twActiveCount - lwActiveCount >= 0 ? '+' : ''}${twActiveCount - lwActiveCount}` },
    { type: "mrkdwn", text: `*CRM Actions*\n${twCRM.total} ${crmTrend.icon} ${crmTrend.pct >= 0 ? '+' : ''}${crmTrend.pct}%` },
    { type: "mrkdwn", text: `*Adoption Rate*\n${adoptionRate}% ${adoptTrend.icon} ${adoptTrend.pct >= 0 ? '+' : ''}${adoptTrend.pct}%` },
  ]
});

// Daily Activity
blocks.push({ type: "divider" });
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `*Daily Activity*\n\`\`\`\n${dailyLines}\n\`\`\`` }
});

// Skills Used
const sortedSkills = Object.entries(twSkills).sort((a, b) => b[1] - a[1]);
if (sortedSkills.length > 0) {
  const skillLines = sortedSkills.map(([skill, count]) => {
    const label = skillLabels[skill] || skill;
    const lwCount = lwSkills[skill] || 0;
    return `${label}: *${count}* ${fmtTrend(count, lwCount)}`;
  }).join('\n');
  blocks.push({ type: "divider" });
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Skills Used (this week)*\n${skillLines}` }
  });
}

// CRM Impact
if (twCRM.total > 0 || lwCRM.total > 0) {
  const crmLines = [];
  if (twCRM.saveCRM > 0 || lwCRM.saveCRM > 0) crmLines.push(`:salesforce: Save to CRM: *${twCRM.saveCRM}* ${fmtTrend(twCRM.saveCRM, lwCRM.saveCRM)}`);
  if (twCRM.createTask > 0 || lwCRM.createTask > 0) crmLines.push(`:memo: Create Task: *${twCRM.createTask}* ${fmtTrend(twCRM.createTask, lwCRM.createTask)}`);
  if (twCRM.draftFollowup > 0 || lwCRM.draftFollowup > 0) crmLines.push(`:email: Draft Follow-up: *${twCRM.draftFollowup}* ${fmtTrend(twCRM.draftFollowup, lwCRM.draftFollowup)}`);
  if (crmLines.length > 0) {
    blocks.push({ type: "divider" });
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: `*CRM Impact*\n${crmLines.join('\n')}` }
    });
  }
}

// Most Active Assistants
if (topUsers.length > 0) {
  blocks.push({ type: "divider" });
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Most Active Assistants*\n${topUsers.join('\n')}` }
  });
}

// Needs Attention
blocks.push({ type: "divider" });
const attentionLines = [];
attentionLines.push(`${inactiveAll.length} user${inactiveAll.length !== 1 ? 's' : ''} inactive all week`);
if (droppedOff.length > 0) {
  attentionLines.push(`${droppedOff.length} user${droppedOff.length !== 1 ? 's' : ''} dropped off (active last week, inactive this week)`);
}
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `*Needs Attention*\n${attentionLines.join('\n')}` }
});

// Footer
blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: `Backstory Assistant Analytics \u2022 Week ${weekNum} ${monDate.getFullYear()}` }]
});

const notificationText = `Weekly Report: ${twTotal} interactions, ${twActiveCount} active users (${adoptionRate}%) ${intTrend.icon} ${intTrend.pct >= 0 ? '+' : ''}${intTrend.pct}% WoW`;

return [{ json: { blocks: JSON.stringify(blocks), notificationText } }];
"""

build_report = {
    "parameters": {"jsCode": build_report_code},
    "id": uid(),
    "name": "Build Weekly Report",
    "type": NODE_CODE,
    "typeVersion": 2,
    "position": [1120, 0],
}

# ── Node 7: Open DM ──────────────────────────────────────────────────
open_dm = {
    "parameters": {
        "method": "POST",
        "url": SLACK_CONVERSATIONS_OPEN,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [{"name": "Content-Type", "value": "application/json"}]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={{ JSON.stringify({ "users": "U061WJ6RMJS" }) }}',
        "options": {},
    },
    "id": uid(),
    "name": "Open DM",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [1344, 0],
    "credentials": {"httpHeaderAuth": SLACK_CRED},
}

# ── Node 8: Send Report ──────────────────────────────────────────────
send_report = {
    "parameters": {
        "method": "POST",
        "url": SLACK_CHAT_POST,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [{"name": "Content-Type", "value": "application/json"}]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": """={{ JSON.stringify({
  "channel": $json.channel.id,
  "text": $('Build Weekly Report').first().json.notificationText,
  "blocks": $('Build Weekly Report').first().json.blocks,
  "username": "Assistant Analytics",
  "icon_emoji": ":bar_chart:"
}) }}""",
        "options": {},
    },
    "id": uid(),
    "name": "Send Report",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [1568, 0],
    "credentials": {"httpHeaderAuth": SLACK_CRED},
}

# ── Assemble nodes ────────────────────────────────────────────────────
nodes = [
    schedule_trigger,
    build_query,
    fetch_users,
    fetch_this_week,
    fetch_last_week,
    build_report,
    open_dm,
    send_report,
]

# ── Sequential connections ────────────────────────────────────────────
connections = {
    "Friday 4pm PT": {
        "main": [[{"node": "Build Query", "type": "main", "index": 0}]]
    },
    "Build Query": {
        "main": [[{"node": "Fetch Users", "type": "main", "index": 0}]]
    },
    "Fetch Users": {
        "main": [[{"node": "Fetch This Week", "type": "main", "index": 0}]]
    },
    "Fetch This Week": {
        "main": [[{"node": "Fetch Last Week", "type": "main", "index": 0}]]
    },
    "Fetch Last Week": {
        "main": [[{"node": "Build Weekly Report", "type": "main", "index": 0}]]
    },
    "Build Weekly Report": {
        "main": [[{"node": "Open DM", "type": "main", "index": 0}]]
    },
    "Open DM": {
        "main": [[{"node": "Send Report", "type": "main", "index": 0}]]
    },
}

# ── Build workflow dict ───────────────────────────────────────────────
workflow = {
    "name": "Weekly Usage Report",
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
    },
    "staticData": None,
}

if __name__ == "__main__":
    result = create_or_update_workflow(workflow, "Weekly Usage Report.json")
    wf_id = result["id"]
    print(f"\nDone! Workflow ID: {wf_id}")
    print(f"  {len(result['nodes'])} nodes, active={result.get('active')}")
