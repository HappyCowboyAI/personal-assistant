-- Multi-turn conversation support
-- New table for tracking active conversations across Slack threads
-- Plus additions to messages table for conversation linking

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    slack_channel_id TEXT NOT NULL,
    slack_thread_ts  TEXT NOT NULL,
    workflow_type    TEXT NOT NULL,
    agent_config     JSONB DEFAULT '{}',
    status           TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'processing', 'completed', 'expired')),
    turn_count       INTEGER NOT NULL DEFAULT 1,
    max_turns        INTEGER NOT NULL DEFAULT 10,
    expires_at       TIMESTAMPTZ NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(slack_channel_id, slack_thread_ts)
);

-- Fast lookup for active conversation by thread
CREATE INDEX idx_conversations_active
    ON conversations(slack_channel_id, slack_thread_ts)
    WHERE status IN ('active', 'processing');

-- Lookup by user for debugging/admin
CREATE INDEX idx_conversations_user
    ON conversations(user_id, created_at DESC);

-- Add conversation linking to messages table
ALTER TABLE messages
    ADD COLUMN conversation_id UUID REFERENCES conversations(id),
    ADD COLUMN slack_thread_ts TEXT,
    ADD COLUMN role TEXT CHECK (role IN ('user', 'assistant'));

-- Index for loading conversation history
CREATE INDEX idx_messages_conversation
    ON messages(conversation_id, sent_at ASC)
    WHERE conversation_id IS NOT NULL;

-- Reuse existing updated_at trigger for conversations
CREATE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
