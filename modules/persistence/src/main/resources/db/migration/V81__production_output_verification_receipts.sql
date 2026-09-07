-- Digest-bound output evidence for the four production workload packs.
--
-- A worker-reported SUCCEEDED status is not enough to advance a production
-- workload.  The runtime writes this receipt in the same transaction as the
-- terminal attempt transition after matching job_type/work_type against the
-- durable work item and evaluating the repository-owned typed gate catalog.

ALTER TABLE runtime.execution_attempts
    ADD CONSTRAINT execution_attempt_tenant_work_identity
    UNIQUE (tenant_id, work_item_id, id);

CREATE TABLE runtime.output_verification_receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES identity.tenants(id),
    work_item_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    schema_version text NOT NULL
        CHECK (schema_version = 'elmos.production-output-verification/v1'),
    pack_id text NOT NULL,
    job_type text NOT NULL CHECK (job_type IN (
        'SPRING_MODERNIZATION',
        'LANGUAGE_CONVERSION',
        'PROJECT_GENERATION',
        'SQL_CONVERSION'
    )),
    work_type text NOT NULL CHECK (length(work_type) BETWEEN 1 AND 120),
    artifact_uri text NOT NULL
        CHECK (artifact_uri ~ '^(cas|s3|gs|azblob|https)://'),
    artifact_sha256 text NOT NULL
        CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    verifier text NOT NULL CHECK (length(verifier) BETWEEN 1 AND 240),
    verification_status text NOT NULL CHECK (verification_status = 'PASSED'),
    certification_status text NOT NULL CHECK (certification_status = 'NOT_CERTIFIED'),
    checks jsonb NOT NULL
        CHECK (jsonb_typeof(checks) = 'object' AND checks <> '{}'::jsonb),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (attempt_id),
    FOREIGN KEY (tenant_id, work_item_id)
        REFERENCES orchestration.work_items(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, work_item_id, attempt_id)
        REFERENCES runtime.execution_attempts(tenant_id, work_item_id, id)
        ON DELETE CASCADE,
    CHECK (
        (job_type = 'SPRING_MODERNIZATION' AND pack_id = 'spring-modernization-v1')
        OR (job_type = 'LANGUAGE_CONVERSION' AND pack_id = 'repository-language-conversion-v1')
        OR (job_type = 'PROJECT_GENERATION' AND pack_id = 'multilingual-project-generation-v1')
        OR (job_type = 'SQL_CONVERSION' AND pack_id = 'sql-dialect-routine-conversion-v1')
    )
);

CREATE INDEX output_verification_work_item_idx
    ON runtime.output_verification_receipts (tenant_id, work_item_id, created_at DESC);

ALTER TABLE runtime.output_verification_receipts ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON runtime.output_verification_receipts
    USING (tenant_id = public.current_tenant_id())
    WITH CHECK (tenant_id = public.current_tenant_id());

COMMENT ON TABLE runtime.output_verification_receipts IS
    'Digest-bound engineering output-gate evidence; never a certification receipt.';
