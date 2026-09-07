BEGIN;

CREATE TABLE IF NOT EXISTS ai_prompt_program (
  tenant_id uuid NOT NULL,
  prompt_program_id text NOT NULL,
  version text NOT NULL,
  program jsonb NOT NULL,
  content_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT','FROZEN','CANARY','RELEASED','ROLLED_BACK','REVOKED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, prompt_program_id, version)
);

CREATE TABLE IF NOT EXISTS ai_policy_bundle (
  tenant_id uuid NOT NULL,
  policy_bundle_id text NOT NULL,
  version text NOT NULL,
  source jsonb NOT NULL,
  compiled_digest text NOT NULL,
  default_decision text NOT NULL DEFAULT 'DENY' CHECK (default_decision IN ('DENY','ALLOW')),
  status text NOT NULL CHECK (status IN ('DRAFT','SHADOW','ACTIVE','ROLLED_BACK','REVOKED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, policy_bundle_id, version)
);

CREATE TABLE IF NOT EXISTS ai_data_quality_run (
  tenant_id uuid NOT NULL,
  run_id uuid NOT NULL,
  dataset_id text NOT NULL,
  dataset_version text NOT NULL,
  metrics jsonb NOT NULL,
  decision text NOT NULL CHECK (decision IN ('PASS','BLOCKED','QUARANTINED')),
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, run_id)
);

CREATE TABLE IF NOT EXISTS ai_cache_evidence (
  tenant_id uuid NOT NULL,
  cache_key text NOT NULL,
  policy_digest text NOT NULL,
  model_fingerprint text NOT NULL,
  tool_digest text NOT NULL,
  corpus_version text NOT NULL,
  prompt_digest text NOT NULL,
  value_hash text NOT NULL,
  status text NOT NULL CHECK (status IN ('ACTIVE','STALE','QUARANTINED','DELETED')),
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, cache_key)
);

CREATE TABLE IF NOT EXISTS ai_tool_contract_version (
  tenant_id uuid NOT NULL,
  tool_id text NOT NULL,
  version text NOT NULL,
  contract jsonb NOT NULL,
  effect_class text NOT NULL,
  idempotency_class text NOT NULL,
  approval_class text NOT NULL,
  digest text NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','DEPRECATED','BLOCKED','RETIRED')),
  PRIMARY KEY (tenant_id, tool_id, version)
);

CREATE TABLE IF NOT EXISTS ai_memory_isolation_audit (
  tenant_id uuid NOT NULL,
  audit_id uuid NOT NULL,
  memory_scope text NOT NULL,
  target_tenant_id uuid NOT NULL,
  result text NOT NULL CHECK (result IN ('PASS','LEAK_FOUND','BLOCKED')),
  counterexamples jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, audit_id)
);

CREATE TABLE IF NOT EXISTS ai_cost_sla_contract (
  tenant_id uuid NOT NULL,
  contract_id text NOT NULL,
  revision_set_id text NOT NULL,
  budget jsonb NOT NULL,
  pricing jsonb NOT NULL,
  sla jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT','ACTIVE','BREACHED','SETTLED','CANCELLED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, contract_id)
);

CREATE TABLE IF NOT EXISTS ai_regulated_decision (
  tenant_id uuid NOT NULL,
  decision_id text NOT NULL,
  revision_set_id text NOT NULL,
  decision jsonb NOT NULL,
  evidence_root text NOT NULL,
  oversight jsonb NOT NULL,
  appeal_status text NOT NULL CHECK (appeal_status IN ('NOT_REQUESTED','OPEN','RESOLVED','CORRECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, decision_id)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['ai_prompt_program','ai_policy_bundle','ai_data_quality_run','ai_cache_evidence','ai_tool_contract_version','ai_memory_isolation_audit','ai_cost_sla_contract','ai_regulated_decision']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', t, t);
    EXECUTE format('CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = nullif(current_setting(''app.tenant_id'', true), )::uuid) WITH CHECK (tenant_id = nullif(current_setting(app.tenant_id, true), )::uuid)', t, t);
  END LOOP;
END $$;

COMMIT;
