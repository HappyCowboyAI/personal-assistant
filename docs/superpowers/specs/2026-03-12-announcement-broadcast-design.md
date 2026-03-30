# Announcement Broadcast System

**Date:** 2026-03-12
**Status:** Approved

## Summary

Admin-only system for broadcasting announcements to all users through their personalized assistants. An admin DMs `announce: <message>`, gets a preview with user count, confirms, and Claude personalizes the message for each user's assistant voice before delivery.

## Architecture

Two components following the existing sub-workflow pattern (like On-Demand Digest, On-Demand Silence Check):

1. **Slack Events Handler** — new route for `announce:` command (admin gate + confirmation flow)
2. **Announcement Broadcast** — new sub-workflow for fan-out delivery

## Component 1: Slack Events Handler Route

### Command Format

```
announce: <message text>
```

### Admin Gate

Code node with hardcoded admin Slack IDs:

```javascript
const ADMIN_IDS = ['U061WJ6RMJS']; // Scott
```

Non-admins receive: "Sorry, only admins can send announcements." (delivered via their assistant identity).

### Confirmation Flow

1. Fetch active users from Supabase: `onboarding_state = 'complete'` AND `announcements_enabled = true`
2. If zero users: reply "No users have announcements enabled — nothing to send." and stop
3. Check for existing pending `announcement_broadcast` action for this admin (HTTP Request GET to Supabase REST API: `?user_id=eq.{uuid}&action_type=eq.announcement_broadcast&status=eq.pending`). If found: reply "You already have a pending announcement — reply **send** or **cancel** first."
4. Send preview to admin DM:
   > Will send this announcement to **N users** through their assistants:
   >
   > *Your message:* <raw message text>
   >
   > Reply **send** to confirm or **cancel** to abort.
5. Store pending action via HTTP Request POST to Supabase REST API (`/rest/v1/pending_actions`):
   - `user_id`: admin's DB user UUID (from Lookup User node)
   - `action_type`: `'announcement_broadcast'`
   - `draft_content`: the raw announcement message text
   - `context`: `{ "user_count": N, "admin_slack_id": "U..." }`
   - `status`: `'pending'`
6. On admin's next DM:
   - `send` → call Announcement Broadcast sub-workflow via Execute Workflow, passing the message text. Update pending action `status = 'approved'`. Reply "Sending announcement to N users now."
   - `cancel` → update pending action `status = 'rejected'`. Reply "Announcement cancelled."

### Pending Action Routing in Route by State

The `Route by State` Code node needs a new check **before** command matching. On every incoming DM:

1. HTTP Request GET to Supabase REST API: `?user_id=eq.{uuid}&status=eq.pending&action_type=eq.announcement_broadcast`
2. If a pending action exists:
   - If message text (lowercased, trimmed) is `send` → route to "Confirm Announcement" output
   - If message text is `cancel` → route to "Cancel Announcement" output
   - Otherwise → clear the pending action (set `status = 'expired'`), continue with normal command routing
3. If no pending action → normal routing continues

This adds a Supabase fetch node before `Route by State` and two new Switch outputs for confirm/cancel. The fetch uses the same HTTP Request pattern as the duplicate check.

## Component 2: Announcement Broadcast Sub-workflow

New workflow triggered via Execute Workflow.

**Input:** `{ message: string, admin_channel_id: string }`

Note: This is a fan-out workflow (one message → many users), so it fetches all users itself rather than receiving a single user record like On-Demand Digest.

### Node Flow

1. **Execute Workflow Trigger** — receives announcement message (`inputSource: "passthrough"`)
2. **Fetch Users** — Supabase getAll from `users`
3. **Filter Active + Opted-in** — Code node: `onboarding_state = 'complete'` AND `announcements_enabled = true`
4. **SplitInBatches** — loop through each user
5. **Resolve Identity** — Code node builds `assistantName`, `assistantEmoji`, `persona` per user (same fallback chain: user override → org default → hardcoded fallback)
6. **Personalize via Claude** — Anthropic Chat Model node with prompt:
   > You are {{ assistantName }}. Rephrase this announcement in your voice (personality: {{ persona }}). Keep it concise — 2-3 sentences max. Don't change the core information, just wrap it in your style.
   >
   > Announcement: {{ message }}
7. **Open Bot DM** — Slack `conversations.open` with user's `slack_user_id`
8. **Send Message** — Slack `chat.postMessage` with `username`/`icon_emoji` override per assistant identity
9. **Log to education_log** — HTTP Request POST to Supabase REST API: `trigger_type = 'announcement'`, `feature_id = 'announcement'`, `message_text` = personalized version sent
10. **Loop back** to SplitInBatches output 1

### Error Handling

- Set "Continue On Fail" on the Open Bot DM and Send Message nodes so individual failures don't abort the loop
- If a DM send fails for one user, log the error and continue to the next user

### Completion Notification

After SplitInBatches output 0 ("done"), send a summary message back to the admin:
> "Announcement delivered to N users."

This requires passing the admin's Slack channel ID as part of the sub-workflow input.

## Database Changes

One new seed row in `feature_catalog`:

```sql
INSERT INTO feature_catalog (id, display_name, description, how_to_use, category) VALUES
('announcement', 'Announcements', 'Broadcast messages from admins', 'Admin-only: announce: <message>', 'core');
```

No schema changes required. Uses existing:
- `pending_actions` table for confirmation state
- `education_log` table with `trigger_type = 'announcement'`
- `users.announcements_enabled` column for opt-out

## Slack Events Handler Switch Route

The Switch node currently has outputs 0-15. Add new outputs:
- Output 16: `announce:` command (admin gate + confirmation flow)
- Output 17: Confirm Announcement (`send` when pending action exists)
- Output 18: Cancel Announcement (`cancel` when pending action exists)

Note: Exact output numbers depend on the live workflow state — verify before implementation.

## What's NOT Included (v1)

- Pending action expiry (24hr default from schema; admin can `cancel` manually)
- Rate limiting (admin-only with confirmation is sufficient)
- Announcement targeting (all opted-in users; per-segment targeting is a future enhancement)
- Interactive button confirmation (text-based `send`/`cancel` for v1; could use Slack block_actions via Interactive Events Handler in v2)
- Logging to `messages` table (only `education_log` for v1; could add `message_type: 'announcement'` to `messages` for unified history in v2)
