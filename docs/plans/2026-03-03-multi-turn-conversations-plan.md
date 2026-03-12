# Multi-Turn Conversation Layer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a centralized multi-turn conversation layer so every agent workflow (Backstory, Presentation, Digest, Meeting Prep, On-Demand Digest) supports follow-up replies in Slack threads, with conversation state stored in Supabase.

**Architecture:** A new `conversations` table tracks active threads. Every agent workflow appends a "conversation bookend" (3 nodes) to create a record and log messages. The Slack Events Handler intercepts thread replies to active conversations and routes them to a shared "Continue Conversation" sub-workflow that loads history, re-invokes the correct agent with context, and posts the reply back to the same thread.

**Tech Stack:** n8n workflows (modified via Python scripts + n8n REST API), Supabase (PostgreSQL), Slack API, Anthropic Claude API with People.ai MCP tools.

**Design Doc:** `docs/plans/2026-03-03-multi-turn-conversations-design.md`

**Key patterns from this codebase:**
- Python scripts use `fetch_workflow()` / `push_workflow()` / `sync_local()` to modify n8n workflows via API
- Supabase inserts use HTTP Request nodes (not Supabase node) per MEMORY.md
- Credential IDs: Supabase `ASRWWkQ0RSMOpNF1`, Anthropic `rlAz7ZSl4y6AwRUq`, People.ai MCP `wvV5pwBeIL7f2vLG`, Slack `LluVuiMJ8NUbAiG7`
- n8n workflow activation: `POST /api/v1/workflows/{id}/activate`
- executeWorkflowTrigger needs `inputSource: "passthrough"` to activate
- Always fetch live workflow before modifying (live may differ from local)

---

## Task 1: Database Migration — conversations table + messages columns

**Files:**
- Create: `supabase/migrations/003_conversations.sql`

**Step 1: Write the migration SQL**

```sql
-- Multi-turn conversation support
-- New table for tracking active conversations across Slack threads
-- Plus additions to messages table for conversation linking

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    slack_channel_id TEXT NOT NULL,
    slack_thread_ts  TEXT NOT NULL,
    workflow_type    TEXT NOT NULL,
    agent_config     JSONB DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'processing', 'completed', 'expired')),
    turn_count       INTEGER NOT NULL DEFAULT 1,
    max_turns        INTEGER NOT NULL DEFAULT 10,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(slack_channel_id, slack_thread_ts)
);

-- Fast lookup for active conversation by thread
CREATE INDEX idx_conversations_active
    ON conversations(slack_channel_id, slack_thread_ts)
    WHERE status IN ('active', 'processing');

-- Lookup by user for debugging/admin
CREATE INDEX idx_conversations_user
    ON conversations(user_id, created_at DESC);

-- Add conversation linking to messages table
ALTER TABLE messages
    ADD COLUMN conversation_id UUID REFERENCES conversations(id),
    ADD COLUMN slack_thread_ts TEXT,
    ADD COLUMN role TEXT CHECK (role IN ('user', 'assistant'));

-- Index for loading conversation history
CREATE INDEX idx_messages_conversation
    ON messages(conversation_id, sent_at ASC)
    WHERE conversation_id IS NOT NULL;

-- Reuse existing updated_at trigger for conversations
CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

**Step 2: Run the migration in Supabase SQL editor**

Copy the SQL above and execute it in the Supabase SQL editor at `https://rhrlnkbphxntxxxcrgvv.supabase.co`. Verify:
- `conversations` table exists with all columns
- `messages` table has new `conversation_id`, `slack_thread_ts`, `role` columns
- Indexes created
- Trigger attached

**Step 3: Verify with a test insert and delete**

Run in SQL editor:
```sql
-- Test insert (use a real org/user ID from your data)
INSERT INTO conversations (organization_id, user_id, slack_channel_id, slack_thread_ts, workflow_type, expires_at)
SELECT organization_id, id, 'C_TEST', '1234567890.000001', 'backstory', now() + interval '4 hours'
FROM users WHERE slack_user_id = 'U061WJ6RMJS';

-- Verify
SELECT * FROM conversations WHERE slack_channel_id = 'C_TEST';

-- Clean up
DELETE FROM conversations WHERE slack_channel_id = 'C_TEST';
```

**Step 4: Commit**

```bash
git add supabase/migrations/003_conversations.sql
git commit -m "feat: add conversations table and message linking for multi-turn support"
```

---

## Task 2: Create "Continue Conversation" Sub-Workflow

This is the centralized engine. A new n8n workflow that receives thread reply context and re-invokes the correct agent.

**Files:**
- Create: `scripts/create_continue_conversation.py`

**Step 1: Write the Python script that creates the sub-workflow**

The script creates a new workflow with these nodes:

1. **Execute Workflow Trigger** — receives `channelId`, `threadTs`, `userId`, `messageText`, `conversationId`, `slackUserName`
2. **Load Conversation** — HTTP GET to Supabase REST: `conversations?id=eq.{conversationId}&select=*`
3. **Check Limits** — Code node: validates status, turn_count < max_turns, not expired. Sets status='processing' via HTTP PATCH. If over limits, returns error message.
4. **Load History** — HTTP GET to Supabase REST: `messages?conversation_id=eq.{conversationId}&order=sent_at.asc&select=role,content`
5. **Log Inbound** — HTTP POST to Supabase REST: insert message with role='user'
6. **Build Agent Context** — Code node: reconstructs `[{role, content}]` array from history, applies ~4000 token budget, prepends system prompt from `agent_config`, appends new user message. If final turn, appends "This is the final exchange" instruction.
7. **Conversation Agent** — Anthropic Chat Model node with dynamic system prompt from expression
8. **People.ai MCP Tool** — MCP tool node connected to the agent, using People.ai credential
9. **Post Response** — HTTP POST to Slack `chat.postMessage` with `thread_ts`, personalized `username`/`icon_emoji`
10. **Log Outbound** — HTTP POST to Supabase REST: insert message with role='assistant'
11. **Update Conversation** — HTTP PATCH to Supabase REST: increment turn_count, slide expires_at, set status='active' (or 'completed' if final turn)

Key Code node — **Build Agent Context**:

```javascript
const conversation = $('Load Conversation').first().json;
const historyItems = $('Load History').all();
const newMessage = $('Execute Workflow Trigger').first().json.messageText;
const config = conversation.agent_config || {};

// Rebuild message history
const messages = historyItems.map(item => ({
  role: item.json.role,
  content: item.json.content
}));

// Add new user message
messages.push({ role: 'user', content: newMessage });

// Token budget: ~4000 tokens ≈ ~16000 chars. Keep last messages, summarize old.
const MAX_HISTORY_CHARS = 16000;
let totalChars = messages.reduce((sum, m) => sum + m.content.length, 0);

let finalMessages = messages;
if (totalChars > MAX_HISTORY_CHARS) {
  // Keep the last 4 exchanges (8 messages) verbatim
  const recent = messages.slice(-8);
  const older = messages.slice(0, -8);
  const summary = older.map(m => `${m.role}: ${m.content.substring(0, 200)}`).join('\n');
  finalMessages = [
    { role: 'user', content: `[Previous conversation summary]\n${summary}` },
    ...recent
  ];
}

// Build system prompt
let systemPrompt = config.systemPrompt || 'You are a helpful sales assistant.';

// Add conversation context instruction
systemPrompt += '\n\nYou are continuing an existing conversation. The message history is provided. Build on what was discussed — do not repeat introductions or re-ask questions that were already answered.';

// Final turn warning
const turnCount = conversation.turn_count || 1;
const maxTurns = conversation.max_turns || 10;
if (turnCount >= maxTurns - 1) {
  systemPrompt += '\n\nIMPORTANT: This is the final exchange in this thread. Provide your best complete answer. If more work is needed, tell the user to start a new conversation.';
}

// Format as chat messages for the agent
const chatHistory = finalMessages.slice(0, -1).map(m =>
  `${m.role === 'user' ? 'Human' : 'Assistant'}: ${m.content}`
).join('\n\n');

const userMessage = finalMessages[finalMessages.length - 1].content;
const agentPrompt = chatHistory
  ? `[Conversation history]\n${chatHistory}\n\n[Current message]\n${userMessage}`
  : userMessage;

return [{
  json: {
    systemPrompt,
    agentPrompt,
    assistantName: config.assistantName || 'Aria',
    assistantEmoji: config.assistantEmoji || ':robot_face:',
    channelId: $('Execute Workflow Trigger').first().json.channelId,
    threadTs: $('Execute Workflow Trigger').first().json.threadTs,
    conversationId: conversation.id,
    turnCount,
    maxTurns,
    isFinalTurn: turnCount >= maxTurns - 1,
    workflowType: conversation.workflow_type
  }
}];
```

Key Code node — **Check Limits**:

```javascript
const conversation = $('Load Conversation').first().json;
const now = new Date();
const expiresAt = new Date(conversation.expires_at);

// Check if expired
if (expiresAt < now) {
  return [{ json: { error: true, errorMessage: 'This conversation has expired. Please start a new request.' } }];
}

// Check if at max turns
if (conversation.turn_count >= conversation.max_turns) {
  return [{ json: { error: true, errorMessage: 'This thread has reached its limit. Please start a new request for further help.' } }];
}

// Check if already processing (race condition guard)
if (conversation.status === 'processing') {
  return [{ json: { error: true, errorMessage: "I'm still working on your last message — one moment!" } }];
}

return [{ json: { error: false, conversationId: conversation.id } }];
```

The script should follow the exact patterns from `scripts/create_profile_sync_workflow.py`:
- Use `requests.post(f"{N8N_BASE_URL}/api/v1/workflows", ...)` to create
- Use `requests.post(f"{N8N_BASE_URL}/api/v1/workflows/{id}/activate")` to activate
- Set `executeWorkflowTrigger` with `inputSource: "passthrough"`
- Use HTTP Request nodes for all Supabase inserts (not Supabase node)
- Use `predefinedCredentialType` + `nodeCredentialType: "supabaseApi"` for Supabase HTTP auth
- Sync local JSON file after creation

**Step 2: Run the script**

```bash
cd /Users/scottmetcalf/projects/oppassistant
python3 scripts/create_continue_conversation.py
```

Expected: "Created workflow: Continue Conversation (ID: ...)" + "Activated" + local JSON synced.

**Step 3: Test the sub-workflow manually in n8n**

Open the workflow in n8n editor. Use "Test workflow" with sample input:
```json
{
  "channelId": "D_TEST",
  "threadTs": "1234567890.000001",
  "userId": "U061WJ6RMJS",
  "messageText": "test message",
  "conversationId": "<uuid from test insert>"
}
```

Verify: workflow runs without node errors (agent invocation will fail without real conversation data — that's expected at this stage).

**Step 4: Commit**

```bash
git add scripts/create_continue_conversation.py n8n/workflows/Continue\ Conversation.json
git commit -m "feat: create Continue Conversation sub-workflow"
```

---

## Task 3: Modify Slack Events Handler — Intercept Thread Replies

Add conversation interception to the existing Events Handler workflow.

**Files:**
- Create: `scripts/add_conversation_routing.py`

**Step 1: Write the Python script**

The script modifies the Slack Events Handler (`QuQbIaWetunUOFUW`) to:

1. **Update "Extract Event Data" Code node** — add `thread_ts` extraction:
   ```javascript
   // Add to the existing return object:
   threadTs: event.thread_ts || null,
   isThreadReply: !!event.thread_ts
   ```

2. **Add new nodes after "Is Bot Message?" and before "Lookup User"**:
   - **Is Thread Reply?** — IF node: `{{ $json.isThreadReply }}` equals `true`
   - **Check Active Conversation** — HTTP GET to Supabase REST: `conversations?slack_channel_id=eq.{channelId}&slack_thread_ts=eq.{threadTs}&status=in.(active,processing)&expires_at=gt.now()&select=id,status`
   - **Has Active Conversation?** — IF node: check if the response array is non-empty
   - **Continue Conversation** — Execute Workflow node: calls the "Continue Conversation" sub-workflow with `{ channelId, threadTs, userId, messageText: text, conversationId }`
   - If not a thread reply, or no active conversation → fall through to existing "Lookup User" node

3. **Handle "processing" status** — If conversation status is "processing", post "Still working on your last message..." to the thread and stop.

The routing logic:
```
Extract Event Data → Is Bot? (existing) → Is Thread Reply?
  → YES → Check Active Conversation (Supabase query)
    → Has active conversation?
      → YES (status=active) → Execute "Continue Conversation" sub-workflow → END
      → YES (status=processing) → Post "still working" to thread → END
      → NO → Fall through to existing Lookup User
  → NO → Fall through to existing Lookup User
```

Important: The script must:
- Fetch the live workflow first (`GET /api/v1/workflows/QuQbIaWetunUOFUW`)
- Find existing nodes by name to get their IDs and positions
- Insert new nodes between "Is Bot Message?" output and "Lookup User" input
- Reconnect: Is Bot false output → Is Thread Reply? → (yes) Check Active Conversation → Has Active? → (yes) Execute Sub-Workflow / (no) Lookup User. Is Thread Reply? (no) → Lookup User.
- Do NOT touch any other routing or node

**Step 2: Run the script**

```bash
python3 scripts/add_conversation_routing.py
```

Expected: Updates the live workflow, syncs local JSON.

**Step 3: Test in n8n**

Open the Slack Events Handler in the n8n editor. Verify:
- New nodes are visible and connected correctly
- Existing routing is intact (test a non-thread DM still routes to onboarding/commands)
- Thread reply to a non-conversation thread falls through to existing routing

**Step 4: Commit**

```bash
git add scripts/add_conversation_routing.py "n8n/workflows/Slack Events Handler.json"
git commit -m "feat: add conversation routing to Slack Events Handler"
```

---

## Task 4: Add Conversation Bookend to Backstory SlackBot

Add the 3-node "conversation bookend" to the Backstory workflow so every `/bs` response creates a conversation record.

**Files:**
- Create: `scripts/add_backstory_conversation.py`

**Step 1: Write the Python script**

The script modifies Backstory SlackBot (`Yg5GB1byqB0qD-5wVDOAn`):

The workflow has two paths (DM and Channel). Both need bookends.

**For Channel path** — after "Update Original Message" (the last node in the channel flow):

1. **Create Conversation (Channel)** — HTTP POST to Supabase REST `/rest/v1/conversations`:
   ```json
   {
     "organization_id": "{{ user.organization_id }}",
     "user_id": "{{ user.id }}",
     "slack_channel_id": "{{ channelId }}",
     "slack_thread_ts": "{{ $('Post Question to Channel').first().json.ts }}",
     "workflow_type": "backstory",
     "agent_config": {
       "systemPrompt": "{{ $('Resolve Assistant Identity').first().json.systemPrompt }}",
       "model": "claude-sonnet-4-5-20241022",
       "mcpEndpoint": "https://mcp.people.ai/mcp",
       "assistantName": "{{ assistantName }}",
       "assistantEmoji": "{{ assistantEmoji }}"
     },
     "expires_at": "{{ new Date(Date.now() + 4*60*60*1000).toISOString() }}"
   }
   ```
   Use a Code node upstream to prepare the JSON body, then HTTP Request to POST it.

2. **Log User Message (Channel)** — HTTP POST to `/rest/v1/messages`:
   ```json
   {
     "user_id": "{{ user.id }}",
     "message_type": "conversation",
     "channel": "slack",
     "direction": "inbound",
     "content": "{{ commandText }}",
     "conversation_id": "{{ conversation.id }}",
     "slack_thread_ts": "{{ threadTs }}",
     "role": "user"
   }
   ```

3. **Log Assistant Message (Channel)** — HTTP POST to `/rest/v1/messages`:
   ```json
   {
     "user_id": "{{ user.id }}",
     "message_type": "conversation",
     "channel": "slack",
     "direction": "outbound",
     "content": "{{ agentOutput }}",
     "conversation_id": "{{ conversation.id }}",
     "slack_thread_ts": "{{ threadTs }}",
     "role": "assistant"
   }
   ```

**For DM path** — same pattern after "DM Post Answer" nodes. The `slack_thread_ts` is the `ts` from the original "DM Post Thinking" message.

Use a shared Code node pattern (the "Prepare Conversation Data" node) that both paths feed into, then the 3 HTTP Request nodes.

**Step 2: Run the script**

```bash
python3 scripts/add_backstory_conversation.py
```

**Step 3: Test end-to-end**

1. Send `/bs what deals are at risk?` in Slack
2. Verify the response appears as usual
3. Check Supabase: `SELECT * FROM conversations ORDER BY created_at DESC LIMIT 1;` — should see a record with `workflow_type = 'backstory'`
4. Check: `SELECT * FROM messages WHERE conversation_id IS NOT NULL ORDER BY sent_at DESC LIMIT 5;` — should see both user and assistant messages
5. Reply in the thread — should trigger Continue Conversation sub-workflow and get a contextual response

**Step 4: Commit**

```bash
git add scripts/add_backstory_conversation.py "n8n/workflows/Backstory SlackBot.json"
git commit -m "feat: add conversation bookend to Backstory SlackBot"
```

---

## Task 5: Add Conversation Bookend to Remaining Workflows

Apply the same bookend pattern to Presentation, Digest, Meeting Prep, and On-Demand Digest workflows.

**Files:**
- Create: `scripts/add_remaining_conversation_bookends.py`

**Step 1: Write the Python script**

This script applies the bookend to each workflow. For each:

| Workflow | ID | workflow_type | MCP Endpoint | thread_ts source |
|---|---|---|---|---|
| Sales Digest | `7sinwSgjkEA40zDj` | `digest` | `mcp-canary.people.ai` | ts from "Send Digest" chat.postMessage |
| On-Demand Digest | `vxGajBdXFBaOCdkG` | `on_demand_digest` | `mcp-canary.people.ai` | ts from Slack post node |
| Meeting Brief | `Cj4HcHfbzy9OZhwE` | `meeting_prep` | `mcp.people.ai` | ts from Slack post node |

For each workflow:
1. Fetch live version
2. Find the final Slack posting node (the one that returns `ts`)
3. Add 3 bookend nodes: Prepare Data (Code) → Create Conversation (HTTP) → Log Messages (HTTP x2)
4. Connect them after the final Slack post
5. Push and sync

The Presentation workflow runs as a sub-workflow from the Events Handler. Its bookend attaches after the Google Slides link is posted to Slack.

**Step 2: Run the script**

```bash
python3 scripts/add_remaining_conversation_bookends.py
```

**Step 3: Verify each workflow in n8n**

Open each workflow and verify:
- Bookend nodes are present and connected
- Existing flow is unchanged
- No orphaned or disconnected nodes

**Step 4: Trigger a test digest**

If you can trigger the On-Demand Digest (easiest to test), verify:
- Digest arrives in Slack
- Conversation record created in Supabase
- Reply in the thread gets a contextual follow-up

**Step 5: Commit**

```bash
git add scripts/add_remaining_conversation_bookends.py "n8n/workflows/Sales Digest.json" "n8n/workflows/"*.json
git commit -m "feat: add conversation bookends to all agent workflows"
```

---

## Task 6: Conversation Expiry Cleanup

Add a simple cron to expire stale conversations. Low urgency since query-time filtering handles correctness, but keeps the table clean.

**Files:**
- Create: `scripts/add_conversation_cleanup.py`

**Step 1: Write the Python script**

Creates a small workflow:
1. **Schedule Trigger** — runs every Sunday at 11pm PT (after profile sync)
2. **Expire Stale Conversations** — HTTP PATCH to Supabase REST: update conversations set `status = 'expired'` where `expires_at < now()` and `status IN ('active', 'processing')`
3. **Log Result** — Code node: log count of expired conversations (optional: post to a Slack admin channel)

**Step 2: Run the script**

```bash
python3 scripts/add_conversation_cleanup.py
```

**Step 3: Verify**

Open workflow in n8n, test manually. Should update any expired conversations.

**Step 4: Commit**

```bash
git add scripts/add_conversation_cleanup.py n8n/workflows/Conversation\ Cleanup.json
git commit -m "feat: add weekly conversation cleanup cron"
```

---

## Task 7: End-to-End Integration Test

Manual test of the full multi-turn flow across all entry points.

**Step 1: Test Backstory multi-turn**

1. `/bs tell me about my pipeline` → get response
2. Reply in thread: "what about the Acme deal specifically?" → should get contextual follow-up
3. Reply again: "when was my last meeting with them?" → should reference Acme from prior turns
4. Verify Supabase: conversation has `turn_count = 3`, messages table has 6 rows (3 user, 3 assistant)

**Step 2: Test Presentation multi-turn**

1. Type `presentation build a renewal review deck` in DM
2. Agent should ask clarifying questions (account name, etc.)
3. Reply with the account details
4. Agent should produce the presentation with the provided context

**Step 3: Test edge cases**

1. **Expiry**: Create a conversation, manually set `expires_at` to the past in Supabase, reply in thread → should get treated as a fresh message
2. **Turn limit**: Manually set `turn_count = 9` on a conversation, reply → agent says "final exchange", conversation completes
3. **Race condition**: Reply twice quickly → second message should get "still working" response
4. **Non-conversation thread**: Reply in an old thread with no conversation record → falls through to normal routing

**Step 4: Verify no regressions**

1. Send a DM to the bot that isn't a thread reply → onboarding/commands work normally
2. Run `/bs` with no prior conversation → works as before
3. Trigger digest → arrives normally with conversation bookend

---

## Summary — Execution Order

| Task | What | Depends On |
|---|---|---|
| 1 | Database migration | Nothing |
| 2 | Create Continue Conversation sub-workflow | Task 1 |
| 3 | Modify Slack Events Handler | Task 2 (needs sub-workflow ID) |
| 4 | Backstory bookend | Task 1 |
| 5 | Remaining workflow bookends | Task 1 |
| 6 | Cleanup cron | Task 1 |
| 7 | Integration testing | Tasks 1-5 |

Tasks 2, 4, 5, 6 can be parallelized after Task 1.
Task 3 depends on Task 2 (needs the sub-workflow ID for the Execute Workflow node).
Task 7 runs after everything else.
