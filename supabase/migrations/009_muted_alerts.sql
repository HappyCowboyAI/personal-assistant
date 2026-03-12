-- 009_muted_alerts.sql
-- Muted alerts table + dead account severity support

CREATE TABLE IF NOT EXISTS muted_alerts (
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

-- Partial index for active mute lookups
CREATE INDEX IF NOT EXISTS idx_muted_alerts_active
  ON muted_alerts(user_id, alert_type_id, entity_name)
  WHERE unmuted_at IS NULL;

-- Expand severity CHECK to include 'dead'
ALTER TABLE alert_history DROP CONSTRAINT IF EXISTS alert_history_severity_check;
ALTER TABLE alert_history ADD CONSTRAINT alert_history_severity_check
  CHECK (severity IN ('info', 'warning', 'critical', 'dead'));

-- Update silence_contract severity levels
UPDATE alert_types
SET severity_levels = '[
  {"level": "info", "threshold": 5, "label": "Getting quiet"},
  {"level": "warning", "threshold": 10, "label": "Gone silent"},
  {"level": "critical", "threshold": 21, "label": "Relationship at risk"},
  {"level": "dead", "threshold": 60, "label": "Likely lost"}
]'::jsonb
WHERE id = 'silence_contract';
