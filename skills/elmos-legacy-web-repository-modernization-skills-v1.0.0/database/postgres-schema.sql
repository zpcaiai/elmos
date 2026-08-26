-- Elmos Java Legacy Web Modernization persistence model
-- PostgreSQL 16+ / 17 recommended
-- Large payloads stay in object storage; tables keep URI + digest + searchable metadata.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS modernization_job (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    state text NOT NULL CHECK (state IN (
        'CREATED','SNAPSHOTTING','FORENSICS','SEMANTIC_RECOVERY','IR_BUILT',
        'PLANNED','TRANSFORMING','BUILDING','VERIFYING','REPAIRING',
        'E4_VERIFIED','CUTOVER_READY','E5_CERTIFIED','PAUSED',
        'CANCEL_REQUESTED','CANCELLED','ROLLBACK','FAILED','BLOCKED_UNKNOWN'
    )),
    source_ref jsonb NOT NULL,
    target_policy jsonb NOT NULL,
    policy_snapshot_hash text NOT NULL,
    owner_environment_id text,
    priority smallint NOT NULL DEFAULT 50,
    current_phase text,
    current_gate text,
    machine_eta jsonb,
    cost_estimate jsonb,
    version bigint NOT NULL DEFAULT 0,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_mod_job_tenant_state ON modernization_job(tenant_id, state, updated_at DESC);

CREATE TABLE IF NOT EXISTS repository_snapshot (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    repository_uri text NOT NULL,
    git_commit text,
    dirty_patch_digest text,
    submodules jsonb NOT NULL DEFAULT '[]',
    lfs_objects jsonb NOT NULL DEFAULT '[]',
    build_environment jsonb NOT NULL,
    source_artifact_id uuid,
    digest text NOT NULL,
    reproducible boolean NOT NULL DEFAULT false,
    baseline_build_status text,
    baseline_runtime_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, digest)
);

CREATE TABLE IF NOT EXISTS transformation_unit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    stable_key text NOT NULL,
    name text NOT NULL,
    risk text NOT NULL CHECK (risk IN ('low','medium','high','critical')),
    module_ids jsonb NOT NULL DEFAULT '[]',
    route_ids jsonb NOT NULL DEFAULT '[]',
    state_ids jsonb NOT NULL DEFAULT '[]',
    side_effect_ids jsonb NOT NULL DEFAULT '[]',
    depends_on jsonb NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'PENDING',
    input_subgraph_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, stable_key)
);

CREATE TABLE IF NOT EXISTS execution_step (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE CASCADE,
    step_key text NOT NULL,
    skill_id text NOT NULL,
    state text NOT NULL CHECK (state IN ('PENDING','READY','LEASED','RUNNING','SAFE_POINT','COMMITTED','FAILED','CANCELLED','ROLLED_BACK','BLOCKED')),
    deterministic_input_hash text NOT NULL,
    policy_snapshot_hash text NOT NULL,
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    attempt_count integer NOT NULL DEFAULT 0,
    next_run_at timestamptz,
    output_artifact_ids jsonb NOT NULL DEFAULT '[]',
    blocking_reason jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, step_key, deterministic_input_hash, policy_snapshot_hash)
);
CREATE INDEX IF NOT EXISTS idx_step_scheduler ON execution_step(state, next_run_at, job_id);
CREATE INDEX IF NOT EXISTS idx_step_unit ON execution_step(transformation_unit_id, state);

CREATE TABLE IF NOT EXISTS step_attempt (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    step_id uuid NOT NULL REFERENCES execution_step(id) ON DELETE CASCADE,
    attempt_no integer NOT NULL,
    executor_id text NOT NULL,
    owner_environment_id text NOT NULL,
    permission_profile_hash text NOT NULL,
    lease_id uuid NOT NULL DEFAULT gen_random_uuid(),
    fencing_token bigint NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    state text NOT NULL CHECK (state IN ('LEASED','RUNNING','SUCCEEDED','FAILED','EXPIRED','CANCELLED','FENCED')),
    started_at timestamptz,
    ended_at timestamptz,
    error jsonb,
    metrics jsonb NOT NULL DEFAULT '{}',
    UNIQUE(step_id, attempt_no),
    UNIQUE(step_id, fencing_token)
);
CREATE INDEX IF NOT EXISTS idx_attempt_lease ON step_attempt(state, lease_expires_at);

CREATE TABLE IF NOT EXISTS execution_checkpoint (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    step_id uuid NOT NULL REFERENCES execution_step(id) ON DELETE CASCADE,
    attempt_id uuid NOT NULL REFERENCES step_attempt(id) ON DELETE CASCADE,
    state text NOT NULL CHECK (state IN ('started','safe-point','committed','failed','cancelled','rolled-back')),
    input_hash text NOT NULL,
    policy_snapshot_hash text NOT NULL,
    fencing_token bigint NOT NULL,
    resume_cursor jsonb,
    artifact_ids jsonb NOT NULL DEFAULT '[]',
    side_effects jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_checkpoint_latest ON execution_checkpoint(step_id, created_at DESC);

CREATE TABLE IF NOT EXISTS artifact (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid REFERENCES modernization_job(id) ON DELETE CASCADE,
    snapshot_id uuid REFERENCES repository_snapshot(id) ON DELETE SET NULL,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE SET NULL,
    type text NOT NULL,
    schema_version text,
    producer_skill text NOT NULL,
    producer_version text NOT NULL,
    state text NOT NULL CHECK (state IN ('STAGED','VALIDATED','PUBLISHED','SUPERSEDED','RETAINED','DELETED')),
    uri text NOT NULL,
    digest text NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    content_type text,
    input_hashes jsonb NOT NULL DEFAULT '[]',
    policy_snapshot_hash text NOT NULL,
    owner_environment_id text,
    evidence_refs jsonb NOT NULL DEFAULT '[]',
    confidence numeric(5,4) CHECK (confidence BETWEEN 0 AND 1),
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    retention_until timestamptz,
    UNIQUE(tenant_id, digest, type, schema_version)
);
CREATE INDEX IF NOT EXISTS idx_artifact_job_type ON artifact(job_id, type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_artifact_digest ON artifact(tenant_id, digest);

CREATE TABLE IF NOT EXISTS evidence_node (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES repository_snapshot(id) ON DELETE CASCADE,
    stable_key text NOT NULL,
    node_type text NOT NULL,
    label text NOT NULL,
    status text NOT NULL CHECK (status IN ('confirmed','inferred','unknown','conflicted','deprecated')),
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    environment_class text,
    locator jsonb NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}',
    source_digest text NOT NULL,
    extractor text NOT NULL,
    extractor_version text NOT NULL,
    observed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(snapshot_id, stable_key, source_digest, extractor, extractor_version)
);
CREATE INDEX IF NOT EXISTS idx_evidence_node_lookup ON evidence_node(job_id, node_type, stable_key);
CREATE INDEX IF NOT EXISTS idx_evidence_node_attr_gin ON evidence_node USING gin(attributes);

CREATE TABLE IF NOT EXISTS evidence_edge (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES repository_snapshot(id) ON DELETE CASCADE,
    from_node_id uuid NOT NULL REFERENCES evidence_node(id) ON DELETE CASCADE,
    to_node_id uuid NOT NULL REFERENCES evidence_node(id) ON DELETE CASCADE,
    edge_type text NOT NULL,
    status text NOT NULL CHECK (status IN ('confirmed','inferred','unknown','conflicted')),
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    attributes jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(snapshot_id, from_node_id, to_node_id, edge_type)
);
CREATE INDEX IF NOT EXISTS idx_evidence_edge_from ON evidence_edge(from_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_evidence_edge_to ON evidence_edge(to_node_id, edge_type);

CREATE TABLE IF NOT EXISTS semantic_ir_chunk (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES repository_snapshot(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE CASCADE,
    ir_type text NOT NULL,
    stable_key text NOT NULL,
    schema_version text NOT NULL,
    uri text NOT NULL,
    digest text NOT NULL,
    evidence_coverage jsonb NOT NULL,
    unknown_refs jsonb NOT NULL DEFAULT '[]',
    producer_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    superseded_by uuid REFERENCES semantic_ir_chunk(id),
    UNIQUE(snapshot_id, ir_type, stable_key, digest)
);
CREATE INDEX IF NOT EXISTS idx_ir_job_type ON semantic_ir_chunk(job_id, ir_type, stable_key);

CREATE TABLE IF NOT EXISTS endpoint_contract (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES repository_snapshot(id) ON DELETE CASCADE,
    endpoint_key text NOT NULL,
    path_pattern text NOT NULL,
    methods text[] NOT NULL,
    dispatcher_types text[] NOT NULL,
    owner_framework text NOT NULL,
    owner_symbol text NOT NULL,
    criticality text NOT NULL CHECK (criticality IN ('low','medium','high','critical')),
    ir_chunk_id uuid REFERENCES semantic_ir_chunk(id),
    contract_artifact_id uuid REFERENCES artifact(id),
    evidence_refs jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(snapshot_id, endpoint_key)
);
CREATE INDEX IF NOT EXISTS idx_endpoint_route ON endpoint_contract(job_id, path_pattern);
CREATE INDEX IF NOT EXISTS idx_endpoint_critical ON endpoint_contract(job_id, criticality);

CREATE TABLE IF NOT EXISTS unknown_semantic (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE SET NULL,
    stable_key text NOT NULL,
    category text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    status text NOT NULL CHECK (status IN ('open','inferred','resolved','accepted-risk')),
    scope jsonb NOT NULL,
    description text NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]',
    resolution_plan jsonb NOT NULL DEFAULT '[]',
    blocking_levels text[] NOT NULL DEFAULT '{}',
    owner text,
    resolved_by_evidence_refs jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, stable_key)
);
CREATE INDEX IF NOT EXISTS idx_unknown_blocking ON unknown_semantic(job_id, severity, status);

CREATE TABLE IF NOT EXISTS risk_item (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE SET NULL,
    stable_key text NOT NULL,
    category text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    score numeric(6,3) NOT NULL,
    dimensions jsonb NOT NULL,
    scope jsonb NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]',
    mitigation jsonb NOT NULL DEFAULT '[]',
    status text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, stable_key)
);

CREATE TABLE IF NOT EXISTS change_set (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid NOT NULL REFERENCES transformation_unit(id) ON DELETE CASCADE,
    sequence_no integer NOT NULL,
    state text NOT NULL CHECK (state IN ('PLANNED','STAGED','APPLIED','VALIDATED','COMMITTED','REVERTED','FAILED')),
    recipe_ids jsonb NOT NULL DEFAULT '[]',
    precondition_hash text NOT NULL,
    operations_artifact_id uuid REFERENCES artifact(id),
    reverse_artifact_id uuid REFERENCES artifact(id),
    source_map_artifact_id uuid REFERENCES artifact(id),
    target_tree_digest text,
    changed_files integer,
    changed_loc integer,
    git_commit text,
    created_at timestamptz NOT NULL DEFAULT now(),
    committed_at timestamptz,
    UNIQUE(transformation_unit_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS verification_run (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE CASCADE,
    run_type text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('strict','normalized','hardened')),
    legacy_artifact_id uuid REFERENCES artifact(id),
    target_artifact_id uuid REFERENCES artifact(id),
    environment_artifact_id uuid REFERENCES artifact(id),
    scenario_set_artifact_id uuid REFERENCES artifact(id),
    state text NOT NULL CHECK (state IN ('PENDING','RUNNING','PASSED','FAILED','BLOCKED','CANCELLED')),
    summary jsonb NOT NULL DEFAULT '{}',
    report_artifact_id uuid REFERENCES artifact(id),
    started_at timestamptz,
    ended_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_verification_job ON verification_run(job_id, run_type, created_at DESC);

CREATE TABLE IF NOT EXISTS differential_observation (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    verification_run_id uuid NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,
    scenario_id text NOT NULL,
    sequence_step text NOT NULL,
    side text NOT NULL CHECK (side IN ('legacy','target')),
    dimension text NOT NULL,
    correlation_id text,
    artifact_id uuid NOT NULL REFERENCES artifact(id),
    digest text NOT NULL,
    summary jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(verification_run_id, scenario_id, sequence_step, side, dimension)
);
CREATE INDEX IF NOT EXISTS idx_observation_pair ON differential_observation(verification_run_id, scenario_id, sequence_step, dimension);

CREATE TABLE IF NOT EXISTS semantic_mismatch (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    verification_run_id uuid NOT NULL REFERENCES verification_run(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE SET NULL,
    mismatch_key text NOT NULL,
    root_cause_key text,
    scenario_id text NOT NULL,
    dimension text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','low','medium','high','critical')),
    classification text NOT NULL,
    status text NOT NULL CHECK (status IN ('open','normalized','accepted-delta','repaired','not-reproducible','unknown')),
    first_divergence jsonb,
    legacy_observation_id uuid REFERENCES differential_observation(id),
    target_observation_id uuid REFERENCES differential_observation(id),
    source_map_refs jsonb NOT NULL DEFAULT '[]',
    evidence_refs jsonb NOT NULL DEFAULT '[]',
    normalizer_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(verification_run_id, mismatch_key)
);
CREATE INDEX IF NOT EXISTS idx_mismatch_root ON semantic_mismatch(job_id, root_cause_key, status);
CREATE INDEX IF NOT EXISTS idx_mismatch_critical ON semantic_mismatch(job_id, severity, status);

CREATE TABLE IF NOT EXISTS repair_attempt (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    transformation_unit_id uuid REFERENCES transformation_unit(id) ON DELETE CASCADE,
    root_cause_key text NOT NULL,
    iteration integer NOT NULL,
    state text NOT NULL CHECK (state IN ('PLANNED','APPLIED','VALIDATED','REVERTED','FAILED','STOPPED')),
    hypothesis text NOT NULL,
    evidence_refs jsonb NOT NULL,
    patch_artifact_id uuid REFERENCES artifact(id),
    reverse_patch_artifact_id uuid REFERENCES artifact(id),
    test_artifact_id uuid REFERENCES artifact(id),
    changed_files integer NOT NULL DEFAULT 0,
    changed_loc integer NOT NULL DEFAULT 0,
    before_mismatch_refs jsonb NOT NULL DEFAULT '[]',
    after_mismatch_refs jsonb NOT NULL DEFAULT '[]',
    stop_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    UNIQUE(job_id, root_cause_key, iteration)
);

CREATE TABLE IF NOT EXISTS gate_result (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    gate_id text NOT NULL,
    certification_level text,
    status text NOT NULL CHECK (status IN ('pending','passed','failed','blocked','waived')),
    rule_results jsonb NOT NULL,
    evidence_refs jsonb NOT NULL DEFAULT '[]',
    waiver jsonb,
    evaluated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, gate_id, evaluated_at)
);
CREATE INDEX IF NOT EXISTS idx_gate_latest ON gate_result(job_id, gate_id, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS certification (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    level text NOT NULL CHECK (level IN ('E0','E1','E2','E3','E4','E5','BLOCKED')),
    state text NOT NULL CHECK (state IN ('DRAFT','ISSUED','REVOKED','SUPERSEDED')),
    bundle_artifact_id uuid NOT NULL REFERENCES artifact(id),
    bundle_digest text NOT NULL,
    policy_snapshot_hash text NOT NULL,
    target_digest text,
    critical_unknown_count integer NOT NULL,
    critical_mismatch_count integer NOT NULL,
    issued_by text,
    issued_at timestamptz,
    revoked_at timestamptz,
    revocation_reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cert_issued_level ON certification(job_id, level) WHERE state = 'ISSUED';

CREATE TABLE IF NOT EXISTS cost_ledger (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    step_id uuid REFERENCES execution_step(id) ON DELETE SET NULL,
    attempt_id uuid REFERENCES step_attempt(id) ON DELETE SET NULL,
    cost_type text NOT NULL,
    provider text,
    model_or_tool text,
    quantity numeric(20,6) NOT NULL,
    unit text NOT NULL,
    amount_usd numeric(20,8),
    cached boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}',
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cost_job ON cost_ledger(job_id, occurred_at);

CREATE TABLE IF NOT EXISTS eta_estimate (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    job_id uuid NOT NULL REFERENCES modernization_job(id) ON DELETE CASCADE,
    model_id text NOT NULL,
    p50_seconds bigint NOT NULL CHECK (p50_seconds >= 0),
    p80_seconds bigint NOT NULL CHECK (p80_seconds >= 0),
    p95_seconds bigint NOT NULL CHECK (p95_seconds >= 0),
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    features jsonb NOT NULL,
    assumptions jsonb NOT NULL DEFAULT '[]',
    human_wait_excluded boolean NOT NULL DEFAULT true,
    as_of timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eta_job ON eta_estimate(job_id, as_of DESC);

CREATE TABLE IF NOT EXISTS cache_entry (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    cache_namespace text NOT NULL,
    cache_key text NOT NULL,
    layer text NOT NULL CHECK (layer IN ('blob','analysis','execution','validated-pattern')),
    artifact_id uuid NOT NULL REFERENCES artifact(id) ON DELETE CASCADE,
    content_hash text NOT NULL,
    dependency_subgraph_hash text,
    extractor_recipe_model_version text NOT NULL,
    target_baseline_hash text,
    policy_snapshot_hash text,
    environment_class text,
    e4_e5_validated boolean NOT NULL DEFAULT false,
    state text NOT NULL CHECK (state IN ('valid','invalidated','expired','quarantined')),
    hit_count bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_hit_at timestamptz,
    expires_at timestamptz,
    invalidated_at timestamptz,
    invalidation_reason text,
    UNIQUE(tenant_id, cache_namespace, cache_key)
);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON cache_entry(tenant_id, cache_namespace, cache_key, state);
CREATE INDEX IF NOT EXISTS idx_cache_dependency ON cache_entry(tenant_id, dependency_subgraph_hash) WHERE state = 'valid';

CREATE TABLE IF NOT EXISTS audit_event (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL,
    job_id uuid REFERENCES modernization_job(id) ON DELETE CASCADE,
    step_id uuid REFERENCES execution_step(id) ON DELETE SET NULL,
    attempt_id uuid REFERENCES step_attempt(id) ON DELETE SET NULL,
    event_type text NOT NULL,
    actor text NOT NULL,
    owner_environment_id text,
    permission_profile_hash text,
    payload jsonb NOT NULL,
    payload_digest text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_job ON audit_event(job_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_event(tenant_id, event_type, occurred_at);

-- Tenant isolation should be implemented with Row Level Security in the host system.
-- Example:
-- ALTER TABLE modernization_job ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY tenant_isolation_mod_job ON modernization_job
--   USING (tenant_id = current_setting('elmos.tenant_id')::uuid);
