"""
Create the "Daily Usage Report" n8n workflow.

Queries Supabase for yesterday's assistant usage data and sends a formatted
Block Kit report to Scott's Slack DM at 8am PT on weekdays.
"""

from n8n_helpers import (
    uid,
    create_or_update_workflow,
    make_code_node,
    make_slack_http_node,
    NODE_SCHEDULE_TRIGGER,
    NODE_HTTP_REQUEST,
    SUPABASE_CRED,
    SLACK_CRED,
    SUPABASE_URL,
    SLACK_CONVERSATIONS_OPEN,
    SLACK_CHAT_POST,
)

# ── Node 1: Schedule Trigger — 8am PT weekdays ──────────────────────────

schedule_trigger = {
    "parameters": {
        "rule": {
            "interval": [
                {
                    "field": "cronExpression",
                    "expression": "0 15 * * 1-5",
                }
            ]
        },
    },
    "id": uid(),
    "name": "8am PT Weekdays",
    "type": NODE_SCHEDULE_TRIGGER,
    "typeVersion": 1.2,
    "position": [0, 0],
}

# ── Node 2: Build Query (Code) ──────────────────────────────────────────

build_query_js = r"""
const now = new Date();
// Get "today" in PT
const ptStr = now.toLocaleString('en-US', { timeZone: 'America/Los_Angeles' });
const ptNow = new Date(ptStr);
const yesterday = new Date(ptNow);
yesterday.setDate(yesterday.getDate() - 1);

const pad = (n) => String(n).padStart(2, '0');
const yStr = `${yesterday.getFullYear()}-${pad(yesterday.getMonth()+1)}-${pad(yesterday.getDate())}`;
const tStr = `${ptNow.getFullYear()}-${pad(ptNow.getMonth()+1)}-${pad(ptNow.getDate())}`;

const base = 'https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1';

return [{ json: {
  messagesUrl: `${base}/messages?select=id,user_id,message_type,direction,sent_at,metadata&sent_at=gte.${yStr}T00:00:00&sent_at=lt.${tStr}T00:00:00&order=sent_at.desc&limit=5000`,
  usersUrl: `${base}/users?select=id,email,assistant_name,onboarding_state&onboarding_state=eq.complete`,
  yesterdayStr: yStr,
  todayStr: tStr,
}}];
"""

build_query = make_code_node("Build Query", build_query_js, [260, 0])

# ── Node 3: Fetch Messages — HTTP GET ───────────────────────────────────

fetch_messages = {
    "parameters": {
        "method": "GET",
        "url": "={{ $json.messagesUrl }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch Messages",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [520, -100],
    "credentials": {"supabaseApi": SUPABASE_CRED},
}

# ── Node 4: Fetch Users — HTTP GET (parallel) ───────────────────────────

fetch_users = {
    "parameters": {
        "method": "GET",
        "url": "={{ $json.usersUrl }}",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "options": {},
    },
    "id": uid(),
    "name": "Fetch Users",
    "type": NODE_HTTP_REQUEST,
    "typeVersion": 4.2,
    "position": [520, 100],
    "credentials": {"supabaseApi": SUPABASE_CRED},
}

# ── Node 5: Build Report (Code) ─────────────────────────────────────────

build_report_js = r"""
const messages = $('Fetch Messages').all().map(i => i.json);
const allMessages = Array.isArray(messages[0]) ? messages[0] : messages;
const users = $('Fetch Users').all().map(i => i.json);
const allUsers = Array.isArray(users[0]) ? users[0] : users;
const dateStr = $('Build Query').first().json.yesterdayStr;

// Count by message_type (outbound only)
const outbound = allMessages.filter(m => m.direction === 'outbound');
const byType = {};
for (const m of outbound) {
  const t = m.message_type || 'unknown';
  byType[t] = (byType[t] || 0) + 1;
}

// Active users (unique user_ids in outbound messages)
const activeUserIds = new Set(outbound.map(m => m.user_id).filter(Boolean));

// User engagement: users who triggered inbound messages
const inbound = allMessages.filter(m => m.direction === 'inbound');
const engagedUserIds = new Set(inbound.map(m => m.user_id).filter(Boolean));

// Format type counts
const typeLabels = {
  'digest': ':sunrise: Morning Digest',
  'meeting_prep': ':calendar: Meeting Brief',
  'meeting_recap': ':clipboard: Meeting Recap',
  'followup_prompt': ':email: Follow-up Prompt',
  'conversation': ':speech_balloon: DM Conversation',
  'slash_command': ':zap: Slash Command (/bs)',
  'silence_alert': ':no_bell: Silence Alert',
  'deal_watch': ':mag: Deal Watch',
  'announcement': ':mega: Announcement',
};

const sortedTypes = Object.entries(byType).sort((a, b) => b[1] - a[1]);
const typeLines = sortedTypes.map(([type, count]) => {
  const label = typeLabels[type] || type;
  return `${label}: *${count}*`;
}).join('\n');

const totalMessages = outbound.length;
const totalUsers = allUsers.length;
const activeCount = activeUserIds.size;
const engagedCount = engagedUserIds.size;
const adoptionRate = totalUsers > 0 ? Math.round((activeCount / totalUsers) * 100) : 0;

// Inactive users (complete onboarding but no messages yesterday)
const inactiveUsers = allUsers.filter(u => !activeUserIds.has(u.id));
const inactiveCount = inactiveUsers.length;

// Build date display
const dateDisplay = new Date(dateStr + 'T12:00:00').toLocaleDateString('en-US', {
  weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'
});

// Build blocks
const blocks = [
  {
    type: "header",
    text: { type: "plain_text", text: ":bar_chart: Assistant Usage Report", emoji: true }
  },
  {
    type: "context",
    elements: [{ type: "mrkdwn", text: dateDisplay }]
  },
  { type: "divider" },
  {
    type: "section",
    fields: [
      { type: "mrkdwn", text: "*Messages Sent*\n" + totalMessages },
      { type: "mrkdwn", text: "*Active Users*\n" + activeCount + " of " + totalUsers + " (" + adoptionRate + "%)" },
      { type: "mrkdwn", text: "*User-Initiated*\n" + engagedCount + " users" },
      { type: "mrkdwn", text: "*Inactive Yesterday*\n" + inactiveCount + " users" },
    ]
  },
  { type: "divider" },
  {
    type: "section",
    text: { type: "mrkdwn", text: "*Messages by Type*\n" + (typeLines || '_No messages yesterday_') }
  },
];

// Top 5 most active users
const userMsgCount = {};
for (const m of outbound) {
  if (m.user_id) userMsgCount[m.user_id] = (userMsgCount[m.user_id] || 0) + 1;
}
const topUsers = Object.entries(userMsgCount)
  .sort((a, b) => b[1] - a[1])
  .slice(0, 5)
  .map(([uid, count]) => {
    const user = allUsers.find(u => u.id === uid);
    const name = user ? (user.assistant_name || user.email) : uid.substring(0, 8);
    return `${name}: ${count} messages`;
  });

if (topUsers.length > 0) {
  blocks.push({ type: "divider" });
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Most Active Users*\n" + topUsers.join('\n') }
  });
}

// Footer
blocks.push({
  type: "context",
  elements: [{ type: "mrkdwn", text: "People.ai Assistant Analytics \u2022 " + totalUsers + " onboarded users" }]
});

const notificationText = `Assistant Usage: ${totalMessages} messages, ${activeCount} active users (${adoptionRate}%)`;

return [{ json: { blocks: JSON.stringify(blocks), notificationText } }];
"""

build_report = make_code_node("Build Report", build_report_js, [780, 0])

# ── Node 6: Open DM ─────────────────────────────────────────────────────

open_dm = make_slack_http_node(
    "Open DM",
    SLACK_CONVERSATIONS_OPEN,
    '={{ JSON.stringify({ "users": "U061WJ6RMJS" }) }}',
    [1040, 0],
)

# ── Node 7: Send Report ─────────────────────────────────────────────────

send_report_body = """={{ JSON.stringify({
  "channel": $json.channel.id,
  "text": $('Build Report').first().json.notificationText,
  "blocks": $('Build Report').first().json.blocks,
  "username": "Assistant Analytics",
  "icon_emoji": ":bar_chart:"
}) }}"""

send_report = make_slack_http_node(
    "Send Report",
    SLACK_CHAT_POST,
    send_report_body,
    [1300, 0],
)

# ── Assemble workflow ────────────────────────────────────────────────────

nodes = [
    schedule_trigger,
    build_query,
    fetch_messages,
    fetch_users,
    build_report,
    open_dm,
    send_report,
]

connections = {
    "8am PT Weekdays": {
        "main": [[{"node": "Build Query", "type": "main", "index": 0}]]
    },
    "Build Query": {
        "main": [[
            {"node": "Fetch Messages", "type": "main", "index": 0},
            {"node": "Fetch Users", "type": "main", "index": 0},
        ]]
    },
    "Fetch Messages": {
        "main": [[{"node": "Build Report", "type": "main", "index": 0}]]
    },
    "Fetch Users": {
        "main": [[{"node": "Build Report", "type": "main", "index": 0}]]
    },
    "Build Report": {
        "main": [[{"node": "Open DM", "type": "main", "index": 0}]]
    },
    "Open DM": {
        "main": [[{"node": "Send Report", "type": "main", "index": 0}]]
    },
}

workflow = {
    "name": "Daily Usage Report",
    "nodes": nodes,
    "connections": connections,
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "callerPolicy": "workflowsFromSameOwner",
        "timezone": "America/Los_Angeles",
    },
}

# ── Create, activate, sync ──────────────────────────────────────────────

if __name__ == "__main__":
    result = create_or_update_workflow(workflow, "Daily Usage Report.json")
    print(f"\nDone! Workflow ID: {result['id']}, Active: {result.get('active')}")
