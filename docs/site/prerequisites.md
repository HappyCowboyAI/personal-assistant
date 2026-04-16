# Prerequisites

Before starting the deployment, ensure you have the following accounts and access.

## Required Accounts

| Service | What You Need | Sign Up |
|---------|---------------|---------|
| **Chat Platform** | Slack, Microsoft Teams, or Google Chat (see below) | — |
| **PostgreSQL Database** | Any Postgres-compatible database (Supabase, AWS RDS, self-hosted, etc.) | Varies by provider |
| **n8n** | Cloud or self-hosted instance | [n8n.io](https://n8n.io) |
| **Anthropic** | API key for Claude | [console.anthropic.com](https://console.anthropic.com) |
| **People.ai** | API credentials (client ID + secret) and MCP access | Contact your People.ai account team |

## Chat Platform Requirements

You need **one** of the following, depending on your chosen platform:

| Platform | What You Need | Admin Access Required |
|----------|---------------|-----------------------|
| **Slack** | Workspace admin access to create and install apps | Slack workspace admin |
| **Microsoft Teams** | Azure subscription + Teams admin access | Azure AD admin + Teams admin |
| **Google Chat** | Google Cloud project + Workspace admin access | Google Workspace admin |

## Access Requirements

### Slack
- **Admin access** to the workspace where the bot will be installed
- Ability to create and install Slack apps
- Ability to approve OAuth scopes for bots

### Microsoft Teams (alternative)
- **Azure subscription** with permission to create Azure Bot resources
- **Azure AD admin** access to grant API permissions (Graph API)
- **Teams admin** access to approve and publish apps to the organization catalog

### Google Chat (alternative)
- **Google Cloud project** with billing enabled
- **Google Workspace admin** access to enable domain-wide delegation and approve Chat apps
- Ability to create service accounts and manage OAuth consent

### PostgreSQL Database
- A running PostgreSQL instance (version 13+)
- Ability to create tables, indexes, triggers, and functions
- A REST API layer is recommended for n8n integration (e.g., Supabase, PostgREST, Hasura)
- Connection credentials (host, port, database name, user, password)

### n8n
- An accessible n8n instance with a **public URL** for webhook endpoints
- Admin access to create credentials and import workflows
- If self-hosted: HTTPS enabled (required for Slack webhook verification)

### Anthropic
- An API key with access to Claude models
- The assistant uses Claude Sonnet for all reasoning tasks

### People.ai
- **OAuth client credentials** (client ID + client secret) for the Query API — used to fetch pipeline data and user hierarchy
- **MCP endpoint access** with multi-header authentication — used for real-time CRM queries during agent reasoning
- Your People.ai account team can provision both

## Network Requirements

Your n8n instance must expose the following webhook endpoints to the public internet (Slack sends events to these):

| Endpoint | Purpose |
|----------|---------|
| `https://your-n8n-instance.com/webhook/slack-events` | Slack event subscriptions (DMs, mentions, app home) |
| `https://your-n8n-instance.com/webhook/slack-interactive` | Button clicks, modal submissions |
| `https://your-n8n-instance.com/webhook/bs` | `/bs` slash command handler |

> These URLs will be configured in the Slack App Setup step.
