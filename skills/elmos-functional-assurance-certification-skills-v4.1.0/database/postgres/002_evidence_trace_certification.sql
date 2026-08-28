BEGIN;
CREATE TABLE IF NOT EXISTS unsupported_feature (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  target_id text NOT NULL,
  feature_key text NOT NULL,
  status text NOT NULL CHECK (status IN ('CONDITIONAL','EMULATED','RUNTIME_MONITORED','WAIVED','UNSUPPORTED','BLOCKED')),
  criticality text NOT NULL CHECK (criticality IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  decision text NOT NULL,
  owner text,
  expires_at timestamptz,
  evidence_ids uuid[] NOT NULL DEFAULT '{}',
  UNIQUE (revision_set_id, target_id, feature_key)
);

CREATE TABLE IF NOT EXISTS normalized_trace (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  run_id uuid NOT NULL,
  target_id text NOT NULL,
  scenario_id text NOT NULL,
  trace_hash text NOT NULL,
  event_count integer NOT NULL CHECK (event_count >= 0),
  artifact_uri text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, target_id, scenario_id)
);

CREATE TABLE IF NOT EXISTS proof_obligation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  obligation_key text NOT NULL,
  subject_ref text NOT NULL,
  claim jsonb NOT NULL,
  assumptions jsonb NOT NULL DEFAULT '[]',
  dependencies uuid[] NOT NULL DEFAULT '{}',
  criticality text NOT NULL CHECK (criticality IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  required_assurance text NOT NULL,
  accepted_evidence jsonb NOT NULL,
  UNIQUE (revision_set_id, obligation_key)
);

CREATE TABLE IF NOT EXISTS proof_result (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  obligation_id uuid NOT NULL REFERENCES proof_obligation(id) ON DELETE CASCADE,
  status text NOT NULL CHECK (status IN ('PROVED','TESTED','BOUNDED','RUNTIME_MONITORED','WAIVED','UNKNOWN','UNSUPPORTED','REFUTED')),
  verifier_name text NOT NULL,
  verifier_digest text NOT NULL,
  input_hash text NOT NULL,
  encoding_version text,
  resource_bounds jsonb NOT NULL,
  assumptions jsonb NOT NULL DEFAULT '[]',
  evidence_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_artifact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE CASCADE,
  producer text NOT NULL,
  media_type text NOT NULL,
  artifact_uri text NOT NULL,
  sha256 text NOT NULL,
  tool_digest text,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  UNIQUE (revision_set_id, sha256)
);

CREATE TABLE IF NOT EXISTS completion_certificate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  revision_set_id uuid NOT NULL REFERENCES ai_solution_revision(id) ON DELETE RESTRICT,
  decision text NOT NULL CHECK (decision IN ('CERTIFIED','BOUNDED','BLOCKED','REVOKED')),
  gates jsonb NOT NULL,
  evidence_root text NOT NULL,
  assumptions jsonb NOT NULL DEFAULT '[]',
  waivers jsonb NOT NULL DEFAULT '[]',
  signer text NOT NULL,
  signature text,
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  revoked_at timestamptz
);
COMMIT;
