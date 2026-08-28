BEGIN;
CREATE TABLE IF NOT EXISTS tevv_program (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, project_id uuid NOT NULL, goal_id uuid NOT NULL, revision_set_id text NOT NULL, context_profile jsonb NOT NULL, scenario_plan jsonb NOT NULL, metric_plan jsonb NOT NULL, uncertainty_plan jsonb NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS tevv_result (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, project_id uuid NOT NULL, goal_id uuid NOT NULL, revision_set_id text NOT NULL, scenario_id text NOT NULL, subgroup jsonb, metric_results jsonb NOT NULL, confidence jsonb NOT NULL, robustness jsonb NOT NULL, fairness jsonb NOT NULL, proof_status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS tevv_result_revision_scenario_idx ON tevv_result(tenant_id, revision_set_id, scenario_id);
ALTER TABLE tevv_program ENABLE ROW LEVEL SECURITY; ALTER TABLE tevv_result ENABLE ROW LEVEL SECURITY;
COMMIT;
