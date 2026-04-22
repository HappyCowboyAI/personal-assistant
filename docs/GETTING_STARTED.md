# Getting Started

This guide walks through setting up the Backstory Personal Assistant from scratch.

## Prerequisites

- [n8n](https://n8n.io) instance (self-hosted or cloud) — we use a Hostinger VPS
- [Supabase](https://supabase.com) project (free tier works for dev)
- [Anthropic API](https://console.anthropic.com) key
- [Slack workspace](https://slack.com) with admin access
- Backstory API access

## Step 1: Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign up / log in
2. Click **New Project**
3. Choose your organization (or create one)
4. Name it (e.g., `oppassistant-dev`)
5. Set a database password — save this somewhere safe
6. Choose a region close to your n8n instance
7. Click **Create new project** and wait for provisioning

### Save these values (you'll need them for n8n):

| Value | Where to find it |
|-------|-----------------|
| **Project URL** | Settings → API → Project URL (e.g., `https://abc123.supabase.co`) |
| **Anon Key** | Settings → API → `anon` `public` key |
| **Service Role Key** | Settings → API → `service_role` key (use this in n8n) |

## Step 2: Run the Migration

1. In Supabase, go to **SQL Editor**
2. Click **New query**
3. Paste the entire contents of `supabase/migrations/001_initial_schema.sql`
4. Click **Run**

This creates:
- `organizations` — customer/tenant records with defaults for assistant name, emoji, persona
- `users` — sales rep profiles with assistant preferences and onboarding state
- `messages` — delivery log for all assistant messages (inbound + outbound)
- `pending_actions` — drafts awaiting approval
- Helper functions: `get_assistant_name()`, `get_assistant_emoji()`, `get_assistant_persona()`

### Seed Your Organization

```sql
INSERT INTO organizations (name, slug, default_assistant_name)
VALUES ('Backstory', 'peopleai', 'Aria');
```

### Add Yourself as a Test User

```sql
INSERT INTO users (organization_id, email, slack_user_id, peopleai_user_id)
SELECT id, 'your@email.com', 'U_YOUR_SLACK_ID', 'your-peopleai-id'
FROM organizations WHERE slug = 'peopleai';
```

To find your Slack user ID: click your profile in Slack → "..." menu → "Copy member ID".

## Step 3: Slack Bot Setup

Follow the detailed instructions in `slack/SETUP.md`.

Key steps:
1. Create Slack app at api.slack.com
2. Add required bot scopes (especially `chat:write.customize` — this is what enables personalized assistant names/emojis)
3. Enable Event Subscriptions
4. Install to workspace
5. Save the Bot Token (`xoxb-...`)

### Slash Command Setup

For the `/bs` (Backstory) command:
1. Go to **Slash Commands** in your Slack app settings
2. Create new command: `/bs`
3. Request URL: `https://<your-n8n-domain>/webhook/bs`
4. Description: "Ask your sales assistant a question"

## Step 4: n8n Configuration

### Credentials

Create these credentials in n8n (Settings → Credentials → Add Credential):

| Name | Type | Values |
|------|------|--------|
| **Supabase** | Supabase API | Project URL + Service Role Key from Step 1 |
| **Slack** | Slack API | Bot User OAuth Token (`xoxb-...`) from Step 3 |
| **Anthropic** | Anthropic API | Your API key from console.anthropic.com |
| **Backstory API** | HTTP Header Auth | `Authorization: Bearer YOUR_KEY` |
| **Backstory MCP** | HTTP Multi-Header Auth | Headers for `https://mcp.people.ai/mcp` endpoint |

### Import Workflows

1. Go to **Workflows** → **Import from File**
2. Import these workflows:
   - `n8n/workflows/nightly_digest.json` — morning pipeline briefing
   - `n8n/workflows/onboarding.json` — user naming/personalization flow
   - `n8n/workflows/Backstory SlackBot.json` — `/bs` slash command
3. In each workflow, update credential references to match your n8n credential names
4. Activate all workflows

### Webhook URLs

Configure these in your Slack app:

| Purpose | URL |
|---------|-----|
| Event Subscriptions | `https://<n8n>/webhook/slack-events` |
| Interactivity | `https://<n8n>/webhook/slack-interactive` |
| `/bs` slash command | `https://<n8n>/webhook/bs` |

## Step 5: Connect Backstory

### API Authentication

Backstory uses OAuth or API keys. Configure the HTTP Header Auth credential in n8n with your access method.

### MCP Integration

The Backstory workflow uses Backstory's MCP server at `https://mcp.people.ai/mcp` for live CRM queries. This requires multi-header authentication configured in n8n.

### Required Endpoints (for non-MCP workflows)

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/opportunities` | Fetch open deals for a rep |
| `GET /v1/engagement-scores` | Get engagement score changes |
| `GET /v1/accounts/{id}` | Account details for meeting prep |
| `GET /v1/contacts` | Stakeholder information |

## Step 6: Test the System

### Test the Slash Command

1. In Slack, type `/bs What is the status of my top accounts?`
2. You should see a "thinking" response followed by a detailed answer
3. Check n8n execution logs if nothing happens

### Manual Digest Test

1. In n8n, open the Nightly Digest workflow
2. Click **Execute Workflow** to run manually
3. Check your Slack DMs for the briefing

### Onboarding Test

1. In Slack, DM your bot
2. You should receive the naming prompt
3. Reply with a name
4. Verify the name updates in Supabase: `SELECT assistant_name FROM users WHERE slack_user_id = 'YOUR_ID';`

## Troubleshooting

### No message received in Slack
- Check n8n execution logs for errors
- Verify Slack credentials are valid
- Confirm user's `slack_user_id` matches their actual Slack member ID

### Claude response is empty
- Check Anthropic API key is valid
- Review the prompt data in n8n execution logs
- Ensure `pipeline_data` is being populated from Backstory

### Backstory returns 401
- Verify API key/token is current
- Check the user's `peopleai_user_id` is correct
- Review Backstory API documentation for auth format

### Slash command times out
- Slack requires a response within 3 seconds — the workflow must acknowledge immediately
- Check that the "Acknowledge Slash Command" node runs before the agent

## Next Steps

Once everything is working:

1. **Personalize** — DM the bot to set your assistant name and emoji
2. **Gather feedback** from 2-3 internal users
3. **Iterate on prompts** based on what's useful vs. noise
4. **Move to Month 2** — Pre-Meeting Briefing workflow

See the project plan in `backstory-personal-assistant.md` for the full roadmap.
