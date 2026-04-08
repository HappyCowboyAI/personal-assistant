# Task Assist Flywheel — Design Spec

**Date:** 2026-04-03
**Status:** Draft

## Problem

The assistant creates tasks from meeting recaps, but those tasks sit in Salesforce as inert to-do items. The assistant already has skills that could handle many of these tasks (drafting emails, building presentations, mapping stakeholders, prepping for meetings) — but today the task system and the skill system are completely disconnected.

## Solution

A Task Assist Flywheel that matches open tasks to assistant skills and surfaces one-click suggestions to the rep. Closes the loop: **create → match → suggest → act → resolve**.

Two entry points:
1. **At recap time** — keyword matching on freshly created tasks, suggestions inline on the recap card
2. **At resolution time** — LLM classification on open tasks (piggybacks on the existing resolution agent), suggestions appended to the resolution summary DM

The assistant suggests and surfaces — it does not act unilaterally. The rep clicks a button to trigger the skill. The Task Resolution Engine detects the completed work on its next scheduled run.

## Skill Registry

A constant array shared across Code nodes. Each entry defines a matchable skill:

```javascript
const SKILL_REGISTRY = [
  {
    id: 'draft_email',
    label: 'Draft Email',
    keywords: ['send email', 'follow up', 'follow-up', 'email', 'reach out',
               'share with', 'send to', 'write to', 'notify',
               'update via email', 'loop in'],
    buttonText: ':email: Draft Email',
    actionId: 'task_assist_draft_email',
    description: 'Draft and send an email or follow-up communication',
  },
  {
    id: 'presentation',
    label: 'Create Presentation',
    keywords: ['create deck', 'build slides', 'presentation', 'qbr',
               'prepare deck', 'slide deck', 'google slides'],
    buttonText: ':bar_chart: Create Deck',
    actionId: 'task_assist_presentation',
    description: 'Generate a branded Google Slides presentation',
  },
  {
    id: 'stakeholder_map',
    label: 'Stakeholder Map',
    keywords: ['map contacts', 'stakeholder', 'decision maker',
               'identify contacts', 'org chart', 'key contacts', 'champion'],
    buttonText: ':busts_in_silhouette: Stakeholder Map',
    actionId: 'task_assist_stakeholders',
    description: 'Map key contacts, roles, and engagement at an account',
  },
  {
    id: 'meeting_prep',
    label: 'Meeting Prep',
    keywords: ['prepare for meeting', 'prep for call', 'research before',
               'meeting brief', 'pre-meeting', 'talking points'],
    buttonText: ':clipboard: Meeting Prep',
    actionId: 'task_assist_meeting_prep',
    description: 'Generate a pre-meeting brief with participants, context, and talking points',
  },
];
```

Adding a new skill = adding one object to this array + handling its `actionId` in the Interactive Events Handler.

## Keyword Matcher

A pure function that runs in Code nodes. No LLM, no API calls. Takes a task subject + description and returns the best matching skill or null.

```javascript
function matchTaskToSkill(taskSubject, taskDescription) {
  const text = (taskSubject + ' ' + taskDescription).toLowerCase();
  for (const skill of SKILL_REGISTRY) {
    for (const kw of skill.keywords) {
      if (text.includes(kw)) {
        return skill;
      }
    }
  }
  return null;
}
```

Priority is implicit — skills checked in registry order. First match wins. Email-related keywords are first since they represent the most common recap task type.

## Entry Point 1: Recap Card (at task creation)

When the recap creates tasks, the Build Recap Card node runs the keyword matcher against each freshly created task.

### Modified nodes

**Build Recap Card** (Follow-up Cron) and **Recap Build Card OD** (Events Handler):

Add the SKILL_REGISTRY constant and keyword matcher function, then after building the task count confirmation line:

```javascript
// Match tasks to assistant skills
const assistable = [];
for (const t of (recap.tasks || [])) {
  const skill = matchTaskToSkill(t.description, '');
  if (skill) {
    assistable.push({ task: t, skill });
  }
}
```

If `assistable.length > 0`, append a section to the blocks:

```javascript
if (assistable.length > 0) {
  const lines = assistable.map(a =>
    `• ${a.task.description}${a.task.owner ? ' — ' + a.task.owner : ''}`
  ).join('\n');

  blocks.push({
    type: "section",
    text: { type: "mrkdwn",
      text: `:robot_face: I can help with ${assistable.length} of these:\n${lines}` }
  });

  // One button per assistable task
  const elements = assistable.slice(0, 5).map(a => ({
    type: "button",
    text: { type: "plain_text", text: a.skill.buttonText, emoji: true },
    action_id: a.skill.actionId,
    value: JSON.stringify({
      action: 'task_assist',
      skill: a.skill.id,
      task_subject: a.task.description,
      account_name: m.accountName,
      account_id: m.accountId || '',
      user_id: data.userId,
      slack_user_id: data.slackUserId,
      assistant_name: assistantName,
      assistant_emoji: assistantEmoji,
      rep_name: data.repName,
    })
  }));

  blocks.push({ type: "actions", elements });
}
```

### Slack output

```
📋 Google · Thu, 8:30 AM — People.ai  AI Agent Onboarding
✅ I saved this recap to CRM and created 3 tasks. Check the thread for details!

🤖 I can help with 1 of these:
• Draft follow-up email to Keith Jones — Keith Jones

[:email: Draft Email]

[Draft Follow-up]  [My Events Today]  [All Tasks Today]
```

The assist section only appears when at least one task matches. Capped at 5 buttons (Slack Block Kit limit per actions block).

**Note:** At recap time, tasks may not have Salesforce IDs yet (Workato creates them async). The button payload uses `task_subject` + `account_name` as the identifier instead of `task_id`. The skill flow doesn't need the SF Task ID — it just needs enough context to do the work. The Task Resolution Engine handles the SF side later.

**Complete button at recap time:** Because SF Task IDs aren't available yet at recap time (async Workato creation), the Complete button cannot be shown on the recap card assist section. It only appears on the resolution summary DM (Entry Point 2), where tasks already have SF IDs.

## Entry Point 2: Resolution Summary DM (scheduled run)

The Task Resolution Agent already evaluates each task for completion. We extend it to also classify assist-ability.

### Resolution Agent prompt extension

Added to the system prompt:

```
You also determine whether the assistant can help with each OPEN task.
Available assistant skills:
- DRAFT_EMAIL: task involves sending an email, follow-up, or written communication
- PRESENTATION: task involves creating a deck, slides, or visual deliverable
- STAKEHOLDER_MAP: task involves identifying or mapping contacts and relationships
- MEETING_PREP: task involves preparing for an upcoming meeting or call
- NONE: assistant cannot help with this task
```

Output schema extends to:

```json
{
  "id": "SF_TASK_ID",
  "status": "COMPLETE|OPEN",
  "evidence": "one-line reason",
  "assist_skill": "DRAFT_EMAIL|PRESENTATION|STAKEHOLDER_MAP|MEETING_PREP|NONE"
}
```

### Modified nodes in Task Resolution Handler

**Parse Resolution Results** — extract `assist_skill` from agent output, build an `assistableTasks` array alongside `completedTasks` and `openTasks`:

```javascript
const assistableTasks = [];
for (const t of tasks) {
  const r = results.find(r => r.id === t.Id);
  if (r && r.status !== 'COMPLETE' && r.assist_skill && r.assist_skill !== 'NONE') {
    assistableTasks.push({
      id: t.Id,
      subject: t.Subject,
      accountName: t.Account_Name || accountName,
      assistSkill: r.assist_skill,
    });
  }
}
```

**Collect All Results** — aggregate `assistableTasks` across all accounts.

**Build Summary** — append assist section to summary text when assistable tasks exist. The summary DM still only posts when `completedCount > 0` (per the "less noise" decision). Assist suggestions are a bonus, not a trigger.

### Slack output

```
📋 Task Update
✅ ~Send pricing proposal to TransUnion~ (email sent yesterday)
✅ ~Review contract with Flexera~ (discussed in today's meeting)

🤖 I can help with 2 open tasks:
• Draft follow-up email to Keith Jones (OpenAI) — [:email: Draft Email] [✅ Complete]
• Build QBR deck for Manhattan Associates — [:bar_chart: Create Deck] [✅ Complete]

Marked 2 tasks complete · 3 still open

[All Tasks Today]
```

### Skill ID mapping

The agent outputs uppercase IDs (`DRAFT_EMAIL`). Map to registry:

```javascript
const SKILL_ID_MAP = {
  'DRAFT_EMAIL': 'draft_email',
  'PRESENTATION': 'presentation',
  'STAKEHOLDER_MAP': 'stakeholder_map',
  'MEETING_PREP': 'meeting_prep',
};
```

## Button Action Handling

When a rep clicks a skill button, the Interactive Events Handler routes it to the existing skill flow.

### Button payload

```json
{
  "action": "task_assist",
  "skill": "draft_email",
  "task_id": "00T...",
  "task_subject": "Send follow-up email to Keith Jones",
  "account_name": "OpenAI",
  "account_id": "001...",
  "user_id": "uuid",
  "slack_user_id": "U061...",
  "assistant_name": "ScottAI",
  "assistant_emoji": ":rocket:",
  "rep_name": "Scott Metcalf"
}
```

### Routing

| actionId | Routes to | What happens |
|---|---|---|
| `task_assist_draft_email` | Existing `draft_followup` agent path | Agent researches account via MCP, drafts email, posts in thread |
| `task_assist_presentation` | Existing `presentation` sub-workflow | Fires Backstory Presentation with topic from task subject |
| `task_assist_stakeholders` | Existing `stakeholders` flow | Runs stakeholder agent for the account |
| `task_assist_meeting_prep` | Existing `meeting_brief` sub-workflow | Fires Meeting Brief for the account's next meeting |

The Interactive Events Handler already has a Switch node for action routing. Add 4 new outputs for the `task_assist_*` action IDs, each wiring to the existing skill's entry point with context from the button payload.

### Post-action behavior

After the skill completes:
- The assistant posts its output (email draft, presentation link, stakeholder map, brief) in a thread under the original message
- The assistant does **not** auto-mark the task complete
- The rep can click the ✅ Complete button on the resolution DM to mark the task done immediately (uses existing `task_complete` → Workato `update_task` flow)
- Alternatively, the Task Resolution Engine detects completion on its next 9am/4pm run if evidence is found (email sent, deck shared, etc.)

Three paths to completion: manual Complete button, resolution engine auto-detection, or the rep marks it done via the `tasks` command.

## Modified Components Summary

| Component | Change type |
|---|---|
| Build Recap Card (Follow-up Cron) | Modified — add SKILL_REGISTRY, keyword matcher, assist section |
| Recap Build Card OD (Events Handler) | Modified — same as above |
| Resolution Agent prompt (Task Resolution Handler) | Modified — add assist_skill classification |
| Parse Resolution Results (Task Resolution Handler) | Modified — extract assist_skill |
| Collect All Results (Task Resolution Handler) | Modified — aggregate assistable tasks |
| Build Summary (Task Resolution Handler) | Modified — append assist section to DM |
| Format Summary DM (Task Resolution Handler) | Modified — add assist buttons |
| Interactive Events Handler Switch | Modified — add 4 task_assist_* routes |

No new workflows. No new Workato actions. No new Supabase tables.

## Extensibility

Adding a new skill:
1. Add an entry to `SKILL_REGISTRY` (keywords, button text, action ID)
2. Add the skill ID to the resolution agent prompt's "Available skills" list
3. Add the action ID routing in the Interactive Events Handler Switch
4. Wire to the existing (or new) skill flow

## Not In Scope

- Auto-executing tasks without user approval (future — Phase 2)
- Prioritizing which task to suggest first when multiple match
- Learning from user behavior (which suggestions get clicked vs ignored)
- Suggesting skills for tasks not owned by the current user
- Task-to-task dependencies ("do X before Y")
