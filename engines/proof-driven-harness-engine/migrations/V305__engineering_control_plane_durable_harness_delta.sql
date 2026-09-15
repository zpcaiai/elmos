-- PostgreSQL 17 durable storage for v3.2 Engineering Control Plane & Durable Harness Delta.
--
-- This repository-authored migration provides durable persistence for:
-- 1. Execution timeline and event sequencing
-- 2. Typed content-addressed execution artifacts
-- 3. Runtime ownership, epoch fencing, and connection state
-- 4. Effect-level approval actions and release evidence verification manifests

CREATE TABLE IF NOT EXISTS execution_timeline (
  execution_id text NOT NULL,
  sequence bigint NOT NULL,
  event_id text NOT NULL,
  event_type text NOT NULL,
  occurred_at timestamptz NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (execution_id, sequence),
  UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS execution_timeline_event_type_idx ON execution_timeline(event_type);
CREATE INDEX IF NOT EXISTS execution_timeline_occurred_at_idx ON execution_timeline(occurred_at);

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

CREATE INDEX IF NOT EXISTS execution_artifacts_digest_idx ON execution_artifacts(digest);

CREATE TABLE IF NOT EXISTS runtime_ownership (
  execution_id text PRIMARY KEY,
  owner_execution_id text NOT NULL,
  owner_epoch bigint NOT NULL,
  ownership_state text NOT NULL,
  parent_execution_id text,
  root_execution_id text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runtime_ownership_state_idx ON runtime_ownership(ownership_state);
CREATE INDEX IF NOT EXISTS runtime_ownership_root_idx ON runtime_ownership(root_execution_id);

CREATE TABLE IF NOT EXISTS runtime_connection_state (
  adapter_id text NOT NULL,
  thread_id text,
  configuration_digest text,
  state text NOT NULL,
  observed_at timestamptz NOT NULL,
  PRIMARY KEY(adapter_id, thread_id)
);

CREATE TABLE IF NOT EXISTS approval_actions (
  approval_id text PRIMARY KEY,
  execution_plan_digest text NOT NULL,
  action_kind text NOT NULL,
  resource_digest text,
  decision text NOT NULL,
  expires_at timestamptz
);

CREATE INDEX IF NOT EXISTS approval_actions_kind_idx ON approval_actions(action_kind);

CREATE TABLE IF NOT EXISTS release_evidence (
  release_id text PRIMARY KEY,
  repository_commit text NOT NULL,
  status text NOT NULL,
  manifest jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS release_evidence_commit_idx ON release_evidence(repository_commit);
