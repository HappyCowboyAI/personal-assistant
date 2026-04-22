# Dead Account Detection & Mute System

## Problem

Silence contract alerts fire every time the cooldown expires, even for accounts that are clearly dead (100+ days silent). Users get the same alerts week after week with no way to act on them besides ignoring them.

## Solution

Two mechanisms working together:

1. **Auto-mute dead accounts** — Accounts silent 60+ days get a `dead` severity classification. They alert once, then auto-mute so they never fire again.
2. **Interactive overflow menus** — Every alerted account gets a `[...]` overflow menu with: Snooze 7d, Snooze 30d, Mark as Lost. Users can manage alerts directly from Slack.

## Database

### Migration `009_muted_alerts.sql` (already applied to Supabase)

```sql
CREATE TABLE muted_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id),
  organization_id UUID NOT NULL REFERENCES organizations(id),
  alert_type_id TEXT NOT NULL REFERENCES alert_types(id),
  entity_name TEXT NOT NULL,
  mute_reason TEXT NOT NULL,  -- 'marked_lost', 'snoozed', 'auto_dead'
  muted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  muted_until TIMESTAMPTZ,    -- NULL = permanent, date = snooze expiry
  unmuted_at TIMESTAMPTZ,     -- set when auto-unmuted by activity
  UNIQUE(user_id, alert_type_id, entity_name)
);

CREATE INDEX idx_muted_alerts_active
  ON muted_alerts(user_id, alert_type_id, entity_name)
  WHERE unmuted_at IS NULL;
```

### Additional schema changes (include in `009_muted_alerts.sql`)

```sql
-- Expand severity CHECK to include 'dead'
ALTER TABLE alert_history DROP CONSTRAINT alert_history_severity_check;
ALTER TABLE alert_history ADD CONSTRAINT alert_history_severity_check
  CHECK (severity IN ('info', 'warning', 'critical', 'dead'));

-- Update silence_contract alert type severity levels
UPDATE alert_types
SET severity_levels = '[
  {"level": "info", "threshold": 5, "label": "Getting quiet"},
  {"level": "warning", "threshold": 10, "label": "Gone silent"},
  {"level": "critical", "threshold": 21, "label": "Relationship at risk"},
  {"level": "dead", "threshold": 60, "label": "Likely lost"}
]'::jsonb
WHERE id = 'silence_contract';
```

- `mute_reason` values: `marked_lost` (user), `snoozed` (user), `auto_dead` (system)
- `muted_until`: NULL for permanent mutes. Timestamp for snoozes.
- `unmuted_at`: Set when activity resumes on a muted account, clearing the mute.
- Active mute query: `WHERE unmuted_at IS NULL AND (muted_until IS NULL OR muted_until > now())`

## Severity Tiers

| Severity | Days Silent | Emoji | Behavior |
|----------|-------------|-------|----------|
| info | 5-9 | :large_blue_circle: | Alert with overflow menu |
| warning | 10-20 | :large_orange_circle: | Alert with overflow menu |
| critical | 21-59 | :red_circle: | Alert with overflow menu |
| dead | 60+ | :skull: | Alert once with overflow menu, then auto-mute |

The agent prompt stays unchanged (it only knows info/warning/critical). The `dead` classification is applied **post-agent** in the Parse & Dedup Code node by reclassifying any `critical` account with 60+ days silent.

## Alert Message Format

Block Kit sections, one line per account with overflow accessory:

```
:skull: *Elastic* — 169 days silent (last: meeting on 2025-09-23)   [...]
:red_circle: *Cyberhaven* — 49 days silent (last: email on 2026-01-20)      [...]
:large_blue_circle: *Vialytics Germany* — 7 days silent                              [...]
```

Overflow menu options per account:
- Snooze 7d (`silence_snooze_7d`)
- Snooze 30d (`silence_snooze_30d`)
- Mark as Lost (`silence_mark_lost`)

Button value: compact format `s7|AccountName`, `s30|AccountName`, `ml|AccountName` (max 75 chars per Slack limit).

`userId` and `organizationId` are derived from the Interactive Events Handler's existing `Lookup User (Action)` node, which fetches the DB user record from the Slack user ID in the payload.

## Button Responses

| Action | Mute row | Confirmation message |
|--------|----------|---------------------|
| Snooze 7d | reason: `snoozed`, muted_until: now+7d | `:white_check_mark: *Elastic* snoozed for 7 days.` |
| Snooze 30d | reason: `snoozed`, muted_until: now+30d | `:white_check_mark: *Elastic* snoozed for 30 days.` |
| Mark as Lost | reason: `marked_lost`, muted_until: NULL | `:white_check_mark: *Elastic* muted — consider closing the open opps in Salesforce.` |

### Response strategy

On overflow action, the Interactive Events Handler receives `payload.message.blocks` (the full original Block Kit message). The handler rebuilds the blocks array with the actioned account's section replaced by the confirmation text, then sends `chat.update` with the full rebuilt blocks. This preserves all other account lines in the message.

## Workflow Changes

### Silence Contract Monitor cron (`6FsYIe3tYj0HfRY2`)

**Parse & Dedup** — Modified:
- Fetch active mutes from Supabase REST (`GET /rest/v1/muted_alerts?user_id=eq.{}&alert_type_id=eq.silence_contract&unmuted_at=is.null`) before filtering
- Filter out muted accounts (also check `muted_until` expiry for snoozes)
- Reclassify accounts with `days_silent >= 60` from `critical` to `dead` (post-agent)
- Auto-insert `muted_alerts` row (reason: `auto_dead`) for `dead` accounts via HTTP Request POST to Supabase REST (`/rest/v1/muted_alerts`, `Prefer: return=representation`, credential: `supabaseApi`)

**Build Alert Message** — Modified:
- Switch from plain text to Block Kit sections
- Each account: section block with overflow accessory menu (3 options)
- Footer block with help text

**Send Alert DM** — Modified:
- Change from `text` param to `blocks` param

### On-Demand Silence Check (`7QaWpTuTp6oNVFjM`)

**Parse Silence Results** — Modified:
- Filter out muted accounts, reclassify 60+ as `dead`, auto-mute dead ones

**Build Alert Message** — Modified:
- Add overflow menus (already Block Kit)

### Interactive Events Handler (`JgVjCqoT6ZwGuDL1`)

**Route Action** Switch — Modified:
- Add 1 new output matching `silence_` prefix (routes all 3 actions to a single handler flow)

**Parse Mute Action** (Code node) — New:
- Parse action_id and button value JSON
- Determine mute_reason and muted_until from action_id
- Rebuild message blocks with actioned account line replaced by confirmation
- Output: mute payload + updated blocks

**Upsert Mute** (HTTP Request) — New:
- POST to `https://rhrlnkbphxntxxxcrgvv.supabase.co/rest/v1/muted_alerts`
- Header: `Prefer: resolution=merge-duplicates,return=representation`
- Uses `predefinedCredentialType: supabaseApi` (credential ID: `ASRWWkQ0RSMOpNF1`)

**Update Alert Message** (HTTP Request) — New:
- `chat.update` with rebuilt blocks array from Parse Mute Action

## Auto-Unmute

Deferred to a future iteration. The agent only reports silent accounts — it does not report accounts that have resumed activity. Detecting resumed activity on muted accounts would require a separate mechanism (e.g., a periodic check that queries Backstory for recent activity on muted accounts). For now, users can re-trigger alerts by letting snoozes expire naturally, or activity resumption will be noticed organically.

Snooze expiry is the primary "auto-unmute": when `muted_until` passes, the account returns to normal alerting on the next cron run.
