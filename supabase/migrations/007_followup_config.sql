-- Migration 007: Add follow-up configuration to users table
-- followup_delay_minutes: how long after a meeting to prompt for follow-up (default 30)
-- followup_enabled: whether proactive follow-up prompts are active

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS followup_delay_minutes INTEGER DEFAULT 30;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS followup_enabled BOOLEAN DEFAULT TRUE;

COMMENT ON COLUMN users.followup_delay_minutes IS 'Minutes after meeting end to prompt for follow-up draft (default 30)';
COMMENT ON COLUMN users.followup_enabled IS 'Whether proactive post-meeting follow-up prompts are enabled';
