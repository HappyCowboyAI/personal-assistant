-- Deal state snapshots for Opportunity Insights state-change alerts
-- Each day's classification run stores a snapshot per deal
-- Transitions (classification changes) trigger proactive alerts

CREATE TABLE deal_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opportunity_crm_id TEXT NOT NULL,
    opportunity_name TEXT NOT NULL,
    account_name TEXT,
    owner_name TEXT,
    classification TEXT NOT NULL
        CHECK (classification IN ('stalled', 'risk', 'healthy', 'accelerating')),
    engagement_level NUMERIC,
    days_in_stage INTEGER,
    metrics JSONB DEFAULT '{}',
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(opportunity_crm_id, snapshot_date)
);

CREATE INDEX idx_deal_snapshots_date ON deal_snapshots(snapshot_date DESC);
CREATE INDEX idx_deal_snapshots_crm ON deal_snapshots(opportunity_crm_id, snapshot_date DESC);
CREATE INDEX idx_deal_snapshots_owner ON deal_snapshots(owner_name, snapshot_date DESC);
