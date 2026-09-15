CREATE TABLE IF NOT EXISTS runtime_ownership (
 execution_id text PRIMARY KEY,
 owner_execution_id text NOT NULL,
 owner_epoch bigint NOT NULL,
 ownership_state text NOT NULL,
 parent_execution_id text,
 root_execution_id text NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS runtime_connection_state (
 adapter_id text NOT NULL,
 thread_id text,
 configuration_digest text,
 state text NOT NULL,
 observed_at timestamptz NOT NULL,
 PRIMARY KEY(adapter_id, thread_id)
);
