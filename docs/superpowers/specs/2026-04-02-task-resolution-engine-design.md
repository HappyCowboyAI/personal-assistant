# Task Resolution Engine — Design Spec

**Date:** 2026-04-02
**Status:** Draft
**Depends on:** Auto-Save Recap (2026-04-02-auto-save-recap-design.md)

## Problem

Tasks are created but never updated. Reps complete work (send emails, have meetings, resolve issues) but don't go back to mark tasks complete in CRM. Open task lists become stale and untrustworthy, breaking the task flywheel.

## Solution

An AI-powered Task Resolution Engine that detects completed tasks by checking Backstory SalesAI activity signals. Two entry points: during meeting recaps (account-scoped) and a 2x daily scheduled job (all open tasks). The assistant marks detected completions automatically — no human data entry required.

## Entry Points

| Entry Point | Trigger | Scope | When |
|-------------|---------|-------|------|
| Recap flow | After recap agent generates | Open tasks for the meeting's account | On recap (cron or on-demand) |
| Scheduled job | 2x daily (9am + 4pm PT) | All open tasks for the user | Alongside Follow-up Cron |

## Task Filter

Open tasks matching:
- Status NOT IN (Completed, Cancelled, Deferred)
- `created_date >= 7 days ago` OR `due_date >= 7 days ago` OR `due_date >= today`
- Excludes truly stale tasks (created 7+ days ago AND overdue 7+ days)

## Architecture

### Workato: New `get_tasks_resolution` action

Added to the existing "Assistant — Read from Salesforce" recipe (`assistant_sf_read`). Same async callback pattern as `get_tasks`:

1. n8n sends: `{ action: "get_tasks_resolution", context: { user_email, account_name (optional), callback_url } }`
2. Workato SOQL query fetches open tasks matching the filter
3. FOR EACH task: POST to n8n callback webhook
4. Signal done to n8n callback

**SOQL:**
```sql
SELECT Id, Subject, Description, ActivityDate, Status, Account.Name, Owner.Email, Owner.Name, CreatedDate
FROM Task
WHERE OwnerId IN (SELECT Id FROM User WHERE Email = :user_email)
  AND Status NOT IN ('Completed', 'Cancelled', 'Deferred')
  AND (CreatedDate >= LAST_N_DAYS:7 OR ActivityDate >= LAST_N_DAYS:7 OR ActivityDate >= TODAY)
ORDER BY ActivityDate ASC
```

If `account_name` is provided (recap mode), add `AND Account.Name = :account_name`.

### n8n: Task Resolution Callback Handler (new workflow)

New webhook workflow that collects tasks from Workato callback, then runs the resolution agent:

1. **Callback Webhook** — receives individual tasks + "done" signal
2. **Collect Tasks** — stores tasks in Supabase pending_actions or workflow static data
3. **On "done" signal** — fetch all collected tasks
4. **Group by Account** — Code node groups tasks by account name
5. **Loop Accounts** — SplitInBatches
6. **Task Resolution Agent** — Claude + Backstory MCP per account
7. **Process Results** — for completed tasks, fire Workato `update_task`
8. **Return Results** — send back to caller (recap flow or scheduled job)

### n8n: Task Resolution Agent

Claude Sonnet + Backstory MCP. Per-account prompt:

```
Here are open CRM tasks for {account_name}:
1. "{task_subject}" — assigned to {owner}, due {date}
2. "{task_subject}" — assigned to {owner}, due {date}

Use Backstory SalesAI tools (ask_sales_ai_about_account) to check recent 
activity, emails, and meeting outcomes for this account.

For each task, determine:
- COMPLETE: Clear evidence the work was done (email sent, meeting held, 
  document delivered, issue resolved)
- OPEN: No evidence of completion, still pending

Output JSON:
{
  "account_name": "...",
  "tasks": [
    {"id": "SF_TASK_ID", "status": "COMPLETE|OPEN", "evidence": "one-line reason"}
  ]
}

Be conservative — only mark COMPLETE if there is clear evidence. 
When in doubt, leave as OPEN.
```

### Recap Flow Integration

Updated flow (builds on auto-save spec):

```
Recap Agent generates
  → Build Auto-Save Payload
  → Send Recap to CRM + Create Tasks (existing auto-save)
  → Fire Workato get_tasks_resolution (account-scoped)
  → Callback collects open tasks
  → Task Resolution Agent evaluates
  → Mark completed tasks via Workato update_task
  → Build Recap Card (includes marked + new tasks)
  → Post to Slack
```

**Dedup:** Before creating new tasks, compare AI-extracted tasks against open tasks. If an open task's Subject closely matches a "new" task description, skip creating the duplicate.

### Scheduled Job

New workflow or addition to Follow-up Cron:

```
2x daily cron (9am + 4pm PT)
  → Get users from Supabase (digest_enabled = true)
  → Loop users
  → Fire Workato get_tasks_resolution (all user tasks, no account filter)
  → Callback collects open tasks
  → Group by account (tasks define the account list)
  → Loop accounts: Task Resolution Agent evaluates
  → Mark completed tasks via Workato update_task
  → If any tasks marked: Post summary DM
  → If no tasks marked: Stay silent
```

## Slack Output

### Recap Card (updated)

```
:clipboard: *TRUCE Software* · Tue, Apr 2 11:00 AM — Working Session
:white_check_mark: I saved this recap to CRM · Marked 2 tasks complete · Created 1 new task
Category: Solution Presentation & Demo · CS Category: Customer Kickoff

Marked complete:
:white_check_mark: ~Follow up on API integration — Scott Metcalf~
:white_check_mark: ~Schedule April check-in call — Max Morris~

New:
• Send updated SOW — Scott Metcalf · by Apr 9

[Draft Follow-up]  [My Events Today]  [All Tasks Today]
```

### Scheduled Job DM (only when tasks were marked)

```
:clipboard: *Task Update*
I reviewed your open tasks against recent activity:

:white_check_mark: ~Send pricing proposal to TransUnion~ (email sent yesterday)
:white_check_mark: ~Review contract with Flexera~ (discussed in today's meeting)

Marked 2 tasks complete · 5 still open

[All Tasks Today]
```

If no tasks were marked complete, the scheduled job posts nothing — no noise.

## Language Rules

- "Marked N tasks complete" — the assistant detected completion and updated the status
- "Created N new tasks" — the assistant created new records
- Never say "Completed N tasks" — that implies the assistant did the work itself

## Workato Changes Summary

### Read Recipe (`assistant_sf_read`)

New action branch: `get_tasks_resolution`
- Same async callback pattern as existing `get_tasks`
- SOQL query with 7-day freshness filter
- Optional account_name scoping
- Callback URL provided in payload

### Write Recipe (`assistant_sf_write`)

No changes — existing `update_task` action already supports marking tasks complete.

## Not In Scope

- Notifying task owners when their tasks are marked complete (future)
- The assistant actually completing tasks (doing the work itself — future)
- Editing task details (only status changes)
- Creating tasks from email signals (only from meeting recaps)
- Tasks older than 7 days past due
