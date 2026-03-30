"""
Create the Announcement Broadcast sub-workflow.

Fan-out workflow: receives an announcement message + admin channel ID,
personalizes it per user's assistant voice via Claude, delivers via Slack DM,
logs to education_log, and notifies admin on completion.

Usage:
    N8N_API_KEY=... python scripts/create_announcement_broadcast.py
"""

from n8n_helpers import (
    uid, create_or_update_workflow,
    make_code_node, make_slack_http_node, make_supabase_http_node,
    SUPABASE_CRED, ANTHROPIC_CRED, SLACK_CRED, SUPABASE_URL,
    SLACK_CONVERSATIONS_OPEN, SLACK_CHAT_POST,
    NODE_SPLIT_IN_BATCHES, NODE_AGENT, NODE_ANTHROPIC_CHAT,
    MODEL_SONNET,
)


def build_workflow():
    nodes = []
    connections = {}

    # ── Node 1: Execute Workflow Trigger ──────────────────────────────
    trigger = {
        "parameters": {"inputSource": "passthrough"},
        "id": uid(),
        "name": "Execute Workflow Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 0],
    }
    nodes.append(trigger)

    # ── Node 2: Fetch Users (Supabase getAll) ─────────────────────────
    fetch_users = {
        "parameters": {
            "operation": "getAll",
            "tableId": "users",
            "returnAll": True,
            "options": {},
        },
        "id": uid(),
        "name": "Fetch Users",
        "type": "n8n-nodes-base.supabase",
        "typeVersion": 1,
        "position": [220, 0],
        "credentials": {"supabaseApi": SUPABASE_CRED},
    }
    nodes.append(fetch_users)

    # ── Node 3: Filter Active + Opted-in ──────────────────────────────
    filter_code = """
const users = $input.all();
const message = $('Execute Workflow Trigger').first().json.message;
const adminChannelId = $('Execute Workflow Trigger').first().json.admin_channel_id;

const active = users.filter(u =>
  u.json.onboarding_state === 'complete' &&
  u.json.announcements_enabled !== false
);

return active.map(u => ({
  json: {
    ...u.json,
    announcementMessage: message,
    adminChannelId: adminChannelId,
    totalUsers: active.length,
  }
}));
"""
    filter_node = make_code_node("Filter Active Users", filter_code, [440, 0])
    nodes.append(filter_node)

    # ── Node 4: SplitInBatches ────────────────────────────────────────
    split = {
        "parameters": {"batchSize": 1, "options": {}},
        "id": uid(),
        "name": "SplitInBatches",
        "type": NODE_SPLIT_IN_BATCHES,
        "typeVersion": 3,
        "position": [660, 0],
    }
    nodes.append(split)

    # ── Node 5: Resolve Identity ──────────────────────────────────────
    resolve_code = """
const user = $json;

const assistantName = user.assistant_name || 'Aria';
const assistantEmoji = user.assistant_emoji || ':robot_face:';
const persona = user.assistant_persona || 'friendly and helpful';

const prompt = `You are ${assistantName}. Rephrase this announcement in your voice (personality: ${persona}). Keep it concise — 2-3 sentences max. Don't change the core information, just wrap it in your style. Use Slack formatting (*bold*, _italic_, bullet points). Do NOT use markdown headers.

Announcement: ${user.announcementMessage}`;

return [{
  json: {
    ...user,
    assistantName,
    assistantEmoji,
    persona,
    personalizePrompt: prompt,
  }
}];
"""
    resolve_node = make_code_node("Resolve Identity", resolve_code, [880, 100])
    nodes.append(resolve_node)

    # ── Node 6: Personalize via Claude (Agent node, no MCP needed) ────
    personalize_agent = {
        "parameters": {
            "promptType": "define",
            "text": "={{ $json.personalizePrompt }}",
            "options": {
                "maxIterations": 1,
            },
        },
        "id": uid(),
        "name": "Personalize Message",
        "type": NODE_AGENT,
        "typeVersion": 1.7,
        "position": [1100, 100],
        "continueOnFail": True,
    }
    nodes.append(personalize_agent)

    personalize_model = {
        "parameters": {
            "model": {
                "__rl": True, "mode": "list",
                "value": MODEL_SONNET,
                "cachedResultName": "Claude Sonnet 4.5",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Anthropic Chat Model (Announce)",
        "type": NODE_ANTHROPIC_CHAT,
        "typeVersion": 1.3,
        "position": [1050, 300],
        "credentials": {"anthropicApi": ANTHROPIC_CRED},
    }
    nodes.append(personalize_model)

    # Wire model → agent
    connections["Anthropic Chat Model (Announce)"] = {
        "ai_languageModel": [[{
            "node": "Personalize Message",
            "type": "ai_languageModel",
            "index": 0,
        }]]
    }

    # ── Node 7: Open Bot DM ───────────────────────────────────────────
    open_dm = make_slack_http_node(
        "Open Bot DM",
        SLACK_CONVERSATIONS_OPEN,
        '={{ JSON.stringify({ users: $json.slack_user_id }) }}',
        [1320, 100],
    )
    open_dm["continueOnFail"] = True
    nodes.append(open_dm)

    # ── Node 8: Send Announcement ─────────────────────────────────────
    send_body = """={{
JSON.stringify({
  channel: $json.channel.id,
  text: $('Personalize Message').first().json.output || $('Resolve Identity').first().json.announcementMessage,
  username: $('Resolve Identity').first().json.assistantName,
  icon_emoji: $('Resolve Identity').first().json.assistantEmoji,
})
}}"""
    send_msg = make_slack_http_node(
        "Send Announcement",
        SLACK_CHAT_POST,
        send_body,
        [1540, 100],
    )
    send_msg["continueOnFail"] = True
    nodes.append(send_msg)

    # ── Node 9: Log to education_log ──────────────────────────────────
    log_code = """
const user = $('Resolve Identity').first().json;
const personalizedText = $('Personalize Message').first().json.output || '';
const sendResult = $json;

return [{
  json: {
    user_id: user.id,
    feature_id: 'announcement',
    trigger_type: 'announcement',
    message_text: personalizedText,
    slack_message_ts: sendResult.ts || null,
    slack_channel_id: sendResult.channel || null,
  }
}];
"""
    log_prepare = make_code_node("Prepare Log Entry", log_code, [1760, 100])
    nodes.append(log_prepare)

    log_insert = make_supabase_http_node(
        "Log to education_log",
        "POST",
        "education_log",
        [1980, 100],
        json_body='={{ JSON.stringify($json) }}',
    )
    log_insert["continueOnFail"] = True
    nodes.append(log_insert)

    # ── Node 10: Notify Admin (after loop done) ───────────────────────
    notify_code = """
const trigger = $('Execute Workflow Trigger').first().json;
const adminChannelId = trigger.admin_channel_id;
// Count is from the first item that went through the filter
const totalUsers = $('Filter Active Users').first().json.totalUsers || 0;

return [{
  json: {
    channel: adminChannelId,
    text: `Announcement delivered to *${totalUsers}* users.`,
  }
}];
"""
    notify_prepare = make_code_node("Prepare Admin Notification", notify_code, [880, -200])
    nodes.append(notify_prepare)

    notify_send = make_slack_http_node(
        "Notify Admin",
        SLACK_CHAT_POST,
        '={{ JSON.stringify({ channel: $json.channel, text: $json.text }) }}',
        [1100, -200],
    )
    nodes.append(notify_send)

    # ── Connections ───────────────────────────────────────────────────
    connections["Execute Workflow Trigger"] = {
        "main": [[{"node": "Fetch Users", "type": "main", "index": 0}]]
    }
    connections["Fetch Users"] = {
        "main": [[{"node": "Filter Active Users", "type": "main", "index": 0}]]
    }
    connections["Filter Active Users"] = {
        "main": [[{"node": "SplitInBatches", "type": "main", "index": 0}]]
    }
    # SplitInBatches: output 0 = done, output 1 = loop
    connections["SplitInBatches"] = {
        "main": [
            [{"node": "Prepare Admin Notification", "type": "main", "index": 0}],
            [{"node": "Resolve Identity", "type": "main", "index": 0}],
        ]
    }
    connections["Resolve Identity"] = {
        "main": [[{"node": "Personalize Message", "type": "main", "index": 0}]]
    }
    connections["Personalize Message"] = {
        "main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]
    }
    connections["Open Bot DM"] = {
        "main": [[{"node": "Send Announcement", "type": "main", "index": 0}]]
    }
    connections["Send Announcement"] = {
        "main": [[{"node": "Prepare Log Entry", "type": "main", "index": 0}]]
    }
    connections["Prepare Log Entry"] = {
        "main": [[{"node": "Log to education_log", "type": "main", "index": 0}]]
    }
    connections["Log to education_log"] = {
        "main": [[{"node": "SplitInBatches", "type": "main", "index": 0}]]
    }
    connections["Prepare Admin Notification"] = {
        "main": [[{"node": "Notify Admin", "type": "main", "index": 0}]]
    }

    return {
        "name": "Announcement Broadcast",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }


if __name__ == "__main__":
    wf = build_workflow()
    result = create_or_update_workflow(wf, "Announcement Broadcast.json")
    print(f"\nDone! Workflow ID: {result['id']}")
