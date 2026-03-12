-- Role-based digest customization
-- Adds department/division from Slack profile and digest_scope for briefing type

ALTER TABLE users
  ADD COLUMN department TEXT,
  ADD COLUMN division TEXT,
  ADD COLUMN digest_scope TEXT DEFAULT 'my_deals'
    CHECK (digest_scope IN ('my_deals', 'team_deals', 'top_pipeline'));

CREATE INDEX idx_users_digest_scope ON users(digest_scope);

-- Backfill existing users
UPDATE users SET department = 'Sales', division = 'Account Executive', digest_scope = 'my_deals'
WHERE email LIKE '%@people.ai';
