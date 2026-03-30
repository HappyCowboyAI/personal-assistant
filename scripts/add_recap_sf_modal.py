#!/usr/bin/env python3
"""
Add Slack modal flow for "Save Recap to SF" in the Interactive Events Handler.

Changes:
1. Route Action output 10 (Recap Save Activity) → new Open Recap SF Modal (instead of Build Activity Payload)
2. Add Open Recap SF Modal (Code) → Send Recap Modal Open (HTTP) nodes
3. Add Is Recap SF Modal? (If) after Respond Modal Close, branching:
   - True → Build Edited Activity Payload → Send Edited Activity to Workato → Confirm Recap Saved
   - False → existing Lookup User (Submission)
4. Extract view_private_metadata in Parse Interactive Payload
5. Remove old Build Activity Payload → Send Activity to Workato → Confirm Activity Saved chain
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from n8n_helpers import (
    fetch_workflow, push_workflow, sync_local, find_node, uid,
    WF_INTERACTIVE_HANDLER, SLACK_CRED,
    NODE_CODE, NODE_HTTP_REQUEST, NODE_IF,
)

WORKFLOW_ID = WF_INTERACTIVE_HANDLER
LOCAL_FILE = "Interactive Events Handler.json"


def modify(nodes, connections):
    changes = 0

    # ── Step 1: Update Parse Interactive Payload to extract view_private_metadata ──
    pip_node = find_node(nodes, "Parse Interactive Payload")
    if not pip_node:
        raise RuntimeError("Cannot find 'Parse Interactive Payload' node")

    old_code = pip_node["parameters"]["jsCode"]
    if "view_private_metadata" not in old_code:
        # Add private_metadata extraction before the return statement
        insertion = "\n// Extract view private_metadata for modal submissions\nconst view_private_metadata = (payload.view && payload.view.private_metadata) ? payload.view.private_metadata : '';\n"
        # Update the return to include view_private_metadata
        old_return = "return [{ json: { type, userId, triggerId, actionId, actionValue, selectedOptionValue, messageTs, channelId, messageBlocks, callbackId, submittedValues } }];"
        new_return = "return [{ json: { type, userId, triggerId, actionId, actionValue, selectedOptionValue, messageTs, channelId, messageBlocks, callbackId, submittedValues, view_private_metadata } }];"
        new_code = old_code.replace(old_return, insertion + new_return)
        pip_node["parameters"]["jsCode"] = new_code
        print("  Updated Parse Interactive Payload with view_private_metadata")
        changes += 1
    else:
        print("  Parse Interactive Payload already has view_private_metadata")

    # ── Step 2: Add Open Recap SF Modal (Code node) ──
    open_modal_code = r"""const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const summary = context.summary || '';
const decisions = (context.key_decisions || []).map(d => '\u2022 ' + d).join('\n');
const tasks = (context.tasks || []).map(t => {
  let line = '\u2022 ' + t.description;
  if (t.owner) line += ' \u2014 ' + t.owner;
  if (t.due_hint) line += ' (' + t.due_hint + ')';
  return line;
}).join('\n');

// Store context in private_metadata for the submission handler
const privateMetadata = JSON.stringify({
  account_name: context.account_name || '',
  account_id: context.account_id || '',
  activity_uid: context.activity_uid || '',
  meeting_subject: context.meeting_subject || '',
  user_id: context.user_id || '',
  slack_user_id: context.slack_user_id || '',
  rep_name: context.rep_name || '',
  rep_email: context.rep_email || '',
  channel_id: payload.channelId || '',
  message_ts: payload.messageTs || '',
  assistant_name: context.assistant_name || 'Aria',
  assistant_emoji: context.assistant_emoji || ':robot_face:',
});

const modal = {
  trigger_id: payload.triggerId,
  view: {
    type: "modal",
    callback_id: "save_recap_to_sf",
    title: { type: "plain_text", text: "Save Recap to Salesforce" },
    submit: { type: "plain_text", text: "Save to Salesforce" },
    close: { type: "plain_text", text: "Cancel" },
    private_metadata: privateMetadata,
    blocks: [
      {
        type: "header",
        text: { type: "plain_text", text: (context.meeting_subject || 'Meeting Recap').substring(0, 150) }
      },
      {
        type: "input",
        block_id: "summary_block",
        label: { type: "plain_text", text: "Summary" },
        element: {
          type: "plain_text_input",
          action_id: "summary_value",
          multiline: true,
          initial_value: summary
        }
      },
      {
        type: "input",
        block_id: "decisions_block",
        label: { type: "plain_text", text: "Key Decisions" },
        element: {
          type: "plain_text_input",
          action_id: "decisions_value",
          multiline: true,
          initial_value: decisions
        },
        optional: true
      },
      {
        type: "input",
        block_id: "tasks_block",
        label: { type: "plain_text", text: "Action Items" },
        element: {
          type: "plain_text_input",
          action_id: "tasks_value",
          multiline: true,
          initial_value: tasks
        },
        optional: true
      }
    ]
  }
};

return [{ json: modal }];"""

    open_modal_node = {
        "parameters": {"jsCode": open_modal_code},
        "id": uid(),
        "name": "Open Recap SF Modal",
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": [1796, 2000],  # Reuse Build Activity Payload position
    }
    nodes.append(open_modal_node)
    print("  Added 'Open Recap SF Modal' code node")
    changes += 1

    # ── Step 3: Add Send Recap Modal Open (HTTP node) ──
    send_modal_node = {
        "parameters": {
            "method": "POST",
            "url": "https://slack.com/api/views.open",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ trigger_id: $json.trigger_id, view: $json.view }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Send Recap Modal Open",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [2046, 2000],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(send_modal_node)
    print("  Added 'Send Recap Modal Open' HTTP node")
    changes += 1

    # ── Step 4: Add Is Recap SF Modal? (If node) ──
    is_recap_modal_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [
                    {
                        "id": uid(),
                        "operator": {
                            "name": "filter.operator.equals",
                            "type": "string",
                            "operation": "equals",
                        },
                        "leftValue": "={{ $('Parse Interactive Payload').first().json.callbackId }}",
                        "rightValue": "save_recap_to_sf",
                    }
                ],
            },
            "options": {},
        },
        "id": uid(),
        "name": "Is Recap SF Modal?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": [872, 100],  # Between Respond Modal Close and Lookup User (Submission)
    }
    nodes.append(is_recap_modal_node)
    print("  Added 'Is Recap SF Modal?' If node")
    changes += 1

    # ── Step 5: Add Build Edited Activity Payload (Code node) ──
    build_edited_code = r"""const p = $('Parse Interactive Payload').first().json;
const vals = p.submittedValues || {};
let meta = {};
try { meta = JSON.parse(p.view_private_metadata || '{}'); } catch(e) {}

const summary = vals.summary_value || '';
const decisions = vals.decisions_value || '';
const tasks = vals.tasks_value || '';

const description = [
  'Meeting: ' + (meta.meeting_subject || ''),
  'Account: ' + (meta.account_name || ''),
  '',
  'Summary:',
  summary,
  '',
  decisions ? 'Key Decisions:\n' + decisions : '',
  '',
  tasks ? 'Action Items:\n' + tasks : '',
].filter(Boolean).join('\n');

return [{ json: {
  webhook_payload: {
    action: 'log_activity',
    salesforce_object: 'Event',
    fields: {
      Subject: meta.meeting_subject || 'Customer Meeting',
      Description: description,
      ActivityDate: new Date().toISOString().split('T')[0],
    },
    context: {
      user_email: meta.rep_email || '',
      account_name: meta.account_name || '',
      activity_uid: meta.activity_uid || ''
    }
  },
  channelId: meta.channel_id || '',
  messageTs: meta.message_ts || '',
  slackUserId: meta.slack_user_id || '',
  assistantName: meta.assistant_name || 'Aria',
  assistantEmoji: meta.assistant_emoji || ':robot_face:',
}}];"""

    build_edited_node = {
        "parameters": {"jsCode": build_edited_code},
        "id": uid(),
        "name": "Build Edited Activity Payload",
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": [1096, 0],
    }
    nodes.append(build_edited_node)
    print("  Added 'Build Edited Activity Payload' code node")
    changes += 1

    # ── Step 6: Add Send Edited Activity to Workato (HTTP node) ──
    send_edited_node = {
        "parameters": {
            "method": "POST",
            "url": "={{ $env.WORKATO_WEBHOOK_URL || 'https://WORKATO_WEBHOOK_PLACEHOLDER' }}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "application/json"}]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.webhook_payload) }}",
            "options": {"timeout": 15000},
        },
        "id": uid(),
        "name": "Send Edited Activity to Workato",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1346, 0],
    }
    nodes.append(send_edited_node)
    print("  Added 'Send Edited Activity to Workato' HTTP node")
    changes += 1

    # ── Step 7: Add Confirm Recap Saved (HTTP node) ──
    confirm_recap_node = {
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
            "jsonBody": "={{ JSON.stringify({ channel: $('Build Edited Activity Payload').first().json.channelId, thread_ts: $('Build Edited Activity Payload').first().json.messageTs, text: ':white_check_mark: Meeting recap saved to Salesforce', username: $('Build Edited Activity Payload').first().json.assistantName, icon_emoji: $('Build Edited Activity Payload').first().json.assistantEmoji }) }}",
            "options": {},
        },
        "id": uid(),
        "name": "Confirm Recap Saved",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": [1596, 0],
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }
    nodes.append(confirm_recap_node)
    print("  Added 'Confirm Recap Saved' HTTP node")
    changes += 1

    # ── Step 8: Remove old nodes ──
    old_node_names = {"Build Activity Payload", "Send Activity to Workato", "Confirm Activity Saved"}
    removed = []
    for name in old_node_names:
        node = find_node(nodes, name)
        if node:
            nodes.remove(node)
            removed.append(name)
            # Also remove from connections
            if name in connections:
                del connections[name]
    if removed:
        print(f"  Removed old nodes: {', '.join(removed)}")
        changes += 1

    # ── Step 9: Rewire connections ──

    # 9a: Route Action output 10 → Open Recap SF Modal (instead of Build Activity Payload)
    if "Route Action" in connections:
        ra_main = connections["Route Action"]["main"]
        if len(ra_main) > 10:
            ra_main[10] = [{"node": "Open Recap SF Modal", "type": "main", "index": 0}]
            print("  Rewired Route Action output 10 → Open Recap SF Modal")
            changes += 1

    # 9b: Open Recap SF Modal → Send Recap Modal Open
    connections["Open Recap SF Modal"] = {
        "main": [[{"node": "Send Recap Modal Open", "type": "main", "index": 0}]]
    }
    print("  Wired Open Recap SF Modal → Send Recap Modal Open")
    changes += 1

    # 9c: Respond Modal Close → Is Recap SF Modal? (instead of Lookup User (Submission))
    if "Respond Modal Close" in connections:
        connections["Respond Modal Close"]["main"] = [
            [{"node": "Is Recap SF Modal?", "type": "main", "index": 0}]
        ]
        print("  Rewired Respond Modal Close → Is Recap SF Modal?")
        changes += 1

    # 9d: Is Recap SF Modal? true (output 0) → Build Edited Activity Payload
    #     Is Recap SF Modal? false (output 1) → Lookup User (Submission)
    connections["Is Recap SF Modal?"] = {
        "main": [
            [{"node": "Build Edited Activity Payload", "type": "main", "index": 0}],
            [{"node": "Lookup User (Submission)", "type": "main", "index": 0}],
        ]
    }
    print("  Wired Is Recap SF Modal? → true: Build Edited Activity Payload, false: Lookup User (Submission)")
    changes += 1

    # 9e: Build Edited Activity Payload → Send Edited Activity to Workato → Confirm Recap Saved
    connections["Build Edited Activity Payload"] = {
        "main": [[{"node": "Send Edited Activity to Workato", "type": "main", "index": 0}]]
    }
    connections["Send Edited Activity to Workato"] = {
        "main": [[{"node": "Confirm Recap Saved", "type": "main", "index": 0}]]
    }
    print("  Wired Build Edited Activity Payload → Send Edited Activity to Workato → Confirm Recap Saved")
    changes += 1

    return changes


def main():
    print(f"=== Adding Recap SF Modal flow to Interactive Events Handler ===\n")
    wf = fetch_workflow(WORKFLOW_ID)
    print(f"  {len(wf['nodes'])} nodes (live)\n")

    changes = modify(wf["nodes"], wf.get("connections", {}))

    if changes == 0:
        print("\nNo changes needed.")
        return

    print(f"\n=== Pushing workflow ({changes} changes) ===")
    result = push_workflow(WORKFLOW_ID, wf)
    print(f"  HTTP 200, {len(result['nodes'])} nodes")

    print("\n=== Syncing ===")
    sync_local(result, LOCAL_FILE)

    print("\n=== Done ===")
    print(f"  Added nodes: Open Recap SF Modal, Send Recap Modal Open, Is Recap SF Modal?,")
    print(f"    Build Edited Activity Payload, Send Edited Activity to Workato, Confirm Recap Saved")
    print(f"  Removed nodes: Build Activity Payload, Send Activity to Workato, Confirm Activity Saved")
    print(f"  Total nodes: {len(result['nodes'])}")


if __name__ == "__main__":
    main()
