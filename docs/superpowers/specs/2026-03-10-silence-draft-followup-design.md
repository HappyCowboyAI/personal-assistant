# Silence Alert — Draft Follow-up Email

## Problem

When a user sees a silent account in their silence contract alert, the natural next step is often to reach out. Currently they have to context-switch: figure out who to email, what to say, and compose it themselves. The overflow menu already offers mute/snooze actions — adding a "Draft Follow-up" option keeps the user in flow.

## Solution

Add "Draft Follow-up" as the first option in the silence alert overflow menu. When selected:

1. A "Drafting..." message appears in a thread under the alert
2. A Claude agent with People.ai MCP tools researches the account and its contacts
3. The agent drafts a re-engagement email with recommended recipients
4. The "Drafting..." message is replaced with the polished draft

No mute or snooze is applied — drafting an email is a separate intent from silencing the alert.

## Overflow Menu (updated)

Each silent account's `[...]` menu now has 4 options:

| Order | Label | Value format |
|-------|-------|-------------|
| 1 | Draft Follow-up | `fd\|AccountName` |
| 2 | Snooze 7d | `s7\|AccountName` |
| 3 | Snooze 30d | `s30\|AccountName` |
| 4 | Mark as Lost | `ml\|AccountName` |

## Re-engagement System Prompt

The agent gets a system prompt distinct from the post-meeting follow-up prompt. Key instructions:

**Contact research** — Use People.ai MCP to:
1. Look up the account's engaged contacts (roles, titles, last activity dates)
2. Identify the best recipient(s) — prioritize contacts the rep has had direct interaction with, and decision-makers relevant to open opportunities
3. Surface secondary contacts worth CC'ing if appropriate

**Tone** — The agent decides based on what it finds (days silent, deal stage, last activity type, relationship depth). No generic "checking in" emails — reference specific context. The agent discovers how long the account has been silent via MCP — this data is not passed through the overflow menu value.

**Email draft format** (Slack mrkdwn):

```
:email: *Re-engagement Draft — AccountName*

*To:* Jane Smith (VP Engineering) — last contact 45 days ago
*CC:* Mike Chen (Technical Lead) — last contact 52 days ago
*Subject:* concise subject line

---
email body (150-250 words)
---

_Reply in this thread to adjust the tone, recipients, or ask me to revise._
```

**Rules:**
- 150-250 words in the email body
- Reference specific context from People.ai (deals, last activity, engagement patterns)
- Include a clear next step / call to action
- Use contact names, not generic "team"
- If there are open opportunities, weave that context in naturally
- Note how long since last engagement in the To/CC lines
- If People.ai returns no engaged contacts, tell the user: "I couldn't find recent contacts for this account. Try reaching out to your last known contact or check Salesforce for the account team."
- Keep under 3000 characters total (Slack limit)

## Workflow Changes

### Silence Contract Monitor (cron, `6FsYIe3tYj0HfRY2`)

**Build Alert Message** — Add "Draft Follow-up" as the first overflow option.

### On-Demand Silence Check (`7QaWpTuTp6oNVFjM`)

**Build Alert Message** — Same change: add "Draft Follow-up" as the first overflow option.

### Interactive Events Handler (`JgVjCqoT6ZwGuDL1`)

The `fd` (draft follow-up) action is routed **before** Parse Mute Action, keeping the mute code node focused on mute logic only.

**Route Silence Action** (new Code node) — Parses `actionCode|accountName` from the overflow value. If `actionCode === 'fd'`, outputs to the draft follow-up path. All other action codes (`s7`, `s30`, `ml`) output to the existing Parse Mute Action path.

Outputs:
- `accountName` (from overflow value)
- `channelId` (from `payload.channel.id`)
- `messageTs` (from `payload.message.ts` — the silence alert message's timestamp, used as `thread_ts` for threading)
- `assistantName`, `assistantEmoji` (from `Lookup User (Action)`)
- `repName` (from `Lookup User (Action)`)

**Post Drafting Message** (new HTTP Request) — `chat.postMessage`:
- Thread reply under the silence alert (`thread_ts` = alert message's `ts`)
- Text: "Drafting a follow-up for *AccountName*... give me a moment."
- Personalized with assistant `username`/`icon_emoji`
- Capture response `ts` for later `chat.update`

> **Note:** This threading pattern is intentionally different from the existing post-meeting follow-up flow (which updates the original button message). Here we must preserve the silence alert message since it contains multiple accounts with active overflow menus.

**Build Re-engagement Prompt** (new Code node) — Constructs:
- System prompt (re-engagement version with contact research instructions)
- User prompt with account name and rep name

**Re-engagement Draft Agent** (new Agent trio):
- Agent node with re-engagement system prompt
- Anthropic Chat Model (Claude Sonnet 4.5)
- People.ai MCP client tool (production endpoint: `https://mcp.people.ai/mcp`, credential: `wvV5pwBeIL7f2vLG`)
- Separate from the existing Followup Draft Agent (different system prompt)
- `continueOnFail: true` — if the agent errors, the flow continues

**Post Draft to Thread** (new HTTP Request) — `chat.update`:
- Replaces the "Drafting..." message with the email draft
- Uses channel + `ts` from Post Drafting Message response
- Fallback text if agent output is empty: "I couldn't draft a follow-up for *AccountName*. Try asking me directly: `/bs who should I reach out to at AccountName?`"

## Data Flow

```
User clicks [...] → "Draft Follow-up" on a silent account
  → Interactive Events Handler receives silence_overflow_* action
  → Route Silence Action parses actionCode = 'fd'
  → Post Drafting Message (thread: "Drafting a follow-up for *Elastic*...")
  → Build Re-engagement Prompt (system prompt + account context)
  → Re-engagement Draft Agent (Claude + People.ai MCP)
  → Post Draft to Thread (chat.update → replaces "Drafting..." with draft)

User clicks [...] → "Snooze 7d" / "Snooze 30d" / "Mark as Lost"
  → Route Silence Action parses actionCode = s7/s30/ml
  → Parse Mute Action (existing, unchanged)
  → Upsert Mute → Update Alert Message (existing, unchanged)
```

## Concurrent Actions

If a user clicks "Draft Follow-up" on multiple accounts before the first draft completes, each action posts its own "Drafting..." thread reply and resolves independently. This is fine — the Interactive Events Handler receives separate webhook hits and they don't interfere with each other.

## What Doesn't Change

- The silence alert message itself — no mute, no confirmation replacement
- The existing Followup Draft Agent path (post-meeting "Draft Follow-up" buttons)
- The mute/snooze overflow actions (still work as before)
- Parse Mute Action code — stays focused on mute logic

## Thread Revision Support

Deferred. The `_Reply in this thread to adjust..._` footer is aspirational — there's no conversation bookend created, so thread replies won't route to the agent. Users manually edit and send. A future iteration could add a conversation bookend to enable multi-turn refinement.
