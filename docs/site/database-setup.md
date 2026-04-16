# Database Setup

The assistant uses a PostgreSQL database for multi-tenant user data, message history, and pending actions. Any PostgreSQL-compatible database works (Supabase, AWS RDS, Google Cloud SQL, self-hosted, etc.).

## Requirements

- PostgreSQL 13 or later
- Ability to create tables, indexes, triggers, and functions
- A **REST API layer** is recommended for integration with n8n (e.g., PostgREST, Supabase, Hasura). Direct PostgreSQL connections also work via n8n's Postgres node.

## Schema Overview

| Table | Purpose |
|-------|---------|
| `organizations` | Customer/tenant records with default assistant settings |
| `users` | Sales rep profiles, assistant preferences, onboarding state |
| `messages` | Delivery log for all assistant messages (inbound + outbound) |
| `pending_actions` | Drafts awaiting user approval (emails, CRM updates) |

## Run the Schema Migration

Execute the following SQL against your PostgreSQL database.

### Core Tables

```sql
-- Organizations (customers/tenants)
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
    assistant_name TEXT,
    assistant_emoji TEXT,
    assistant_persona TEXT,
    assistant_avatar_url TEXT,
    timezone TEXT DEFAULT 'America/Los_Angeles',
    digest_enabled BOOLEAN DEFAULT TRUE,
    digest_time TIME DEFAULT '06:00:00',
    meeting_prep_enabled BOOLEAN DEFAULT TRUE,
    meeting_prep_minutes_before INTEGER DEFAULT 120,
    onboarding_state TEXT DEFAULT 'new',
    department TEXT,
    division TEXT,
    digest_scope TEXT DEFAULT 'my_deals'
        CHECK (digest_scope IN ('my_deals', 'team_deals', 'top_pipeline')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(organization_id, email),
    UNIQUE(organization_id, slack_user_id)
);

-- Message history
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    message_type TEXT NOT NULL,
    channel TEXT NOT NULL,
    direction TEXT DEFAULT 'outbound',
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pending actions (drafts awaiting approval)
CREATE TABLE pending_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    opportunity_id TEXT,
    draft_content TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    slack_message_ts TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    resolved_at TIMESTAMPTZ
);
```

### Indexes

```sql
CREATE INDEX idx_users_slack ON users(slack_user_id);
CREATE INDEX idx_users_org ON users(organization_id);
CREATE INDEX idx_users_digest_scope ON users(digest_scope);
CREATE INDEX idx_messages_user ON messages(user_id, sent_at DESC);
CREATE INDEX idx_messages_type ON messages(user_id, message_type);
CREATE INDEX idx_pending_actions_user ON pending_actions(user_id, status);
```

### Auto-Update Trigger

```sql
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
```

### Helper Functions

These functions implement the assistant identity resolution chain: user override → org default → hardcoded fallback.

```sql
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
```

## Seed Data

After running the migration, seed your first organization:

```sql
INSERT INTO organizations (name, slug, default_assistant_name)
VALUES ('Your Company', 'your-company', 'Aria');
```

Add yourself as a test user:

```sql
INSERT INTO users (organization_id, email, slack_user_id)
SELECT id, 'admin@yourcompany.com', 'U0EXAMPLE'
FROM organizations WHERE slug = 'your-company';
```

> To find your Slack user ID: click your profile in Slack → "..." menu → "Copy member ID".

## Row-Level Security

For production multi-tenant deployments, enable Row-Level Security (RLS) to ensure data isolation between organizations:

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users scoped to organization"
  ON users FOR ALL
  USING (organization_id = current_setting('app.current_org_id')::uuid);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Messages scoped to user's organization"
  ON messages FOR ALL
  USING (user_id IN (
    SELECT id FROM users
    WHERE organization_id = current_setting('app.current_org_id')::uuid
  ));
```

> The specific RLS implementation depends on your database provider and authentication layer. The examples above use PostgreSQL session variables — adapt to your setup (Supabase auth, Hasura permissions, application-level filtering, etc.).

## Column Reference

### `users` Table — Key Fields

| Column | Type | Description |
|--------|------|-------------|
| `onboarding_state` | TEXT | `new` → `awaiting_name` → `awaiting_emoji` → `complete` |
| `assistant_name` | TEXT | User's chosen name (NULL = use org default) |
| `assistant_emoji` | TEXT | User's chosen emoji (NULL = use org default) |
| `assistant_persona` | TEXT | Freeform personality description (NULL = use org default) |
| `digest_enabled` | BOOLEAN | Whether the user receives daily digests |
| `digest_scope` | TEXT | `my_deals` (IC), `team_deals` (Manager), `top_pipeline` (Exec) |
| `department` | TEXT | From Slack profile — used for digest scope detection |
| `division` | TEXT | From Slack profile — used for role inference |

### `messages` Table — Message Types

| `message_type` | Description |
|----------------|-------------|
| `digest` | Daily pipeline briefing |
| `meeting_prep` | Pre-meeting intelligence packet |
| `follow_up_draft` | Re-engagement email draft |
| `alert` | Proactive risk/silence alert |
| `conversation` | Multi-turn thread message |
| `slash_command` | `/bs` command response |
