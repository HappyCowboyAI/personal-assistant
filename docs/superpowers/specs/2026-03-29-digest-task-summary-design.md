# Digest Task Summary — Design Spec

**Date:** 2026-03-29
**Status:** Approved design, not yet planned for implementation

## Summary

Add a "Tasks" section to the morning Sales Digest that surfaces overdue and due-this-week tasks. No separate reminders — tasks appear as part of the existing 6am daily touchpoint.

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| When to surface tasks? | In the morning digest only (no separate DM) | Avoids notification fatigue, fits existing daily touchpoint |
| When to show the section? | Only when actionable (overdue or due this week) | Keeps digest lean on quiet days |
| Level of detail? | Summary line + top 3-5 most urgent tasks by name | Enough context to know what's slipping without bloating the digest |
| Data source? | Workato SOQL query against Salesforce | Backstory Query API does not sync SF Task objects |

## Design

### Task Section in Digest

When a user has overdue or due-this-week tasks, the Claude agent includes a task section at the end of the digest. Example output:

```
*Tasks*
You have 3 overdue and 2 due this week:
- :red_circle: Hold technical session with Iris Ayelin (2 days overdue)
- :red_circle: Review Slackbot docs with security team (2 days overdue)
- :red_circle: Follow up with Matt Olsson on signal prioritization (2 days overdue)
- :warning: Prep demo for AiDoc (due Thu)
- :warning: Send pricing proposal to Glean (due Fri)

Type `tasks` for the full list.
```

When no tasks are overdue or due this week, the section is omitted entirely.

### Data Flow

The digest cron needs task data available **before** the Claude agent generates the briefing, so tasks can be woven into the narrative naturally (not appended as a separate block).

#### Option A — Synchronous Workato branch (recommended)

Add a new action `get_tasks_sync` to the existing "Assistant — Read from Salesforce" Workato recipe:

1. New IF branch: `action = "get_tasks_sync"`
2. Same SOQL query: `SELECT Id, Subject, Status, Priority, ActivityDate, Account.Name, Owner.Name, Owner.Email, Category__c FROM Task WHERE Owner.Email = :email AND TaskSubtype = 'Task' AND Type NOT IN ('Reminder', 'Intercom Chat', 'Email') AND Status NOT IN ('Completed', 'Expired', 'Deferred', 'Cancelled') AND IsDeleted = false ORDER BY ActivityDate ASC`
3. Collect results into array
4. **Reply to webhook** with JSON array of tasks (synchronous response)

In the n8n Sales Digest workflow:
1. Before the user loop, add an HTTP Request node calling Workato with `action: "get_tasks_sync"` and each user's email
2. Parse the response — filter to overdue + due-this-week only
3. Pass task summary as context to the Claude agent prompt (alongside the existing opportunity data)

#### Option B — Async Workato with n8n orchestration (fallback)

Reuse the existing async callback pattern. More complex because the digest cron must:
1. Send `get_my_tasks` to Workato per user
2. Wait for callback to Task Callback Handler
3. Collect results before invoking the Claude agent

This adds significant orchestration complexity and is not recommended.

### Prompt Integration

Add to the digest system prompt (after the opportunity context section):

```
## Task Context

The user has the following open tasks due soon:

{{task_summary_table}}

If the user has overdue or due-this-week tasks, weave a brief "Tasks" section at the end of your briefing highlighting the most urgent items. If there are no tasks due, omit the section entirely.
```

### SOQL Query

Reuse the existing query from the Workato recipe with `IsDeleted = false` filter (already fixed). No changes needed to the query itself.

## Open Items

- [ ] Workato: Add synchronous `get_tasks_sync` branch with "Reply to webhook" response
- [ ] n8n: Add pre-loop task fetch to Sales Digest workflow (per-user HTTP request inside the batch loop)
- [ ] Prompt: Add task context injection to the digest prompt template
- [ ] Test: Verify digest renders correctly with 0 tasks, 1-5 tasks, and >5 tasks

## Out of Scope

- Standalone task reminder DMs
- Task status updates from the digest (use `tasks` command for interactive actions)
- Team/manager task visibility in digest (future enhancement)
- Natural language task creation ("remind me to...")
