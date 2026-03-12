# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **People.ai Personal Assistant** — a proactive, agentic AI sales assistant delivered through Slack. Each sales rep gets a named, personalized assistant (e.g., "ScottAI", "Luna") that monitors their pipeline and delivers insights without being prompted.

The product is not a chatbot — it's an agent with its own agenda that runs on a schedule and acts proactively.

## Architecture

Three-layer stack:

| Layer | Tool | Role |
|-------|------|------|
| Orchestration | **n8n** | Scheduling, API routing, conditional logic, delivery |
| Reasoning | **Claude (Anthropic API)** | Synthesizes People.ai data into natural language briefings |
| Intelligence | **People.ai API** | Engagement scores, activity signals, deal health, stakeholder data |
| Delivery | **Slack** | All user interaction — onboarding, digests, commands, approvals |
| Data store | **Supabase** (PostgreSQL) | Multi-tenant user/org data, message logs, pending actions |

There is no custom backend code. All orchestration logic lives in n8n workflows.

## Repository Structure

- `n8n/workflows/` — n8n workflow JSON files (import directly into n8n)
  - `nightly_digest.json` — (legacy template) placeholder credentials, not deployed
  - `Sales Digest.json` — 6am weekday cron → Supabase users → Claude agent + People.ai MCP → Slack DM → log
  - `onboarding.json` — (legacy) Slack DM trigger → check/create user → naming flow + command parsing
  - `Backstory SlackBot.json` — `/bs` slash command → Claude Sonnet 4.5 agent + People.ai MCP → Slack response
  - `Slack Events Handler.json` — Slack Events API webhook → onboarding + settings commands via DM
  - `Weekly Profile Sync.json` — Sunday 10pm PT cron → Slack users.info → update department/division/digest_scope in Supabase
- `prompts/` — Claude prompt templates with `{{variable}}` placeholders
  - `assistant_system.md` — Shared base prompt (identity, personality, formatting) + task-specific extensions
  - `nightly_digest.md` — Morning briefing prompt (personality, structure, Slack formatting rules)
  - `onboarding_conversation.md` — All onboarding/command response templates
- `supabase/migrations/` — SQL schema migrations (run manually in Supabase SQL editor)
  - `001_initial_schema.sql` — All tables, indexes, triggers, and helper functions (consolidated single migration)
  - `002_role_based_digest.sql` — Adds department, division, digest_scope columns to users table
- `scripts/` — Python upgrade scripts for n8n workflow modifications
  - `upgrade_role_based_digest.py` — Adds hierarchy fetch + role-aware filtering + role-specific prompts to Sales Digest, and department/division capture to Slack Events Handler
  - `create_profile_sync_workflow.py` — Creates and activates the Weekly Profile Sync workflow
- `slack/SETUP.md` — Slack app creation and bot configuration guide
- `docs/` — Setup guides and credential templates
- `people-ai-personal-assistant.md` — Full product concept and roadmap

## Key Design Decisions

- **Multi-tenancy from day one**: Every record is scoped to an `organization_id`. The `users` table has unique constraints on `(organization_id, email)` and `(organization_id, slack_user_id)`.
- **Single Slack bot, many personas**: One bot uses `chat:write.customize` to override display name/avatar per message, so each rep sees messages from their named assistant.
- **Assistant resolution chains** (name, emoji, persona all follow the same pattern): User-level override → org default → hardcoded fallback. DB helper functions: `get_assistant_name()`, `get_assistant_emoji()`, `get_assistant_persona()`. In n8n Code nodes: `user.assistant_name || user.org_default_assistant_name || 'Aria'`.
- **Assistant persona**: Freeform text field (e.g., "witty and casual" or "formal and data-driven") injected into the shared system prompt. Allows per-user personality customization beyond just name/emoji.
- **Prompt templates live in `prompts/`** but the canonical versions used at runtime are embedded in the n8n workflow JSON nodes. Keep both in sync when editing. The shared base prompt in `prompts/assistant_system.md` documents how all entry points compose the system message.
- **Onboarding state machine**: `users.onboarding_state` tracks progress: `new` → `awaiting_name` → `awaiting_emoji` → `complete`.

## Working with n8n Workflows

The JSON files in `n8n/workflows/` are exported n8n workflows. To modify:

1. Import into n8n via **Workflows → Import from File**
2. Edit visually in n8n's editor
3. Export back to JSON and commit

Credential IDs in the JSON (e.g., `SUPABASE_CREDENTIAL_ID`) are placeholders — each n8n instance needs its own credential references configured.

The Sales Digest workflow (6am weekdays, 18 nodes): Uses a **Query API + MCP hybrid** approach with **role-based digest customization**. Pre-loop fetches user hierarchy AND open opportunities via People.ai Query API, then filters per user based on their `digest_scope` (IC: own deals, Manager: team deals, Exec: top pipeline). Three prompt variants generate different briefing styles.

Flow: `6am Trigger → Get Auth Token (People.ai client credentials) → Fetch User Hierarchy (Query API: user objects with manager data) → Parse Hierarchy (Code: builds email→user map + manager→reports map) → Fetch Open Opps (Query API export, CSV) → Parse Opps CSV (Code: CSV→array) → Get Digest Users (Supabase getAll) → Filter Active Users (Code: onboarding_state=complete) → Split In Batches → [loop] Filter User Opps (Code: role-aware filtering by digest_scope) → Resolve Identity (Code: role-specific system prompt + assistant identity) → Open Bot DM (conversations.open) → Digest Agent (Claude + People.ai MCP) → Parse Blocks (Code: JSON→Block Kit) → Send Digest (chat.postMessage with blocks) → Log to Messages (Supabase create) → [loop back]`. Sub-nodes: Anthropic Chat Model + People.ai MCP (canary) feed into Digest Agent. Workflow ID: `7sinwSgjkEA40zDj`.

Role-based digest scoping: `users.digest_scope` column controls briefing type. Derived from Slack profile `title` (Division) during onboarding. Values: `my_deals` (IC — 60s personal briefing), `team_deals` (Manager — 90s team coaching briefing), `top_pipeline` (Exec — 90s strategic pipeline briefing). People.ai user hierarchy (manager→reports) is fetched at runtime to determine whose opps to include for team/exec views.

The Backstory Slackbot workflow (`/bs` command): `Webhook POST → Acknowledge 200 → Extract slash command data → Supabase user lookup → Resolve Assistant Identity (Code node: name/emoji/persona fallback chain + pre-builds systemPrompt, thinkingText, answeredText) → Has question? → Is DM? → [DM: response_url thinking + agent + response_url answer] or [Channel: chat.postMessage with personalized username/icon_emoji + agent + thread reply + update original]`. Uses Claude Sonnet 4.5 with People.ai MCP tools (`https://mcp.people.ai/mcp`) for live CRM data. The system prompt is dynamically built from the user's DB record — both agents reference `$('Resolve Assistant Identity').first().json.systemPrompt`. The Supabase `Lookup User` node has `alwaysOutputData: true` so the flow continues with defaults if the user isn't in the DB.

The Slack Events Handler workflow (`/webhook/slack-events`): `Webhook POST → Is Challenge? → [true: respond with challenge text] / [false: Acknowledge 200 → Extract Event Data → Is Bot? → Lookup User (Supabase) → Route by State (Code) → Switch Route (8 outputs)]`. Routes: New User (get Slack user info → create DB record → send greeting), Greeting (set awaiting_name → send greeting), Capture Name (save name → ask emoji), Capture Emoji (save emoji → confirm onboarding complete), Rename/Emoji/Persona (parse → update DB → confirm), Other (help text, digest toggle, unrecognized). All Slack messages use `chat.postMessage` with personalized `username`/`icon_emoji` via Slackbot Auth Token.

Additional credentials (configured in n8n, with real credential IDs unlike the placeholder workflows):
- **Slackbot Auth Token**: HTTP Header Auth for Slack API calls
- **People.ai MCP Multi-Header**: Multi-header auth for the People.ai MCP endpoint

## Database

Run migrations via the Supabase SQL editor. Schema uses UUIDs, `TIMESTAMPTZ`, and JSONB for metadata. RLS policies are defined in `docs/ENV_TEMPLATE.md` but not in the migration — enable before any customer deployment.

## Required Credentials (configured in n8n)

- **Supabase API**: project URL + service role key
- **Slack API**: Bot User OAuth Token (`xoxb-...`)
- **Anthropic API**: API key
- **People.ai API**: HTTP Header Auth (`Authorization: Bearer ...`)

## Slack Bot Requirements

Critical scope: `chat:write.customize` — without this, personalized assistant names don't work. Full scope list and event subscriptions are documented in `slack/SETUP.md`.

Webhook endpoints to configure:
- Event Subscriptions: `https://<n8n>/webhook/slack-events`
- Interactivity: `https://<n8n>/webhook/slack-interactive`
- Backstory slash command (`/bs`): `https://<n8n>/webhook/bs`

## Build Roadmap (current phase: Month 1)

1. **Month 1**: Nightly Digest (current — cron + People.ai + Claude + Slack)
2. **Month 2**: Pre-Meeting Briefing (calendar trigger, 2hr before meetings)
3. **Month 3**: First agentic action (draft re-engagement emails, one-click approval in Slack)
4. **Month 4**: Shareable demo with real user feedback

## Prompt Engineering Notes

- Prompts use Slack formatting (`*bold*`, bullet points) — not Markdown headers
- Digest prompt enforces 300 word limit and "no Good morning" rule
- Assistant personality: direct, action-oriented, conversational, uses "I" and "we"
- Pipeline data is pre-fetched via People.ai Query API (client credentials, service account) and filtered per user based on digest_scope. Agent receives opp table as context and uses MCP only for revenue story depth on top deals
- Three digest prompt variants (IC/Manager/Exec) are embedded in Resolve Identity Code node. Reference docs in `prompts/nightly_digest.md`
- User hierarchy (manager→reports) fetched at runtime via Query API `user` object export — not stored in Supabase
