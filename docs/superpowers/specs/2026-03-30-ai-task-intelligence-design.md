# AI Task Intelligence (Passive Features) — Design Spec

**Date:** 2026-03-30
**Status:** Approved design, parked for future implementation

## Summary

Two passive AI features that make open Salesforce tasks smarter without requiring rep action:

1. **MCP-Enriched Task Coaching** — overdue/due-today tasks in the morning digest get AI-generated coaching tips grounded in real Backstory activity data
2. **Smart Completion Suggestions** — after a meeting recap, the assistant identifies open tasks that were likely addressed and suggests marking them done

Both features layer onto existing infrastructure (digest task summary, meeting recap pipeline, Workato SF bridge).

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| How smart should coaching be? | MCP-enriched (dedicated call per account) | Grounded in real data, not agent guessing |
| How many tasks get coaching? | Top 3, deduplicated by account | Caps latency at ~15 seconds, one MCP call per account |
| How to match tasks to meetings? | AI semantic matching + confidence threshold | Handles paraphrasing, confidence prevents false positives |
| Confidence thresholds? | 80% = suggest complete, 50-79% = mention, <50% = omit | Gives agent room to be uncertain |
| Where do completion suggestions appear? | In the meeting recap card | Rep is already in context reviewing the recap |

---

## Feature 1: MCP-Enriched Task Coaching in Digest

### What the Rep Sees

When the digest shows urgent tasks (overdue or due today), the top 3 get a coaching one-liner based on real CRM activity:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Open Tasks — 5 open, 2 overdue · My Open Tasks · My Completed · Last 30 Days
🔴 Prepare AI presentation for OpenAI — 3 days overdue
    💡 OpenAI POC results landed Mar 27 — lead with those. Last meeting was 12 days ago.
🔴 Follow up with Matt on signals — 3 days overdue
    💡 Matt's engagement dropped to 15 this week — re-engage before it goes cold.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

When no tasks are urgent, no coaching is generated (existing behavior — summary line only or section omitted).

### Data Flow

```
Filter Urgent Tasks (existing)
    → identifies overdue + due-today tasks
    → passes taskContext to prompt

Enrich Task Context (NEW node, Code)
    → deduplicates urgent tasks by account name
    → selects top 3 most overdue
    → outputs list of unique accounts needing MCP enrichment

Fetch Task Activity (NEW node, MCP or HTTP)
    → for each unique account (max 3), call Backstory MCP:
      - get_recent_account_activity or ask_sales_ai_about_account
      - pull: last meeting date, last email date, engagement score, recent activity summary
    → aggregate results keyed by account name

Build Enriched Task Context (NEW node, Code)
    → merges task list with per-account activity data
    → builds enriched prompt context:
      "TASK: Prepare AI presentation for OpenAI (3 days overdue)
       ACCOUNT CONTEXT: Last meeting Mar 18 (12 days ago), engagement 45 (↓ from 62),
       recent activity: POC results shared Mar 27, no follow-up since"
    → passes to Resolve Identity for prompt injection

Resolve Identity (MODIFIED)
    → injects enriched task context into system prompt
    → prompt instructs agent: "For each urgent task with account context,
      generate a 💡 coaching tip — one sentence, action-oriented,
      referencing specific dates/data from the account context"
```

### Prompt Addition

Added to the existing TASK SECTION INSTRUCTIONS in Resolve Identity:

```
TASK COACHING:
For each urgent task that has ACCOUNT CONTEXT below it, generate a coaching tip on the
line immediately after the task. Format: "    💡 [one sentence, action-oriented, referencing
specific data like last meeting date, engagement trend, or recent activity]"

Only generate coaching tips for tasks that have ACCOUNT CONTEXT. Tasks without context
(e.g., MCP call failed) should display without a tip.
```

### Constraints

- Max 3 enriched tasks per digest (capped in Enrich Task Context node)
- Max 1 MCP call per unique account (deduplicated)
- If an MCP call fails or times out (15s), show the task without a coaching tip — don't block the digest
- Coaching tip is exactly one line, starts with 💡, references specific data (dates, scores, names)
- Added latency: ~3-5 seconds per MCP call × up to 3 accounts = 9-15 seconds max
- No coaching for the summary-only case (open tasks but none urgent)

### Nodes to Add (Sales Digest + On-Demand Digest)

| Node | Type | Position | Purpose |
|------|------|----------|---------|
| Enrich Task Context | Code | After Filter Urgent Tasks | Deduplicate by account, select top 3 |
| Fetch Task Activity | MCP Client Tool or HTTP | After Enrich Task Context | Backstory activity per account |
| Build Enriched Task Context | Code | After Fetch Task Activity | Merge task + activity data for prompt |

### MCP Call Details

Using Backstory MCP (`https://mcp.people.ai/mcp` or canary endpoint):

- **Tool:** `get_recent_account_activity` or `ask_sales_ai_about_account`
- **Input:** account name
- **Desired output:** last meeting date, last email date, engagement score, engagement trend, notable recent events
- **Credential:** `wvV5pwBeIL7f2vLG` (Backstory MCP Multi-Header)
- **Timeout:** 15 seconds per call
- **Fallback:** if call fails, omit coaching tip for that task's account

---

## Feature 2: Smart Completion Suggestions in Meeting Recaps

### What the Rep Sees

After a meeting recap generates, if any open tasks appear to have been addressed in the meeting, a "Tasks Addressed" section appears in the recap card:

```
📋 Tasks Addressed
✅ "Prepare AI presentation for OpenAI" — appears completed (discussed presentation results)  [Mark Done]
❓ "Follow up on pricing" — possibly discussed (pricing mentioned briefly)
```

- **✅ High confidence (≥80%):** task subject + reason + [Mark Done] button
- **❓ Medium confidence (50-79%):** task subject + reason, no button
- **Below 50%:** not shown

### Data Flow

```
Follow-up Cron generates recap (existing)
    → recap output includes: meeting subject, account, summary, decisions, action items

Fetch User Tasks for Recap (NEW)
    → reuse get_tasks_digest Workato action
    → fire-and-forget to Workato, wait 8 seconds, read from Supabase
    → filter to tasks matching the meeting's account only
    → if no open tasks for this account, skip matching entirely

Match Tasks to Recap (NEW, Claude agent call)
    → input: meeting recap content + filtered open tasks
    → prompt: "Given this meeting recap and these open Salesforce tasks,
      identify which tasks were likely addressed in this meeting.
      Return JSON array of matches."
    → output schema:
      [
        {
          "task_id": "00TRi00001HwLGMMA3",
          "task_subject": "Prepare AI presentation for OpenAI",
          "confidence": 85,
          "reason": "discussed presentation results and received positive feedback"
        }
      ]

Build Recap Task Section (NEW, Code node)
    → filter matches by confidence threshold
    → ≥80%: render with ✅ and [Mark Done] button (action_id: recap_task_complete_{task_id})
    → 50-79%: render with ❓, no button
    → <50%: omit
    → append section to recap card blocks

Mark Done button handler (MODIFY Interactive Events Handler)
    → reuse existing task_complete_* pattern
    → sends update_task to Workato → SF marks task Completed
    → confirms in thread
```

### Task Matching Prompt

```
You are analyzing a meeting to determine if any open Salesforce tasks were addressed.

MEETING:
Subject: {meeting_subject}
Account: {account_name}
Summary: {recap_summary}
Decisions: {decisions}
Action Items: {action_items}

OPEN TASKS FOR THIS ACCOUNT:
{for each task: ID, Subject, Status, Due Date}

For each open task, assess whether the meeting content indicates the task was completed or
substantially addressed. Return a JSON array of matches:

[
  {
    "task_id": "SF task ID",
    "task_subject": "task subject",
    "confidence": 0-100,
    "reason": "brief explanation of why this task appears addressed"
  }
]

Guidelines:
- Only include tasks with confidence >= 50
- 80-100: strong evidence the task was completed (explicit discussion, decision made, deliverable reviewed)
- 50-79: partial evidence (topic mentioned but unclear if task is fully done)
- The reason should reference specific meeting content ("discussed pricing terms" not "related to pricing")
- Do not match tasks that are merely related to the account — match on the specific task subject
- Return empty array [] if no tasks were addressed
```

### Constraints

- Only match tasks for the same account as the meeting (pre-filtered before agent call)
- Max 5 task matches shown per recap
- Confidence thresholds: ≥80% gets [Mark Done] button, 50-79% mention only, <50% omit
- Uses same Workato async bridge as digest (get_tasks_digest → pending_actions)
- Task fetch adds ~8 seconds to recap generation (same Wait pattern as digest)
- If task fetch fails, recap generates normally without the "Tasks Addressed" section
- [Mark Done] button reuses existing task_complete_* Interactive Events Handler pattern

### Nodes to Add (Follow-up Cron)

| Node | Type | Position | Purpose |
|------|------|----------|---------|
| Fetch Recap Tasks | HTTP Request | After Build Recap Context | Call Workato get_tasks_digest |
| Wait for Recap Tasks | Wait | After Fetch Recap Tasks | 8-second delay for async bridge |
| Read Recap Tasks | HTTP Request | After Wait | Read from Supabase pending_actions |
| Filter Account Tasks | Code | After Read Recap Tasks | Filter to meeting account only |
| Match Tasks to Recap | Agent (Claude) | After Filter Account Tasks | Semantic matching with confidence |
| Build Recap Task Section | Code | After Match Tasks | Render ✅/❓ section for recap card |

### Interactive Events Handler Changes

Add a new route for `recap_task_complete_*` action IDs:
- Extract task_id from button value
- Reuse existing Build Complete Payload → Send Complete to Workato → Confirm flow
- Same as existing task_complete_* but triggered from recap card instead of tasks list

---

## Shared Infrastructure

Both features reuse existing components:

| Component | Used By | Already Exists? |
|-----------|---------|----------------|
| Workato `get_tasks_digest` action | Both | Yes (built today) |
| Supabase pending_actions bridge | Both | Yes (built today) |
| 8-second Wait + Read pattern | Both | Yes (built today) |
| Backstory MCP tools | Feature 1 | Yes (used by Backstory, Digest Agent) |
| task_complete_* handler | Feature 2 | Yes (Interactive Events Handler) |
| Claude agent with MCP | Feature 1 | Yes (Digest Agent node) |
| Claude agent for matching | Feature 2 | New call, but same pattern as recap agent |

## Implementation Order

1. **Feature 1 (Task Coaching)** first — smaller scope, layers onto digest infrastructure we just built, no new UI elements
2. **Feature 2 (Smart Completion)** second — requires Follow-up Cron changes, new agent call, and Interactive Events Handler routing

## Out of Scope

- On-demand task help (`help with <task>` command) — separate spec
- Auto-draft deliverables for tasks — separate spec
- Automatic task completion without user confirmation — always require button click
- Task creation suggestions (agent proposing new tasks) — separate feature
- Cross-account task matching (matching a task to a meeting for a different account)
