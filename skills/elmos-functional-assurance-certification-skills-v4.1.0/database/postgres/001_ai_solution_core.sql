BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS ai_solution (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name text NOT NULL,
  archetype text NOT NULL,
  current_revision_set_id uuid,
  status text NOT NULL CHECK (status IN ('DRAFT','FROZEN','GENERATING','BLOCKED','COMPLETED','CANCELLED','FAILED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, name)
);

CREATE TABLE IF NOT EXISTS ai_solution_revision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  solution_id uuid NOT NULL REFERENCES ai_solution(id) ON DELETE CASCADE,
  parent_id uuid REFERENCES ai_solution_revision(id),
  revision_number bigint NOT NULL,
  source_root_hash text NOT NULL,
  requirement_hash text NOT NULL,
  ai_sir_hash text,
  target_portfolio_hash text,
  policy_bundle_hash text NOT NULL,
  toolchain_lock_hash text,
  frozen boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (solution_id, revision_number)
);

ALTER TABLE ai_solution
  ADD CONSTRAINT fk_current_revision
  FOREIGN KEY (current_revision_set_id) REFERENCES ai_solution_revision(id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS target_portfolio (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  target_id text NOT NULL,
  target_role text NOT NULL,
  adapter_name text NOT NULL,
  upstream_version text,
  adapter_digest text,
  capability_decision jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PLANNED','SUPPORTED','BOUNDED','BLOCKED','GENERATED','VALIDATED')),
  UNIQUE (revision_set_id, target_id, target_role)
);

CREATE TABLE IF NOT EXISTS generated_project (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  target_id text NOT NULL,
  repository_tree_hash text NOT NULL,
  commit_hash text,
  artifact_uri text NOT NULL,
  adapter_digest text NOT NULL,
  generated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (revision_set_id, target_id, repository_tree_hash)
);

CREATE INDEX IF NOT EXISTS idx_ai_solution_tenant_project ON ai_solution(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_target_portfolio_revision ON target_portfolio(revision_set_id);
CREATE INDEX IF NOT EXISTS idx_generated_project_revision ON generated_project(revision_set_id);
COMMIT;
