"""
Add Task Assist buttons to recap cards.

Modifies two nodes:
1. "Build Recap Card" in Follow-up Cron (JhDuCvZdFN4PFTOW)
   — adds SKILL_REGISTRY keyword matching on recap tasks
   — inserts "I can help" section + assist buttons before existing action row

2. "Recap Build Card OD" in Slack Events Handler (QuQbIaWetunUOFUW)
   — same pattern, different data source ($('Build Auto-Save OD'))
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n8n_helpers import (
    find_node,
    make_code_node,
    make_switch_rule,
    modify_workflow,
    uid,
    WF_EVENTS_HANDLER,
    WF_FOLLOWUP_CRON,
    WF_INTERACTIVE_HANDLER,
)

WF_TASK_RESOLUTION = "dnoslQTCCTHZVexp"

# ── Shared JS constants ─────────────────────────────────────────────────

SKILL_REGISTRY_JS = r"""const SKILL_REGISTRY = [
  { id: 'draft_email', label: 'Draft Email',
    keywords: ['send email', 'follow up', 'follow-up', 'email', 'reach out', 'share with', 'send to', 'write to', 'notify', 'update via email', 'loop in'],
    buttonText: ':email: Draft Email', actionId: 'task_assist_draft_email' },
  { id: 'presentation', label: 'Create Presentation',
    keywords: ['create deck', 'build slides', 'presentation', 'qbr', 'prepare deck', 'slide deck', 'google slides'],
    buttonText: ':bar_chart: Create Deck', actionId: 'task_assist_presentation' },
  { id: 'stakeholder_map', label: 'Stakeholder Map',
    keywords: ['map contacts', 'stakeholder', 'decision maker', 'identify contacts', 'org chart', 'key contacts', 'champion'],
    buttonText: ':busts_in_silhouette: Stakeholder Map', actionId: 'task_assist_stakeholders' },
  { id: 'meeting_prep', label: 'Meeting Prep',
    keywords: ['prepare for meeting', 'prep for call', 'research before', 'meeting brief', 'pre-meeting', 'talking points'],
    buttonText: ':clipboard: Meeting Prep', actionId: 'task_assist_meeting_prep' },
];

function matchTaskToSkill(taskSubject, taskDescription) {
  const text = (taskSubject + ' ' + (taskDescription || '')).toLowerCase();
  for (const skill of SKILL_REGISTRY) {
    for (const kw of skill.keywords) {
      if (text.includes(kw)) return skill;
    }
  }
  return null;
}"""

SKILL_ID_MAP_JS = r"""const SKILL_ID_MAP = Object.fromEntries(
  SKILL_REGISTRY.map(s => [s.id, s])
);"""

# ── Build Recap Card JS (Follow-up Cron) ────────────────────────────────

BUILD_RECAP_CARD_JS = r"""// Compact recap card with Task Assist buttons
""" + SKILL_REGISTRY_JS + r"""

""" + SKILL_ID_MAP_JS + r"""

const data = $('Build Auto-Save Payload').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const subjectLine = m.subject || 'Customer Meeting';
const blocks = [];

// Header: account + time + subject
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr}, ${m.timeStr} \u2014 ${subjectLine}` }
});

// Compact confirmation line
const parts = ['I saved this recap to CRM'];
if (taskCount > 0) parts.push(`created ${taskCount} task${taskCount === 1 ? '' : 's'}`);
const confirmText = ':white_check_mark: ' + parts.join(' and ') + '. Check the thread for details!';

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: confirmText }
});

// Task Assist — keyword matching on tasks
const matched = [];
for (const t of (recap.tasks || [])) {
  const skill = matchTaskToSkill(t.description, '');
  if (skill && !matched.find(m => m.skill.id === skill.id && m.task.description === t.description)) {
    matched.push({ skill, task: t });
  }
}

if (matched.length > 0) {
  const helpLines = matched.map(m => `\u2022 ${m.task.description} \u2192 *${m.skill.label}*`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `:robot_face: I can help with ${matched.length} of these:\n${helpLines}` }
  });

  const assistButtons = matched.slice(0, 5).map(m => ({
    type: "button",
    text: { type: "plain_text", text: m.skill.buttonText, emoji: true },
    action_id: m.skill.actionId,
    value: JSON.stringify({
      action: 'task_assist',
      skill: m.skill.id,
      task_subject: m.task.description,
      account_name: m.meeting_accountName || data.meeting.accountName,
      account_id: m.meeting_accountId || data.meeting.accountId || '',
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      organization_id: data.organizationId || '',
      assistant_name: assistantName,
      assistant_emoji: assistantEmoji,
      rep_name: data.repName,
    }),
  }));

  blocks.push({ type: "actions", elements: assistButtons });
}

// Action buttons — Draft Follow-up + links
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

# ── Recap Build Card OD JS (Events Handler) ─────────────────────────────

BUILD_RECAP_CARD_OD_JS = r"""// Compact recap card with Task Assist buttons (on-demand)
""" + SKILL_REGISTRY_JS + r"""

""" + SKILL_ID_MAP_JS + r"""

const data = $('Build Auto-Save OD').first().json;
const recap = data.recap;
const m = data.meeting;
const assistantName = data.assistantName || 'Aria';
const assistantEmoji = data.assistantEmoji || ':robot_face:';
const taskCount = data.taskCount || 0;

const subjectLine = m.subject || 'Customer Meeting';
const blocks = [];

// Header: account + time + subject
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: `:clipboard: *${m.accountName}* \u00b7 ${m.dayStr} ${m.timeStr} \u2014 ${subjectLine}` }
});

// Compact confirmation line
const parts = ['I saved this recap to CRM'];
if (taskCount > 0) parts.push(`created ${taskCount} task${taskCount === 1 ? '' : 's'}`);
const confirmText = ':white_check_mark: ' + parts.join(' and ') + '. Check the thread for details!';

blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: confirmText }
});

// Task Assist — keyword matching on tasks
const matched = [];
for (const t of (recap.tasks || [])) {
  const skill = matchTaskToSkill(t.description, '');
  if (skill && !matched.find(m => m.skill.id === skill.id && m.task.description === t.description)) {
    matched.push({ skill, task: t });
  }
}

if (matched.length > 0) {
  const helpLines = matched.map(m => `\u2022 ${m.task.description} \u2192 *${m.skill.label}*`).join('\n');
  blocks.push({
    type: "section",
    text: { type: "mrkdwn", text: `:robot_face: I can help with ${matched.length} of these:\n${helpLines}` }
  });

  const assistButtons = matched.slice(0, 5).map(m => ({
    type: "button",
    text: { type: "plain_text", text: m.skill.buttonText, emoji: true },
    action_id: m.skill.actionId,
    value: JSON.stringify({
      action: 'task_assist',
      skill: m.skill.id,
      task_subject: m.task.description,
      account_name: m.meeting_accountName || data.meeting.accountName,
      account_id: m.meeting_accountId || data.meeting.accountId || '',
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      organization_id: data.organizationId || '',
      assistant_name: data.assistantName,
      assistant_emoji: data.assistantEmoji,
      rep_name: data.repName,
    }),
  }));

  blocks.push({ type: "actions", elements: assistButtons });
}

// Action buttons — Draft Follow-up + links
const truncContext = (recap.followUpContext || '').substring(0, 500);
const draftPayload = JSON.stringify({
  action: 'draft_followup', account_name: m.accountName, account_id: m.accountId || '',
  activity_uid: m.activityUid, meeting_subject: m.subject,
  participants: m.participants || '', follow_up_context: truncContext,
  user_id: data.userId, db_user_id: data.userId, slack_user_id: data.slackUserId,
  organization_id: data.organizationId || '',
  assistant_name: data.assistantName, assistant_emoji: data.assistantEmoji, rep_name: data.repName,
});

blocks.push({ type: "actions", elements: [
  { type: "button", text: { type: "plain_text", text: ":email: Draft Follow-up", emoji: true }, action_id: "recap_draft_followup", value: draftPayload },
  { type: "button", text: { type: "plain_text", text: "My Events Today", emoji: true }, url: "https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61", action_id: "pg_events_link" },
  { type: "button", text: { type: "plain_text", text: "All Tasks Today", emoji: true }, url: "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5", action_id: "pg_tasks_link" },
]});

return [{ json: { ...data, blocks: JSON.stringify(blocks), promptText: `Meeting Recap \u2014 ${m.accountName}: ${subjectLine}`, assistantName, assistantEmoji, activityUids: [m.activityUid] } }];"""


# ── Modifier functions ───────────────────────────────────────────────────

def add_assist_to_recap_card():
    """Replace Build Recap Card jsCode in Follow-up Cron with Task Assist version."""

    def modifier(nodes, connections):
        node = find_node(nodes, "Build Recap Card")
        if not node:
            print("  ERROR: 'Build Recap Card' not found")
            return 0

        current_code = node["parameters"].get("jsCode", "")
        if "SKILL_REGISTRY" in current_code:
            print("  Build Recap Card already has SKILL_REGISTRY — skipping")
            return 0

        node["parameters"]["jsCode"] = BUILD_RECAP_CARD_JS
        print("  [1/1] Replaced Build Recap Card with Task Assist version")
        return 1

    return modify_workflow(WF_FOLLOWUP_CRON, "Follow-up Cron.json", modifier)


def add_assist_to_recap_card_od():
    """Replace Recap Build Card OD jsCode in Events Handler with Task Assist version."""

    def modifier(nodes, connections):
        node = find_node(nodes, "Recap Build Card OD")
        if not node:
            print("  ERROR: 'Recap Build Card OD' not found")
            return 0

        current_code = node["parameters"].get("jsCode", "")
        if "SKILL_REGISTRY" in current_code:
            print("  Recap Build Card OD already has SKILL_REGISTRY — skipping")
            return 0

        node["parameters"]["jsCode"] = BUILD_RECAP_CARD_OD_JS
        print("  [1/1] Replaced Recap Build Card OD with Task Assist version")
        return 1

    return modify_workflow(WF_EVENTS_HANDLER, "Slack Events Handler.json", modifier)


# ── Task 4: Resolution Agent prompt with assist_skill classification ────

RESOLUTION_SYSTEM_PROMPT = (
    "You are a task resolution analyst. You evaluate whether CRM tasks have been "
    "completed based on recent account activity from People.ai SalesAI.\n\n"
    "RULES:\n"
    "- Only mark a task COMPLETE if there is CLEAR evidence the work was done\n"
    "- Evidence includes: email sent, meeting held, document delivered, issue resolved, follow-up completed\n"
    "- When in doubt, leave as OPEN\n"
    "- Be conservative — false completions are worse than missed completions\n"
    "- Output ONLY valid JSON, no prose\n\n"
    "You also determine whether the assistant can help with each OPEN task.\n"
    "Available assistant skills:\n"
    "- DRAFT_EMAIL: task involves sending an email, follow-up, or written communication\n"
    "- PRESENTATION: task involves creating a deck, slides, or visual deliverable\n"
    "- STAKEHOLDER_MAP: task involves identifying or mapping contacts and relationships\n"
    "- MEETING_PREP: task involves preparing for an upcoming meeting or call\n"
    "- NONE: assistant cannot help with this task"
)

RESOLUTION_USER_PROMPT = (
    '={{ "Review these open CRM tasks for " + $json.accountName + ":\\n\\n" '
    '+ $json.taskList + "\\n\\nUse People.ai SalesAI tools (ask_sales_ai_about_account) '
    'to check recent activity, emails, and meeting outcomes for " + $json.accountName '
    '+ ".\\n\\nFor each task, determine if it was completed based on evidence from recent '
    'activity. Also determine if the assistant can help with each OPEN task.\\n\\nOutput JSON:'
    '\\n{\\n  \\"account_name\\": \\"" + $json.accountName + "\\",\\n  \\"results\\": '
    '[\\n    {\\"id\\": \\"SF_TASK_ID\\", \\"status\\": \\"COMPLETE\\" or \\"OPEN\\", '
    '\\"evidence\\": \\"one-line reason\\", \\"assist_skill\\": '
    '\\"DRAFT_EMAIL|PRESENTATION|STAKEHOLDER_MAP|MEETING_PREP|NONE\\"}\\n  ]\\n}" }}'
)


def update_resolution_agent_prompt():
    """Add assist_skill classification to the Resolution Agent prompt."""

    def modifier(nodes, connections):
        node = find_node(nodes, "Resolution Agent")
        if not node:
            print("  ERROR: 'Resolution Agent' not found")
            return 0

        system_prompt = node["parameters"].get("options", {}).get("systemMessage", "")
        if "assist_skill" in system_prompt:
            print("  Resolution Agent already has assist_skill — skipping")
            return 0

        node["parameters"]["options"]["systemMessage"] = RESOLUTION_SYSTEM_PROMPT
        node["parameters"]["text"] = RESOLUTION_USER_PROMPT
        print("  [1/1] Updated Resolution Agent with assist_skill prompt")
        return 1

    return modify_workflow(WF_TASK_RESOLUTION, "Task Resolution Handler.json", modifier)


# ── Task 5: Downstream nodes — parse, collect, build, format ────────────

PARSE_RESOLUTION_JS = r"""// Parse resolution results with assistable task detection
const SKILL_ID_MAP = {
  'DRAFT_EMAIL': 'draft_email',
  'PRESENTATION': 'presentation',
  'STAKEHOLDER_MAP': 'stakeholder_map',
  'MEETING_PREP': 'meeting_prep',
};

const agentOutput = $input.first().json.output || $input.first().json.text || '';
const accountName = $('Group by Account').first().json.accountName || '';

// Extract JSON from agent output
let parsed;
try {
  const jsonMatch = agentOutput.match(/\{[\s\S]*\}/);
  parsed = jsonMatch ? JSON.parse(jsonMatch[0]) : { results: [] };
} catch (e) {
  parsed = { results: [] };
}

const results = parsed.results || [];
const completedTasks = [];
const openTasks = [];
const assistableTasks = [];

for (const r of results) {
  if (r.status === 'COMPLETE') {
    completedTasks.push({
      id: r.id,
      evidence: r.evidence || '',
      accountName,
    });
  } else {
    openTasks.push({
      id: r.id,
      evidence: r.evidence || '',
      accountName,
    });
    // Check for assistable skill
    const skillId = SKILL_ID_MAP[r.assist_skill];
    if (skillId) {
      assistableTasks.push({
        id: r.id,
        subject: r.subject || r.id,
        accountName,
        assistSkill: skillId,
      });
    }
  }
}

return [{
  json: {
    accountName,
    completedTasks,
    openTasks,
    assistableTasks,
    completedCount: completedTasks.length,
    openCount: openTasks.length,
    assistableCount: assistableTasks.length,
  }
}];"""

COLLECT_ALL_RESULTS_JS = r"""// Collect results from all loop iterations
const items = $input.all();
let completedDetails = [];
let assistableDetails = [];
let totalCompleted = 0;
let totalOpen = 0;

for (const item of items) {
  const d = item.json;
  if (d.completedTasks) {
    completedDetails = completedDetails.concat(d.completedTasks);
  }
  if (d.assistableTasks) {
    assistableDetails = assistableDetails.concat(d.assistableTasks);
  }
  totalCompleted += (d.completedCount || 0);
  totalOpen += (d.openCount || 0);
}

return [{
  json: {
    completedDetails,
    assistableDetails,
    totalCompleted,
    totalOpen,
    completedCount: completedDetails.length,
    assistableCount: assistableDetails.length,
  }
}];"""

BUILD_SUMMARY_JS = r"""// Build summary text with assist suggestions
const data = $input.first().json;
const completedDetails = data.completedDetails || [];
const assistableDetails = data.assistableDetails || [];
const completedCount = data.completedCount || 0;
const totalOpen = data.totalOpen || 0;

let summaryLines = [];

if (completedCount > 0) {
  summaryLines.push(`:white_check_mark: *${completedCount} task${completedCount === 1 ? '' : 's'} auto-resolved*`);
  for (const t of completedDetails) {
    summaryLines.push(`• ${t.accountName}: ${t.evidence}`);
  }
}

if (assistableDetails.length > 0) {
  summaryLines.push('');
  summaryLines.push(`:robot_face: *I can help with ${assistableDetails.length} open task${assistableDetails.length === 1 ? '' : 's'}:*`);
  for (const t of assistableDetails) {
    summaryLines.push(`• ${t.accountName}: ${t.subject}`);
  }
}

const summaryText = summaryLines.join('\n');
const shouldPost = completedCount > 0;

return [{
  json: {
    summaryText,
    shouldPost,
    completedCount,
    totalOpen,
    completedDetails,
    assistableDetails,
  }
}];"""

FORMAT_SUMMARY_DM_JS = r"""// Format summary DM with assist buttons
const SKILL_BUTTON_MAP = {
  'draft_email': { text: ':email: Draft Email', actionId: 'task_assist_draft_email' },
  'presentation': { text: ':bar_chart: Create Deck', actionId: 'task_assist_presentation' },
  'stakeholder_map': { text: ':busts_in_silhouette: Stakeholder Map', actionId: 'task_assist_stakeholders' },
  'meeting_prep': { text: ':clipboard: Meeting Prep', actionId: 'task_assist_meeting_prep' },
};

const data = $input.first().json;
const summaryText = data.summaryText || '';
const assistableDetails = data.assistableDetails || [];

const blocks = [];

// Summary text section
blocks.push({
  type: "section",
  text: { type: "mrkdwn", text: summaryText }
});

// Assist buttons for assistable tasks (max 3 tasks, each gets skill + complete button)
const tasksToShow = assistableDetails.slice(0, 3);
if (tasksToShow.length > 0) {
  const elements = [];
  for (const t of tasksToShow) {
    const skillBtn = SKILL_BUTTON_MAP[t.assistSkill];
    if (skillBtn) {
      elements.push({
        type: "button",
        text: { type: "plain_text", text: skillBtn.text, emoji: true },
        action_id: `${skillBtn.actionId}_${t.id}`,
        value: JSON.stringify({
          action: 'task_assist',
          skill: t.assistSkill,
          task_subject: t.subject,
          account_name: t.accountName,
          task_id: t.id,
        }),
      });
      elements.push({
        type: "button",
        text: { type: "plain_text", text: ':white_check_mark: Complete', emoji: true },
        action_id: `task_complete_${t.id}`,
        value: JSON.stringify({
          task_id: t.id,
          task_subject: t.subject,
          account_name: t.accountName,
        }),
        style: "primary",
      });
    }
  }
  if (elements.length > 0) {
    blocks.push({ type: "actions", elements });
  }
}

// "All Tasks Today" link button at the bottom
blocks.push({
  type: "actions",
  elements: [
    {
      type: "button",
      text: { type: "plain_text", text: "All Tasks Today", emoji: true },
      action_id: "link_all_tasks",
      url: "https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5"
    }
  ]
});

return [{
  json: {
    blocks: JSON.stringify(blocks),
    summaryText,
  }
}];"""


def update_resolution_downstream_nodes():
    """Add assistable task tracking to Parse, Collect, Build, and Format nodes."""

    def modifier(nodes, connections):
        changes = 0

        # Node 1: Parse Resolution Results
        node = find_node(nodes, "Parse Resolution Results")
        if not node:
            print("  ERROR: 'Parse Resolution Results' not found")
        else:
            current = node["parameters"].get("jsCode", "")
            if "assistableTasks" in current:
                print("  Parse Resolution Results already has assistableTasks — skipping")
            else:
                node["parameters"]["jsCode"] = PARSE_RESOLUTION_JS
                print("  [1/4] Updated Parse Resolution Results")
                changes += 1

        # Node 2: Collect All Results
        node = find_node(nodes, "Collect All Results")
        if not node:
            print("  ERROR: 'Collect All Results' not found")
        else:
            current = node["parameters"].get("jsCode", "")
            if "assistableDetails" in current:
                print("  Collect All Results already has assistableDetails — skipping")
            else:
                node["parameters"]["jsCode"] = COLLECT_ALL_RESULTS_JS
                print("  [2/4] Updated Collect All Results")
                changes += 1

        # Node 3: Build Summary
        node = find_node(nodes, "Build Summary")
        if not node:
            print("  ERROR: 'Build Summary' not found")
        else:
            current = node["parameters"].get("jsCode", "")
            if "assistableDetails" in current:
                print("  Build Summary already has assistableDetails — skipping")
            else:
                node["parameters"]["jsCode"] = BUILD_SUMMARY_JS
                print("  [3/4] Updated Build Summary")
                changes += 1

        # Node 4: Format Summary DM
        node = find_node(nodes, "Format Summary DM")
        if not node:
            print("  ERROR: 'Format Summary DM' not found")
        else:
            current = node["parameters"].get("jsCode", "")
            if "task_assist_" in current:
                print("  Format Summary DM already has task_assist_ buttons — skipping")
            else:
                node["parameters"]["jsCode"] = FORMAT_SUMMARY_DM_JS
                print("  [4/4] Updated Format Summary DM")
                changes += 1

        return changes

    return modify_workflow(WF_TASK_RESOLUTION, "Task Resolution Handler.json", modifier)


# ── Task 6: Route task_assist buttons in Interactive Events Handler ────

BRIDGE_TASK_ASSIST_JS = r"""const payload = $('Parse Interactive Payload').first().json;
let context = {};
try { context = JSON.parse(payload.actionValue || '{}'); } catch(e) {}

const skill = context.skill || '';
const accountName = context.account_name || '';
const accountId = context.account_id || '';
const taskSubject = context.task_subject || '';

// Reformat to match what Bridge Recap to Draft expects
const enrichedValue = JSON.stringify({
  accountName,
  accountId,
  activityUid: '',
  meetingSubject: '',
  participants: '',
  userId: context.user_id || '',
  dbUserId: context.user_id || '',
  slackUserId: context.slack_user_id || '',
  organizationId: context.organization_id || '',
  assistantName: context.assistant_name || 'Aria',
  assistantEmoji: context.assistant_emoji || ':robot_face:',
  repName: context.rep_name || '',
  recapContext: 'Task: ' + taskSubject,
});

return [{ json: {
  ...payload,
  actionValue: enrichedValue,
  actionId: 'followup_draft',
  routeSkill: skill,
}}];"""

TASK_ASSIST_ACTION_IDS = [
    "task_assist_draft_email",
    "task_assist_presentation",
    "task_assist_stakeholders",
    "task_assist_meeting_prep",
]

SWITCH_LEFT_EXPR = "={{ $('Parse Interactive Payload').first().json.actionId }}"


def add_task_assist_routing():
    """Add routing for task_assist_* button actions in Interactive Events Handler."""

    def modifier(nodes, connections):
        # Idempotency: check if Bridge Task Assist already exists
        if find_node(nodes, "Bridge Task Assist"):
            print("  Bridge Task Assist node already exists — skipping")
            return 0

        route_action = find_node(nodes, "Route Action")
        if not route_action:
            print("  ERROR: 'Route Action' not found")
            return 0

        changes = 0

        # Step 1: Add Bridge Task Assist Code node
        ra_pos = route_action["position"]
        bridge_pos = [ra_pos[0] + 400, ra_pos[1] + 600]
        bridge_node = make_code_node("Bridge Task Assist", BRIDGE_TASK_ASSIST_JS, bridge_pos)
        nodes.append(bridge_node)
        print("  [1/4] Added Bridge Task Assist Code node")
        changes += 1

        # Step 2: Add Switch conditions for the 4 action IDs
        rules = route_action["parameters"]["rules"]["values"]

        # Check which action IDs already exist
        existing_action_ids = set()
        for rule in rules:
            conds = rule.get("conditions", {}).get("conditions", [])
            for c in conds:
                rv = c.get("rightValue", "")
                if rv in TASK_ASSIST_ACTION_IDS:
                    existing_action_ids.add(rv)

        new_rule_indices = []
        for action_id in TASK_ASSIST_ACTION_IDS:
            if action_id in existing_action_ids:
                print(f"  Rule for '{action_id}' already exists — skipping")
                continue

            rule_index = len(rules)
            output_key = f"output_{rule_index}"
            rule = make_switch_rule(output_key, SWITCH_LEFT_EXPR, action_id)
            rules.append(rule)
            new_rule_indices.append(rule_index)
            print(f"  [2/4] Added Switch rule for '{action_id}' at index {rule_index}")
            changes += 1

        # Step 3: Wire Switch outputs to Bridge Task Assist
        if "Route Action" not in connections:
            connections["Route Action"] = {"main": []}
        main_outputs = connections["Route Action"]["main"]

        for rule_index in new_rule_indices:
            # Output index is rule_index + 1 (output 0 is the default/fallback)
            output_index = rule_index + 1

            # Pad the main array if needed
            while len(main_outputs) <= output_index:
                main_outputs.append([])

            main_outputs[output_index] = [
                {"node": "Bridge Task Assist", "type": "main", "index": 0}
            ]
        if new_rule_indices:
            print(f"  [3/4] Wired {len(new_rule_indices)} Switch outputs to Bridge Task Assist")
            changes += 1

        # Step 4: Wire Bridge Task Assist -> Bridge Recap to Draft
        connections["Bridge Task Assist"] = {
            "main": [[{"node": "Bridge Recap to Draft", "type": "main", "index": 0}]]
        }
        print("  [4/4] Wired Bridge Task Assist -> Bridge Recap to Draft")
        changes += 1

        return changes

    return modify_workflow(
        WF_INTERACTIVE_HANDLER, "Interactive Events Handler.json", modifier
    )


def main():
    print("=== Task Assist Flywheel Deployment ===\n")

    print("\n--- Entry Point 1: Recap Cards ---\n")
    add_assist_to_recap_card()
    add_assist_to_recap_card_od()

    print("\n--- Entry Point 2: Resolution Handler ---\n")
    update_resolution_agent_prompt()
    update_resolution_downstream_nodes()

    print("\n--- Button Routing ---\n")
    add_task_assist_routing()

    print("\n=== Done! ===")
    print("Recap cards: keyword matching + assist buttons")
    print("Resolution handler: LLM classification + assist section in DM")
    print("Interactive handler: task_assist_* routing -> existing skill flows")


if __name__ == "__main__":
    main()
