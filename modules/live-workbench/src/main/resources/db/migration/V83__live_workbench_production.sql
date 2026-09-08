-- Live Workbench lw.v1 durable control plane. External provider effects remain behind typed adapters.
CREATE TABLE lw_runtime_profiles (
    tenant_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK (qualification IN ('CANDIDATE','QUALIFIED','UNSUPPORTED','NOT_RUN')),
    runtime_digest CHAR(71) NOT NULL CHECK (runtime_digest ~ '^sha256:[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, profile_id)
);

CREATE TABLE lw_deliveries (
    tenant_id TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    snapshot_id CHAR(71) NOT NULL CHECK (snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    runtime_profile_id TEXT NOT NULL,
    build_artifact_digest CHAR(71) NOT NULL CHECK (build_artifact_digest ~ '^sha256:[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, delivery_id),
    FOREIGN KEY (tenant_id, runtime_profile_id) REFERENCES lw_runtime_profiles(tenant_id, profile_id) ON DELETE RESTRICT
);

CREATE TABLE lw_source_anchors (
    tenant_id TEXT NOT NULL,
    anchor_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    snapshot_id CHAR(71) NOT NULL CHECK (snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    path TEXT NOT NULL,
    blob_digest CHAR(71) NOT NULL CHECK (blob_digest ~ '^sha256:[a-f0-9]{64}$'),
    byte_start INTEGER NOT NULL CHECK (byte_start >= 0),
    byte_end INTEGER NOT NULL CHECK (byte_end >= byte_start),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, anchor_id),
    UNIQUE (tenant_id, repository_id, snapshot_id, path, byte_start, byte_end)
);

CREATE TABLE lw_claims (
    tenant_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    snapshot_id CHAR(71) NOT NULL CHECK (snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    classification TEXT NOT NULL CHECK (classification IN ('VERIFIED_STATIC','RUNTIME_OBSERVED','INFERRED','UNKNOWN','RECOMMENDED')),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, claim_id)
);

CREATE TABLE lw_claim_evidence (
    tenant_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('SOURCE_ANCHOR','RUNTIME_EVENT')),
    evidence_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id, claim_id, evidence_kind, evidence_id),
    FOREIGN KEY (tenant_id, claim_id) REFERENCES lw_claims(tenant_id, claim_id) ON DELETE RESTRICT
);

CREATE TABLE lw_missions (
    tenant_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    snapshot_id CHAR(71) NOT NULL CHECK (snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, mission_id)
);

CREATE TABLE lw_correspondences (
    tenant_id TEXT NOT NULL,
    mapping_id TEXT NOT NULL,
    source_snapshot_id CHAR(71) NOT NULL CHECK (source_snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    target_snapshot_id CHAR(71) NOT NULL CHECK (target_snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    payload JSONB NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, mapping_id)
);

CREATE TABLE lw_sessions (
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    snapshot_id CHAR(71) NOT NULL CHECK (snapshot_id ~ '^sha256:[a-f0-9]{64}$'),
    runtime_profile_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('run','debug','compare','learn')),
    generation INTEGER NOT NULL CHECK (generation > 0),
    slot_weight INTEGER NOT NULL CHECK (slot_weight BETWEEN 1 AND 3),
    state TEXT NOT NULL CHECK (state IN ('PREPARING','READY','EXPIRED','TERMINATED','CLEANUP_PENDING','CLEANED','QUARANTINED','FAILED')),
    runtime_status TEXT NOT NULL CHECK (runtime_status IN ('PENDING','RUNNING','STOPPED','DEGRADED','UNKNOWN')),
    created_at_epoch BIGINT NOT NULL CHECK (created_at_epoch >= 0),
    first_ready_at_epoch BIGINT,
    expires_at_epoch BIGINT,
    provider_hard_deadline_epoch BIGINT NOT NULL DEFAULT 0,
    provider_session_id TEXT,
    resource_lease_id TEXT,
    resource_members JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    readiness_verifier_id TEXT,
    readiness_signature_ref TEXT,
    cleanup_reason TEXT,
    cleanup_requested_at_epoch BIGINT,
    cleanup_claim_until_epoch BIGINT,
    cleanup_observed_at_epoch BIGINT,
    cleanup_verifier_id TEXT,
    cleanup_checks JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_code TEXT,
    request_digest CHAR(71) NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
    idempotency_key TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, session_id),
    UNIQUE (tenant_id, account_id, idempotency_key),
    CHECK ((first_ready_at_epoch IS NULL AND expires_at_epoch IS NULL) OR expires_at_epoch = first_ready_at_epoch + 600),
    CHECK (state <> 'READY' OR (first_ready_at_epoch IS NOT NULL AND expires_at_epoch IS NOT NULL AND provider_session_id IS NOT NULL)),
    FOREIGN KEY (tenant_id, delivery_id) REFERENCES lw_deliveries(tenant_id, delivery_id) ON DELETE RESTRICT
);
CREATE INDEX lw_sessions_active_quota_idx ON lw_sessions(tenant_id, account_id, state);
CREATE INDEX lw_sessions_expiry_idx ON lw_sessions(expires_at_epoch) WHERE state='READY';
CREATE INDEX lw_sessions_cleanup_idx ON lw_sessions(cleanup_requested_at_epoch) WHERE state IN ('CLEANUP_PENDING','QUARANTINED');

CREATE TABLE lw_debug_commands (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    command_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest CHAR(71) NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
    command_name TEXT NOT NULL CHECK (command_name IN ('continue','pause','next','stepIn','stepOut','terminate','stackTrace','variables')),
    arguments_digest CHAR(71) NOT NULL CHECK (arguments_digest ~ '^sha256:[a-f0-9]{64}$'),
    stop_epoch INTEGER NOT NULL CHECK (stop_epoch >= 0),
    control_lease_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('PENDING','COMMITTED','UNKNOWN','DENIED')),
    code TEXT NOT NULL,
    evidence_ref TEXT,
    response_digest CHAR(71) CHECK (response_digest IS NULL OR response_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    completed_at_epoch BIGINT,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, session_id, command_id),
    UNIQUE (tenant_id, session_id, idempotency_key),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_runtime_events (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation > 0),
    event_id TEXT NOT NULL,
    stop_epoch INTEGER NOT NULL CHECK (stop_epoch >= 0),
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    kind TEXT NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    source_anchor_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    redaction_status TEXT NOT NULL CHECK (redaction_status IN ('none-needed','redacted','omitted')),
    server_time_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, session_id, generation, sequence),
    UNIQUE (tenant_id, session_id, event_id),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_resource_members (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    member_kind TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    deadline_epoch BIGINT NOT NULL CHECK (deadline_epoch > 0),
    cleanup_state TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (cleanup_state IN ('ACTIVE','CLEANED','QUARANTINED')),
    cleanup_evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, session_id, member_kind),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_cleanup_receipts (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    receipt_version BIGINT NOT NULL CHECK (receipt_version > 0),
    status TEXT NOT NULL CHECK (status IN ('CLEANED','QUARANTINED')),
    verifier_id TEXT NOT NULL,
    member_checks JSONB NOT NULL,
    evidence_refs JSONB NOT NULL,
    observed_at_epoch BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, session_id, receipt_version),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_attempts (
    tenant_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_digest CHAR(71) NOT NULL CHECK (request_digest ~ '^sha256:[a-f0-9]{64}$'),
    state TEXT NOT NULL CHECK (state IN ('PENDING','COMMITTED','UNKNOWN','DENIED')),
    receipt JSONB,
    created_at_epoch BIGINT NOT NULL,
    completed_at_epoch BIGINT,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, mission_id, attempt_id),
    UNIQUE (tenant_id, mission_id, actor_id, idempotency_key),
    FOREIGN KEY (tenant_id, mission_id) REFERENCES lw_missions(tenant_id, mission_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_audit_events (
    tenant_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence > 0),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    observed_at_epoch BIGINT NOT NULL,
    previous_hash CHAR(71) NOT NULL CHECK (previous_hash ~ '^sha256:[a-f0-9]{64}$'),
    entry_hash CHAR(71) NOT NULL CHECK (entry_hash ~ '^sha256:[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id, session_id, sequence),
    UNIQUE (tenant_id, entry_hash),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);

CREATE TABLE lw_outbox (
    tenant_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_digest CHAR(71) NOT NULL CHECK (payload_digest ~ '^sha256:[a-f0-9]{64}$'),
    created_at_epoch BIGINT NOT NULL,
    published_at_epoch BIGINT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, session_id) REFERENCES lw_sessions(tenant_id, session_id) ON DELETE RESTRICT
);
CREATE INDEX lw_outbox_pending_idx ON lw_outbox(created_at_epoch) WHERE published_at_epoch IS NULL;

ALTER TABLE lw_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_debug_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_debug_commands FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_runtime_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_runtime_events FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_outbox FORCE ROW LEVEL SECURITY;

ALTER TABLE lw_runtime_profiles ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_runtime_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_deliveries ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_deliveries FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_source_anchors ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_source_anchors FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_claims ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_claims FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_claim_evidence ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_claim_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_missions ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_missions FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_correspondences ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_correspondences FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_resource_members ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_resource_members FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_cleanup_receipts ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_cleanup_receipts FORCE ROW LEVEL SECURITY;
ALTER TABLE lw_attempts ENABLE ROW LEVEL SECURITY; ALTER TABLE lw_attempts FORCE ROW LEVEL SECURITY;

CREATE POLICY lw_sessions_tenant_policy ON lw_sessions USING (
    tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true'
) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_debug_commands_tenant_policy ON lw_debug_commands USING (
    tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true'
) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_runtime_events_tenant_policy ON lw_runtime_events USING (
    tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true'
) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_audit_events_tenant_policy ON lw_audit_events USING (
    tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true'
) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_outbox_tenant_policy ON lw_outbox USING (
    tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true'
) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');

CREATE POLICY lw_runtime_profiles_tenant_policy ON lw_runtime_profiles USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_deliveries_tenant_policy ON lw_deliveries USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_source_anchors_tenant_policy ON lw_source_anchors USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_claims_tenant_policy ON lw_claims USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_claim_evidence_tenant_policy ON lw_claim_evidence USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_missions_tenant_policy ON lw_missions USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_correspondences_tenant_policy ON lw_correspondences USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));
CREATE POLICY lw_resource_members_tenant_policy ON lw_resource_members USING (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true') WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_cleanup_receipts_tenant_policy ON lw_cleanup_receipts USING (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true') WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true) OR current_setting('elmos.system_worker', true) = 'true');
CREATE POLICY lw_attempts_tenant_policy ON lw_attempts USING (tenant_id = current_setting('elmos.tenant_id', true)) WITH CHECK (tenant_id = current_setting('elmos.tenant_id', true));

COMMENT ON TABLE lw_sessions IS 'lw.v1 tenant-scoped preview state; exact 600 second window starts only after committed readiness';
COMMENT ON TABLE lw_debug_commands IS 'durable debug side-effect ledger; UNKNOWN must be reconciled before new intent';
COMMENT ON TABLE lw_runtime_events IS 'committed, redacted, generation-fenced runtime event stream';
COMMENT ON TABLE lw_audit_events IS 'append-only tenant/session hash chain';
COMMENT ON TABLE lw_attempts IS 'private assessment attempts; public payloads never contain hidden answers';
