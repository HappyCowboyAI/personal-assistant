"""
Split Meeting Recap into compact card + detailed thread reply.

Modifies the Follow-up Cron workflow (JhDuCvZdFN4PFTOW):
- Replaces "Build Recap Blocks" with "Build Recap Card" (compact top-level)
- Adds "Build Recap Thread" Code node (detailed thread reply)
- Adds "Send Recap Thread" HTTP node (posts thread reply using ts from Send Recap)
- Rewires: Parse Recap Output → Build Recap Card → Open Bot DM → Send Recap
                                                                      → Build Recap Thread → Send Recap Thread → Prepare Log Data
"""
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import (
    fetch_workflow, find_node, push_workflow, sync_local,
    make_code_node, make_slack_http_node,
    WF_FOLLOWUP_CRON, SLACK_CRED, SLACK_CHAT_POST,
)

LOCAL_FILENAME = "Follow-up Cron.json"


def split_recap():
    wf = fetch_workflow(WF_FOLLOWUP_CRON)
    nodes = wf["nodes"]
    connections = wf["connections"]
    print(f"Fetched Follow-up Cron: {len(nodes)} nodes")

    # ── Step 1: Replace Build Recap Blocks with Build Recap Card ──────────
    old_blocks = find_node(nodes, "Build Recap Blocks")
    if not old_blocks:
        print("ERROR: Could not find 'Build Recap Blocks' node")
        return
    pos = old_blocks["position"]

    # Rewrite the node in-place
    old_blocks["name"] = "Build Recap Card"
    old_blocks["parameters"]["jsCode"] = r"""// Build compact top-level recap card (summary + action buttons)
const data = $('Parse Recap Output').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Header
blocks.push({
  type: "header",
  text: { type: "plain_text", text: `:clipboard: Meeting Recap — ${m.accountName}`, emoji: true }
});

// Meeting info + sentiment
const subjectLine = m.subject || 'Customer Meeting';
const sentLine = `${recap.sentimentEmoji} ${recap.sentimentSignal || recap.sentiment}`;
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `*${subjectLine}*  |  ${m.dayStr} ${m.timeStr}\n${sentLine}` }
});

blocks.push({ type: "divider" });

// Summary (2-3 sentences)
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: recap.summary }
});

blocks.push({ type: "divider" });

// Action buttons row — Draft Follow-up (primary) + Save Recap to SF
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
  assistant_name: data.assistantName,
  assistant_emoji: data.assistantEmoji,
  rep_name: data.repName,
});

const savePayload = JSON.stringify({
  action: 'save_activity',
  account_name: m.accountName,
  account_id: m.accountId || '',
  activity_uid: m.activityUid,
  meeting_subject: m.subject,
  summary: recap.summary,
  key_decisions: recap.keyDecisions || [],
  tasks: recap.tasks || [],
  sentiment: recap.sentiment,
  user_id: data.userId,
  slack_user_id: data.slackUserId,
  rep_name: data.repName,
  rep_email: data.email || '',
});

blocks.push({
  type: "actions",
  elements: [
    {
      type: "button",
      text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true },
      style: "primary",
      action_id: "recap_draft_followup",
      value: draftPayload
    },
    {
      type: "button",
      text: { type: "plain_text", text: ":salesforce: Save Recap to SF", emoji: true },
      action_id: "recap_save_activity",
      value: savePayload
    }
  ]
});

// Footer
blocks.push({
  type: "context",
  elements: [
    { type: "mrkdwn", text: "People.ai meeting intelligence • Type `stop followups` to pause" }
  ]
});

const promptText = `Meeting Recap — ${m.accountName}: ${subjectLine}`;

return [{ json: {
  ...data,
  blocks: JSON.stringify(blocks),
  promptText,
  assistantName,
  assistantEmoji,
  activityUids: [m.activityUid],
}}];"""
    print("  Replaced 'Build Recap Blocks' → 'Build Recap Card'")

    # ── Step 2: Add Build Recap Thread node ───────────────────────────────
    # Position it after Send Recap (which is after Open Bot DM)
    send_recap = find_node(nodes, "Send Recap")
    if not send_recap:
        print("ERROR: Could not find 'Send Recap' node")
        return
    sr_pos = send_recap["position"]

    thread_node = make_code_node(
        "Build Recap Thread",
        r"""// Build detailed thread reply with decisions + tasks + Create in SF buttons
const data = $('Parse Recap Output').first().json;
const recap = data.recap;
const m = data.meeting;
const sendResult = $('Send Recap').first().json;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';

const blocks = [];

// Key Decisions
if (recap.keyDecisions && recap.keyDecisions.length > 0) {
  const decisionText = recap.keyDecisions.map(d => `• ${d}`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `*Key Decisions*\n${decisionText}` }
  });
  blocks.push({ type: "divider" });
}

// Action Items with individual "Create in SF" buttons
if (recap.tasks && recap.tasks.length > 0) {
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: "*Action Items*" }
  });

  for (let i = 0; i < recap.tasks.length; i++) {
    const task = recap.tasks[i];
    const taskText = `• ${task.description}` +
      (task.owner ? ` — _${task.owner}_` : '') +
      (task.due_hint ? ` (${task.due_hint})` : '');

    const taskPayload = JSON.stringify({
      action: 'create_task',
      task_index: i,
      task_description: task.description,
      task_owner: task.owner || '',
      task_due_hint: task.due_hint || '',
      account_name: m.accountName,
      account_id: m.accountId || '',
      activity_uid: m.activityUid,
      meeting_subject: m.subject,
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      rep_name: data.repName,
      rep_email: data.email || '',
    });

    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text: taskText },
      accessory: {
        type: "button",
        text: { type: "plain_text", text: ":salesforce: Create Task", emoji: true },
        action_id: `recap_create_task_${i}`,
        value: taskPayload
      }
    });
  }
}

// If no decisions and no tasks, still post something useful
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
    { type: "mrkdwn", text: "Reply in this thread to discuss this meeting" }
  ]
});

return [{ json: {
  threadBlocks: JSON.stringify(blocks),
  threadTs: sendResult.ts,
  channelId: sendResult.channel,
  assistantName,
  assistantEmoji,
}}];""",
        [sr_pos[0] + 250, sr_pos[1]]
    )
    nodes.append(thread_node)
    print("  Added 'Build Recap Thread' node")

    # ── Step 3: Add Send Recap Thread HTTP node ───────────────────────────
    send_thread_body = (
        '={{ JSON.stringify({ '
        'channel: $json.channelId, '
        'thread_ts: $json.threadTs, '
        'blocks: JSON.parse($json.threadBlocks), '
        'text: "Meeting details", '
        'username: $json.assistantName, '
        'icon_emoji: $json.assistantEmoji '
        '}) }}'
    )
    send_thread_node = make_slack_http_node(
        "Send Recap Thread",
        SLACK_CHAT_POST,
        send_thread_body,
        [sr_pos[0] + 500, sr_pos[1]]
    )
    nodes.append(send_thread_node)
    print("  Added 'Send Recap Thread' node")

    # ── Step 4: Rewire connections ────────────────────────────────────────
    # Rename connection keys: Build Recap Blocks → Build Recap Card
    if "Build Recap Blocks" in connections:
        connections["Build Recap Card"] = connections.pop("Build Recap Blocks")

    # Update any node that connects TO the old name
    for src_name, conn_data in connections.items():
        for conn_type, outputs in conn_data.items():
            for output_list in outputs:
                for link in output_list:
                    if link.get("node") == "Build Recap Blocks":
                        link["node"] = "Build Recap Card"

    # New chain from Send Recap onwards:
    # Send Recap → Build Recap Thread → Send Recap Thread → Prepare Log Data
    connections["Send Recap"] = {
        "main": [[{"node": "Build Recap Thread", "type": "main", "index": 0}]]
    }
    connections["Build Recap Thread"] = {
        "main": [[{"node": "Send Recap Thread", "type": "main", "index": 0}]]
    }
    connections["Send Recap Thread"] = {
        "main": [[{"node": "Prepare Log Data", "type": "main", "index": 0}]]
    }
    print("  Rewired connections for card+thread flow")

    # ── Step 5: Update Prepare Log Data to reference Build Recap Card ─────
    log_node = find_node(nodes, "Prepare Log Data")
    if log_node:
        code = log_node["parameters"]["jsCode"]
        if "Build Recap Blocks" in code:
            code = code.replace("Build Recap Blocks", "Build Recap Card")
            log_node["parameters"]["jsCode"] = code
            print("  Updated Prepare Log Data reference: Build Recap Blocks → Build Recap Card")
    else:
        print("  WARNING: Could not find 'Prepare Log Data'")

    # ── Step 6: Push and sync ─────────────────────────────────────────────
    print(f"\n=== Pushing workflow ({len(nodes)} nodes) ===")
    result = push_workflow(WF_FOLLOWUP_CRON, wf)
    print(f"Pushed Follow-up Cron: {len(result['nodes'])} nodes")
    sync_local(result, LOCAL_FILENAME)
    print("\nDone!")
    return result


if __name__ == "__main__":
    split_recap()
