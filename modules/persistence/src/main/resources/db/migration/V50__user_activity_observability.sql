-- Privacy-safe user activity observability for the Web control center.
-- audit_events remains append-only through the trigger installed by V9.

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS event_kind varchar(32) NOT NULL DEFAULT 'BUSINESS_ACTION',
    ADD COLUMN IF NOT EXISTS business_line varchar(64) NOT NULL DEFAULT 'UNCLASSIFIED',
    ADD COLUMN IF NOT EXISTS route text NOT NULL DEFAULT '/',
    ADD COLUMN IF NOT EXISTS target text NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS session_id varchar(96),
    ADD COLUMN IF NOT EXISTS duration_ms integer,
    ADD COLUMN IF NOT EXISTS error_code varchar(96),
    ADD COLUMN IF NOT EXISTS metric_name varchar(64),
    ADD COLUMN IF NOT EXISTS metric_value double precision,
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS received_at timestamptz NOT NULL DEFAULT current_timestamp;

ALTER TABLE audit_events
    ADD CONSTRAINT audit_events_duration_non_negative
        CHECK (duration_ms IS NULL OR duration_ms >= 0),
    ADD CONSTRAINT audit_events_metric_finite
        CHECK (metric_value IS NULL OR metric_value NOT IN ('Infinity'::float8, '-Infinity'::float8));

CREATE INDEX IF NOT EXISTS idx_audit_events_org_occurred
    ON audit_events (organization_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_org_business_line
    ON audit_events (organization_id, business_line, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_org_result
    ON audit_events (organization_id, result, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_org_session
    ON audit_events (organization_id, session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;

COMMENT ON COLUMN audit_events.metadata IS
    'Allow-listed technical dimensions only; input values, tokens, request bodies, query strings, raw IPs, and raw user agents are prohibited.';
COMMENT ON COLUMN audit_events.received_at IS
    'Server receipt time used to diagnose client clock and delivery delay.';
