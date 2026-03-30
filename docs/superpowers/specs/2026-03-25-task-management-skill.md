# Task Management Skill — `tasks <account>`

## Overview

On-demand Slack skill that surfaces Salesforce Tasks for a given account with the ability to mark tasks complete directly from Slack. Closes the loop on the Meeting Recap + Action Hub — users create tasks from recaps, now they can track and complete them without leaving Slack.

## User Experience

```
User: tasks aidoc

📋 Aidoc — Open Tasks (4)

• Schedule training session with Nick — Rachel (CSM) · Due Mar 28
  [Complete ✓]

• Finalize security review docs — Ronen · Due Apr 1
  [Complete ✓]

• Prepare expansion proposal — Susan (AE) · Due Apr 3
  [Complete ✓]

• Configure Slackbot integration — Iris · Due Apr 5
  [Complete ✓]

✅ Recently Completed (2)
• Conducted technical demo — Rachel · Completed Mar 18
• Delivered performance cheat sheet — Rachel · Completed Mar 20

View all tasks in PeopleGlass
```

### Interactions
- **`tasks <account>`** — shows open + recently completed tasks for that account
- **`tasks`** (no account) — shows the user's own open tasks across all accounts
- **Complete button** — marks the task as Completed in Salesforce, updates the Slack message to show it as done

## Architecture

### Read Path (new)
```
n8n → Workato "read" webhook → SOQL query → Workato POSTs results to n8n callback → Slack message
```

### Write-back Path (reuses existing)
```
Slack "Complete" button → n8n Interactive Handler → Workato "write" webhook → SF Task update
```

## Implementation

### Component 1: Workato Read Recipe

**New recipe:** "People.ai Assistant — Read from Salesforce"

**Trigger:** Webhook (`assistant_sf_read`)

**Payload schema:**
```json
{
  "action": "get_tasks",
  "account_name": "Aidoc",
  "user_email": "scott.metcalf@people.ai",
  "callback_url": "https://scottai.trackslife.com/webhook/sf-read-callback",
  "request_id": "uuid"
}
```

**Steps:**
1. Webhook trigger
2. IF action equals `get_tasks`
3. Search Accounts by name (limit 1) → get Account ID
4. SOQL query for open tasks:
   ```sql
   SELECT Id, Subject, Description, Status, Priority, ActivityDate,
          Owner.Name, Owner.Email, Category__c, CallDurationInMinutes
   FROM Task
   WHERE WhatId = '{AccountId}'
   AND (Status != 'Completed' OR (Status = 'Completed' AND LastModifiedDate >= LAST_N_DAYS:14))
   ORDER BY Status ASC, ActivityDate ASC
   ```
5. HTTP POST results back to `callback_url` with `request_id`

**Callback payload:**
```json
{
  "request_id": "uuid",
  "account_name": "Aidoc",
  "account_id": "001Ri...",
  "tasks": [
    {
      "id": "00TRi...",
      "subject": "Schedule training session",
      "status": "Not Started",
      "priority": "Normal",
      "due_date": "2026-03-28",
      "owner_name": "Rachel Jennings-Keane",
      "owner_email": "rachel.jenningskeane@people.ai",
      "category": "Training & Enablement",
      "duration_minutes": 60
    }
  ]
}
```

### Component 2: n8n Callback Webhook

**New webhook endpoint:** `POST /webhook/sf-read-callback`

Could be a standalone workflow or a sub-workflow. Receives Workato's response, matches to the original request via `request_id`, and posts the Slack message.

**Design consideration:** The callback is async — between the user typing `tasks aidoc` and the Slack message appearing, there's a delay (Workato processing + SF query). Send a "Looking up tasks for Aidoc..." thinking message first, then update it when the callback arrives.

**State tracking:** Store `request_id → { channel_id, message_ts, user_id, assistant_name, assistant_emoji }` temporarily so the callback knows where to post. Options:
- Supabase `pending_actions` table (already exists)
- n8n static data
- In-memory (if the callback arrives within seconds)

### Component 3: Slack Events Handler — `tasks` Command

**Route:** `cmd_tasks` in Route by State

**Matching:**
- `tasks` / `tasks <account>` — exact prefix
- `my tasks` — alias for no-account variant
- Fuzzy: `/\btasks?\b/` in text

**Flow:**
1. Parse account name (or default to user's own tasks)
2. Send "Looking up tasks..." thinking message
3. POST to Workato read webhook with callback URL + request_id
4. Store request context in Supabase pending_actions
5. (Wait for callback — handled by Component 2)

### Component 4: Task List Message Builder

**Slack Block Kit structure:**
```
Header: 📋 {Account} — Open Tasks ({count})

[For each open task:]
Section: • {Subject} — {Owner} ({Role}) · Due {Date}
  Accessory: [Complete ✓] button

Divider

Section: ✅ Recently Completed ({count})
[For each completed task (last 14 days):]
Context: • {Subject} — {Owner} · Completed {Date}

Context: "View all tasks in PeopleGlass" (linked)
```

**"Complete" button payload:**
```json
{
  "action": "complete_task",
  "task_id": "00TRi...",
  "task_subject": "Schedule training session",
  "account_name": "Aidoc"
}
```

### Component 5: Complete Button Handler

**Interactive Events Handler additions:**

1. New Route Action output: `task_complete`
2. `Build Complete Payload` Code node — constructs Workato webhook payload:
   ```json
   {
     "action": "update_task",
     "salesforce_object": "Task",
     "task_id": "00TRi...",
     "fields": { "Status": "Completed" }
   }
   ```
3. Send to existing Workato write webhook
4. Update the Slack message — move the completed task from "Open" to "Completed" section, remove the Complete button
5. Thread reply: "✅ Marked complete: {task subject}"

### Component 6: Workato Write Recipe Update

Add `update_task` action to the existing "People.ai Assistant — Save to Salesforce" recipe:

1. New IF branch: `action equals update_task`
2. Update Task in Salesforce by `task_id`
3. Map `fields.Status` → Status field

## Variants

### `tasks` (no account)
- Query SF for the user's own open tasks: `WHERE OwnerId = '{UserSFId}'`
- Requires looking up the user's SF ID from their email
- Shows tasks grouped by account

### `tasks <account>`
- Query SF for all tasks on that account: `WHERE WhatId = '{AccountId}'`
- Shows tasks for all assignees

## Dependencies

- Workato read recipe (new)
- n8n callback webhook (new)
- Supabase pending_actions table (existing, reuse for request tracking)
- Existing Workato write recipe (add update_task branch)

## PeopleGlass Integration

- Link to user's task sheet: `https://glass.people.ai/sheet/8dfddcd5-bc40-4c6a-aeeb-ae1de4d8aab3`
- Cannot deep-link to account-filtered view — Slack message provides the account-specific view, PeopleGlass link is for the full picture

## Future Enhancements

- **Slack Lists sync** — push tasks to a per-user Slack List in addition to SF
- **Status dropdown** — allow changing to any status (In Progress, Waiting, Deferred) not just Complete
- **Create task from scratch** — `tasks new aidoc` opens the Create Task modal without needing a recap
- **Task reminders** — proactive DM when a task is overdue
- **Team view** — managers see their team's tasks: `tasks team`

## Estimated Effort

| Component | Effort |
|---|---|
| Workato read recipe | 30 min (Workato UI) |
| n8n callback webhook | 30 min |
| `tasks` command routing + thinking msg | 20 min |
| Task list message builder | 30 min |
| Complete button handler | 20 min |
| Workato update_task branch | 15 min |
| Testing + iteration | 30 min |
| **Total** | **~3 hours** |
