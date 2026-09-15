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
