# Slack App Setup

This guide walks through creating and configuring the Slack bot.

## Create the Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name: `People.ai Assistant` (or your preferred name)
4. Select your workspace
5. Click **Create App**

## Configure Bot Permissions

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

### Required Scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to users |
| `chat:write.customize` | Override bot name and avatar per message — **this is critical** for personalized assistant names |
| `im:history` | Read DM history for conversation context |
| `im:read` | Access DM channels |
| `im:write` | Open DM conversations with users |
| `channels:history` | Read messages in public channels (for multi-turn thread conversations) |
| `users:read` | Get user info (name, timezone) |
| `users:read.email` | Get user email for People.ai matching |

### Optional Scopes (for future features)

| Scope | Purpose |
|-------|---------|
| `files:write` | Attach files to messages |
| `reactions:write` | Add emoji reactions |

> **Important:** The `chat:write.customize` scope is what enables the personalized assistant experience. Without it, all messages will show the default bot name instead of each rep's chosen assistant name.

## Enable Event Subscriptions

1. Navigate to **Event Subscriptions**
2. Toggle **Enable Events** to On
3. Set **Request URL** to:
   ```
   https://your-n8n-instance.com/webhook/slack-events
   ```
4. Under **Subscribe to bot events**, add:
   - `message.im` — DMs to the bot
   - `message.channels` — Messages in public channels (for multi-turn threads)
   - `app_home_opened` — Renders the App Home settings tab
   - `app_mention` — @mentions in channels (optional)
5. Click **Save Changes**

> Slack will send a verification challenge to your webhook URL. Your n8n Slack Events Handler workflow must be active and accessible for this to succeed.

## Enable App Home

1. Navigate to **App Home**
2. Under **Show Tabs**, enable the **Home Tab**
3. Optionally enable the **Messages Tab**

The Home Tab serves as a settings panel where reps can view and modify their assistant preferences.

## Enable Interactivity

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to On
3. Set **Request URL** to:
   ```
   https://your-n8n-instance.com/webhook/slack-interactive
   ```

This handles button clicks and modal submissions (e.g., App Home settings edits, meeting recap save-to-CRM modals).

## Register Slash Commands

1. Navigate to **Slash Commands**
2. Click **Create New Command**
3. Configure:

| Field | Value |
|-------|-------|
| Command | `/bs` |
| Request URL | `https://your-n8n-instance.com/webhook/bs` |
| Short Description | Ask your sales assistant a question |
| Usage Hint | `[your question about an account, deal, or pipeline]` |

## Install to Workspace

1. Navigate to **Install App**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

> Save this token securely — you will need it when configuring n8n credentials.

## Verify Installation

1. In Slack, find your bot in the Apps section
2. Open a DM with the bot
3. Send any message

If the n8n Slack Events Handler workflow is active, you should see the onboarding flow trigger. If not, check the Troubleshooting page.

## Production: Customer Workspace OAuth

For deploying to customer workspaces (multi-tenant), you will need full OAuth 2.0:

1. Enable **OAuth 2.0** in your Slack app settings
2. Add **Redirect URLs** for your auth flow
3. Store per-tenant tokens securely in your database
4. Handle token refresh

### Rate Limits

Key Slack API rate limits:

| Method | Tier | Approximate Limit |
|--------|------|-------------------|
| `chat.postMessage` | Tier 2 | ~20 per minute |
| `conversations.open` | Tier 3 | ~50 per minute |
| `users.info` | Tier 2 | ~20 per minute |

For high-volume deployments, implement queuing in your n8n workflows.
