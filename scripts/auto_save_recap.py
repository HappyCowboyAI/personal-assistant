"""
Auto-save meeting recaps to CRM via Workato webhook.

Modifies the Follow-up Cron workflow (JhDuCvZdFN4PFTOW):
- Adds "Build Auto-Save Payload" Code node after Parse Recap Output
- Adds "Send Recap to CRM" HTTP node (POST to Workato)
- Adds "Prepare Task Payloads" Code node (fans out tasks)
- Adds "Send Tasks to CRM" HTTP node (POST each task to Workato)
- Rewires: Parse Recap Output → Build Auto-Save Payload → [Send Recap to CRM + Prepare Task Payloads]
           Send Recap to CRM → Build Recap Card → Open Bot DM → Send Recap → Build Recap Thread → Send Recap Thread
           Prepare Task Payloads → Send Tasks to CRM (fire-and-forget)
- Replaces Build Recap Card code (auto-save confirmation card)
- Replaces Build Recap Thread code (read-only thread, no Create Task buttons)
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import (
    fetch_workflow, find_node, push_workflow, sync_local,
    make_code_node, uid,
    WF_FOLLOWUP_CRON, NODE_HTTP_REQUEST,
)

LOCAL_FILENAME = "Follow-up Cron.json"
WORKATO_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"


# ── Node JS Code ─────────────────────────────────────────────────────────

BUILD_AUTO_SAVE_PAYLOAD_JS = r"""// Build Workato payloads for auto-saving recap to CRM
const data = $('Parse Recap Output').first().json;
const recap = data.recap;
const m = data.meeting;

// Build description from recap parts
const descParts = [];
if (recap.summary) descParts.push('Summary: ' + recap.summary);
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  descParts.push('Key Decisions:\n' + recap.keyDecisions.map(d => '- ' + d).join('\n'));
}
if (recap.tasks && recap.tasks.length > 0) {
  descParts.push('Action Items:\n' + recap.tasks.map(t =>
    '- ' + t.description + (t.owner ? ' (' + t.owner + ')' : '')
  ).join('\n'));
}
const description = descParts.join('\n\n');

// Activity payload for logging the meeting recap
const activityPayload = {
  action: 'log_activity',
  salesforce_object: 'Event',
  fields: {
    Subject: m.subject || 'Customer Meeting',
    Description: description,
    ActivityDate: m.dayStr || new Date().toISOString().split('T')[0],
    meeting_category: recap.meetingCategory || null,
    cs_category: recap.csCategory || null,
  },
  context: {
    user_email: data.email || '',
    account_name: m.accountName || '',
    activity_uid: m.activityUid || '',
    prepend_description: true,
  }
};

// Parse due date hints into actual dates
function parseDueDate(hint) {
  if (!hint) return '';
  const now = new Date();
  const lower = hint.toLowerCase().trim();
  if (lower === 'today') return now.toISOString().split('T')[0];
  if (lower === 'tomorrow') {
    const d = new Date(now); d.setDate(d.getDate() + 1);
    return d.toISOString().split('T')[0];
  }
  if (lower === 'this week' || lower === 'end of week') {
    const d = new Date(now);
    const dayOfWeek = d.getDay();
    d.setDate(d.getDate() + (5 - dayOfWeek));
    return d.toISOString().split('T')[0];
  }
  if (lower === 'next week') {
    const d = new Date(now);
    d.setDate(d.getDate() + 7);
    return d.toISOString().split('T')[0];
  }
  // Try parsing as a date string
  const parsed = new Date(hint);
  if (!isNaN(parsed.getTime())) return parsed.toISOString().split('T')[0];
  // Default: 1 week from now
  const d = new Date(now); d.setDate(d.getDate() + 7);
  return d.toISOString().split('T')[0];
}

// Task payloads
const taskPayloads = (recap.tasks || []).map(t => ({
  action: 'create_task',
  salesforce_object: 'Task',
  fields: {
    Subject: t.description || 'Follow-up task',
    Description: 'From meeting: ' + (m.subject || '') + ' with ' + (m.accountName || '') +
      (t.due_hint ? '\nDue: ' + t.due_hint : ''),
    ActivityDate: parseDueDate(t.due_hint),
    Status: 'Not Started',
    Priority: 'Normal',
    TaskDuration: t.duration_minutes || 30,
    Category: t.task_category || '',
  },
  context: {
    user_email: data.email || '',
    account_name: m.accountName || '',
    meeting_subject: m.subject || '',
    assignee_name: t.owner || '',
    assignee_email: t.owner_email || '',
    assignee_role: t.assignee_role || '',
  }
}));

return [{ json: {
  ...data,
  activityPayload,
  taskPayloads,
  taskCount: taskPayloads.length,
}}];"""

PREPARE_TASK_PAYLOADS_JS = r"""// Fan out task payloads for batch sending to Workato
const data = $('Build Auto-Save Payload').first().json;
const taskPayloads = data.taskPayloads || [];

if (taskPayloads.length === 0) {
  return [{ json: { skip: true } }];
}

return taskPayloads.map(p => ({ json: { webhook_payload: p } }));"""

BUILD_RECAP_CARD_JS = r"""// Auto-save confirmation card with assistant voice
const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const subjectLine = m.subject || 'Customer Meeting';
const blocks = [];

// Header line: account + time + subject
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr}, ${m.timeStr} \u2014 ${subjectLine}` }
});

// Auto-save confirmation + task list
let confirmText = ':white_check_mark: I saved this recap to CRM';
if (taskCount > 0) {
  confirmText += ` and created ${taskCount} task${taskCount === 1 ? '' : 's'}:`;
  const taskLines = (recap.tasks || []).map(t => {
    const ownerPart = t.owner ? ` \u2014 *${t.owner}*` : '';
    const duePart = t.due_hint ? ` \u00b7 by ${t.due_hint}` : '';
    return `\u2022 ${t.description}${ownerPart}${duePart}`;
  });
  confirmText += '\n\n' + taskLines.join('\n');
} else {
  confirmText += '.';
}

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: confirmText }
});

// Action buttons
const truncContext = (recap.followUpContext || '').substring(0, 500);
const draftPayload = JSON.stringify({
  action: 'draft_followup',
  account_name: m.accountName,
  account_id: m.accountId || '',
  activity_uid: m.activityUid,
  meeting_subject: m.subject,
  participants: m.participants || '',
  follow_up_context: truncContext,
  user_id: data.userId,
  db_user_id: data.userId,
  slack_user_id: data.slackUserId,
  organization_id: data.organizationId || '',
  assistant_name: assistantName,
  assistant_emoji: assistantEmoji,
  rep_name: data.repName,
});

blocks.push({
  type: "actions",
  elements: [
    {
      type: "button",
      text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true },
      action_id: "recap_draft_followup",
      value: draftPayload
    },
    {
      type: "button",
      text: { type: "plain_text", text: "My Events Today", emoji: true },
      action_id: "link_my_events",
      url: "https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61"
    },
    {
      type: "button",
      text: { type: "plain_text", text: "All Tasks Today", emoji: true },
      action_id: "link_all_tasks",
      url: "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"
    }
  ]
});

const promptText = `Meeting Recap \u2014 ${m.accountName}: ${subjectLine}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  activityUids: [m.activityUid],
}}];"""

BUILD_RECAP_THREAD_JS = r"""// Simplified thread reply — read-only, no Create Task buttons
const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const sendResult = $('Send Recap').first().json;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Summary + sentiment
const sentLine = `${recap.sentimentEmoji} ${recap.sentimentSignal || recap.sentiment}`;
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `${sentLine}\n\n${recap.summary}` }
});

blocks.push({ type: "divider" });

// Key Decisions
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `\u2022 ${d}`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\n${decisionText}` }
  });
  blocks.push({ type: "divider" });
}

// Action Items — read-only list
if (recap.tasks && recap.tasks.length > 0) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Action Items*" }
  });

  for (const task of recap.tasks) {
    const roleBadge = task.assignee_role ? ` (${task.assignee_role})` : '';
    const durationBadge = task.duration_minutes ? ` \u00b7 ${task.duration_minutes} min` : '';
    const taskText = `\u2022 ${task.description}` +
      (task.owner ? ` \u2014 _${task.owner}_` + roleBadge : '') +
      durationBadge +
      (task.due_hint ? ` \u00b7 ${task.due_hint}` : '');
    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: taskText }
    });
  }
}

// If nothing captured
if ((!recap.keyDecisions || recap.keyDecisions.length === 0) &&
    (!recap.tasks || recap.tasks.length === 0)) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "_No key decisions or action items were captured for this meeting._" }
  });
}

// Thread footer
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "Tasks and recap saved to CRM \u00b7 Use PeopleGlass to review or modify \u00b7 Reply in this thread to discuss" }
  ]
});

return [{ json: {
  threadBlocks: JSON.stringify(blocks),
  threadTs: sendResult.ts,
  channelId: sendResult.channel,
  assistantName,
  assistantEmoji,
}}];"""


def make_workato_http_node(name, json_body_expr, position):
    """Create an HTTP Request node for Workato webhook (no auth needed)."""
    return {
        "parameters": {
            "method": "POST",
            "url": WORKATO_URL,
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": json_body_expr,
            "options": {"timeout": 15000},
        },
        "id": uid(),
        "name": name,
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": position,
        "continueOnFail": True,
    }


def auto_save_recap():
    print("=== Fetching Follow-up Cron (live) ===")
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"  {len(nodes)} nodes")

    # ── Verify key nodes exist ───────────────────────────────────────────
    parse_recap = find_node(nodes, "Parse Recap Output")
    build_card = find_node(nodes, "Build Recap Card")
    build_thread = find_node(nodes, "Build Recap Thread")
    open_dm = find_node(nodes, "Open Bot DM")
    send_recap = find_node(nodes, "Send Recap")

    for name, node in [("Parse Recap Output", parse_recap), ("Build Recap Card", build_card),
                        ("Build Recap Thread", build_thread), ("Open Bot DM", open_dm),
                        ("Send Recap", send_recap)]:
        if not node:
            print(f"ERROR: Could not find '{name}' node")
            return
    print("  All key nodes found")

    # ── Determine positions ──────────────────────────────────────────────
    # Parse Recap Output is at ~[3370, 304]
    # Insert new nodes between Parse Recap Output and Build Recap Card
    parse_pos = parse_recap["position"]
    card_pos = build_card["position"]

    # Build Auto-Save Payload: right after Parse Recap Output
    auto_save_pos = [parse_pos[0] + 250, parse_pos[1]]
    # Send Recap to CRM: next
    send_crm_pos = [auto_save_pos[0] + 250, auto_save_pos[1]]
    # Prepare Task Payloads: below Send Recap to CRM
    prep_tasks_pos = [auto_save_pos[0] + 250, auto_save_pos[1] + 200]
    # Send Tasks to CRM: after Prepare Task Payloads
    send_tasks_pos = [prep_tasks_pos[0] + 250, prep_tasks_pos[1]]

    # Shift existing downstream nodes right to make room
    # Build Recap Card, Open Bot DM, Send Recap, Build Recap Thread, Send Recap Thread,
    # Prepare Log Data, Log Follow-up Prompt all need to shift right by 500
    shift_nodes = [
        "Build Recap Card", "Open Bot DM", "Send Recap",
        "Build Recap Thread", "Send Recap Thread",
        "Prepare Log Data", "Log Follow-up Prompt",
    ]
    for name in shift_nodes:
        n = find_node(nodes, name)
        if n:
            n["position"][0] += 500

    # ── Create new nodes ─────────────────────────────────────────────────
    build_payload_node = make_code_node(
        "Build Auto-Save Payload", BUILD_AUTO_SAVE_PAYLOAD_JS, auto_save_pos
    )
    send_crm_node = make_workato_http_node(
        "Send Recap to CRM",
        "={{ JSON.stringify($json.activityPayload) }}",
        send_crm_pos,
    )
    prep_tasks_node = make_code_node(
        "Prepare Task Payloads", PREPARE_TASK_PAYLOADS_JS, prep_tasks_pos
    )
    send_tasks_node = make_workato_http_node(
        "Send Tasks to CRM",
        "={{ JSON.stringify($json.webhook_payload) }}",
        send_tasks_pos,
    )

    nodes.extend([build_payload_node, send_crm_node, prep_tasks_node, send_tasks_node])
    print("  Added 4 new nodes")

    # ── Replace Build Recap Card code ────────────────────────────────────
    build_card["parameters"]["jsCode"] = BUILD_RECAP_CARD_JS
    print("  Replaced Build Recap Card code")

    # ── Replace Build Recap Thread code ──────────────────────────────────
    build_thread["parameters"]["jsCode"] = BUILD_RECAP_THREAD_JS
    print("  Replaced Build Recap Thread code")

    # ── Rewire connections ───────────────────────────────────────────────
    # Old: Parse Recap Output → Build Recap Card
    # New: Parse Recap Output → Build Auto-Save Payload
    connections["Parse Recap Output"] = {
        "main": [[{"node": "Build Auto-Save Payload", "type": "main", "index": 0}]]
    }

    # Build Auto-Save Payload → [Send Recap to CRM, Prepare Task Payloads]
    connections["Build Auto-Save Payload"] = {
        "main": [[
            {"node": "Send Recap to CRM", "type": "main", "index": 0},
            {"node": "Prepare Task Payloads", "type": "main", "index": 0},
        ]]
    }

    # Send Recap to CRM → Build Recap Card (waits for CRM save before Slack)
    connections["Send Recap to CRM"] = {
        "main": [[{"node": "Build Recap Card", "type": "main", "index": 0}]]
    }

    # Prepare Task Payloads → Send Tasks to CRM (fire-and-forget)
    connections["Prepare Task Payloads"] = {
        "main": [[{"node": "Send Tasks to CRM", "type": "main", "index": 0}]]
    }

    # Send Tasks to CRM has no downstream (fire-and-forget)
    connections["Send Tasks to CRM"] = {"main": [[]]}

    # Build Recap Card → Open Bot DM (unchanged but make sure it's correct)
    connections["Build Recap Card"] = {
        "main": [[{"node": "Open Bot DM", "type": "main", "index": 0}]]
    }

    print("  Rewired connections")

    # ── Also update Send Recap jsonBody to read from Build Auto-Save Payload ─
    # The Send Recap node reads from Build Recap Card which now reads from
    # Build Auto-Save Payload. Send Recap's jsonBody references
    # $("Build Recap Card") — that's fine, Build Recap Card passes through all data.

    # ── Push ─────────────────────────────────────────────────────────────
    print("\n=== Pushing workflow ===")
    result = push_workflow(WF_FOLLOWUP_CRON, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing local ===")
    sync_local(result, LOCAL_FILENAME)

    print("\n=== Done ===")
    print(f"  Added: Build Auto-Save Payload, Send Recap to CRM, Prepare Task Payloads, Send Tasks to CRM")
    print(f"  Updated: Build Recap Card (auto-save confirmation), Build Recap Thread (read-only)")
    print(f"  Rewired: Parse Recap Output → Build Auto-Save Payload → [CRM + Tasks] → Slack card")


if __name__ == "__main__":
    auto_save_recap()
