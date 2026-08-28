BEGIN;

CREATE TABLE IF NOT EXISTS etgb.product_feature (
  product_feature_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  feature_key text NOT NULL,
  domain_key text NOT NULL,
  title text NOT NULL,
  priority text NOT NULL CHECK (priority IN ('P0','P1','P2')),
  lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('DECLARED','IMPLEMENTED','DEPRECATED','RETIRED')),
  owner_key text NOT NULL,
  required_adapter text NOT NULL,
  release_policy text NOT NULL CHECK (release_policy IN ('MUST_PASS','MANUAL_APPROVAL')),
  registry_digest text NOT NULL CHECK (registry_digest ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, feature_key, registry_digest)
);

CREATE TABLE IF NOT EXISTS etgb.feature_test_binding (
  feature_test_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  product_feature_id uuid NOT NULL REFERENCES etgb.product_feature(product_feature_id) ON DELETE CASCADE,
  case_id uuid NOT NULL REFERENCES etgb.benchmark_case(case_id) ON DELETE CASCADE,
  context_key text NOT NULL,
  variant_key text NOT NULL,
  adapter_id text NOT NULL,
  critical boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, product_feature_id, case_id)
);

CREATE TABLE IF NOT EXISTS etgb.product_journey (
  product_journey_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  journey_key text NOT NULL,
  title text NOT NULL,
  priority text NOT NULL CHECK (priority IN ('P0','P1','P2')),
  journey_document jsonb NOT NULL,
  journey_digest text NOT NULL CHECK (journey_digest ~ '^sha256:[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, journey_key, journey_digest)
);

CREATE TABLE IF NOT EXISTS etgb.assurance_control (
  assurance_control_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  profile_key text NOT NULL,
  control_key text NOT NULL,
  source_reference text NOT NULL,
  source_version text,
  non_accreditation_notice boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, profile_key, control_key, source_version)
);

CREATE TABLE IF NOT EXISTS etgb.adapter_conformance (
  adapter_conformance_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  adapter_id text NOT NULL,
  candidate_digest text NOT NULL CHECK (candidate_digest ~ '^sha256:[0-9a-f]{64}$'),
  environment_digest text NOT NULL CHECK (environment_digest ~ '^sha256:[0-9a-f]{64}$'),
  status text NOT NULL CHECK (status IN ('REQUIRED','CONFORMANT','FAILED','BLOCKED','RETIRED')),
  conformance_document jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_manifest_digest text,
  checked_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  UNIQUE (tenant_id, adapter_id, candidate_digest, environment_digest)
);

CREATE TABLE IF NOT EXISTS etgb.coverage_gap (
  coverage_gap_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  candidate_digest text NOT NULL,
  feature_key text,
  gap_type text NOT NULL CHECK (gap_type IN ('UNDECLARED_FEATURE','NO_CASE','NO_ADAPTER','NO_ORACLE','UNAVAILABLE','STALE_EVIDENCE','MISSING_JOURNEY','MISSING_CONTROL')),
  severity text NOT NULL CHECK (severity IN ('P0','P1','P2')),
  status text NOT NULL CHECK (status IN ('OPEN','ACCEPTED','FIXED','BLOCKED')),
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_product_feature_domain ON etgb.product_feature(tenant_id, domain_key, priority);
CREATE INDEX IF NOT EXISTS idx_feature_test_binding_feature ON etgb.feature_test_binding(tenant_id, product_feature_id);
CREATE INDEX IF NOT EXISTS idx_adapter_conformance_status ON etgb.adapter_conformance(tenant_id, status, adapter_id);
CREATE INDEX IF NOT EXISTS idx_coverage_gap_open ON etgb.coverage_gap(tenant_id, severity, gap_type) WHERE status = 'OPEN';

COMMIT;
