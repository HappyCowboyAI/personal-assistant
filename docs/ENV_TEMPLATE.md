# Environment Variables & Credentials

This document lists all credentials and configuration needed for the assistant.

## n8n Credentials

Configure these in n8n's credential manager:

### Supabase API
```
Name: Supabase
Type: Supabase API

Host: https://YOUR_PROJECT.supabase.co
API Key: YOUR_SERVICE_ROLE_KEY
```

### Slack API
```
Name: Slack
Type: Slack API

Access Token: xoxb-YOUR-BOT-TOKEN
```

### Anthropic API
```
Name: Anthropic
Type: Anthropic API

API Key: sk-ant-YOUR-KEY
```

### Backstory API
```
Name: Backstory API
Type: HTTP Header Auth

Header Name: Authorization
Header Value: Bearer YOUR_PEOPLEAI_TOKEN
```

## Supabase Configuration

### Project Settings
```
Project URL: https://YOUR_PROJECT.supabase.co
Anon Key: (for client-side, if needed)
Service Role Key: (for n8n - has full access)
```

### Row Level Security (Production)

For production, enable RLS policies:

```sql
-- Users can only see their own data
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own data" ON users
  FOR SELECT USING (auth.uid()::text = id::text);

-- Messages scoped to user
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own messages" ON messages
  FOR SELECT USING (user_id IN (
    SELECT id FROM users WHERE auth.uid()::text = id::text
  ));
```

## Slack App Configuration

### App Settings (api.slack.com)
```
App ID: A0XXXXXXXXX
Client ID: (for OAuth flow)
Client Secret: (for OAuth flow)
Signing Secret: (for request verification)
```

### Webhook URLs (point to your n8n)
```
Event Subscriptions: https://YOUR_N8N/webhook/slack-events
Interactivity: https://YOUR_N8N/webhook/slack-interactive
```

## Backstory API

### Endpoints
```
Base URL: https://api.people.ai/v1
```

### Authentication Options

**Option 1: API Key**
```
Header: Authorization: Bearer YOUR_API_KEY
```

**Option 2: OAuth (for customer deployments)**
```
Auth URL: https://api.people.ai/oauth/authorize
Token URL: https://api.people.ai/oauth/token
Scopes: opportunities:read contacts:read engagement:read
```

## Local Development

For local n8n development, create a `.env` file (not committed):

```bash
# n8n
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=your-password
WEBHOOK_URL=https://your-tunnel.ngrok.io

# Credentials are stored in n8n, but for reference:
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx
SLACK_BOT_TOKEN=xoxb-xxx
ANTHROPIC_API_KEY=sk-ant-xxx
PEOPLEAI_API_KEY=xxx
```

## Security Notes

- Never commit credentials to version control
- Use n8n's credential manager (encrypted at rest)
- For production, use environment variables or secrets manager
- Rotate API keys periodically
- Enable RLS in Supabase before customer deployment
