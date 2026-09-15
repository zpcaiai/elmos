CREATE TABLE IF NOT EXISTS execution_artifacts (
  execution_id text NOT NULL,
  artifact_type text NOT NULL,
  identity_key text NOT NULL,
  digest text NOT NULL,
  uri text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (execution_id, artifact_type, identity_key)
);
