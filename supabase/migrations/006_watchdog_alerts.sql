-- Watchdog Framework: Proactive alert system
-- Unified lifecycle: Monitor → Detect → Deduplicate → Deliver → Track
-- First alert type: Silence Contracts (engagement gaps on key accounts)

-- ============================================================
-- Alert Types Registry
-- ============================================================
-- Each row defines a category of alert the system can fire.
-- Thresholds and templates live here so they're tunable without
-- code changes.

CREATE TABLE alert_types (
    id TEXT PRIMARY KEY,                -- e.g. 'silence_contract', 'deal_momentum', 'meeting_prep'
    display_name TEXT NOT NULL,         -- e.g. 'Silence Contract'
    description TEXT,
    category TEXT NOT NULL              -- 'engagement', 'pipeline', 'meeting'
        CHECK (category IN ('engagement', 'pipeline', 'meeting', 'custom')),
    default_enabled BOOLEAN DEFAULT TRUE,
    severity_levels JSONB NOT NULL      -- e.g. [{"level":"info","days":5}, {"level":"warning","days":10}, {"level":"critical","days":21}]
        DEFAULT '[]',
    cooldown_hours INTEGER DEFAULT 72,  -- min hours between re-alerts for same entity
    monitor_schedule TEXT DEFAULT 'daily', -- 'rapid' (15min), 'daily', 'weekly'
    prompt_template TEXT,               -- Claude prompt template for generating alert text
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER alert_types_updated_at
    BEFORE UPDATE ON alert_types
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Alert History
-- ============================================================
-- Every fired alert gets a row. Used for deduplication, tracking
-- delivery, and analytics (how often do users act on alerts?).

CREATE TABLE alert_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type_id TEXT NOT NULL REFERENCES alert_types(id),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id UUID NOT NULL REFERENCES organizations(id),

    -- What entity triggered the alert
    entity_type TEXT NOT NULL           -- 'account', 'opportunity', 'contact'
        CHECK (entity_type IN ('account', 'opportunity', 'contact')),
    entity_id TEXT NOT NULL,            -- CRM ID of the entity
    entity_name TEXT NOT NULL,          -- Human-readable name

    severity TEXT NOT NULL              -- 'info', 'warning', 'critical'
        CHECK (severity IN ('info', 'warning', 'critical')),
    title TEXT NOT NULL,                -- Short alert headline
    body TEXT,                          -- Full alert text (Slack-formatted)

    -- Detection context
    detection_data JSONB DEFAULT '{}',  -- Raw signals that triggered the alert
                                        -- e.g. {"days_silent": 14, "last_activity": "2026-02-17", "activity_type": "email"}

    -- Delivery tracking
    delivered_at TIMESTAMPTZ,
    delivery_channel TEXT DEFAULT 'slack',
    slack_message_ts TEXT,              -- For threading follow-ups
    slack_channel_id TEXT,

    -- User response
    status TEXT DEFAULT 'pending'       -- 'pending', 'delivered', 'acknowledged', 'acted', 'dismissed', 'expired'
        CHECK (status IN ('pending', 'delivered', 'acknowledged', 'acted', 'dismissed', 'expired')),
    user_action TEXT,                   -- What the user did (freeform)
    resolved_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER alert_history_updated_at
    BEFORE UPDATE ON alert_history
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Fast lookups
CREATE INDEX idx_alert_history_user
    ON alert_history(user_id, created_at DESC);

CREATE INDEX idx_alert_history_dedup
    ON alert_history(alert_type_id, user_id, entity_id, created_at DESC);

CREATE INDEX idx_alert_history_pending
    ON alert_history(user_id, status)
    WHERE status IN ('pending', 'delivered');

CREATE INDEX idx_alert_history_entity
    ON alert_history(entity_type, entity_id, created_at DESC);

-- ============================================================
-- User Alert Preferences
-- ============================================================
-- Per-user opt-in/out and threshold overrides for each alert type.
-- If no row exists, the alert_type defaults apply.

CREATE TABLE user_alert_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type_id TEXT NOT NULL REFERENCES alert_types(id),
    enabled BOOLEAN DEFAULT TRUE,
    min_severity TEXT DEFAULT 'info'    -- Only deliver alerts at or above this level
        CHECK (min_severity IN ('info', 'warning', 'critical')),
    custom_thresholds JSONB,            -- Override severity_levels from alert_type
    delivery_method TEXT DEFAULT 'dm'   -- 'dm', 'digest', 'both'
        CHECK (delivery_method IN ('dm', 'digest', 'both')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, alert_type_id)
);

CREATE TRIGGER user_alert_preferences_updated_at
    BEFORE UPDATE ON user_alert_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Seed: Silence Contract alert type
-- ============================================================

INSERT INTO alert_types (id, display_name, description, category, severity_levels, cooldown_hours, monitor_schedule, prompt_template)
VALUES (
    'silence_contract',
    'Silence Contract',
    'Detects when key accounts or contacts go quiet — no emails, meetings, or calls for an extended period.',
    'engagement',
    '[
        {"level": "info",     "days": 5,  "label": "Getting quiet"},
        {"level": "warning",  "days": 10, "label": "Gone silent"},
        {"level": "critical", "days": 21, "label": "Relationship at risk"}
    ]'::jsonb,
    72,     -- 3-day cooldown between re-alerts for same entity
    'daily',
    'You are a sales intelligence assistant analyzing engagement gaps.

Given the following silence detection:
- Account: {{account_name}}
- Last activity: {{last_activity_date}} ({{days_silent}} days ago)
- Activity type: {{last_activity_type}}
- Severity: {{severity}} — {{severity_label}}
- Open opportunities: {{open_opps}}

Write a brief, actionable Slack alert (3-4 sentences max) that:
1. States the silence period clearly
2. Notes what the last interaction was
3. Suggests a specific next step based on the deal context
4. Uses Slack formatting (*bold*, bullet points)

Tone: direct and helpful, not alarmist. This is a nudge, not a fire alarm.'
);

-- ============================================================
-- Seed: Deal Momentum alert type
-- ============================================================

INSERT INTO alert_types (id, display_name, description, category, severity_levels, cooldown_hours, monitor_schedule)
VALUES (
    'deal_momentum',
    'Deal Momentum',
    'Detects significant changes in deal velocity — stalled deals, accelerating deals, or stage regression.',
    'pipeline',
    '[
        {"level": "info",     "signal": "stage_advance",     "label": "Deal advancing"},
        {"level": "warning",  "signal": "stalled_7d",        "label": "Deal stalling"},
        {"level": "critical", "signal": "stage_regression",  "label": "Deal regressed"}
    ]'::jsonb,
    48,
    'daily'
);

-- ============================================================
-- Seed: Meeting Prep alert type
-- ============================================================

INSERT INTO alert_types (id, display_name, description, category, severity_levels, cooldown_hours, monitor_schedule)
VALUES (
    'meeting_prep',
    'Pre-Meeting Brief',
    'Delivers a contextual briefing before customer meetings — engagement history, open deals, recent activity.',
    'meeting',
    '[
        {"level": "info", "minutes_before": 120, "label": "Meeting in 2 hours"}
    ]'::jsonb,
    0,      -- No cooldown — each meeting gets its own alert
    'rapid'
);
