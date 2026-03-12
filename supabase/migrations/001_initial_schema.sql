-- People.ai Personal Assistant - Consolidated Schema
-- Designed for multi-tenancy from day one
-- Includes: core tables, assistant emoji, assistant persona

-- Organizations (customers)
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    default_assistant_name TEXT DEFAULT 'Aria',
    default_assistant_emoji TEXT DEFAULT ':robot_face:',
    default_assistant_persona TEXT DEFAULT 'direct, action-oriented, conversational',
    default_assistant_avatar_url TEXT,
    peopleai_api_key_encrypted TEXT,
    slack_workspace_id TEXT,
    slack_bot_token_encrypted TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users (sales reps)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    slack_user_id TEXT,
    peopleai_user_id TEXT,
    assistant_name TEXT,          -- NULL = use org default
    assistant_emoji TEXT,         -- NULL = use org default
    assistant_persona TEXT,       -- NULL = use org default (freeform personality description)
    assistant_avatar_url TEXT,    -- NULL = use org default
    timezone TEXT DEFAULT 'America/Los_Angeles',
    digest_enabled BOOLEAN DEFAULT TRUE,
    digest_time TIME DEFAULT '06:00:00',
    meeting_prep_enabled BOOLEAN DEFAULT TRUE,
    meeting_prep_minutes_before INTEGER DEFAULT 120,
    onboarding_state TEXT DEFAULT 'new', -- 'new', 'awaiting_name', 'awaiting_emoji', 'complete'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, email),
    UNIQUE(organization_id, slack_user_id)
);

-- Message history (for context and debugging)
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    message_type TEXT NOT NULL, -- 'digest', 'meeting_prep', 'follow_up_draft', 'alert', 'conversation', 'slash_command'
    channel TEXT NOT NULL,      -- 'slack', 'email'
    direction TEXT DEFAULT 'outbound', -- 'inbound' (user message) or 'outbound' (assistant message)
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pending actions (drafts awaiting approval)
CREATE TABLE pending_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL, -- 'send_email', 'update_crm'
    opportunity_id TEXT,       -- People.ai opportunity ID
    draft_content TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'expired'
    slack_message_ts TEXT,    -- for updating the message after action
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    resolved_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_users_slack ON users(slack_user_id);
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_messages_user ON messages(user_id, sent_at DESC);
CREATE INDEX idx_messages_type ON messages(user_id, message_type);
CREATE INDEX idx_pending_actions_user ON pending_actions(user_id, status);

-- Updated at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Helper: get effective assistant name for a user
-- Resolution: user override → org default → 'Aria'
CREATE OR REPLACE FUNCTION get_assistant_name(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_name TEXT;
    v_org_name TEXT;
BEGIN
    SELECT u.assistant_name, o.default_assistant_name
    INTO v_user_name, v_org_name
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;

    RETURN COALESCE(v_user_name, v_org_name, 'Aria');
END;
$$ LANGUAGE plpgsql;

-- Helper: get effective assistant emoji for a user
-- Resolution: user override → org default → ':robot_face:'
CREATE OR REPLACE FUNCTION get_assistant_emoji(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_emoji TEXT;
    v_org_emoji TEXT;
BEGIN
    SELECT u.assistant_emoji, o.default_assistant_emoji
    INTO v_user_emoji, v_org_emoji
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;

    RETURN COALESCE(v_user_emoji, v_org_emoji, ':robot_face:');
END;
$$ LANGUAGE plpgsql;

-- Helper: get effective assistant persona for a user
-- Resolution: user override → org default → generic fallback
CREATE OR REPLACE FUNCTION get_assistant_persona(p_user_id UUID)
RETURNS TEXT AS $$
DECLARE
    v_user_persona TEXT;
    v_org_persona TEXT;
BEGIN
    SELECT u.assistant_persona, o.default_assistant_persona
    INTO v_user_persona, v_org_persona
    FROM users u
    JOIN organizations o ON u.organization_id = o.id
    WHERE u.id = p_user_id;

    RETURN COALESCE(v_user_persona, v_org_persona, 'direct, action-oriented, conversational');
END;
$$ LANGUAGE plpgsql;
