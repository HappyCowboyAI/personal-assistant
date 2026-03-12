-- Migration 005: Add focus column to users table
-- focus controls the briefing lens: revenue (default), retention, technical, executive

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS focus VARCHAR(20) DEFAULT 'revenue';

ALTER TABLE users
  DROP CONSTRAINT IF EXISTS users_focus_check;

ALTER TABLE users
  ADD CONSTRAINT users_focus_check
  CHECK (focus IN ('revenue', 'retention', 'technical', 'executive'));

COMMENT ON COLUMN users.focus IS 'Briefing lens: revenue (new logo/ARR), retention (renewals only), technical (POC/SE view), executive (strategic overview)';
