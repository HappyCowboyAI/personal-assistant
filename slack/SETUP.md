# Slack Bot Setup Guide

This guide walks through setting up the Slack bot for the Backstory Personal Assistant.

## Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name: `Backstory Assistant` (or your preferred name)
4. Select your workspace
5. Click **Create App**

## Configure Bot Permissions

Navigate to **OAuth & Permissions** and add these **Bot Token Scopes**:

### Required Scopes
| Scope | Purpose |
|-------|---------|
| `chat:write` | Send messages to users |
| `chat:write.customize` | Customize bot name/avatar per message |
| `im:history` | Read DM history for context |
| `im:read` | Access DM channels |
| `im:write` | Open DMs with users |
| `channels:history` | Receive message events in public channels (for multi-turn conversations) |
| `users:read` | Get user info (name, timezone) |
| `users:read.email` | Get user email for matching |

### Optional (for future features)
| Scope | Purpose |
|-------|---------|
| `files:write` | Attach files to messages |
| `reactions:write` | Add emoji reactions |

## Enable Event Subscriptions

1. Navigate to **Event Subscriptions**
2. Toggle **Enable Events** to On
3. Set **Request URL** to your n8n webhook URL:
   ```
   https://your-n8n-instance.com/webhook/slack-events
   ```
4. Under **Subscribe to bot events**, add:
   - `message.im` — DMs to the bot
   - `message.channels` — messages in public channels (for multi-turn thread conversations)
   - `app_home_opened` — renders the App Home settings/onboarding tab
   - `app_mention` — @mentions in channels (optional)

5. Click **Save Changes**

## Enable App Home Tab

1. Navigate to **App Home**
2. Under **Show Tabs**, enable the **Home Tab**
3. Optionally enable the **Messages Tab** as well

## Enable Interactivity (required for App Home edit buttons)

1. Navigate to **Interactivity & Shortcuts**
2. Toggle **Interactivity** to On
3. Set **Request URL** to:
   ```
   https://scottai.trackslife.com/webhook/slack-interactive
   ```
   This handles button clicks and modal submissions from the App Home settings panel.

## Install to Workspace

1. Navigate to **Install App**
2. Click **Install to Workspace**
3. Review permissions and click **Allow**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

## Configure n8n

Add a new credential in n8n:

1. Go to **Credentials** → **Add Credential**
2. Select **Slack API**
3. Paste your Bot User OAuth Token
4. Test the connection

## Dynamic Bot Name/Avatar

The key feature enabling personalized assistant names is the `chat:write.customize` scope. When sending messages via the Slack API, include these optional parameters:

```json
{
  "channel": "U12345678",
  "text": "Your pipeline briefing...",
  "username": "ScottAI",
  "icon_emoji": ":robot_face:"
}
```

Or with a custom avatar URL:
```json
{
  "channel": "U12345678",
  "text": "Your pipeline briefing...",
  "username": "Luna",
  "icon_url": "https://your-cdn.com/avatars/luna.png"
}
```

The bot will appear to the user with whatever name and avatar you specify, creating the illusion of a personalized assistant.

## Testing

1. In Slack, start a DM with your bot
2. Send any message
3. The onboarding flow should trigger and ask for a name
4. Reply with a name to complete onboarding

## Troubleshooting

### Bot doesn't respond to DMs
- Check Event Subscriptions are enabled
- Verify the webhook URL is correct and accessible
- Check n8n execution logs for errors

### Messages show default bot name
- Verify `chat:write.customize` scope is added
- Reinstall the app after adding new scopes
- Check that `username` is being passed in the API call

### "missing_scope" error
- Go to OAuth & Permissions
- Add the missing scope
- Reinstall the app to your workspace

## Production Considerations

### For Customer Workspaces (OAuth)

When deploying to customer workspaces, you'll need full OAuth:

1. Enable **OAuth 2.0** in your Slack app settings
2. Add **Redirect URLs** for your auth flow
3. Store tokens securely per-tenant in Supabase
4. Handle token refresh

### Rate Limits

Slack API rate limits to consider:
- `chat.postMessage`: Tier 2 (20+ per minute)
- `users.info`: Tier 2

For high-volume usage, implement queuing in n8n.

### Avatar CDN

Consider hosting assistant avatars on a CDN for consistent branding:
- Default avatars for common names
- Allow orgs to upload custom avatars
- Fallback to emoji if URL fails
