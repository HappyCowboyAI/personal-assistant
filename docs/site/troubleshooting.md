# Troubleshooting

Common issues and how to resolve them, organized by integration point.

## Slack Issues

### Bot doesn't respond to DMs

1. Check that the **Slack Events Handler** workflow is active in n8n
2. Verify Event Subscriptions are enabled in your Slack app settings
3. Confirm the webhook URL (`https://your-n8n-instance.com/webhook/slack-events`) is correct and accessible
4. Check n8n execution logs for incoming events
5. Ensure the `message.im` bot event is subscribed

### Messages show the default bot name instead of the assistant name

1. Verify the `chat:write.customize` scope is added to your Slack app
2. **Reinstall the app** after adding new scopes (scope changes require reinstallation)
3. Check that the `username` parameter is being passed in Slack API calls
4. Verify the user has an `assistant_name` value in the database

### "missing_scope" error

1. Go to **OAuth & Permissions** in your Slack app settings
2. Add the missing scope
3. Reinstall the app to your workspace

### Slash command times out

Slack requires a response within 3 seconds. The workflow must acknowledge the command immediately before running the agent.

1. Check that the "Acknowledge" node runs before the agent node
2. Verify the webhook URL for the slash command matches the n8n workflow

## Database Issues

### Migration fails

1. Ensure you're running PostgreSQL 13 or later
2. Check that `gen_random_uuid()` is available (requires the `pgcrypto` extension on older versions):
   ```sql
   CREATE EXTENSION IF NOT EXISTS pgcrypto;
   ```
3. Run the migrations in order: core schema first, then role-based digest additions

### Queries return empty results with RLS enabled

If Row-Level Security is enabled but the API requests aren't setting the organization context:

1. Verify your REST API layer passes the organization ID
2. For service-level access (n8n workflows), use a service role key that bypasses RLS
3. Check the RLS policies match your authentication approach

## n8n Issues

### Workflow doesn't trigger on schedule

1. Check that the workflow is **Active** (toggle in top-right)
2. Verify the timezone setting matches your intended schedule
3. Check n8n system logs for scheduler errors
4. For manual testing, click **Execute Workflow** to run immediately

### Credential errors

1. Open the workflow and click on nodes with yellow warning triangles
2. Select the correct credential for each node
3. Test the credential connection using n8n's built-in test button
4. For HTTP Request nodes, verify the auth type matches (Header Auth vs. Multi-Header Auth)

### Webhook not receiving events

1. Ensure your n8n instance has a **public HTTPS URL**
2. Check that the webhook path in n8n matches the URL configured in Slack
3. Test the webhook with a curl request:
   ```bash
   curl -X POST https://your-n8n-instance.com/webhook/slack-events \
     -H "Content-Type: application/json" \
     -d '{"type": "url_verification", "challenge": "test"}'
   ```
4. You should receive the challenge string back

## People.ai Issues

### Authentication failures (401)

1. **Query API (OAuth):** Verify the client ID and secret are correct. Request a new token to test:
   ```bash
   curl -X POST https://api.people.ai/v3/auth/tokens \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "client_id=your-client-id&client_secret=your-client-secret&grant_type=client_credentials"
   ```
2. **MCP endpoint:** Verify the multi-header authentication values with your People.ai account team

### Query API returns empty data

1. Confirm your service account has access to the relevant data
2. Check the export filter — ensure `ootb_opportunity_is_closed` is set to `false` for open opportunities
3. Verify the column slugs in the export request match the People.ai schema

### MCP connection fails in agent node

1. Verify the MCP endpoint URL is correct (`https://mcp.people.ai/mcp` or the canary endpoint)
2. Check that the credential type is **HTTP Multiple Headers Auth** (not single header)
3. Ensure the n8n node's `endpointUrl` field is set (not `url`)

## Common Scenarios

### Digest not arriving

1. Is the user's `onboarding_state` set to `complete`?
2. Is `digest_enabled` set to `true`?
3. Does the user have a valid `slack_user_id`?
4. Check the Sales Digest execution log in n8n for errors on that user

### Onboarding stuck

| Symptom | Check |
|---------|-------|
| No greeting received | Is the Slack Events Handler active? Is `message.im` subscribed? |
| Greeting received but no name prompt | Check the routing logic in the Switch node |
| Name saved but no emoji prompt | Check the node connecting name capture to emoji prompt |
| State shows `complete` but no digests | Check `digest_enabled` and that the Sales Digest workflow is active |

### How to re-trigger a digest manually

1. Open the Sales Digest workflow in n8n
2. Click **Execute Workflow**
3. This runs the full digest for all active users

To trigger for a single user, you can also use the On-Demand Digest sub-workflow if it's configured.

## Getting Help

If you're stuck after working through this page:

1. Check the n8n execution logs — they show the full data flow for each run
2. Verify each integration independently (Slack, database, People.ai, Claude)
3. Contact your People.ai account team for API access issues
