# Multi-Turn Conversation Layer — Design Doc

**Date:** 2026-03-03
**Status:** Approved
**Scope:** All agent workflows (Backstory, Presentation, Meeting Prep, Digest, On-Demand Digest)

## Problem

Agent workflows are fire-and-forget. When an agent needs clarification (e.g. the Presentation Agent asking "which account?"), the response dead-ends in Slack with no way to continue the conversation. Users must re-trigger the command with more context or give up.

## Solution

A centralized conversation layer that makes every agent interaction multi-turn by default. Every agent response posts to a Slack thread, creates a conversation record in Supabase, and listens for replies. A shared "Continue Conversation" sub-workflow handles all follow-ups regardless of which agent started the thread.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Approach | Centralized conversation router (sub-workflow) | DRY — one engine, all agents inherit |
| Scope | All agent workflows | Build general-purpose from the start |
| Output classification | None — always assume multi-turn | Simplest, most natural UX |
| Context source | Supabase conversation log | We control context quality, no Slack API dependency |
| TTL | 4 hours, sliding window | Covers a work session without stale context risk |
| Max turns | 10 | 5 exchanges, bounds token costs |
| Agent re-invocation | Single dynamic agent node from `agent_config` JSONB | Avoids per-workflow agent duplication |
| Lock mechanism | `status = 'processing'` during execution | Prevents race conditions on rapid replies |

## Database Schema

### New table: `conversations`

```sql
CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    slack_channel_id TEXT NOT NULL,
    slack_thread_ts  TEXT NOT NULL,
    workflow_type    TEXT NOT NULL,  -- 'backstory', 'presentation', 'digest', 'meeting_prep', 'on_demand_digest'
    agent_config     JSONB DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'active',  -- 'active', 'processing', 'completed', 'expired'
    turn_count       INTEGER NOT NULL DEFAULT 1,
    max_turns        INTEGER NOT NULL DEFAULT 10,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(slack_channel_id, slack_thread_ts)
);

CREATE INDEX idx_conversations_active
    ON conversations(slack_channel_id, slack_thread_ts)
    WHERE status = 'active';
```

### Additions to `messages` table

```sql
ALTER TABLE messages
    ADD COLUMN conversation_id UUID REFERENCES conversations(id),
    ADD COLUMN slack_thread_ts TEXT,
    ADD COLUMN role TEXT;  -- 'user' or 'assistant'
```

### `agent_config` JSONB structure

```json
{
  "systemPrompt": "You are a presentation architect for Backstory...",
  "model": "claude-sonnet-4-5-20241022",
  "mcpEndpoint": "https://mcp.people.ai/mcp",
  "assistantName": "ScottAI",
  "assistantEmoji": ":rocket:"
}
```

## Conversation Flow

### Starting a Conversation (any agent workflow)

```
User triggers agent (e.g. /bs, digest, meeting prep)
  -> Agent runs, produces response
  -> Post response to Slack thread (capture thread_ts)
  -> Create conversation record in Supabase
  -> Log user input (role='user') + agent response (role='assistant') to messages
```

Every agent workflow gets a 3-node "conversation bookend" appended:
1. Create conversation record
2. Log user input message
3. Log agent output message

### Continuing a Conversation (centralized sub-workflow)

```
User replies in Slack thread
  -> Slack Events Handler receives message event
  -> Extract Event Data: captures thread_ts
  -> NEW route (before existing routing):
     Query: active conversation for this channel + thread_ts?
  -> YES: Execute "Continue Conversation" sub-workflow
  -> NO: Fall through to existing routing (onboarding, commands, etc.)
```

### Continue Conversation Sub-Workflow

Triggered via Execute Workflow. Receives: `channelId`, `threadTs`, `userId`, `messageText`, `conversationId`.

**Nodes:**
1. **Load Conversation** — Supabase getAll on conversations by ID
2. **Check Limits** — Code: expired? Over max turns? Set status='processing'
3. **Load History** — Supabase getAll on messages where conversation_id, ORDER BY sent_at
4. **Log Inbound** — HTTP Request to Supabase REST (insert message, role='user')
5. **Build Agent Context** — Code: reconstruct message array, merge with agent_config.systemPrompt, apply token budget (~4000 tokens for history)
6. **Resolve Agent** — Switch on workflow_type: pick Claude model + MCP tools
7. **Agent Node** — Anthropic Chat Model + tools (configured per workflow_type)
8. **Post Response** — HTTP Request to Slack chat.postMessage with thread_ts
9. **Log Outbound** — HTTP Request to Supabase REST (insert message, role='assistant')
10. **Update Conversation** — Supabase update: increment turn_count, slide expires_at, set status='active'

## Component Changes

### A. Slack Events Handler (`QuQbIaWetunUOFUW`)

- **Extract Event Data**: Add `thread_ts` extraction from `event.thread_ts`
- **New route before existing Switch**: Query Supabase for active conversation matching `(channel_id, thread_ts)`. If found, route to Execute Workflow node for the sub-workflow. If not found, fall through to existing routing.

Existing routing is completely unchanged. Thread replies to active conversations are intercepted before any other logic runs.

### B. Backstory SlackBot (`Yg5GB1byqB0qD-5wVDOAn`)

Add 3 nodes after the existing response posting:
1. Create conversation record (`workflow_type: 'backstory'`)
2. Log user question (role='user')
3. Log agent response (role='assistant')

No changes to existing agent or response flow.

### C. Other Workflows (Presentation, Meeting Prep, Digest, On-Demand Digest)

Same 3-node "conversation bookend" pattern, each with their own `workflow_type` and `agent_config`.

### D. New Sub-Workflow: "Continue Conversation"

New 10-node workflow as described above. Receives context via Execute Workflow trigger, dynamically configures the agent from `agent_config`.

## Edge Cases & Guardrails

### Race Conditions
- Slack retry dedup: already handled via `x-slack-retry-num` header filter
- Rapid user messages: `status = 'processing'` lock prevents parallel agent invocations. If message arrives during processing, post "Still working on your last message..."

### Context Window Management
- Token budget of ~4000 tokens for conversation history
- If history exceeds budget: summarize older turns into a "conversation so far" block, keep last 3-4 exchanges verbatim
- Large agent outputs (e.g. full Block Kit JSON): store in messages, truncate when rebuilding context

### Expiry & Cleanup
- Query-time filter: conversation lookup already requires `expires_at > now()`
- Sliding window: each continuation resets `expires_at` to `now() + 4 hours`
- Background cleanup cron (weekly): set `status = 'expired'` on stale records

### Turn Limit
- At turn 10: still process the user's message
- Append to system prompt: "This is the final exchange. Provide your best complete answer."
- Set `status = 'completed'` after posting

### Bot Loop Prevention
- Events Handler already filters bot messages
- Sub-workflow verifies userId is not the bot's own ID

### Unknown Workflow Type
- If `agent_config` is malformed: post "I lost context on this thread — could you start a new request?" and close conversation

### Concurrent Conversations
- Users can have multiple active conversations in different threads/channels
- Each keyed by unique `(channel_id, thread_ts)`, fully independent

## Workflow Types & Agent Configs

| Workflow Type | Model | MCP Endpoint | Tools |
|---|---|---|---|
| `backstory` | Claude Sonnet 4.5 | `https://mcp.people.ai/mcp` | Backstory MCP |
| `presentation` | Claude Sonnet 4.5 | `https://mcp.people.ai/mcp` | Backstory MCP |
| `digest` | Claude Sonnet 4.5 | `https://mcp-canary.people.ai/mcp` | Backstory MCP (canary) |
| `meeting_prep` | Claude Sonnet 4.5 | `https://mcp.people.ai/mcp` | Backstory MCP |
| `on_demand_digest` | Claude Sonnet 4.5 | `https://mcp-canary.people.ai/mcp` | Backstory MCP (canary) |
