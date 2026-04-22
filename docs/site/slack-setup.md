# Chat Platform Setup

The assistant delivers all output through your team's chat platform. This guide covers setup for each supported platform.

> **Slack is the primary reference platform** — it has the most complete feature support, including per-message bot name customization. Microsoft Teams and Google Chat sections cover what changes when deploying on those platforms.

## Platform Comparison

| Capability | Slack | Microsoft Teams | Google Chat |
|------------|-------|-----------------|-------------|
| Proactive DMs (scheduled digests) | Yes | Yes (requires conversation reference storage) | Yes |
| Slash commands | Native (`/bs`) | Messaging extensions | Native (`@mention` or DM) |
| Per-message bot name override | Yes (`chat:write.customize`) | No — fixed bot name | No — fixed app name |
| Interactive elements | Block Kit (buttons, modals) | Adaptive Cards (buttons, inputs) | Cards v2 (buttons, inputs) |
| App Home / settings tab | Yes | No native equivalent | No native equivalent |
| n8n integration | Built-in node | Built-in node + HTTP Request | Built-in node |

---

## Slack

### Create the Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name: `Backstory Assistant` (or your preferred name)
4. Select your workspace
5. Click **Create App**

### Configure Bot Permissions

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

#### Required Scopes

| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to users |
| `chat:write.customize` | Override bot name and avatar per message — **this is critical** for personalized assistant names |
| `im:history` | Read DM history for conversation context |
| `im:read` | Access DM channels |
| `im:write` | Open DM conversations with users |
| `channels:history` | Read messages in public channels (for multi-turn thread conversations) |
| `users:read` | Get user info (name, timezone) |
| `users:read.email` | Get user email for Backstory matching |

#### Optional Scopes (for future features)

| Scope | Purpose |
|-------|---------|
| `files:write` | Attach files to messages |
| `reactions:write` | Add emoji reactions |

> **Important:** The `chat:write.customize` scope is what enables the personalized assistant experience. Without it, all messages will show the default bot name instead of each rep's chosen assistant name.

### Enable Event Subscriptions

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

### Enable App Home

1. Navigate to **App Home**
2. Under **Show Tabs**, enable the **Home Tab**
3. Optionally enable the **Messages Tab**

The Home Tab serves as a settings panel where reps can view and modify their assistant preferences.

### Enable Interactivity

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to On
3. Set **Request URL** to:
   ```
   https://your-n8n-instance.com/webhook/slack-interactive
   ```

This handles button clicks and modal submissions (e.g., App Home settings edits, meeting recap save-to-CRM modals).

### Register Slash Commands

1. Navigate to **Slash Commands**
2. Click **Create New Command**
3. Configure:

| Field | Value |
|-------|-------|
| Command | `/bs` |
| Request URL | `https://your-n8n-instance.com/webhook/bs` |
| Short Description | Ask your sales assistant a question |
| Usage Hint | `[your question about an account, deal, or pipeline]` |

### Install to Workspace

1. Navigate to **Install App**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

> Save this token securely — you will need it when configuring n8n credentials.

### Verify Installation

1. In Slack, find your bot in the Apps section
2. Open a DM with the bot
3. Send any message

If the n8n Slack Events Handler workflow is active, you should see the onboarding flow trigger. If not, check the Troubleshooting page.

### Production: Customer Workspace OAuth

For deploying to customer workspaces (multi-tenant), you will need full OAuth 2.0:

1. Enable **OAuth 2.0** in your Slack app settings
2. Add **Redirect URLs** for your auth flow
3. Store per-tenant tokens securely in your database
4. Handle token refresh

#### Rate Limits

| Method | Tier | Approximate Limit |
|--------|------|-------------------|
| `chat.postMessage` | Tier 2 | ~20 per minute |
| `conversations.open` | Tier 3 | ~50 per minute |
| `users.info` | Tier 2 | ~20 per minute |

For high-volume deployments, implement queuing in your n8n workflows.

---

## Microsoft Teams

> Teams does not support per-message bot name customization. The bot will always display the name configured in Azure Bot Service. Personalization is achieved through message content (e.g., "Hey, it's ScottAI — here's your morning briefing").

### Register the Bot

1. Go to the [Azure Portal](https://portal.azure.com)
2. Create a new **Azure Bot** resource
3. Choose **Multi-tenant** for the bot type
4. Note the **Microsoft App ID** and generate a **Client Secret** — save both securely

Alternatively, use the [Teams Developer Portal](https://dev.teams.microsoft.com) to create and manage your app.

### Configure the Messaging Endpoint

Set the **Messaging endpoint** to your n8n webhook URL:

```
https://your-n8n-instance.com/webhook/teams-events
```

This receives all bot activity (messages, mentions, conversation updates).

### Required API Permissions

In the Azure App Registration, add these **Microsoft Graph** permissions:

| Permission | Type | Purpose |
|------------|------|---------|
| `ChatMessage.Send` | Application | Send messages to users |
| `Chat.Create` | Application | Open 1:1 conversations for proactive messaging |
| `User.Read.All` | Application | Look up user info (name, email) |
| `TeamsActivity.Send` | Application | Send activity feed notifications |

> Grant admin consent for these permissions in the Azure Portal.

### Proactive Messaging

Teams requires **conversation references** to send proactive messages (like scheduled digests). Unlike Slack's simple `conversations.open`, you must:

1. Store the conversation reference when the user first interacts with the bot
2. Use the stored reference to send future proactive messages via the Bot Framework SDK

In n8n, this means:
- The first user interaction stores a conversation reference in your database
- Scheduled workflows (digests, alerts) load the reference and use an HTTP Request node to send messages via the Bot Framework REST API

### Rich Messages: Adaptive Cards

Teams uses **Adaptive Cards** instead of Slack's Block Kit. The JSON structure is different but serves the same purpose.

| Slack Block Kit | Teams Adaptive Card Equivalent |
|-----------------|-------------------------------|
| `header` block | `TextBlock` with `size: Large, weight: Bolder` |
| `section` with `mrkdwn` | `TextBlock` with markdown support |
| `section` with `fields` | `ColumnSet` with `Column` items |
| `divider` | `Container` with separator |
| `actions` (buttons) | `ActionSet` with `Action.Submit` |
| Modal (`views.open`) | **Task Module** (iframe or Adaptive Card) |

The n8n workflow's "Parse Blocks" node would need a Teams-specific variant that outputs Adaptive Card JSON instead of Block Kit JSON.

### Create the Teams App Package

1. In the Teams Developer Portal, create a new app
2. Add a **Bot** capability pointing to your Azure Bot
3. Configure commands (equivalent to Slack slash commands):
   - Command: `bs`
   - Description: "Ask your sales assistant a question"
4. Publish to your organization's app catalog

### Install to Your Organization

1. Upload the app package to the **Teams Admin Center**
2. Approve the app for your organization
3. Users can then find and install it from the Teams app store

---

## Google Chat

> Google Chat does not support per-message app name customization. The app will always display the name configured in the Google Cloud Console. Personalization is achieved through message content.

### Create the Chat App

1. Go to the [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Chat API**
4. Navigate to **APIs & Services → Google Chat API → Configuration**
5. Configure:
   - **App name:** `Backstory Assistant`
   - **Avatar URL:** Your assistant's avatar image
   - **Description:** Pipeline intelligence assistant
   - **Functionality:** Check "Receive 1:1 messages" and "Join spaces and group conversations"
   - **Connection settings:** Choose **HTTP endpoint URL**
   - **HTTP endpoint URL:** `https://your-n8n-instance.com/webhook/gchat-events`

### Required OAuth Scopes

| Scope | Purpose |
|-------|---------|
| `https://www.googleapis.com/auth/chat.messages.create` | Send messages |
| `https://www.googleapis.com/auth/chat.spaces` | List and access spaces (DMs) |
| `https://www.googleapis.com/auth/chat.memberships.readonly` | List space members |

> These scopes require **domain-wide delegation** or **admin approval** for your Google Workspace.

### Service Account Setup

For proactive messaging (scheduled digests), create a **service account**:

1. In Google Cloud Console → **IAM & Admin → Service Accounts**
2. Create a new service account
3. Download the JSON key file
4. In the Google Workspace **Admin Console**, grant domain-wide delegation to the service account with the Chat scopes above

### Rich Messages: Card Messages

Google Chat uses **Cards v2** for rich formatting.

| Slack Block Kit | Google Chat Card Equivalent |
|-----------------|----------------------------|
| `header` block | `CardHeader` with title and subtitle |
| `section` with `mrkdwn` | `TextParagraph` widget |
| `section` with `fields` | `DecoratedText` widgets in columns |
| `divider` | `Divider` widget |
| `actions` (buttons) | `ButtonList` widget |
| Modal (`views.open`) | **Dialog** (card-based form) |

The n8n workflow's "Parse Blocks" node would need a Google Chat variant that outputs Card v2 JSON.

### Publish the App

1. In the Google Cloud Console, set the app's **Visibility** to your organization
2. In the Google Workspace **Admin Console** → **Apps → Google Workspace Marketplace apps**, approve the app
3. Users can then find and add it from Google Chat

### Proactive Messaging

Google Chat's proactive messaging is simpler than Teams:

1. Use the Chat API to list the bot's DM spaces: `GET https://chat.googleapis.com/v1/spaces?filter=spaceType="DIRECT_MESSAGE"`
2. Send a message to the space: `POST https://chat.googleapis.com/v1/spaces/{space}/messages`

In n8n, use HTTP Request nodes with the service account credentials to call these endpoints from scheduled workflows.

---

## What Changes in n8n Workflows

When deploying on Teams or Google Chat instead of Slack, these workflow components need adaptation:

| Component | Slack | Teams | Google Chat |
|-----------|-------|-------|-------------|
| **Message delivery node** | HTTP Request to `chat.postMessage` | HTTP Request to Bot Framework REST API | HTTP Request to Chat API |
| **DM open** | `conversations.open` API | Store + replay conversation reference | `spaces.list` to find DM space |
| **Rich formatting** | Block Kit JSON | Adaptive Card JSON | Card v2 JSON |
| **Event webhook** | `/webhook/slack-events` | `/webhook/teams-events` | `/webhook/gchat-events` |
| **Auth credential** | Slack Bot Token (HTTP Header) | Azure App ID + Secret | Google Service Account JSON |
| **Interactive handler** | `/webhook/slack-interactive` | Same endpoint as events | Same endpoint as events |
| **User lookup** | `users.info` API | Microsoft Graph `users` API | Google People API or Workspace Directory |

> The core logic (Backstory data fetch → AI agent → parse output → deliver) stays the same across all platforms. Only the delivery and event-handling layers change.
