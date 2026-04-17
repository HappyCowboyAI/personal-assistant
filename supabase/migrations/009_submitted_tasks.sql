-- Task submission dedup for Follow-up Cron
-- Prevents creating duplicate Salesforce Tasks when the same meeting
-- triggers multiple recap agent runs (e.g., one per participant).

CREATE TABLE submitted_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_name_lower TEXT NOT NULL,
    assignee_email_lower TEXT NOT NULL,
    task_subject_lower TEXT NOT NULL,
    meeting_activity_uid TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(account_name_lower, assignee_email_lower, task_subject_lower)
);

CREATE INDEX idx_submitted_tasks_submitted_at ON submitted_tasks(submitted_at);

-- Atomic conditional upsert: returns true if the slot was claimed (new or
-- last submitted > 14 days ago), false if blocked (submitted within 14 days).
CREATE OR REPLACE FUNCTION claim_task_slot(
    p_account TEXT,
    p_assignee TEXT,
    p_subject TEXT,
    p_activity_uid TEXT
) RETURNS BOOLEAN AS $$
DECLARE
    v_claimed BOOLEAN := false;
BEGIN
    INSERT INTO submitted_tasks (
        account_name_lower,
        assignee_email_lower,
        task_subject_lower,
        meeting_activity_uid
    ) VALUES (
        lower(trim(p_account)),
        lower(trim(p_assignee)),
        lower(trim(p_subject)),
        p_activity_uid
    )
    ON CONFLICT (account_name_lower, assignee_email_lower, task_subject_lower)
    DO UPDATE SET
        submitted_at = NOW(),
        meeting_activity_uid = EXCLUDED.meeting_activity_uid
    WHERE submitted_tasks.submitted_at < NOW() - INTERVAL '14 days'
    RETURNING true INTO v_claimed;

    RETURN COALESCE(v_claimed, false);
END;
$$ LANGUAGE plpgsql;
