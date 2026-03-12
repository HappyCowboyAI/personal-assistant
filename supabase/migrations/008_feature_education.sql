-- Migration 008: Progressive Feature Education
-- Tracks feature adoption and education delivery history.
-- Enables the assistant to teach users about features over time:
--   - Onboarding drip (first 2 weeks)
--   - Re-engagement nudges (feature dormant 14+ days)
--   - New feature announcements (one-time push)

-- ============================================================
-- Feature Catalog
-- ============================================================
-- Registry of features the assistant can teach users about.

CREATE TABLE feature_catalog (
    id TEXT PRIMARY KEY,                -- e.g. 'dm_conversation', 'meeting_brief'
    display_name TEXT NOT NULL,         -- e.g. 'Ask Me Anything'
    description TEXT NOT NULL,          -- What it does (for Claude to rephrase)
    how_to_use TEXT NOT NULL,           -- Command or trigger
    category TEXT NOT NULL              -- 'core', 'productivity', 'customization'
        CHECK (category IN ('core', 'productivity', 'customization')),
    drip_order INTEGER,                 -- NULL = not part of onboarding drip; 1-5 = sequence
    drip_day INTEGER,                   -- Day after onboarding to send (e.g. 1, 2, 3, 5, 7)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Feature Usage Tracking
-- ============================================================
-- One row per user per feature. Updated on first/subsequent use.

CREATE TABLE feature_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_id TEXT NOT NULL REFERENCES feature_catalog(id),
    first_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    use_count INTEGER NOT NULL DEFAULT 1,
    UNIQUE(user_id, feature_id)
);

CREATE INDEX idx_feature_usage_user ON feature_usage(user_id);

-- ============================================================
-- Education Log
-- ============================================================
-- Every tip/announcement sent. Used for dedup + pacing.

CREATE TABLE education_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    feature_id TEXT NOT NULL REFERENCES feature_catalog(id),
    trigger_type TEXT NOT NULL           -- 'onboarding_drip', 're_engagement', 'announcement'
        CHECK (trigger_type IN ('onboarding_drip', 're_engagement', 'announcement')),
    message_text TEXT,                   -- What was actually sent
    slack_message_ts TEXT,
    slack_channel_id TEXT,
    delivered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_education_log_user ON education_log(user_id, delivered_at DESC);
CREATE INDEX idx_education_log_dedup ON education_log(user_id, feature_id, trigger_type);

-- ============================================================
-- Upsert helper for feature usage tracking
-- ============================================================

CREATE OR REPLACE FUNCTION track_feature_usage(p_user_id UUID, p_feature_id TEXT)
RETURNS void AS $$
BEGIN
  INSERT INTO feature_usage (user_id, feature_id, first_used_at, last_used_at, use_count)
  VALUES (p_user_id, p_feature_id, NOW(), NOW(), 1)
  ON CONFLICT (user_id, feature_id)
  DO UPDATE SET last_used_at = NOW(), use_count = feature_usage.use_count + 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- User preference columns
-- ============================================================

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS tips_enabled BOOLEAN DEFAULT TRUE;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS announcements_enabled BOOLEAN DEFAULT TRUE;

COMMENT ON COLUMN users.tips_enabled IS 'Whether onboarding drip and re-engagement tips are enabled (stop tips)';
COMMENT ON COLUMN users.announcements_enabled IS 'Whether new feature announcements are enabled (stop announcements)';

-- ============================================================
-- Seed: Feature Catalog
-- ============================================================

-- Onboarding drip features (sent in sequence during first 2 weeks)
INSERT INTO feature_catalog (id, display_name, description, how_to_use, category, drip_order, drip_day) VALUES
('dm_conversation', 'Ask Me Anything',
 'Ask questions about any account, deal, or contact directly in DM — I''ll pull live data from People.ai.',
 'Just DM me a question like "what''s happening with AMD?"',
 'core', 1, 1),

('meeting_brief', 'Meeting Briefs',
 'Get a contextual briefing before customer meetings — engagement history, open deals, key contacts.',
 'Type "brief" or I''ll auto-send one 2 hours before your meetings.',
 'core', 2, 2),

('backstory', 'Backstory (/bs)',
 'Ask me about any account from any Slack channel using the /bs slash command.',
 'Type "/bs what''s the latest with Nvidia?" in any channel.',
 'core', 3, 3),

('persona', 'Personality Customization',
 'Customize how I communicate — casual, formal, witty, data-driven, whatever suits you.',
 'Type "persona casual and witty" or "persona formal and data-driven".',
 'customization', 4, 5),

('followup_draft', 'Follow-up Drafts',
 'After customer meetings, I''ll offer to draft a follow-up email based on the meeting context.',
 'I''ll prompt you after meetings — just click "Draft Follow-up" when you see it.',
 'productivity', 5, 7);

-- Non-drip features (re-engagement only)
INSERT INTO feature_catalog (id, display_name, description, how_to_use, category) VALUES
('rename', 'Rename Me',
 'Change my display name to whatever you want.',
 'Type "rename Luna" or whatever name you prefer.',
 'customization'),

('emoji', 'Change My Emoji',
 'Change the emoji that appears with my messages.',
 'Type "emoji :star:" or any emoji you like.',
 'customization'),

('digest', 'Morning Digest',
 'Your daily pipeline briefing delivered every morning at 6am.',
 'It''s automatic! Type "stop digest" to pause or "resume digest" to restart.',
 'core'),

('silence_alerts', 'Silence Alerts',
 'I''ll warn you when key accounts go quiet — no emails, meetings, or calls for extended periods.',
 'Automatic — I''ll DM you when I detect engagement gaps.',
 'productivity'),

('stakeholders', 'Stakeholder Map',
 'See who''s engaged on a deal and who you need to reach.',
 'Type "stakeholders" followed by a deal or account name.',
 'productivity'),

('insights', 'Pipeline Insights',
 'Deep analysis of your pipeline health, deal velocity, and risk areas.',
 'Type "insights" for a full pipeline analysis.',
 'productivity'),

('focus', 'Digest Focus',
 'Focus your morning digest on specific accounts or themes.',
 'Type "focus AMD, Nvidia" to prioritize those accounts.',
 'customization');
