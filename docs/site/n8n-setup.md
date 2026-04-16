# n8n Setup

This guide covers importing workflows, configuring credentials, and activating the assistant in n8n.

## Create Credentials

In n8n, go to **Settings → Credentials → Add Credential** and create the following:

### Slack Bot Token

| Field | Value |
|-------|-------|
| Type | HTTP Header Auth |
| Header Name | `Authorization` |
| Header Value | `Bearer xoxb-your-bot-token` |

> Use the Bot User OAuth Token from the Slack App Setup step.

### Anthropic API

| Field | Value |
|-------|-------|
| Type | Anthropic API |
| API Key | `sk-ant-your-api-key` |

### People.ai MCP (Multi-Header Auth)

| Field | Value |
|-------|-------|
| Type | HTTP Multiple Headers Auth |
| Headers | As provided by your People.ai account team |

> The MCP endpoint is used for real-time CRM queries during agent reasoning. Your People.ai team will provide the required authentication headers.

### People.ai Query API (OAuth)

The Sales Digest workflow uses People.ai's Query API with OAuth client credentials to fetch pipeline data. The client ID and secret are embedded in the workflow's authentication node — update them after import.

### Database Connection

Choose one of:

**Option A — REST API (recommended for Supabase / PostgREST)**

| Field | Value |
|-------|-------|
| Type | Supabase API (or HTTP Header Auth for PostgREST) |
| Host | `https://your-database-rest-endpoint.com` |
| API Key | `your-service-role-key` |

**Option B — Direct PostgreSQL**

| Field | Value |
|-------|-------|
| Type | PostgreSQL |
| Host | `your-db-host.com` |
| Port | `5432` |
| Database | `your-database-name` |
| User | `your-db-user` |
| Password | `your-db-password` |

## Import Workflows

1. Go to **Workflows → Import from File**
2. Import the workflow JSON files from the `n8n/workflows/` directory in the repository
3. For each imported workflow, update credential references to match the credential names you created above

### Key Workflows to Import

| File | Purpose | Activate? |
|------|---------|-----------|
| `Sales Digest.json` | Daily pipeline briefings (6am weekdays) | Yes |
| `Backstory SlackBot.json` | `/bs` slash command handler | Yes |
| `Slack Events Handler.json` | Onboarding, settings, DM conversations | Yes |

> Import all workflow files from the repository. Some are sub-workflows (called by other workflows) and need to be present for the main workflows to function.

## Update Credential References

After importing each workflow:

1. Open the workflow in the editor
2. Click on each node that has a credential warning (yellow triangle)
3. Select the matching credential you created above
4. Save the workflow

### Common Credential Mappings

| Node Type | Credential to Use |
|-----------|-------------------|
| Slack `chat.postMessage` (HTTP Request) | Slack Bot Token |
| Anthropic Chat Model | Anthropic API |
| People.ai MCP Client | People.ai MCP (Multi-Header) |
| Supabase nodes | Database Connection |
| People.ai Query API (HTTP Request) | Update the OAuth token node in-workflow |

## Update Webhook URLs

If your n8n instance URL differs from what's in the workflow JSONs, update the webhook trigger nodes:

| Webhook Path | Used By |
|--------------|---------|
| `/webhook/slack-events` | Slack Events Handler |
| `/webhook/slack-interactive` | Interactive Events Handler |
| `/webhook/bs` | Backstory SlackBot |

## Configure Timezone

The Sales Digest workflow defaults to `America/Los_Angeles` (Pacific Time). To change:

1. Open the workflow
2. Go to **Settings** (gear icon)
3. Update the **Timezone** setting

## Activate Workflows

1. Open each workflow
2. Toggle the **Active** switch in the top-right corner
3. Verify the webhook URLs are registered (n8n will show them in the trigger node)

> Start with the Slack Events Handler — this enables onboarding. Then activate the Sales Digest and Backstory SlackBot.

## Verify Setup

### Test the Slash Command

1. In Slack, type `/bs What are my top accounts?`
2. You should see a "Thinking..." response followed by a detailed answer
3. If nothing happens, check the n8n execution logs

### Test the Digest Manually

1. Open the Sales Digest workflow in n8n
2. Click **Execute Workflow** to run it manually
3. Check your Slack DMs for the briefing

### Test Onboarding

1. In Slack, open a DM with your bot
2. Send any message
3. The onboarding flow should ask you to name your assistant
4. Verify the name appears in your database: `SELECT assistant_name FROM users WHERE slack_user_id = 'your-slack-id';`
