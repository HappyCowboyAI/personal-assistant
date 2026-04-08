# Auto-Save Meeting Recap & Tasks — Design Spec

**Date:** 2026-04-02
**Status:** Draft

## Problem

The meeting recap flow generates high-quality AI recaps and tasks, but requires reps to click "Review & Log" and "Tasks" buttons to save to CRM. Adoption is near zero — the human-in-the-loop step blocks the entire flywheel (tasks exist → morning digest shows them → silence checks reference them → system becomes self-reinforcing).

## Solution

Remove the human gate. Auto-save recaps and tasks to CRM immediately when the AI generates them. Reps can review and edit after the fact via PeopleGlass.

## New Flow

```
Meeting ends
  → Follow-up Cron detects ended meeting
  → Recap Agent generates summary + tasks
  → Auto-Save to CRM (Workato webhook: log_activity)
  → Auto-Create Tasks (Workato webhook: create_task × N)
  → Post simplified Slack card confirming what was saved
  → Rep reviews/edits in PeopleGlass if needed
```

**Old flow:** AI generates → Slack card with buttons → Rep clicks → Modal → Edit → Save to CRM
**New flow:** AI generates → Save to CRM immediately → Slack card confirms + PeopleGlass links

## Slack Card Format

The recap card changes from action-prompting to confirmation:

```
:clipboard: TRUCE Software · Tue, Apr 2 11:00 AM
:white_check_mark: I saved this recap to CRM and created 3 tasks:

• Follow up on API integration — Scott Metcalf · by Apr 9
• Schedule April check-in call — Max Morris · by Apr 14
• Revisit license expansion — Max Morris · by Jul 29

[Draft Follow-up]    [My Events Today]    [All Tasks Today]
```

The assistant speaks in first person ("I saved", "I created") consistent with its personality. The message comes from the rep's named assistant (e.g., Pikachu) with their chosen emoji.

### Buttons

| Button | Type | Action |
|--------|------|--------|
| Draft Follow-up | action button | Existing `recap_draft_followup` — fires re-engagement agent (unchanged) |
| My Events Today | link button | `https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61` |
| All Tasks Today | link button | `https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5` |

### Thread Reply

Simplified — no more individual "Create Task" buttons. Shows the full recap text for reference, plus the task list as confirmation.

## Workato Recipe Changes

### `log_activity` action

1. SOQL finds the Event by Subject + Account name (no change)
2. **Category protection:** If Event.Category is null → set to AI-suggested category. If already set → leave it.
3. **Description prepend:** New Description = AI Recap + `"\n\n---\n\n"` + Existing Description. If Description is blank, just set AI Recap.
4. n8n payload adds `"prepend_description": true` flag for backward compatibility.

### `create_task` action

No change — new records, always set all fields including Task.Category.

## Follow-up Cron Changes (ID: JhDuCvZdFN4PFTOW)

### New nodes (after Parse Recap Output):

**Auto-Save to CRM** — HTTP Request node fires Workato webhook:
- URL: `https://webhooks.workato.com/webhooks/rest/cfff4d3a-6f27-4ba4-9754-ac22c759ecaa/assistant_sf_write`
- Payload: `{ action: "log_activity", account_name, subject, description (AI recap), category, prepend_description: true }`
- Uses the same fields the modal currently sends, but from the AI output directly (no human edit)

**Auto-Create Tasks** — Loop through AI-extracted tasks, fire Workato webhook for each:
- Payload: `{ action: "create_task", account_name, subject, description, assignee_email, duration, category, due_date }`
- Same payload format as the current task creation modal

### Modified nodes:

**Build Recap Card** — New button layout:
- Remove `recap_save_activity` button
- Remove `recap_view_tasks` button
- Keep `recap_draft_followup` button
- Add `My Events Today` link button (PeopleGlass)
- Add `All Tasks Today` link button (PeopleGlass)
- Add task list in the card body (compact, one line per task)
- Header changes from action prompt to assistant voice confirmation: `:white_check_mark: I saved this recap to CRM and created N tasks:`
- All copy uses first person ("I saved", "I created") to match the assistant's personality

**Build Recap Thread** — Simplified:
- Remove individual `recap_create_task_N` buttons
- Keep the full recap text for reference
- Add task list as read-only confirmation

## Interactive Events Handler Changes (ID: JgVjCqoT6ZwGuDL1)

### No changes

Leave all existing modal flows in place (recap_save_activity, recap_view_tasks, recap_create_task). They become dormant — no buttons trigger them. Keeps the option to revert if needed.

## PeopleGlass Links

| View | URL | Shows |
|------|-----|-------|
| My Events Today | `https://glass.people.ai/sheet/294e924a-d11a-46b7-a373-aae4182c4a61` | User's events modified today — for reviewing/editing the recap |
| All Tasks Today | `https://glass.people.ai/sheet/0250d214-84ba-48e4-b272-6839c03462f5` | All tasks modified today — includes tasks assigned to others |

Note: PeopleGlass "My Tasks" view shows tasks assigned to the viewing user by default. Tasks assigned to other reps (CSM, SE) require filtering by account in PeopleGlass.

## CRM Field Protection

| Object | Field | Who | Behavior |
|--------|-------|-----|----------|
| Event | Meeting Category | Sales/AE | Only set if currently blank |
| Event | CS Category | CSM | Only set if currently blank |
| Event | Description | All | Prepend AI recap to existing content (never overwrite) |
| Task | Category | All | Always set (new record) |
| Task | All fields | All | Always set (new record) |

### CS Category Valid Values

None, 1x1 Training, Admin Training, Adoption Program, Business Reviews, CE Enablement Planning, CE Workshop Training, CSM Enablement Planning, CSM Group Training, Customer Kickoff, Office Hours, Other, PeopleGlass, Procurement Process, Success Plan, Technical Support, In-Person Meetings, EBR (Executive Business Review), Demo, RKO/SKO

## What's Not Changing

- Recap Agent prompt and output format — unchanged
- Draft Follow-up button and flow — unchanged
- Interactive Events Handler modal flows — left dormant (not removed)
- Workato webhook URL — unchanged
- Task intelligence (smart assignee, duration, category) — unchanged
- Follow-up Cron schedule (9am + 4pm PT) — unchanged

## Not In Scope

- PeopleGlass deep linking to specific events/tasks (not supported)
- User opt-in/opt-out for auto-save (all users get auto-save)
- Editing recaps or tasks from within Slack (use PeopleGlass)
- Removing dormant modal flows from Interactive Events Handler
