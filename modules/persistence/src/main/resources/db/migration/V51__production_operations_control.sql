-- Production operations control plane.
--
-- Security audit and product telemetry have intentionally different lifecycles:
-- audit_events remains append-only, while privacy-safe product telemetry may be
-- deleted by an authorized retention run after aggregate evidence is recorded.

CREATE TABLE product_telemetry_events (
    event_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    request_id varchar(128) NOT NULL,
    session_id varchar(96) NOT NULL,
    event_kind varchar(32) NOT NULL,
    action varchar(64) NOT NULL,
    business_line varchar(64) NOT NULL,
    route varchar(160) NOT NULL,
    target varchar(160) NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT current_timestamp,
    duration_ms integer,
    result varchar(16) NOT NULL,
    error_code varchar(96),
    metric_name varchar(64),
    metric_value double precision,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT product_telemetry_duration_range
        CHECK (duration_ms IS NULL OR duration_ms BETWEEN 0 AND 3600000),
    CONSTRAINT product_telemetry_result
        CHECK (result IN ('SUCCESS', 'FAILURE', 'CANCELLED')),
    CONSTRAINT product_telemetry_metric_finite
        CHECK (metric_value IS NULL OR metric_value NOT IN ('Infinity'::float8, '-Infinity'::float8)),
    CONSTRAINT product_telemetry_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX idx_product_telemetry_org_time
    ON product_telemetry_events (organization_id, occurred_at DESC);
CREATE INDEX idx_product_telemetry_org_line_time
    ON product_telemetry_events (organization_id, business_line, occurred_at DESC);
CREATE INDEX idx_product_telemetry_org_result_time
    ON product_telemetry_events (organization_id, result, occurred_at DESC);
CREATE INDEX idx_product_telemetry_org_session_time
    ON product_telemetry_events (organization_id, session_id, occurred_at DESC);

COMMENT ON TABLE product_telemetry_events IS
    'Privacy-safe technical telemetry only. Raw source, prompts, input values, request or response bodies, tokens, cookies, query strings, IP addresses, user agents, error messages and stacks are prohibited.';

CREATE TABLE operations_slo_policies (
    policy_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    business_line varchar(64) NOT NULL,
    latency_p95_budget_ms integer NOT NULL,
    failure_rate_budget_bps integer NOT NULL,
    minimum_event_count integer NOT NULL,
    evaluation_window_minutes integer NOT NULL,
    owner_actor_id varchar(128) NOT NULL,
    runbook_url varchar(512) NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT current_timestamp,
    updated_at timestamptz NOT NULL DEFAULT current_timestamp,
    CONSTRAINT operations_slo_latency_range CHECK (latency_p95_budget_ms BETWEEN 50 AND 3600000),
    CONSTRAINT operations_slo_failure_range CHECK (failure_rate_budget_bps BETWEEN 0 AND 10000),
    CONSTRAINT operations_slo_event_range CHECK (minimum_event_count BETWEEN 1 AND 1000000),
    CONSTRAINT operations_slo_window_range CHECK (evaluation_window_minutes BETWEEN 5 AND 44640),
    UNIQUE (organization_id, business_line)
);

CREATE TABLE operations_alerts (
    alert_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    fingerprint varchar(128) NOT NULL,
    business_line varchar(64) NOT NULL,
    signal varchar(32) NOT NULL,
    severity varchar(16) NOT NULL,
    status varchar(16) NOT NULL,
    observed_value numeric(20,6) NOT NULL,
    threshold_value numeric(20,6) NOT NULL,
    occurrence_count integer NOT NULL DEFAULT 1,
    owner_actor_id varchar(128) NOT NULL,
    runbook_url varchar(512) NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    acknowledged_at timestamptz,
    resolved_at timestamptz,
    silence_until timestamptz,
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT operations_alert_signal CHECK (signal IN ('FAILURE_RATE_BPS', 'LATENCY_P95_MS')),
    CONSTRAINT operations_alert_severity CHECK (severity IN ('P0', 'P1', 'P2')),
    CONSTRAINT operations_alert_status CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'SILENCED', 'RESOLVED')),
    UNIQUE (organization_id, fingerprint)
);
CREATE INDEX idx_operations_alerts_org_status
    ON operations_alerts (organization_id, status, last_seen_at DESC);

CREATE TABLE operations_incidents (
    incident_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    alert_id varchar(64) NOT NULL REFERENCES operations_alerts(alert_id),
    business_line varchar(64) NOT NULL,
    severity varchar(16) NOT NULL,
    status varchar(24) NOT NULL,
    summary_code varchar(96) NOT NULL,
    owner_actor_id varchar(128) NOT NULL,
    opened_at timestamptz NOT NULL,
    acknowledged_at timestamptz,
    mitigated_at timestamptz,
    resolved_at timestamptz,
    resolution_code varchar(96),
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT operations_incident_severity CHECK (severity IN ('P0', 'P1', 'P2')),
    CONSTRAINT operations_incident_status
        CHECK (status IN ('OPEN', 'ACKNOWLEDGED', 'MITIGATED', 'RESOLVED')),
    UNIQUE (organization_id, alert_id)
);
CREATE INDEX idx_operations_incidents_org_status
    ON operations_incidents (organization_id, status, opened_at DESC);

CREATE TABLE operations_remediation_proposals (
    proposal_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    incident_id varchar(64) NOT NULL REFERENCES operations_incidents(incident_id),
    recipe_id varchar(96) NOT NULL,
    remediation_kind varchar(24) NOT NULL,
    risk_level varchar(16) NOT NULL,
    status varchar(24) NOT NULL,
    title_code varchar(96) NOT NULL,
    precondition_digest varchar(71) NOT NULL,
    artifact_digest varchar(71),
    patch_preview jsonb NOT NULL,
    expected_diagnostic_delta jsonb NOT NULL,
    required_tests jsonb NOT NULL,
    rollback_plan jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    decided_at timestamptz,
    decided_by varchar(128),
    executed_at timestamptz,
    verified_at timestamptz,
    rolled_back_at timestamptz,
    version integer NOT NULL DEFAULT 1,
    CONSTRAINT operations_remediation_kind CHECK (remediation_kind IN ('PERFORMANCE', 'BUG_FIX')),
    CONSTRAINT operations_remediation_risk CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH')),
    CONSTRAINT operations_remediation_status CHECK (
        status IN (
            'PROPOSED', 'APPROVED', 'REJECTED', 'READY_FOR_SCM',
            'EXECUTED', 'VERIFIED', 'VERIFICATION_FAILED', 'ROLLED_BACK'
        )
    ),
    CONSTRAINT operations_remediation_digests CHECK (
        precondition_digest ~ '^sha256:[0-9a-f]{64}$'
        AND (artifact_digest IS NULL OR artifact_digest ~ '^sha256:[0-9a-f]{64}$')
    ),
    UNIQUE (organization_id, incident_id, recipe_id)
);
CREATE INDEX idx_operations_remediations_org_status
    ON operations_remediation_proposals (organization_id, status, created_at DESC);

CREATE TABLE operations_workflow_events (
    workflow_event_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    aggregate_type varchar(32) NOT NULL,
    aggregate_id varchar(64) NOT NULL,
    action varchar(64) NOT NULL,
    actor_id varchar(128) NOT NULL,
    request_id varchar(128) NOT NULL,
    before_status varchar(32),
    after_status varchar(32) NOT NULL,
    occurred_at timestamptz NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX idx_operations_workflow_org_aggregate
    ON operations_workflow_events (organization_id, aggregate_type, aggregate_id, occurred_at DESC);
CREATE TRIGGER operations_workflow_events_append_only
    BEFORE UPDATE OR DELETE ON operations_workflow_events
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE operations_notification_outbox (
    notification_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    alert_id varchar(64) NOT NULL REFERENCES operations_alerts(alert_id),
    channel varchar(32) NOT NULL,
    destination_ref varchar(160) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'PENDING',
    payload jsonb NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL,
    delivered_at timestamptz,
    last_error_code varchar(96),
    CONSTRAINT operations_notification_status
        CHECK (status IN ('PENDING', 'DELIVERING', 'DELIVERED', 'FAILED', 'BLOCKED')),
    CONSTRAINT operations_notification_attempts CHECK (attempt_count BETWEEN 0 AND 20),
    UNIQUE (organization_id, alert_id, channel, destination_ref)
);
CREATE INDEX idx_operations_notification_pending
    ON operations_notification_outbox (organization_id, status, available_at);

CREATE TABLE operations_retention_runs (
    retention_run_id varchar(64) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    actor_id varchar(128) NOT NULL,
    request_id varchar(128) NOT NULL,
    retention_days integer NOT NULL,
    cutoff_at timestamptz NOT NULL,
    deleted_event_count bigint NOT NULL,
    aggregate_evidence jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    CONSTRAINT operations_retention_days CHECK (retention_days BETWEEN 7 AND 365),
    CONSTRAINT operations_retention_deleted CHECK (deleted_event_count >= 0)
);
CREATE INDEX idx_operations_retention_org_time
    ON operations_retention_runs (organization_id, occurred_at DESC);
CREATE TRIGGER operations_retention_runs_append_only
    BEFORE UPDATE OR DELETE ON operations_retention_runs
    FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'product_telemetry_events',
        'operations_slo_policies',
        'operations_alerts',
        'operations_incidents',
        'operations_remediation_proposals',
        'operations_workflow_events',
        'operations_notification_outbox',
        'operations_retention_runs'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            table_name
        );
    END LOOP;
END;
$$;
