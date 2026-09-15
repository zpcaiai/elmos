CREATE TABLE IF NOT EXISTS approval_actions (
 approval_id text PRIMARY KEY,
 execution_plan_digest text NOT NULL,
 action_kind text NOT NULL,
 resource_digest text,
 decision text NOT NULL,
 expires_at timestamptz
);
CREATE TABLE IF NOT EXISTS release_evidence (
 release_id text PRIMARY KEY,
 repository_commit text NOT NULL,
 status text NOT NULL,
 manifest jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
