"""
Add duration + assignee_role to recap tasks, and replace direct task creation
with a Slack modal in the Interactive Events Handler.

Changes:
1. Follow-up Cron: Update Build Recap Context, Parse Recap Output, Build Recap Thread
2. Slack Events Handler: Update Recap Build Context, Recap Parse Output OD, Recap Build Thread OD
3. Interactive Events Handler: Replace Build Task Payload → modal flow, add task modal submission handling
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import (
    fetch_workflow, find_node, push_workflow, sync_local, modify_workflow, uid,
    WF_FOLLOWUP_CRON, WF_EVENTS_HANDLER, WF_INTERACTIVE_HANDLER,
    SLACK_CRED, NODE_HTTP_REQUEST, NODE_CODE, NODE_IF,
)

WORKATO_URL = "https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write"


# ── Shared updated task schema for system prompts ──────────────────────

OLD_TASK_SCHEMA = '''"tasks": [
    {
      "description": "specific action item from the meeting",
      "owner": "person name",
      "due_hint": "timeframe suggestion"
    }
  ]'''

NEW_TASK_SCHEMA = '''"tasks": [
    {
      "description": "specific action item from the meeting",
      "owner": "person name",
      "assignee_role": "CSM or AE — CSM for technical, training, onboarding, implementation tasks; AE for strategic, commercial, expansion, executive engagement tasks",
      "duration_minutes": "estimated minutes (15, 30, 45, 60, 90, 120)",
      "due_hint": "timeframe suggestion"
    }
  ]'''

TASK_INSTRUCTION = "\nFor each task, estimate the duration in minutes and assign the role (CSM or AE) based on the nature of the work."


# ── Part 1 & 2: Update Follow-up Cron ──────────────────────────────────

def modify_followup_cron(nodes, connections):
    changes = 0

    # --- Build Recap Context: update task schema in system prompt ---
    node = find_node(nodes, "Build Recap Context")
    if not node:
        print("  ERROR: Build Recap Context not found")
        return 0
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        code = code.replace(OLD_TASK_SCHEMA, NEW_TASK_SCHEMA)
        # Add instruction before TOOL CALL BUDGET
        code = code.replace(
            "TOOL CALL BUDGET:",
            TASK_INSTRUCTION + "\n\nTOOL CALL BUDGET:"
        )
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Build Recap Context (task schema + instruction)")
    else:
        print("  Build Recap Context already has assignee_role")

    # --- Parse Recap Output: pass through new fields ---
    node = find_node(nodes, "Parse Recap Output")
    if not node:
        print("  ERROR: Parse Recap Output not found")
        return changes
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        # The tasks are sliced: (recap.tasks || []).slice(0, 5)
        # We need to ensure the fields pass through. They already do since
        # tasks is just the raw parsed array. But let's make it explicit by
        # mapping to ensure fields exist.
        old_tasks_line = "tasks: (recap.tasks || []).slice(0, 5),"
        new_tasks_line = """tasks: (recap.tasks || []).slice(0, 5).map(t => ({
      description: t.description || '',
      owner: t.owner || '',
      assignee_role: t.assignee_role || '',
      duration_minutes: t.duration_minutes || 30,
      due_hint: t.due_hint || '',
    })),"""
        code = code.replace(old_tasks_line, new_tasks_line)
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Parse Recap Output (pass through assignee_role, duration_minutes)")
    else:
        print("  Parse Recap Output already has assignee_role")

    # --- Build Recap Thread: update task display + button payload ---
    node = find_node(nodes, "Build Recap Thread")
    if not node:
        print("  ERROR: Build Recap Thread not found")
        return changes
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        # Update task text display
        old_task_text = """const taskText = `• ${task.description}` +
      (task.owner ? ` — _${task.owner}_` : '') +
      (task.due_hint ? ` (${task.due_hint})` : '');"""
        new_task_text = """const roleBadge = task.assignee_role ? ` (${task.assignee_role})` : '';
    const durationBadge = task.duration_minutes ? ` · ${task.duration_minutes} min` : '';
    const taskText = `• ${task.description}` +
      (task.owner ? ` — _${task.owner}_` + roleBadge : '') +
      durationBadge +
      (task.due_hint ? ` · ${task.due_hint}` : '');"""
        code = code.replace(old_task_text, new_task_text)

        # Update button payload to include new fields
        old_payload_end = """      rep_name: data.repName,
      rep_email: data.email || '',
    });"""
        new_payload_end = """      rep_name: data.repName,
      rep_email: data.email || '',
      assignee_role: task.assignee_role || '',
      duration_minutes: task.duration_minutes || 30,
      assistant_name: data.assistantName || 'Aria',
      assistant_emoji: data.assistantEmoji || ':robot_face:',
    });"""
        code = code.replace(old_payload_end, new_payload_end)
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Build Recap Thread (display + payload)")
    else:
        print("  Build Recap Thread already has assignee_role")

    return changes


# ── Part 1 & 2: Update Slack Events Handler ────────────────────────────

def modify_events_handler(nodes, connections):
    changes = 0

    # --- Recap Build Context: update task schema in system prompt ---
    node = find_node(nodes, "Recap Build Context")
    if not node:
        print("  ERROR: Recap Build Context not found")
        return 0
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        code = code.replace(OLD_TASK_SCHEMA, NEW_TASK_SCHEMA)
        code = code.replace(
            "TOOL CALL BUDGET:",
            TASK_INSTRUCTION + "\n\nTOOL CALL BUDGET:"
        )
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Recap Build Context (task schema + instruction)")
    else:
        print("  Recap Build Context already has assignee_role")

    # --- Recap Parse Output OD: pass through new fields ---
    node = find_node(nodes, "Recap Parse Output OD")
    if not node:
        print("  ERROR: Recap Parse Output OD not found")
        return changes
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        old_tasks_line = "tasks: (recap.tasks || []).slice(0, 5),"
        new_tasks_line = """tasks: (recap.tasks || []).slice(0, 5).map(t => ({
      description: t.description || '',
      owner: t.owner || '',
      assignee_role: t.assignee_role || '',
      duration_minutes: t.duration_minutes || 30,
      due_hint: t.due_hint || '',
    })),"""
        code = code.replace(old_tasks_line, new_tasks_line)
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Recap Parse Output OD (pass through assignee_role, duration_minutes)")
    else:
        print("  Recap Parse Output OD already has assignee_role")

    # --- Recap Build Thread OD: update task display + button payload ---
    node = find_node(nodes, "Recap Build Thread OD")
    if not node:
        print("  ERROR: Recap Build Thread OD not found")
        return changes
    code = node["parameters"]["jsCode"]
    if "assignee_role" not in code:
        # Update task text display (uses \u2022 and \u2014 unicode escape sequences)
        old_task_text = r"""const taskText = `\u2022 ${task.description}` +
      (task.owner ? ` \u2014 _${task.owner}_` : '') +
      (task.due_hint ? ` (${task.due_hint})` : '');"""
        new_task_text = r"""const roleBadge = task.assignee_role ? ` (${task.assignee_role})` : '';
    const durationBadge = task.duration_minutes ? ` \u00b7 ${task.duration_minutes} min` : '';
    const taskText = `\u2022 ${task.description}` +
      (task.owner ? ` \u2014 _${task.owner}_` + roleBadge : '') +
      durationBadge +
      (task.due_hint ? ` \u00b7 ${task.due_hint}` : '');"""
        code = code.replace(old_task_text, new_task_text)

        # Update button payload to include new fields
        old_payload_end = """      rep_name: data.repName,
      rep_email: (data.userRecord || {}).email || '',
    });"""
        new_payload_end = """      rep_name: data.repName,
      rep_email: (data.userRecord || {}).email || '',
      assignee_role: task.assignee_role || '',
      duration_minutes: task.duration_minutes || 30,
      assistant_name: data.assistantName || 'Aria',
      assistant_emoji: data.assistantEmoji || ':robot_face:',
    });"""
        code = code.replace(old_payload_end, new_payload_end)
        node["parameters"]["jsCode"] = code
        changes += 1
        print("  Updated Recap Build Thread OD (display + payload)")
    else:
        print("  Recap Build Thread OD already has assignee_role")

    return changes


# ── Part 3 & 4: Update Interactive Events Handler ──────────────────────

OPEN_TASK_MODAL_JS = r"""// Open a modal for creating a task in Salesforce
const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

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

const roleOpts = [
  { text: { type: "plain_text", text: "CSM" }, value: "CSM" },
  { text: { type: "plain_text", text: "AE" }, value: "AE" }
];

const roleElement = {
  type: "static_select",
  action_id: "task_role_value",
  placeholder: { type: "plain_text", text: "Select role" },
  options: roleOpts,
};
if (context.assignee_role === 'CSM' || context.assignee_role === 'AE') {
  roleElement.initial_option = { text: { type: "plain_text", text: context.assignee_role }, value: context.assignee_role };
}

const modal = {
  trigger_id: payload.triggerId,
  view: {
    type: "modal",
    callback_id: "save_task_to_sf",
    title: { type: "plain_text", text: "Create Task in Salesforce" },
    submit: { type: "plain_text", text: "Create Task" },
    close: { type: "plain_text", text: "Cancel" },
    private_metadata: privateMetadata,
    blocks: [
      {
        type: "input",
        block_id: "task_desc_block",
        label: { type: "plain_text", text: "Task Description" },
        element: {
          type: "plain_text_input",
          action_id: "task_desc_value",
          multiline: true,
          initial_value: context.task_description || ''
        }
      },
      {
        type: "input",
        block_id: "task_owner_block",
        label: { type: "plain_text", text: "Assigned To" },
        element: {
          type: "plain_text_input",
          action_id: "task_owner_value",
          initial_value: context.task_owner || ''
        }
      },
      {
        type: "input",
        block_id: "task_role_block",
        label: { type: "plain_text", text: "AI Suggested Role" },
        element: roleElement,
        optional: true
      },
      {
        type: "input",
        block_id: "task_duration_block",
        label: { type: "plain_text", text: "Estimated Duration (minutes)" },
        element: {
          type: "plain_text_input",
          action_id: "task_duration_value",
          initial_value: String(context.duration_minutes || '30')
        },
        optional: true
      },
      {
        type: "input",
        block_id: "task_due_block",
        label: { type: "plain_text", text: "Due Date Hint" },
        element: {
          type: "plain_text_input",
          action_id: "task_due_value",
          initial_value: context.task_due_hint || ''
        },
        optional: true
      }
    ]
  }
};

return [{ json: modal }];"""

BUILD_TASK_FROM_MODAL_JS = r"""// Build Workato webhook payload from task modal submission
const p = $('Parse Interactive Payload').first().json;
const vals = p.submittedValues || {};
let meta = {};
try { meta = JSON.parse(p.view_private_metadata || '{}'); } catch(e) {}

const description = vals.task_desc_value || '';
const owner = vals.task_owner_value || '';
const role = vals.task_role_value || '';
const duration = vals.task_duration_value || '30';
const dueHint = vals.task_due_value || '';

// Parse due_hint into a date
const now = new Date();
let dueDate = '';
const hint = (dueHint).toLowerCase();
if (hint.includes('asap') || hint.includes('today') || hint.includes('immediate')) {
  dueDate = now.toISOString().split('T')[0];
} else if (hint.includes('tomorrow')) {
  const d = new Date(now.getTime() + 86400000);
  dueDate = d.toISOString().split('T')[0];
} else if (hint.includes('friday') || hint.includes('end of week') || hint.includes('this week')) {
  const d = new Date(now);
  d.setDate(d.getDate() + ((5 - d.getDay() + 7) % 7 || 7));
  dueDate = d.toISOString().split('T')[0];
} else if (hint.includes('next week')) {
  const d = new Date(now.getTime() + 7 * 86400000);
  dueDate = d.toISOString().split('T')[0];
} else {
  const d = new Date(now.getTime() + 7 * 86400000);
  dueDate = d.toISOString().split('T')[0];
}

return [{ json: {
  webhook_payload: {
    action: 'create_task',
    salesforce_object: 'Task',
    fields: {
      Subject: description.substring(0, 255),
      Description: 'From meeting: ' + (meta.meeting_subject || '') + ' with ' + (meta.account_name || '') +
        '\nAssigned to: ' + owner + ' (' + role + ')' +
        '\nEstimated duration: ' + duration + ' minutes',
      ActivityDate: dueDate,
      Status: 'Not Started',
      Priority: 'Normal'
    },
    context: {
      user_email: meta.rep_email || '',
      account_name: meta.account_name || '',
      meeting_subject: meta.meeting_subject || '',
      activity_uid: meta.activity_uid || '',
      assignee_role: role,
      duration_minutes: parseInt(duration) || 30,
    }
  },
  channelId: meta.channel_id || '',
  messageTs: meta.message_ts || '',
  slackUserId: meta.slack_user_id || '',
  task_description: description,
  assistantName: meta.assistant_name || 'Aria',
  assistantEmoji: meta.assistant_emoji || ':robot_face:',
}}];"""


def modify_interactive_handler(nodes, connections):
    changes = 0

    # --- 4a: Replace Build Task Payload with Open Task SF Modal ---
    # First, find positions of existing nodes for layout
    build_task_node = find_node(nodes, "Build Task Payload")
    if not build_task_node:
        print("  ERROR: Build Task Payload not found")
        return 0
    build_task_pos = build_task_node["position"]

    # Create new "Open Task SF Modal" code node at same position
    open_task_modal_node = {
        "parameters": {"jsCode": OPEN_TASK_MODAL_JS},
        "id": uid(),
        "name": "Open Task SF Modal",
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": build_task_pos,
    }

    # Create "Send Task Modal Open" HTTP node (same pattern as Send Recap Modal Open)
    send_task_modal_pos = [build_task_pos[0] + 250, build_task_pos[1]]
    send_task_modal_node = {
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
        "name": "Send Task Modal Open",
        "type": NODE_HTTP_REQUEST,
        "typeVersion": 4.2,
        "position": send_task_modal_pos,
        "credentials": {"httpHeaderAuth": SLACK_CRED},
    }

    # Create "Is Task Modal?" If node to route between recap vs task submissions
    is_recap_node = find_node(nodes, "Is Recap SF Modal?")
    is_recap_pos = is_recap_node["position"]
    is_task_modal_pos = [is_recap_pos[0] + 250, is_recap_pos[1]]
    is_task_modal_node = {
        "parameters": {
            "conditions": {
                "options": {
                    "version": 2,
                    "leftValue": "",
                    "caseSensitive": True,
                    "typeValidation": "strict",
                },
                "combinator": "and",
                "conditions": [{
                    "id": uid(),
                    "operator": {
                        "name": "filter.operator.equals",
                        "type": "string",
                        "operation": "equals",
                    },
                    "leftValue": "={{ $('Parse Interactive Payload').first().json.callbackId }}",
                    "rightValue": "save_task_to_sf",
                }],
            },
            "options": {},
        },
        "id": uid(),
        "name": "Is Task Modal?",
        "type": NODE_IF,
        "typeVersion": 2.2,
        "position": is_task_modal_pos,
    }

    # Create "Build Task from Modal" Code node
    build_task_from_modal_pos = [is_task_modal_pos[0] + 250, is_task_modal_pos[1] - 100]
    build_task_from_modal_node = {
        "parameters": {"jsCode": BUILD_TASK_FROM_MODAL_JS},
        "id": uid(),
        "name": "Build Task from Modal",
        "type": NODE_CODE,
        "typeVersion": 2,
        "position": build_task_from_modal_pos,
    }

    # --- Remove Build Task Payload node ---
    nodes[:] = [n for n in nodes if n["name"] != "Build Task Payload"]
    # Remove old connections from/to Build Task Payload
    connections.pop("Build Task Payload", None)
    print("  Removed Build Task Payload node")

    # Add new nodes
    nodes.extend([
        open_task_modal_node,
        send_task_modal_node,
        is_task_modal_node,
        build_task_from_modal_node,
    ])
    changes += 4
    print("  Added: Open Task SF Modal, Send Task Modal Open, Is Task Modal?, Build Task from Modal")

    # --- Update connections ---

    # 4a: Route Action output 9 (Recap Create Task) -> Open Task SF Modal (instead of Build Task Payload)
    route_action_conns = connections.get("Route Action", {}).get("main", [])
    if len(route_action_conns) > 9:
        route_action_conns[9] = [{"node": "Open Task SF Modal", "type": "main", "index": 0}]
        print("  Rewired Route Action[9] -> Open Task SF Modal")
        changes += 1

    # 4b: Open Task SF Modal -> Send Task Modal Open
    connections["Open Task SF Modal"] = {
        "main": [[{"node": "Send Task Modal Open", "type": "main", "index": 0}]]
    }
    print("  Wired Open Task SF Modal -> Send Task Modal Open")
    changes += 1

    # 4d: Update Is Recap SF Modal? to match BOTH save_recap_to_sf and save_task_to_sf
    # Change condition from equals "save_recap_to_sf" to startsWith "save_"
    is_recap_node["parameters"]["conditions"]["conditions"][0]["operator"] = {
        "name": "filter.operator.startsWith",
        "type": "string",
        "operation": "startsWith",
    }
    is_recap_node["parameters"]["conditions"]["conditions"][0]["rightValue"] = "save_"
    print("  Updated Is Recap SF Modal? condition to startsWith 'save_'")
    changes += 1

    # Is Recap SF Modal? true branch -> Is Task Modal? (instead of Build Edited Activity Payload)
    connections["Is Recap SF Modal?"] = {
        "main": [
            [{"node": "Is Task Modal?", "type": "main", "index": 0}],  # true -> Is Task Modal?
            connections.get("Is Recap SF Modal?", {}).get("main", [None, None])[1] or [],  # false stays same
        ]
    }
    # Preserve the false branch (Lookup User (Submission))
    print("  Rewired Is Recap SF Modal? true -> Is Task Modal?")
    changes += 1

    # Is Task Modal? true -> Build Task from Modal, false -> Build Edited Activity Payload (existing recap flow)
    connections["Is Task Modal?"] = {
        "main": [
            [{"node": "Build Task from Modal", "type": "main", "index": 0}],  # true = task
            [{"node": "Build Edited Activity Payload", "type": "main", "index": 0}],  # false = recap
        ]
    }
    print("  Wired Is Task Modal? true -> Build Task from Modal, false -> Build Edited Activity Payload")
    changes += 1

    # Build Task from Modal -> Send Task to Workato
    connections["Build Task from Modal"] = {
        "main": [[{"node": "Send Task to Workato", "type": "main", "index": 0}]]
    }
    print("  Wired Build Task from Modal -> Send Task to Workato")
    changes += 1

    # 4f: Update Confirm Task Created to reference Build Task from Modal instead of Build Task Payload
    confirm_node = find_node(nodes, "Confirm Task Created")
    if confirm_node:
        old_ref = "$('Build Task Payload')"
        new_ref = "$('Build Task from Modal')"
        body = confirm_node["parameters"]["jsonBody"]
        body = body.replace(old_ref, new_ref)
        confirm_node["parameters"]["jsonBody"] = body
        print("  Updated Confirm Task Created references -> Build Task from Modal")
        changes += 1

    return changes


# ── Main ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Part 1+2: Follow-up Cron — recap agent + parse + thread")
    print("=" * 60)
    modify_workflow(
        WF_FOLLOWUP_CRON,
        "Follow-up Cron.json",
        modify_followup_cron,
    )

    print()
    print("=" * 60)
    print("Part 1+2: Slack Events Handler — recap agent + parse + thread")
    print("=" * 60)
    modify_workflow(
        WF_EVENTS_HANDLER,
        "Slack Events Handler.json",
        modify_events_handler,
    )

    print()
    print("=" * 60)
    print("Part 3+4: Interactive Events Handler — task modal flow")
    print("=" * 60)
    modify_workflow(
        WF_INTERACTIVE_HANDLER,
        "Interactive Events Handler.json",
        modify_interactive_handler,
    )

    print()
    print("ALL DONE")
