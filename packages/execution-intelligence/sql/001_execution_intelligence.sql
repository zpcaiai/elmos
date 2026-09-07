-- packages/execution-intelligence — durable execution schema (PostgreSQL 14+)
--
-- Design rules this schema enforces rather than documents:
--   * A run's event stream carries a gapless, monotonic sequence per run, so a
--     client can reconnect with Last-Event-ID and be replayed exactly what it
--     missed. Sequence allocation is inside the same transaction as the state
--     change, so an event can never describe a state that was rolled back.
--   * Every side effect goes through idempotency_keys. A replayed request
--     returns the original response instead of performing the effect twice.
--   * Outbox rows are written in the same transaction as the state change and
--     published afterwards, so "state changed but nobody was told" cannot happen.
--   * Artifacts are content-addressed and immutable. Re-publishing identical
--     bytes is a no-op; publishing different bytes under the same logical name
--     creates a new version rather than overwriting.
--
-- The Python package in src/ does forecasting and ships a SQLite reference
-- implementation of the same contract (see durable.py). This file is the
-- production target.

BEGIN;

CREATE SCHEMA IF NOT EXISTS execution_intelligence;
SET search_path TO execution_intelligence, public;

-- ---------------------------------------------------------------- tenancy ----

CREATE TABLE IF NOT EXISTS tenant (
    tenant_id      TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE tenant IS
    'Every row in every other table is scoped by tenant_id. Cross-tenant reads must be impossible by construction, not by query hygiene.';

-- ----------------------------------------------------------------- runs ------

CREATE TYPE run_state AS ENUM (
    'pending', 'running', 'paused', 'recovering', 'succeeded', 'failed', 'cancelled'
);

CREATE TABLE IF NOT EXISTS run (
    run_id             UUID PRIMARY KEY,
    tenant_id          TEXT NOT NULL REFERENCES tenant(tenant_id),
    project_id         TEXT NOT NULL,
    dag_id             TEXT NOT NULL,
    state              run_state NOT NULL DEFAULT 'pending',
    definition_of_done JSONB NOT NULL,
    forecast           JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    -- Highest event sequence handed out for this run. Allocation happens under
    -- the row lock taken by the state transition, which is what makes the
    -- stream gapless.
    last_event_seq     BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT run_finished_requires_terminal_state CHECK (
        (finished_at IS NULL) OR (state IN ('succeeded', 'failed', 'cancelled'))
    )
);

CREATE INDEX IF NOT EXISTS run_tenant_state_idx ON run (tenant_id, state, created_at DESC);

-- ----------------------------------------------------------------- tasks -----

CREATE TYPE task_state AS ENUM (
    'pending', 'ready', 'running', 'blocked', 'succeeded', 'failed', 'skipped', 'cancelled'
);

CREATE TABLE IF NOT EXISTS task (
    run_id         UUID NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    task_id        TEXT NOT NULL,
    tenant_id      TEXT NOT NULL REFERENCES tenant(tenant_id),
    name           TEXT NOT NULL,
    category       TEXT,
    complexity     TEXT,
    depends_on     TEXT[] NOT NULL DEFAULT '{}',
    worker_units   NUMERIC(6, 3) NOT NULL DEFAULT 1 CHECK (worker_units > 0),
    state          task_state NOT NULL DEFAULT 'pending',
    attempt_count  INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    estimate       JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, task_id)
);

CREATE INDEX IF NOT EXISTS task_run_state_idx ON task (run_id, state);

CREATE TYPE attempt_outcome AS ENUM (
    'succeeded', 'transient_failure', 'permanent_failure', 'business_conflict', 'cancelled', 'lost'
);

-- One row per execution attempt. 'lost' is what a heartbeat sweeper writes for
-- an attempt whose worker disappeared: it is not the same as a failure, and
-- conflating the two is how a recovered run double-counts its retries.
CREATE TABLE IF NOT EXISTS task_attempt (
    attempt_id     UUID PRIMARY KEY,
    run_id         UUID NOT NULL,
    task_id        TEXT NOT NULL,
    tenant_id      TEXT NOT NULL REFERENCES tenant(tenant_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    worker_id      TEXT NOT NULL,
    outcome        attempt_outcome,
    failure_class  TEXT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    queue_ms       BIGINT,
    execution_ms   BIGINT,
    build_ms       BIGINT,
    test_ms        BIGINT,
    recovery_ms    BIGINT,
    FOREIGN KEY (run_id, task_id) REFERENCES task(run_id, task_id) ON DELETE CASCADE,
    UNIQUE (run_id, task_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS task_attempt_heartbeat_idx
    ON task_attempt (heartbeat_at) WHERE finished_at IS NULL;

-- ------------------------------------------------------------ checkpoints ----

CREATE TABLE IF NOT EXISTS checkpoint (
    checkpoint_id   UUID PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    task_id         TEXT,
    tenant_id       TEXT NOT NULL REFERENCES tenant(tenant_id),
    kind            TEXT NOT NULL CHECK (kind IN ('workspace', 'git', 'object-store', 'state')),
    git_commit      TEXT,
    git_branch      TEXT,
    workspace_uri   TEXT,
    workspace_digest TEXT,
    state_blob      JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS checkpoint_run_created_idx ON checkpoint (run_id, created_at DESC);

COMMENT ON COLUMN checkpoint.workspace_digest IS
    'Digest of the snapshot contents. Recovery compares this against the restored tree before deciding to retry; a mismatch means restore, not re-run.';

-- ----------------------------------------------------------------- events ----

CREATE TABLE IF NOT EXISTS run_event (
    run_id      UUID NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    seq         BIGINT NOT NULL CHECK (seq > 0),
    tenant_id   TEXT NOT NULL REFERENCES tenant(tenant_id),
    event_type  TEXT NOT NULL,
    task_id     TEXT,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS run_event_stream_idx ON run_event (run_id, seq);

COMMENT ON TABLE run_event IS
    'Append-only. A client reconnecting with Last-Event-ID: N is served every row with seq > N in seq order. Rows are never updated or deleted before the run is purged.';

-- Allocates the next sequence number under the run row lock, so two concurrent
-- writers cannot mint the same seq or leave a hole.
CREATE OR REPLACE FUNCTION append_run_event(
    p_run_id UUID,
    p_tenant_id TEXT,
    p_event_type TEXT,
    p_task_id TEXT,
    p_payload JSONB
) RETURNS BIGINT AS $$
DECLARE
    next_seq BIGINT;
BEGIN
    UPDATE run
       SET last_event_seq = last_event_seq + 1
     WHERE run_id = p_run_id AND tenant_id = p_tenant_id
    RETURNING last_event_seq INTO next_seq;

    IF next_seq IS NULL THEN
        RAISE EXCEPTION 'unknown run % for tenant %', p_run_id, p_tenant_id;
    END IF;

    INSERT INTO run_event (run_id, seq, tenant_id, event_type, task_id, payload)
    VALUES (p_run_id, next_seq, p_tenant_id, p_event_type, p_task_id, p_payload);

    RETURN next_seq;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------- idempotency -----

CREATE TABLE IF NOT EXISTS idempotency_key (
    tenant_id       TEXT NOT NULL REFERENCES tenant(tenant_id),
    key             TEXT NOT NULL,
    scope           TEXT NOT NULL,
    request_digest  TEXT NOT NULL,
    response        JSONB,
    state           TEXT NOT NULL DEFAULT 'in_flight'
                    CHECK (state IN ('in_flight', 'completed', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, scope, key)
);

COMMENT ON COLUMN idempotency_key.request_digest IS
    'Digest of the request body. Reusing a key with a different body is a client bug and must be rejected with 409, not silently served the old response.';

-- -------------------------------------------------------------- outbox -------

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenant(tenant_id),
    run_id        UUID,
    topic         TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    attempts      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS outbox_unpublished_idx
    ON outbox (created_at) WHERE published_at IS NULL;

-- ------------------------------------------------------------ artifacts ------

CREATE TABLE IF NOT EXISTS artifact (
    artifact_id   UUID PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenant(tenant_id),
    run_id        UUID NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    logical_name  TEXT NOT NULL,
    version       INTEGER NOT NULL CHECK (version >= 1),
    media_type    TEXT NOT NULL,
    size_bytes    BIGINT NOT NULL CHECK (size_bytes >= 0),
    sha256        TEXT NOT NULL CHECK (char_length(sha256) = 64),
    storage_uri   TEXT NOT NULL,
    git_ref       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, logical_name, version),
    UNIQUE (run_id, logical_name, sha256)
);

COMMENT ON TABLE artifact IS
    'Immutable. The (run, logical_name, sha256) unique constraint makes re-publishing identical bytes a no-op; different bytes take the next version.';

-- ------------------------------------------------------------- telemetry -----

-- Feeds `elmos-ei calibrate`. Column names match the observability contract the
-- Skills declare, so a telemetry export is a plain SELECT.
CREATE TABLE IF NOT EXISTS model_usage (
    usage_id            UUID PRIMARY KEY,
    tenant_id           TEXT NOT NULL REFERENCES tenant(tenant_id),
    run_id              UUID NOT NULL REFERENCES run(run_id) ON DELETE CASCADE,
    task_id             TEXT NOT NULL,
    step_id             TEXT,
    attempt             INTEGER NOT NULL CHECK (attempt >= 1),
    model               TEXT NOT NULL,
    input_tokens        BIGINT NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    cached_input_tokens BIGINT NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
    cache_write_tokens  BIGINT NOT NULL DEFAULT 0 CHECK (cache_write_tokens >= 0),
    output_tokens       BIGINT NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    reasoning_tokens    BIGINT NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
    queue_ms            BIGINT,
    execution_ms        BIGINT,
    status              TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS model_usage_run_task_idx ON model_usage (run_id, task_id, attempt);

-- Rolls executed usage up into exactly the shape `calibrate` consumes as JSONL.
CREATE OR REPLACE VIEW calibration_input AS
SELECT
    t.run_id,
    t.task_id,
    t.category                                          AS task_type,
    t.complexity,
    u.model,
    (t.estimate ->> 'most_likely_minutes')::NUMERIC     AS estimated_minutes,
    SUM(COALESCE(a.execution_ms, 0)) / 60000.0          AS actual_minutes,
    -- The five token categories are disjoint and there is no stored 'total';
    -- summing them here is what keeps this view from silently returning NULL.
    COALESCE((t.estimate #>> '{token_profile,input}')::NUMERIC, 0)
      + COALESCE((t.estimate #>> '{token_profile,cached_input}')::NUMERIC, 0)
      + COALESCE((t.estimate #>> '{token_profile,cache_write}')::NUMERIC, 0)
      + COALESCE((t.estimate #>> '{token_profile,output}')::NUMERIC, 0)
      + COALESCE((t.estimate #>> '{token_profile,reasoning_output}')::NUMERIC, 0)
                                                        AS estimated_total_tokens,
    SUM(u.input_tokens + u.cached_input_tokens + u.cache_write_tokens
        + u.output_tokens + u.reasoning_tokens)         AS actual_total_tokens
FROM task t
JOIN model_usage u ON u.run_id = t.run_id AND u.task_id = t.task_id
LEFT JOIN task_attempt a ON a.run_id = t.run_id AND a.task_id = t.task_id
WHERE t.state = 'succeeded'
GROUP BY t.run_id, t.task_id, t.category, t.complexity, u.model, t.estimate;

COMMIT;
