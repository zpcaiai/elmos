-- PostgreSQL 17 durable storage for the v3.1 runtime-assurance delta.
--
-- This repository-authored migration treats the source archive as inert input.
-- It is applied only by tools/apply_delta_migration.py, which owns the
-- transaction and writes the detached digest after these exact bytes execute.
-- Application identities must obtain app.tenant_id, app.project_id and
-- app.actor_id from authenticated middleware; request JSON is never authority.

DO $runtime_assurance_prerequisite$
DECLARE
  observed_name text;
  observed_digest text;
  server_version_number integer;
BEGIN
  server_version_number := current_setting('server_version_num')::integer;
  IF server_version_number < 170000 OR server_version_number >= 180000 THEN
    RAISE EXCEPTION 'runtime-assurance V304 requires PostgreSQL 17 exactly'
      USING ERRCODE = '0A000';
  END IF;

  IF to_regclass('proof_harness_runtime.schema_migrations') IS NULL
     OR to_regclass('proof_harness_runtime.migration_digest_ledger') IS NULL
     OR to_regclass('proof_harness_runtime.projects') IS NULL
     OR to_regclass('proof_harness_runtime.actors') IS NULL
     OR to_regclass('proof_harness_runtime.runs') IS NULL
     OR to_regprocedure('proof_harness.current_tenant_key()') IS NULL
     OR to_regprocedure('proof_harness.current_project_key()') IS NULL
     OR to_regprocedure('proof_harness.reject_immutable_mutation()') IS NULL THEN
    RAISE EXCEPTION 'runtime-assurance V304 requires the complete V001 base schema'
      USING ERRCODE = '55000';
  END IF;

  SELECT migration_name
    INTO observed_name
    FROM proof_harness_runtime.schema_migrations
   WHERE version = 1;
  IF observed_name IS DISTINCT FROM 'V001__proof_harness_core.sql' THEN
    RAISE EXCEPTION 'runtime-assurance V304 requires the exact V001 migration record'
      USING ERRCODE = '55000';
  END IF;

  SELECT content_sha256
    INTO observed_digest
    FROM proof_harness_runtime.migration_digest_ledger
   WHERE version = 1
     AND migration_name = 'V001__proof_harness_core.sql';
  IF observed_digest IS DISTINCT FROM
       'sha256:bdddb1ff1a962df931df57e4d8d428e08c232b4ac88e5189bf8c2ccde34e388f' THEN
    RAISE EXCEPTION 'runtime-assurance V304 base migration digest mismatch'
      USING ERRCODE = '55000';
  END IF;

  IF to_regclass('proof_harness_runtime.runtime_assurance_migrations') IS NOT NULL
     OR to_regclass('proof_harness_runtime.runtime_assurance_migration_digest_ledger') IS NOT NULL THEN
    RAISE EXCEPTION 'runtime-assurance migration metadata already exists; reconcile before retry'
      USING ERRCODE = '55000';
  END IF;
END
$runtime_assurance_prerequisite$;

CREATE TABLE proof_harness_runtime.runtime_assurance_migrations (
  version integer NOT NULL CHECK (version > 0),
  migration_name text NOT NULL CHECK (length(btrim(migration_name)) BETWEEN 1 AND 255),
  package_version text NOT NULL CHECK (package_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  required_base_version integer NOT NULL CHECK (required_base_version = 1),
  required_base_sha256 text NOT NULL CHECK (required_base_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  control_fingerprint_sha256 text CHECK (
    control_fingerprint_sha256 IS NULL
    OR control_fingerprint_sha256 ~ '^sha256:[0-9a-f]{64}$'
  ),
  applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (version, migration_name),
  UNIQUE (package_version),
  CHECK (version = 304),
  CHECK (migration_name = 'V304__harness_runtime_assurance_delta.sql')
);

CREATE TABLE proof_harness_runtime.runtime_assurance_migration_digest_ledger (
  version integer NOT NULL,
  migration_name text NOT NULL,
  content_sha256 text NOT NULL CHECK (content_sha256 ~ '^sha256:[0-9a-f]{64}$'),
  recorded_by text NOT NULL CHECK (length(btrim(recorded_by)) BETWEEN 1 AND 255),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (version, migration_name),
  UNIQUE (content_sha256),
  FOREIGN KEY (version, migration_name)
    REFERENCES proof_harness_runtime.runtime_assurance_migrations(version, migration_name)
    ON DELETE RESTRICT
);

INSERT INTO proof_harness_runtime.runtime_assurance_migrations(
  version,
  migration_name,
  package_version,
  required_base_version,
  required_base_sha256
) VALUES (
  304,
  'V304__harness_runtime_assurance_delta.sql',
  '3.1.0',
  1,
  'sha256:bdddb1ff1a962df931df57e4d8d428e08c232b4ac88e5189bf8c2ccde34e388f'
);

CREATE OR REPLACE FUNCTION proof_harness_runtime.is_bounded_text_array(
  value jsonb,
  maximum_elements integer,
  maximum_text_length integer
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = pg_catalog
AS $bounded_text_array$
  SELECT jsonb_typeof(value) = 'array'
     AND maximum_elements BETWEEN 0 AND 1024
     AND maximum_text_length BETWEEN 1 AND 8192
     AND jsonb_array_length(value) <= maximum_elements
     AND pg_column_size(value) <= 1048576
     AND NOT EXISTS (
       SELECT 1
         FROM jsonb_array_elements(value) AS item(element)
        WHERE jsonb_typeof(element) <> 'string'
           OR length(btrim(element #>> '{}')) < 1
           OR octet_length(element #>> '{}') > maximum_text_length
     )
     AND (
       SELECT count(*) = count(DISTINCT element #>> '{}')
         FROM jsonb_array_elements(value) AS item(element)
     )
$bounded_text_array$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.is_valid_interceptor_chain(value jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = pg_catalog
AS $valid_interceptor_chain$
  SELECT jsonb_typeof(value) = 'array'
     AND jsonb_array_length(value) <= 64
     AND pg_column_size(value) <= 1048576
     AND NOT EXISTS (
       SELECT 1
         FROM jsonb_array_elements(value) AS item(element)
        WHERE jsonb_typeof(element) <> 'object'
           OR NOT (element ?& ARRAY['interceptorId', 'version', 'decisionHash'])
           OR (SELECT count(*) FROM jsonb_object_keys(element)) <> 3
           OR length(btrim(element ->> 'interceptorId')) NOT BETWEEN 1 AND 512
           OR length(btrim(element ->> 'version')) NOT BETWEEN 1 AND 128
           OR (element ->> 'decisionHash') !~ '^sha256:[0-9a-f]{64}$'
     )
$valid_interceptor_chain$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.is_valid_workspace_scopes(value jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = pg_catalog
AS $valid_workspace_scopes$
  SELECT proof_harness_runtime.is_bounded_text_array(value, 256, 2048)
     AND jsonb_array_length(value) >= 1
     AND NOT EXISTS (
       SELECT 1
         FROM jsonb_array_elements_text(value) AS scope(path)
        WHERE path IS DISTINCT FROM btrim(path)
           OR left(path, 1) = '/'
           OR position(E'\\' IN path) > 0
           OR EXISTS (
             SELECT 1
               FROM unnest(string_to_array(path, '/')) AS segment(name)
              WHERE name IN ('', '.', '..')
           )
     )
$valid_workspace_scopes$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.canonical_jsonb_text(value jsonb)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
SET search_path = pg_catalog, proof_harness_runtime
AS $canonical_jsonb_text$
DECLARE
  kind text := jsonb_typeof(value);
  rendered text;
BEGIN
  IF kind = 'object' THEN
    SELECT '{' || COALESCE(string_agg(
      to_jsonb(member.key)::text || ':' ||
        proof_harness_runtime.canonical_jsonb_text(member.value),
      ',' ORDER BY member.key COLLATE "C"
    ), '') || '}' INTO rendered
      FROM jsonb_each(value) AS member(key, value);
    RETURN rendered;
  END IF;
  IF kind = 'array' THEN
    SELECT '[' || COALESCE(string_agg(
      proof_harness_runtime.canonical_jsonb_text(member.value),
      ',' ORDER BY member.ordinality
    ), '') || ']' INTO rendered
      FROM jsonb_array_elements(value) WITH ORDINALITY AS member(value, ordinality);
    RETURN rendered;
  END IF;
  RETURN value::text;
END
$canonical_jsonb_text$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.append_runtime_assurance_event(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_event_type text,
  p_subject_id text,
  p_payload jsonb,
  p_created_at timestamptz
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $append_runtime_assurance_event$
DECLARE
  event_id text := 'evt-' || gen_random_uuid()::text;
  payload_json text;
  payload_sha256 text;
BEGIN
  IF p_event_type !~ '^[A-Z][A-Z0-9_]{0,127}$'
     OR p_subject_id IS NULL OR btrim(p_subject_id) = ''
     OR p_created_at IS NULL THEN
    RAISE EXCEPTION 'runtime-assurance event identity is invalid'
      USING ERRCODE = '22023';
  END IF;
  payload_json := proof_harness_runtime.canonical_jsonb_text(p_payload);
  payload_sha256 := 'sha256:' || encode(
    sha256(
      convert_to('elmos.proof-harness.v1', 'UTF8') || decode('00', 'hex') ||
      convert_to('event-payload', 'UTF8') || decode('00', 'hex') ||
      convert_to(payload_json, 'UTF8')
    ),
    'hex'
  );
  INSERT INTO proof_harness_runtime.audit_events(
    tenant_id, project_id, event_id, actor_id, event_type, subject_id,
    payload_json, payload_sha256, created_at
  ) VALUES (
    p_tenant_id, p_project_id, event_id, p_actor_id, p_event_type, p_subject_id,
    p_payload, payload_sha256, p_created_at
  );
  INSERT INTO proof_harness_runtime.outbox_events(
    tenant_id, project_id, event_id, topic, aggregate_id,
    payload_json, payload_sha256, created_at
  ) VALUES (
    p_tenant_id, p_project_id, event_id,
    'proof-harness.' || lower(p_event_type), p_subject_id,
    p_payload, payload_sha256, p_created_at
  );
  RETURN event_id;
END
$append_runtime_assurance_event$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.runtime_assurance_event_is_exact(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_event_type text,
  p_subject_id text,
  p_event_id text,
  p_payload_sha256 text,
  p_payload jsonb,
  p_created_at timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $runtime_assurance_event_is_exact$
DECLARE
  payload_json text;
  payload_sha256 text;
  matched bigint;
BEGIN
  payload_json := proof_harness_runtime.canonical_jsonb_text(p_payload);
  payload_sha256 := 'sha256:' || encode(
    sha256(
      convert_to('elmos.proof-harness.v1', 'UTF8') || decode('00', 'hex') ||
      convert_to('event-payload', 'UTF8') || decode('00', 'hex') ||
      convert_to(payload_json, 'UTF8')
    ),
    'hex'
  );
  IF payload_sha256 IS DISTINCT FROM p_payload_sha256 THEN
    RETURN false;
  END IF;
  SELECT count(*) INTO matched
    FROM proof_harness_runtime.audit_events AS audit
    JOIN proof_harness_runtime.outbox_events AS event
      ON event.tenant_id = audit.tenant_id
     AND event.project_id = audit.project_id
     AND event.event_id = audit.event_id
   WHERE audit.tenant_id = p_tenant_id
     AND audit.project_id = p_project_id
     AND audit.actor_id = p_actor_id
     AND audit.event_id = p_event_id
     AND audit.event_type = p_event_type
     AND audit.subject_id = p_subject_id
     AND audit.payload_json = p_payload
     AND audit.payload_sha256 = p_payload_sha256
     AND audit.created_at = p_created_at
     AND event.topic = 'proof-harness.' || lower(p_event_type)
     AND event.aggregate_id = p_subject_id
     AND event.payload_json = p_payload
     AND event.payload_sha256 = p_payload_sha256
     AND event.created_at = p_created_at;
  RETURN matched = 1;
END
$runtime_assurance_event_is_exact$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_runtime_run_actor_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $guard_runtime_run_actor_identity$
BEGIN
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id THEN
    RAISE EXCEPTION 'runtime run tenant/project/run/actor identity is immutable'
      USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END
$guard_runtime_run_actor_identity$;

CREATE TRIGGER runs_actor_identity_guard
BEFORE UPDATE ON proof_harness_runtime.runs
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_runtime_run_actor_identity();

CREATE OR REPLACE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $assert_runtime_assurance_scope$
DECLARE
  candidate jsonb;
  bounded_field record;
  trusted_tenant text;
  trusted_project text;
  trusted_actor text;
  trusted_run text;
  trusted_epoch text;
  trusted_fence text;
  trusted_authority text;
  trusted_revision_set text;
BEGIN
  candidate := to_jsonb(NEW);
  FOR bounded_field IN
    SELECT * FROM (VALUES
      ('tenant_id', 255),
      ('project_id', 255),
      ('run_id', 512),
      ('actor_id', 512),
      ('invocation_id', 512),
      ('call_id', 512),
      ('tool_id', 512),
      ('plan_id', 512),
      ('lease_id', 512),
      ('environment_id', 512),
      ('server_id', 512),
      ('snapshot_id', 512),
      ('effect_id', 512),
      ('workspace_id', 512),
      ('repository_id', 1024),
      ('base_revision', 512),
      ('event_type', 255),
      ('event_id', 512),
      ('correlation_id', 512),
      ('ingress_id', 512),
      ('producer_execution_id', 512),
      ('deduplication_key', 512),
      ('budget_reservation_id', 512)
      ,('reservation_id', 512)
      ,('operation_invocation_id', 512)
    ) AS limits(field_name, maximum_octets)
  LOOP
    IF candidate ? bounded_field.field_name
       AND candidate ->> bounded_field.field_name IS NOT NULL
       AND octet_length(candidate ->> bounded_field.field_name)
           > bounded_field.maximum_octets THEN
      RAISE EXCEPTION 'runtime-assurance indexed field % exceeds its byte bound',
        bounded_field.field_name USING ERRCODE = '22001';
    END IF;
  END LOOP;
  trusted_tenant := proof_harness.current_tenant_key();
  trusted_project := proof_harness.current_project_key();
  trusted_actor := current_setting('app.actor_id', true);
  trusted_run := current_setting('app.run_id', true);
  trusted_epoch := current_setting('app.execution_epoch', true);
  trusted_fence := current_setting('app.fencing_generation', true);
  trusted_authority := current_setting('app.authority_revision', true);
  trusted_revision_set := current_setting('app.revision_set_id', true);
  IF trusted_actor IS NULL
     OR trusted_actor = ''
     OR trusted_run IS NULL
     OR trusted_run = ''
     OR trusted_epoch IS NULL
     OR trusted_epoch = ''
     OR trusted_fence IS NULL
     OR trusted_fence = ''
     OR trusted_authority IS NULL
     OR trusted_authority = ''
     OR trusted_revision_set IS NULL
     OR trusted_revision_set = ''
     OR NEW.tenant_id IS DISTINCT FROM trusted_tenant
     OR NEW.project_id IS DISTINCT FROM trusted_project
     OR NEW.actor_id IS DISTINCT FROM trusted_actor
     OR NEW.run_id IS DISTINCT FROM trusted_run
     OR NEW.execution_epoch::text IS DISTINCT FROM trusted_epoch
     OR NEW.fencing_generation::text IS DISTINCT FROM trusted_fence
     OR NEW.authority_revision IS DISTINCT FROM trusted_authority
     OR NEW.revision_set_id IS DISTINCT FROM trusted_revision_set THEN
    RAISE EXCEPTION 'runtime-assurance scope does not match trusted transaction context'
      USING ERRCODE = '42501';
  END IF;
  IF TG_OP = 'UPDATE' AND (
       OLD.tenant_id IS DISTINCT FROM trusted_tenant
       OR OLD.project_id IS DISTINCT FROM trusted_project
       OR OLD.actor_id IS DISTINCT FROM trusted_actor
       OR OLD.run_id IS DISTINCT FROM trusted_run
       OR OLD.execution_epoch::text IS DISTINCT FROM trusted_epoch
       OR OLD.fencing_generation::text IS DISTINCT FROM trusted_fence
       OR OLD.authority_revision IS DISTINCT FROM trusted_authority
       OR OLD.revision_set_id IS DISTINCT FROM trusted_revision_set
       OR OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
       OR OLD.project_id IS DISTINCT FROM NEW.project_id
       OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
       OR OLD.run_id IS DISTINCT FROM NEW.run_id
       OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
       OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
       OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
       OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     ) THEN
    RAISE EXCEPTION 'runtime-assurance scope is immutable and must match trusted context'
      USING ERRCODE = '42501';
  END IF;
  IF NOT EXISTS (
    SELECT 1
      FROM proof_harness_runtime.runs AS run
     WHERE run.tenant_id = NEW.tenant_id
       AND run.project_id = NEW.project_id
       AND run.run_id = NEW.run_id
       AND run.actor_id = NEW.actor_id
       AND run.execution_epoch = NEW.execution_epoch
       AND run.fencing_generation = NEW.fencing_generation
       AND run.revision_set_id = NEW.revision_set_id
  ) THEN
    RAISE EXCEPTION 'runtime-assurance row is stale or outside the exact run scope'
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END
$assert_runtime_assurance_scope$;

CREATE TABLE proof_harness_runtime.tool_result_commits (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  invocation_id text NOT NULL CHECK (length(btrim(invocation_id)) BETWEEN 1 AND 512),
  call_id text NOT NULL CHECK (length(btrim(call_id)) BETWEEN 1 AND 512),
  attempt integer NOT NULL CHECK (attempt >= 1),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  execution_plan_hash text NOT NULL CHECK (execution_plan_hash ~ '^sha256:[0-9a-f]{64}$'),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  raw_result_ref text NOT NULL CHECK (length(btrim(raw_result_ref)) BETWEEN 1 AND 2048),
  effective_result_ref text NOT NULL CHECK (length(btrim(effective_result_ref)) BETWEEN 1 AND 2048),
  interceptor_chain jsonb NOT NULL CHECK (
    proof_harness_runtime.is_valid_interceptor_chain(interceptor_chain)
  ),
  mutation_provenance_ref text CHECK (
    mutation_provenance_ref IS NULL OR length(btrim(mutation_provenance_ref)) BETWEEN 1 AND 2048
  ),
  failure_kind text CHECK (failure_kind IS NULL OR failure_kind IN (
    'INTERCEPTOR_REJECTED', 'INTERCEPTOR_ERROR', 'VALIDATION_FAILED',
    'AUTHORITY_REVOKED', 'CANCELLED', 'TIMED_OUT'
  )),
  failure_reason text CHECK (
    failure_reason IS NULL OR length(btrim(failure_reason)) BETWEEN 1 AND 2048
  ),
  state text NOT NULL CHECK (state IN (
    'RAW_CAPTURED', 'INTERCEPTING', 'COMMITTED', 'PUBLISHED', 'ABORTED'
  )),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  committed_at timestamptz,
  published_at timestamptz,
  aborted_at timestamptz,
  recovery_evidence_ref text CHECK (
    recovery_evidence_ref IS NULL
    OR length(btrim(recovery_evidence_ref)) BETWEEN 1 AND 2048
  ),
  mutation_event_id text NOT NULL CHECK (
    mutation_event_id ~ '^evt-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  mutation_event_type text NOT NULL CHECK (mutation_event_type IN (
    'TOOL_RESULT_RAW_CAPTURED', 'TOOL_RESULT_INTERCEPTING',
    'TOOL_RESULT_COMMITTED', 'TOOL_RESULT_PUBLISHED',
    'TOOL_RESULT_ABORTED', 'TOOL_RESULT_ABORTED_RECOVERY'
  )),
  mutation_payload_sha256 text NOT NULL CHECK (
    mutation_payload_sha256 ~ '^sha256:[0-9a-f]{64}$'
  ),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id, call_id, attempt
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (updated_at >= created_at),
  CHECK (state NOT IN ('COMMITTED', 'PUBLISHED') OR committed_at IS NOT NULL),
  CHECK (state NOT IN ('RAW_CAPTURED', 'INTERCEPTING') OR committed_at IS NULL),
  CHECK (state NOT IN ('RAW_CAPTURED', 'INTERCEPTING') OR (
    effective_result_ref = raw_result_ref
    AND interceptor_chain = '[]'::jsonb
    AND mutation_provenance_ref IS NULL
    AND failure_kind IS NULL
    AND failure_reason IS NULL
    AND published_at IS NULL
    AND aborted_at IS NULL
  )),
  CHECK (state NOT IN ('COMMITTED', 'PUBLISHED') OR (
    failure_kind IS NULL AND failure_reason IS NULL AND aborted_at IS NULL
  )),
  CHECK ((state = 'PUBLISHED') = (published_at IS NOT NULL)),
  CHECK ((state = 'ABORTED') = (aborted_at IS NOT NULL)),
  CHECK ((state = 'ABORTED') = (failure_kind IS NOT NULL)),
  CHECK ((state = 'ABORTED') = (failure_reason IS NOT NULL)),
  CHECK (recovery_evidence_ref IS NULL OR state = 'ABORTED'),
  CHECK (
    (state = 'RAW_CAPTURED' AND mutation_event_type = 'TOOL_RESULT_RAW_CAPTURED')
    OR (state = 'INTERCEPTING'
        AND mutation_event_type = 'TOOL_RESULT_INTERCEPTING')
    OR (state = 'COMMITTED' AND mutation_event_type = 'TOOL_RESULT_COMMITTED')
    OR (state = 'PUBLISHED' AND mutation_event_type = 'TOOL_RESULT_PUBLISHED')
    OR (state = 'ABORTED'
        AND mutation_event_type IN (
          'TOOL_RESULT_ABORTED', 'TOOL_RESULT_ABORTED_RECOVERY'
        ))
  ),
  CHECK (committed_at IS NULL OR committed_at >= created_at),
  CHECK (published_at IS NULL OR (committed_at IS NOT NULL AND published_at >= committed_at)),
  CHECK (aborted_at IS NULL OR aborted_at >= created_at),
  CHECK (aborted_at IS NULL OR committed_at IS NULL OR aborted_at >= committed_at)
);

CREATE TABLE proof_harness_runtime.step_execution_plans (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  plan_id text NOT NULL CHECK (length(btrim(plan_id)) BETWEEN 1 AND 512),
  step_id text NOT NULL CHECK (length(btrim(step_id)) BETWEEN 1 AND 512),
  plan_hash text NOT NULL CHECK (plan_hash ~ '^sha256:[0-9a-f]{64}$'),
  model_snapshot jsonb NOT NULL CHECK (
    jsonb_typeof(model_snapshot) = 'object' AND pg_column_size(model_snapshot) <= 262144
  ),
  tool_plan jsonb NOT NULL CHECK (
    jsonb_typeof(tool_plan) = 'object' AND pg_column_size(tool_plan) <= 1048576
  ),
  tool_contracts jsonb NOT NULL CHECK (
    jsonb_typeof(tool_contracts) = 'object' AND pg_column_size(tool_contracts) <= 1048576
  ),
  handler_digests jsonb NOT NULL CHECK (
    jsonb_typeof(handler_digests) = 'object' AND pg_column_size(handler_digests) <= 262144
  ),
  capabilities jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    proof_harness_runtime.is_bounded_text_array(capabilities, 256, 512)
  ),
  tool_mode text NOT NULL CHECK (length(btrim(tool_mode)) BETWEEN 1 AND 128),
  environment_snapshot_id text NOT NULL CHECK (
    length(btrim(environment_snapshot_id)) BETWEEN 1 AND 512
  ),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  state text NOT NULL CHECK (state IN ('CANDIDATE', 'FINALIZED', 'ACTIVE', 'RETIRED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  finalized_at timestamptz,
  activated_at timestamptz,
  retired_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (updated_at >= created_at),
  CHECK ((state IN ('FINALIZED', 'ACTIVE', 'RETIRED')) = (finalized_at IS NOT NULL)),
  CHECK ((state IN ('ACTIVE', 'RETIRED')) = (activated_at IS NOT NULL)),
  CHECK ((state = 'RETIRED') = (retired_at IS NOT NULL)),
  CHECK (finalized_at IS NULL OR finalized_at >= created_at),
  CHECK (activated_at IS NULL OR (finalized_at IS NOT NULL AND activated_at >= finalized_at)),
  CHECK (retired_at IS NULL OR (activated_at IS NOT NULL AND retired_at >= activated_at))
);

CREATE TABLE proof_harness_runtime.step_plan_tool_bindings (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  plan_hash text NOT NULL CHECK (plan_hash ~ '^sha256:[0-9a-f]{64}$'),
  tool_id text NOT NULL CHECK (length(btrim(tool_id)) BETWEEN 1 AND 512),
  tool_contract jsonb NOT NULL CHECK (
    jsonb_typeof(tool_contract) = 'object'
    AND pg_column_size(tool_contract) <= 1048576
  ),
  contract_digest text NOT NULL CHECK (contract_digest ~ '^sha256:[0-9a-f]{64}$'),
  handler_digest text NOT NULL CHECK (handler_digest ~ '^sha256:[0-9a-f]{64}$'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash, tool_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash
  ) REFERENCES proof_harness_runtime.step_execution_plans(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash
  ) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.capability_leases (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  lease_id text NOT NULL CHECK (length(btrim(lease_id)) BETWEEN 1 AND 512),
  invocation_id text NOT NULL CHECK (length(btrim(invocation_id)) BETWEEN 1 AND 512),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
  ),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (
    authority_revision ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  capability_set jsonb NOT NULL CHECK (
    jsonb_array_length(capability_set) >= 1
    AND proof_harness_runtime.is_bounded_text_array(capability_set, 256, 512)
  ),
  delegation_allowed boolean NOT NULL DEFAULT false,
  state text NOT NULL CHECK (state IN ('ACTIVE', 'REVOKED', 'EXPIRED')),
  issued_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  revocation_reason text CHECK (revocation_reason IS NULL OR revocation_reason IN (
    'CANCELLED', 'TIMED_OUT', 'TURN_ABORTED', 'EXECUTOR_REPLACED',
    'AUTHORITY_REVOKED', 'COMPLETED'
  )),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, lease_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (issued_at < expires_at),
  CHECK (expires_at <= issued_at + interval '15 minutes'),
  CHECK (updated_at >= issued_at),
  CHECK ((state = 'REVOKED') = (revoked_at IS NOT NULL)),
  CHECK ((state = 'REVOKED') = (revocation_reason IS NOT NULL)),
  CHECK (revoked_at IS NULL OR revoked_at >= issued_at)
);

CREATE UNIQUE INDEX capability_leases_active_invocation_idx
  ON proof_harness_runtime.capability_leases(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  )
  WHERE state = 'ACTIVE';

CREATE UNIQUE INDEX step_execution_plans_one_active_scope
  ON proof_harness_runtime.step_execution_plans(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id
  )
  WHERE state = 'ACTIVE';

CREATE TABLE proof_harness_runtime.pending_tool_call_bindings (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  invocation_id text NOT NULL CHECK (length(btrim(invocation_id)) BETWEEN 1 AND 512),
  call_id text NOT NULL CHECK (length(btrim(call_id)) BETWEEN 1 AND 512),
  attempt integer NOT NULL CHECK (attempt >= 1),
  execution_plan_hash text NOT NULL CHECK (
    execution_plan_hash ~ '^sha256:[0-9a-f]{64}$'
  ),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  tool_id text NOT NULL CHECK (length(btrim(tool_id)) BETWEEN 1 AND 512),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING', 'RECONCILED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  reconciled_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, call_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id, call_id, attempt
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id, call_id, attempt,
    execution_plan_hash, environment_id, authority_snapshot_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, execution_plan_hash
  ) REFERENCES proof_harness_runtime.step_execution_plans(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash
  ) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, execution_plan_hash, tool_id
  ) REFERENCES proof_harness_runtime.step_plan_tool_bindings(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash, tool_id
  ) ON DELETE RESTRICT,
  CHECK (updated_at >= created_at),
  CHECK ((state = 'RECONCILED') = (reconciled_at IS NOT NULL)),
  CHECK (reconciled_at IS NULL OR reconciled_at >= created_at)
);

CREATE INDEX pending_tool_call_bindings_state_idx
  ON proof_harness_runtime.pending_tool_call_bindings(
    tenant_id, project_id, run_id, state, updated_at
  );

CREATE TABLE proof_harness_runtime.runtime_authority_capability_receipts (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  operation_invocation_id text NOT NULL CHECK (
    length(btrim(operation_invocation_id)) BETWEEN 1 AND 512
  ),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  capability_set jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(capability_set, 256, 512)
  ),
  delegation_allowed boolean NOT NULL,
  authority_digest text NOT NULL CHECK (authority_digest ~ '^sha256:[0-9a-f]{64}$'),
  origin_skill_id text NOT NULL CHECK (length(btrim(origin_skill_id)) BETWEEN 1 AND 512),
  origin_skill_name text NOT NULL CHECK (length(btrim(origin_skill_name)) BETWEEN 1 AND 512),
  origin_owner_kernel text NOT NULL CHECK (origin_owner_kernel IN (
    'K1','K2','K3','K4','K5','K6','K7','K8'
  )),
  origin_execution_id text NOT NULL CHECK (
    length(btrim(origin_execution_id)) BETWEEN 1 AND 512
  ),
  origin_step_id text NOT NULL CHECK (length(btrim(origin_step_id)) BETWEEN 1 AND 512),
  extension_skill text NOT NULL CHECK (length(btrim(extension_skill)) BETWEEN 1 AND 512),
  origin_receipt_ref text NOT NULL CHECK (
    length(btrim(origin_receipt_ref)) BETWEEN 1 AND 2048
  ),
  origin_receipt_state text NOT NULL CHECK (origin_receipt_state IN (
    'PLANNING','EXECUTING','RESUMING','VERIFYING','CERTIFYING'
  )),
  origin_receipt_digest text NOT NULL CHECK (
    origin_receipt_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  origin_signing_key_id text NOT NULL CHECK (
    length(btrim(origin_signing_key_id)) BETWEEN 1 AND 512
  ),
  origin_signature_algorithm text NOT NULL CHECK (origin_signature_algorithm IN (
    'ED25519','ECDSA_P256_SHA256','RSA_PSS_SHA256','LOCAL_SELF_ATTESTED'
  )),
  origin_signature text NOT NULL CHECK (
    length(btrim(origin_signature)) BETWEEN 1 AND 4096
  ),
  host_envelope_payload_digest text NOT NULL CHECK (
    host_envelope_payload_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  host_envelope_digest text NOT NULL CHECK (host_envelope_digest ~ '^sha256:[0-9a-f]{64}$'),
  host_envelope_issuer text NOT NULL CHECK (
    length(btrim(host_envelope_issuer)) BETWEEN 1 AND 512
  ),
  host_envelope_signing_key_id text NOT NULL CHECK (
    length(btrim(host_envelope_signing_key_id)) BETWEEN 1 AND 512
  ),
  host_envelope_signature_algorithm text NOT NULL CHECK (host_envelope_signature_algorithm IN (
    'ED25519','ECDSA_P256_SHA256','RSA_PSS_SHA256','LOCAL_SELF_ATTESTED'
  )),
  host_envelope_signature text NOT NULL CHECK (
    length(btrim(host_envelope_signature)) BETWEEN 1 AND 4096
  ),
  host_envelope_issued_at timestamptz NOT NULL,
  host_envelope_verifier_id text NOT NULL CHECK (
    length(btrim(host_envelope_verifier_id)) BETWEEN 1 AND 512
  ),
  host_envelope_verification_evidence_ref text NOT NULL CHECK (
    length(btrim(host_envelope_verification_evidence_ref)) BETWEEN 1 AND 2048
  ),
  host_envelope_verification_evidence_digest text NOT NULL CHECK (
    host_envelope_verification_evidence_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  host_envelope_verified_at timestamptz NOT NULL,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, operation_invocation_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, host_envelope_digest
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT
);

ALTER TABLE proof_harness_runtime.capability_leases
  ADD CONSTRAINT capability_leases_authority_receipt_fk FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ) REFERENCES proof_harness_runtime.runtime_authority_capability_receipts(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, operation_invocation_id
  ) ON DELETE RESTRICT;

CREATE TABLE proof_harness_runtime.subagent_budget_reservation_bindings (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  reservation_id text NOT NULL CHECK (length(btrim(reservation_id)) BETWEEN 1 AND 512),
  operation_invocation_id text NOT NULL CHECK (
    length(btrim(operation_invocation_id)) BETWEEN 1 AND 512
  ),
  parent_execution_id text NOT NULL CHECK (
    length(btrim(parent_execution_id)) BETWEEN 1 AND 512
  ),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  provider text NOT NULL CHECK (length(btrim(provider)) BETWEEN 1 AND 255),
  model text NOT NULL CHECK (length(btrim(model)) BETWEEN 1 AND 512),
  reasoning_effort text NOT NULL CHECK (reasoning_effort IN (
    'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'
  )),
  child_authority jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(child_authority, 256, 512)
  ),
  child_tools jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(child_tools, 256, 512)
  ),
  max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 1000000),
  max_cost_budget text NOT NULL CHECK (
    length(max_cost_budget) BETWEEN 1 AND 128
    AND max_cost_budget ~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
    AND max_cost_budget::numeric > 0
  ),
  wall_clock_deadline timestamptz NOT NULL,
  tool_plan_hash text NOT NULL CHECK (tool_plan_hash ~ '^sha256:[0-9a-f]{64}$'),
  authority_envelope_digest text NOT NULL CHECK (
    authority_envelope_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  host_envelope_payload_digest text NOT NULL CHECK (
    host_envelope_payload_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  host_envelope_digest text NOT NULL CHECK (host_envelope_digest ~ '^sha256:[0-9a-f]{64}$'),
  host_envelope_issuer text NOT NULL CHECK (
    length(btrim(host_envelope_issuer)) BETWEEN 1 AND 512
  ),
  host_envelope_signing_key_id text NOT NULL CHECK (
    length(btrim(host_envelope_signing_key_id)) BETWEEN 1 AND 512
  ),
  host_envelope_signature_algorithm text NOT NULL CHECK (host_envelope_signature_algorithm IN (
    'ED25519','ECDSA_P256_SHA256','RSA_PSS_SHA256','LOCAL_SELF_ATTESTED'
  )),
  host_envelope_signature text NOT NULL CHECK (
    length(btrim(host_envelope_signature)) BETWEEN 1 AND 4096
  ),
  host_envelope_issued_at timestamptz NOT NULL,
  host_envelope_verifier_id text NOT NULL CHECK (
    length(btrim(host_envelope_verifier_id)) BETWEEN 1 AND 512
  ),
  host_envelope_verification_evidence_ref text NOT NULL CHECK (
    length(btrim(host_envelope_verification_evidence_ref)) BETWEEN 1 AND 2048
  ),
  host_envelope_verification_evidence_digest text NOT NULL CHECK (
    host_envelope_verification_evidence_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  host_envelope_verified_at timestamptz NOT NULL,
  state text NOT NULL DEFAULT 'RESERVED' CHECK (state IN ('RESERVED', 'CONSUMED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  consumed_at timestamptz,
  consumer_execution_id text CHECK (
    consumer_execution_id IS NULL
    OR length(btrim(consumer_execution_id)) BETWEEN 1 AND 512
  ),
  consume_event_id text CHECK (
    consume_event_id IS NULL
    OR consume_event_id ~ '^evt-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  consume_payload_sha256 text CHECK (
    consume_payload_sha256 IS NULL OR consume_payload_sha256 ~ '^sha256:[0-9a-f]{64}$'
  ),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, reservation_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, operation_invocation_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, reservation_id, operation_invocation_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, tool_plan_hash
  ) REFERENCES proof_harness_runtime.step_execution_plans(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, plan_hash
  ) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, authority_envelope_digest
  ) REFERENCES proof_harness_runtime.runtime_authority_capability_receipts(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, host_envelope_digest
  ) ON DELETE RESTRICT,
  CHECK (wall_clock_deadline > created_at),
  CHECK (updated_at >= created_at),
  CHECK ((state = 'CONSUMED') = (consumed_at IS NOT NULL)),
  CHECK ((state = 'CONSUMED') = (consumer_execution_id IS NOT NULL)),
  CHECK ((state = 'CONSUMED') = (consume_event_id IS NOT NULL)),
  CHECK ((state = 'CONSUMED') = (consume_payload_sha256 IS NOT NULL)),
  CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE TABLE proof_harness_runtime.executor_generations (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  executor_identity text NOT NULL CHECK (length(btrim(executor_identity)) BETWEEN 1 AND 1024),
  executor_generation bigint NOT NULL CHECK (executor_generation >= 1),
  connection_epoch bigint NOT NULL CHECK (connection_epoch >= 1),
  state text NOT NULL CHECK (state IN ('CONNECTING', 'ACTIVE', 'RETIRED', 'FAILED')),
  live_probe_evidence_ref text CHECK (
    live_probe_evidence_ref IS NULL OR length(btrim(live_probe_evidence_ref)) BETWEEN 1 AND 2048
  ),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  activated_at timestamptz,
  retired_at timestamptz,
  failed_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, environment_id,
    executor_generation, connection_epoch
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (updated_at >= created_at),
  CHECK ((state = 'ACTIVE') = (
    activated_at IS NOT NULL AND retired_at IS NULL AND failed_at IS NULL
  )),
  CHECK (state NOT IN ('ACTIVE', 'RETIRED') OR live_probe_evidence_ref IS NOT NULL),
  CHECK ((state = 'RETIRED') = (retired_at IS NOT NULL)),
  CHECK ((state = 'FAILED') = (failed_at IS NOT NULL)),
  CHECK (activated_at IS NULL OR activated_at >= created_at),
  CHECK (retired_at IS NULL OR retired_at >= COALESCE(activated_at, created_at)),
  CHECK (failed_at IS NULL OR failed_at >= COALESCE(activated_at, created_at))
);

CREATE UNIQUE INDEX executor_generations_one_active_environment
  ON proof_harness_runtime.executor_generations(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, environment_id
  )
  WHERE state = 'ACTIVE';

CREATE TABLE proof_harness_runtime.environment_attachments (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  server_id text NOT NULL CHECK (length(btrim(server_id)) BETWEEN 1 AND 512),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  snapshot_id text NOT NULL CHECK (snapshot_id ~ '^sha256:[0-9a-f]{64}$'),
  previous_snapshot_id text CHECK (
    previous_snapshot_id IS NULL OR previous_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
  ),
  generation bigint NOT NULL CHECK (generation >= 1),
  owner_authority_ref text NOT NULL CHECK (
    owner_authority_ref ~ '^sha256:[0-9a-f]{64}$'
    AND owner_authority_ref = authority_revision
  ),
  parent_authority_ref text NOT NULL CHECK (
    parent_authority_ref ~ '^sha256:[0-9a-f]{64}$'
  ),
  effective_permissions jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(effective_permissions, 256, 512)
  ),
  settings_authority jsonb NOT NULL CHECK (
    jsonb_typeof(settings_authority) = 'object'
    AND pg_column_size(settings_authority) <= 262144
  ),
  settings_digest text NOT NULL CHECK (settings_digest ~ '^sha256:[0-9a-f]{64}$'),
  state text NOT NULL CHECK (state IN ('ACTIVE', 'SUPERSEDED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  superseded_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, server_id, environment_id, generation
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, server_id, environment_id, snapshot_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK ((generation = 1) = (previous_snapshot_id IS NULL)),
  CHECK ((state = 'SUPERSEDED') = (superseded_at IS NOT NULL)),
  CHECK (updated_at >= created_at),
  CHECK (superseded_at IS NULL OR superseded_at >= created_at)
);

CREATE UNIQUE INDEX environment_attachments_one_active
  ON proof_harness_runtime.environment_attachments(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, server_id, environment_id
  )
  WHERE state = 'ACTIVE';

CREATE TABLE proof_harness_runtime.executor_replacement_effects (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  effect_id text NOT NULL CHECK (length(btrim(effect_id)) BETWEEN 1 AND 512),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  executor_generation bigint NOT NULL CHECK (executor_generation >= 1),
  connection_epoch bigint NOT NULL CHECK (connection_epoch >= 1),
  kind text NOT NULL CHECK (kind IN (
    'CAPABILITY_REVOCATION', 'WORKSPACE_RECONCILIATION',
    'EXTERNAL_EFFECT_RECONCILIATION'
  )),
  state text NOT NULL CHECK (state IN ('PENDING', 'SUCCEEDED', 'FAILED', 'UNKNOWN')),
  evidence_ref text CHECK (
    evidence_ref IS NULL OR length(btrim(evidence_ref)) BETWEEN 1 AND 2048
  ),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  reconciled_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, effect_id
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, environment_id, executor_generation,
    connection_epoch, kind
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, environment_id, executor_generation,
    connection_epoch
  ) REFERENCES proof_harness_runtime.executor_generations(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, environment_id, executor_generation,
    connection_epoch
  ) ON DELETE RESTRICT,
  CHECK ((state = 'PENDING') = (reconciled_at IS NULL)),
  CHECK ((state = 'PENDING') = (evidence_ref IS NULL)),
  CHECK (updated_at >= created_at),
  CHECK (reconciled_at IS NULL OR reconciled_at >= created_at)
);

CREATE TABLE proof_harness_runtime.workspace_leases (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  workspace_id text NOT NULL CHECK (length(btrim(workspace_id)) BETWEEN 1 AND 512),
  owner_execution_id text NOT NULL CHECK (
    length(btrim(owner_execution_id)) BETWEEN 1 AND 512
  ),
  generation bigint NOT NULL CHECK (generation >= 1),
  repository_id text NOT NULL CHECK (length(btrim(repository_id)) BETWEEN 1 AND 1024),
  base_revision text NOT NULL CHECK (length(btrim(base_revision)) BETWEEN 1 AND 512),
  write_scopes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (
    proof_harness_runtime.is_valid_workspace_scopes(write_scopes)
  ),
  state text NOT NULL CHECK (state IN (
    'ACTIVE', 'HANDOFF_PENDING', 'RETIRED', 'TAKEOVER_PENDING'
  )),
  takeover_evidence_ref text CHECK (
    takeover_evidence_ref IS NULL
    OR length(btrim(takeover_evidence_ref)) BETWEEN 1 AND 2048
  ),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  retired_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, workspace_id, generation
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (updated_at >= created_at),
  CHECK ((state = 'RETIRED') = (retired_at IS NOT NULL)),
  CHECK (state <> 'TAKEOVER_PENDING' OR takeover_evidence_ref IS NOT NULL),
  CHECK (
    state NOT IN ('ACTIVE', 'HANDOFF_PENDING', 'RETIRED')
    OR takeover_evidence_ref IS NULL
  ),
  CHECK (retired_at IS NULL OR retired_at >= created_at)
);

CREATE UNIQUE INDEX workspace_leases_one_active_owner
  ON proof_harness_runtime.workspace_leases(
    tenant_id, project_id, workspace_id
  )
  WHERE state IN ('ACTIVE', 'HANDOFF_PENDING', 'TAKEOVER_PENDING');

-- PostgreSQL cannot express hierarchical JSON scope overlap as a portable
-- exclusion constraint without an extension.  This conservative physical
-- checkout fence serializes one live writer per repository/base tuple.  The
-- application additionally checks exact nested scopes under a tenant/project
-- advisory transaction lock before insertion.
CREATE UNIQUE INDEX workspace_leases_one_live_repository_base
  ON proof_harness_runtime.workspace_leases(
    tenant_id, project_id, repository_id, base_revision
  )
  WHERE state IN ('ACTIVE', 'HANDOFF_PENDING', 'TAKEOVER_PENDING');

CREATE TABLE proof_harness_runtime.durable_event_registrations (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  event_type text NOT NULL CHECK (length(btrim(event_type)) BETWEEN 1 AND 255),
  owner text NOT NULL CHECK (length(btrim(owner)) BETWEEN 1 AND 512),
  schema_version integer NOT NULL CHECK (schema_version >= 1),
  semantics text NOT NULL CHECK (semantics IN ('OPTIONAL_OBSERVATION', 'REQUIRED_STATE')),
  compatibility text NOT NULL DEFAULT 'STRICT' CHECK (
    compatibility IN ('STRICT', 'BACKWARD', 'FORWARD', 'FULL')
  ),
  validator_ref text NOT NULL CHECK (length(btrim(validator_ref)) BETWEEN 1 AND 2048),
  upgrader_ref text NOT NULL CHECK (length(btrim(upgrader_ref)) BETWEEN 1 AND 2048),
  projections jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(projections, 128, 512)
  ),
  registration_hash text NOT NULL CHECK (registration_hash ~ '^sha256:[0-9a-f]{64}$'),
  registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, event_type, schema_version
  ),
  UNIQUE (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, registration_hash
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT
);

CREATE TABLE proof_harness_runtime.durable_event_instances (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  event_id text NOT NULL CHECK (length(btrim(event_id)) BETWEEN 1 AND 512),
  event_type text NOT NULL CHECK (length(btrim(event_type)) BETWEEN 1 AND 255),
  schema_version integer NOT NULL CHECK (schema_version >= 1),
  payload_ref text NOT NULL CHECK (length(btrim(payload_ref)) BETWEEN 1 AND 2048),
  payload_digest text NOT NULL CHECK (payload_digest ~ '^sha256:[0-9a-f]{64}$'),
  causation_id text CHECK (
    causation_id IS NULL OR length(btrim(causation_id)) BETWEEN 1 AND 512
  ),
  correlation_id text NOT NULL CHECK (length(btrim(correlation_id)) BETWEEN 1 AND 512),
  parent_event_id text CHECK (
    parent_event_id IS NULL OR length(btrim(parent_event_id)) BETWEEN 1 AND 512
  ),
  source_scope jsonb NOT NULL CHECK (
    jsonb_typeof(source_scope) = 'object' AND pg_column_size(source_scope) <= 16384
  ),
  fork_lineage jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(fork_lineage, 256, 512)
  ),
  compatibility_decision text NOT NULL CHECK (
    compatibility_decision IN ('EXACT', 'UPGRADED', 'SKIPPED')
  ),
  state text NOT NULL CHECK (state IN ('PENDING', 'PROCESSED', 'SKIPPED')),
  skip_reason text CHECK (
    skip_reason IS NULL OR length(btrim(skip_reason)) BETWEEN 1 AND 2048
  ),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  processed_at timestamptz,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, event_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, event_type, schema_version
  ) REFERENCES proof_harness_runtime.durable_event_registrations(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, event_type, schema_version
  ) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, parent_event_id
  ) REFERENCES proof_harness_runtime.durable_event_instances(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, event_id
  ) ON DELETE RESTRICT,
  CHECK ((parent_event_id IS NULL) = (jsonb_array_length(fork_lineage) = 0)),
  CHECK (parent_event_id IS NULL OR fork_lineage ->> (jsonb_array_length(fork_lineage) - 1) = parent_event_id),
  CHECK (source_scope = jsonb_build_object(
    'tenantId', tenant_id,
    'projectId', project_id,
    'runId', run_id,
    'actorId', actor_id,
    'executionEpoch', execution_epoch,
    'fencingGeneration', fencing_generation,
    'authorityRevision', authority_revision,
    'revisionSetId', revision_set_id
  )),
  CHECK ((state = 'SKIPPED') = (skip_reason IS NOT NULL)),
  CHECK ((state = 'PENDING') = (processed_at IS NULL)),
  CHECK (updated_at >= created_at),
  CHECK (processed_at IS NULL OR processed_at >= created_at)
);

CREATE INDEX durable_event_instances_correlation_idx
  ON proof_harness_runtime.durable_event_instances(
    tenant_id, project_id, run_id, correlation_id, created_at, event_id
  );

CREATE TABLE proof_harness_runtime.typed_ingress_records (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  ingress_id text NOT NULL CHECK (length(btrim(ingress_id)) BETWEEN 1 AND 512),
  producer_execution_id text NOT NULL CHECK (
    length(btrim(producer_execution_id)) BETWEEN 1 AND 512
  ),
  deduplication_key text NOT NULL CHECK (
    length(btrim(deduplication_key)) BETWEEN 1 AND 512
  ),
  kind text NOT NULL CHECK (kind IN (
    'USER_INPUT', 'TOOL_RESULT', 'EXTERNAL_EVENT', 'APPROVAL_INPUT', 'CONTROL_INPUT'
  )),
  envelope_digest text NOT NULL CHECK (envelope_digest ~ '^sha256:[0-9a-f]{64}$'),
  payload_ref text NOT NULL CHECK (length(btrim(payload_ref)) BETWEEN 1 AND 2048),
  originating_call_id text CHECK (
    originating_call_id IS NULL
    OR length(btrim(originating_call_id)) BETWEEN 1 AND 512
  ),
  causation_id text CHECK (
    causation_id IS NULL OR length(btrim(causation_id)) BETWEEN 1 AND 512
  ),
  correlation_id text NOT NULL CHECK (
    length(btrim(correlation_id)) BETWEEN 1 AND 512
  ),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  persisted_sequence bigint GENERATED ALWAYS AS IDENTITY,
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, ingress_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, originating_call_id
  ) REFERENCES proof_harness_runtime.pending_tool_call_bindings(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, call_id
  ) ON DELETE RESTRICT,
  CHECK (kind <> 'TOOL_RESULT' OR originating_call_id IS NOT NULL),
  CHECK (recorded_at >= occurred_at)
);

CREATE UNIQUE INDEX typed_ingress_records_dedup_unique
  ON proof_harness_runtime.typed_ingress_records(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, producer_execution_id, deduplication_key
  );

CREATE TABLE proof_harness_runtime.subagent_execution_specs (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  invocation_id text NOT NULL CHECK (length(btrim(invocation_id)) BETWEEN 1 AND 512),
  parent_execution_id text NOT NULL CHECK (
    length(btrim(parent_execution_id)) BETWEEN 1 AND 512
  ),
  provider text NOT NULL CHECK (length(btrim(provider)) BETWEEN 1 AND 255),
  model text NOT NULL CHECK (length(btrim(model)) BETWEEN 1 AND 512),
  reasoning_effort text NOT NULL CHECK (reasoning_effort IN (
    'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra'
  )),
  authority_snapshot_id text NOT NULL CHECK (
    authority_snapshot_id ~ '^sha256:[0-9a-f]{64}$'
  ),
  environment_id text NOT NULL CHECK (length(btrim(environment_id)) BETWEEN 1 AND 512),
  budget_reservation_id text NOT NULL CHECK (
    length(btrim(budget_reservation_id)) BETWEEN 1 AND 512
  ),
  max_output_tokens integer NOT NULL CHECK (max_output_tokens BETWEEN 1 AND 1000000),
  tool_plan_hash text NOT NULL CHECK (tool_plan_hash ~ '^sha256:[0-9a-f]{64}$'),
  child_authority jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(child_authority, 256, 512)
  ),
  child_tools jsonb NOT NULL CHECK (
    proof_harness_runtime.is_bounded_text_array(child_tools, 256, 512)
  ),
  cost_budget text NOT NULL CHECK (
    length(cost_budget) BETWEEN 1 AND 128
    AND cost_budget ~ '^(0|[1-9][0-9]*)(\.[0-9]+)?$'
    AND cost_budget::numeric > 0
  ),
  wall_clock_deadline timestamptz NOT NULL,
  spec_hash text NOT NULL CHECK (spec_hash ~ '^sha256:[0-9a-f]{64}$'),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (
    authority_revision ~ '^sha256:[0-9a-f]{64}$'
    AND authority_snapshot_id = authority_revision
  ),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  state text NOT NULL DEFAULT 'RESERVED' CHECK (state IN ('RESERVED', 'CONSUMED')),
  consumer_execution_id text CHECK (
    consumer_execution_id IS NULL
    OR length(btrim(consumer_execution_id)) BETWEEN 1 AND 512
  ),
  consumed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, budget_reservation_id, invocation_id
  ) REFERENCES proof_harness_runtime.subagent_budget_reservation_bindings(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, reservation_id, operation_invocation_id
  ) ON DELETE RESTRICT,
  CHECK (wall_clock_deadline > recorded_at),
  CHECK (updated_at >= recorded_at),
  CHECK ((state = 'CONSUMED') = (consumer_execution_id IS NOT NULL)),
  CHECK ((state = 'CONSUMED') = (consumed_at IS NOT NULL)),
  CHECK (consumed_at IS NULL OR consumed_at >= recorded_at)
);

CREATE UNIQUE INDEX subagent_execution_specs_budget_unique
  ON proof_harness_runtime.subagent_execution_specs(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, budget_reservation_id
  );

CREATE TABLE proof_harness_runtime.runtime_assurance_invocation_receipts (
  tenant_id text NOT NULL CHECK (length(btrim(tenant_id)) BETWEEN 1 AND 255),
  project_id text NOT NULL CHECK (length(btrim(project_id)) BETWEEN 1 AND 255),
  run_id text NOT NULL CHECK (length(btrim(run_id)) BETWEEN 1 AND 512),
  actor_id text NOT NULL CHECK (length(btrim(actor_id)) BETWEEN 1 AND 512),
  execution_epoch bigint NOT NULL CHECK (execution_epoch >= 1),
  fencing_generation bigint NOT NULL CHECK (fencing_generation >= 1),
  authority_revision text NOT NULL CHECK (authority_revision ~ '^sha256:[0-9a-f]{64}$'),
  revision_set_id text NOT NULL CHECK (revision_set_id ~ '^sha256:[0-9a-f]{64}$'),
  invocation_id text NOT NULL CHECK (length(btrim(invocation_id)) BETWEEN 1 AND 512),
  request_digest text NOT NULL CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
  claim_epoch bigint NOT NULL DEFAULT 1 CHECK (claim_epoch = 1),
  claim_backend_pid integer NOT NULL CHECK (claim_backend_pid >= 1),
  claim_lock_key bigint NOT NULL,
  state text NOT NULL CHECK (state IN (
    'IN_PROGRESS', 'COMPLETED', 'RECOVERY_REQUIRED'
  )),
  result_ref text CHECK (
    result_ref IS NULL OR length(btrim(result_ref)) BETWEEN 1 AND 2048
  ),
  result_digest text CHECK (
    result_digest IS NULL OR result_digest ~ '^sha256:[0-9a-f]{64}$'
  ),
  claimed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  completed_at timestamptz,
  recovery_evidence_ref text CHECK (
    recovery_evidence_ref IS NULL
    OR length(btrim(recovery_evidence_ref)) BETWEEN 1 AND 2048
  ),
  mutation_event_id text NOT NULL CHECK (
    mutation_event_id ~ '^evt-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  ),
  mutation_event_type text NOT NULL CHECK (mutation_event_type IN (
    'INVOCATION_CLAIMED', 'INVOCATION_RECOVERY_REQUIRED',
    'INVOCATION_COMPLETED', 'INVOCATION_RECOVERY_RECONCILED'
  )),
  mutation_payload_sha256 text NOT NULL CHECK (
    mutation_payload_sha256 ~ '^sha256:[0-9a-f]{64}$'
  ),
  PRIMARY KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ),
  FOREIGN KEY (tenant_id, project_id, actor_id)
    REFERENCES proof_harness_runtime.actors(tenant_id, project_id, actor_id) ON DELETE RESTRICT,
  FOREIGN KEY (tenant_id, project_id, run_id)
    REFERENCES proof_harness_runtime.runs(tenant_id, project_id, run_id) ON DELETE RESTRICT,
  CHECK (updated_at >= claimed_at),
  CHECK ((state = 'COMPLETED') = (completed_at IS NOT NULL)),
  CHECK ((state = 'COMPLETED') = (result_ref IS NOT NULL)),
  CHECK ((state = 'COMPLETED') = (result_digest IS NOT NULL)),
  CHECK (state = 'COMPLETED' OR recovery_evidence_ref IS NULL),
  CHECK (
    (state = 'IN_PROGRESS' AND mutation_event_type = 'INVOCATION_CLAIMED')
    OR (state = 'RECOVERY_REQUIRED'
        AND mutation_event_type = 'INVOCATION_RECOVERY_REQUIRED')
    OR (state = 'COMPLETED'
        AND mutation_event_type IN (
          'INVOCATION_COMPLETED', 'INVOCATION_RECOVERY_RECONCILED'
        ))
  ),
  CHECK (completed_at IS NULL OR completed_at >= claimed_at)
);

ALTER TABLE proof_harness_runtime.pending_tool_call_bindings
  ADD CONSTRAINT pending_tool_call_invocation_receipt_fk FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ) REFERENCES proof_harness_runtime.runtime_assurance_invocation_receipts(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ) ON DELETE RESTRICT;

ALTER TABLE proof_harness_runtime.tool_result_commits
  ADD CONSTRAINT tool_result_pending_call_fk FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id, call_id, attempt,
    execution_plan_hash, environment_id, authority_snapshot_id
  ) REFERENCES proof_harness_runtime.pending_tool_call_bindings(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id, call_id, attempt,
    execution_plan_hash, environment_id, authority_snapshot_id
  ) ON DELETE RESTRICT;

ALTER TABLE proof_harness_runtime.runtime_authority_capability_receipts
  ADD CONSTRAINT authority_receipt_invocation_claim_fk FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, operation_invocation_id
  ) REFERENCES proof_harness_runtime.runtime_assurance_invocation_receipts(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ) ON DELETE RESTRICT;

ALTER TABLE proof_harness_runtime.subagent_budget_reservation_bindings
  ADD CONSTRAINT subagent_reservation_invocation_claim_fk FOREIGN KEY (
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, operation_invocation_id
  ) REFERENCES proof_harness_runtime.runtime_assurance_invocation_receipts(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, invocation_id
  ) ON DELETE RESTRICT;

CREATE INDEX tool_result_commits_run_idx
  ON proof_harness_runtime.tool_result_commits(tenant_id, project_id, run_id, created_at);
CREATE INDEX step_execution_plans_run_state_idx
  ON proof_harness_runtime.step_execution_plans(tenant_id, project_id, run_id, state);
CREATE INDEX capability_leases_expiry_idx
  ON proof_harness_runtime.capability_leases(tenant_id, project_id, state, expires_at);
CREATE INDEX durable_event_registrations_type_idx
  ON proof_harness_runtime.durable_event_registrations(tenant_id, project_id, event_type);
CREATE INDEX typed_ingress_records_run_idx
  ON proof_harness_runtime.typed_ingress_records(tenant_id, project_id, run_id, recorded_at);
CREATE INDEX typed_ingress_records_correlation_page_idx
  ON proof_harness_runtime.typed_ingress_records(
    tenant_id, project_id, run_id, execution_epoch, fencing_generation,
    authority_revision, revision_set_id, correlation_id, occurred_at, ingress_id
  );
CREATE INDEX subagent_execution_specs_run_idx
  ON proof_harness_runtime.subagent_execution_specs(tenant_id, project_id, run_id, recorded_at);
CREATE INDEX runtime_assurance_invocation_receipts_state_idx
  ON proof_harness_runtime.runtime_assurance_invocation_receipts(
    tenant_id, project_id, run_id, state, updated_at
  );

CREATE OR REPLACE FUNCTION proof_harness_runtime.is_live_runtime_assurance_claim(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_run_id text,
  p_execution_epoch bigint,
  p_fencing_generation bigint,
  p_authority_revision text,
  p_revision_set_id text,
  p_invocation_id text,
  p_require_current_backend boolean
)
RETURNS boolean
LANGUAGE sql
STABLE
STRICT
SET search_path = pg_catalog, proof_harness_runtime
AS $is_live_runtime_assurance_claim$
  SELECT EXISTS (
    SELECT 1
      FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
      JOIN pg_catalog.pg_locks AS held
        ON held.locktype = 'advisory'
       AND held.mode = 'ExclusiveLock'
       AND held.database = (
         SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database()
       )
       AND held.pid = receipt.claim_backend_pid
       AND held.classid = (((receipt.claim_lock_key >> 32) & 4294967295)::oid)
       AND held.objid = ((receipt.claim_lock_key & 4294967295)::oid)
       AND held.objsubid = 1
       AND held.granted
     WHERE receipt.tenant_id = p_tenant_id
       AND receipt.project_id = p_project_id
       AND receipt.actor_id = p_actor_id
       AND receipt.run_id = p_run_id
       AND receipt.execution_epoch = p_execution_epoch
       AND receipt.fencing_generation = p_fencing_generation
       AND receipt.authority_revision = p_authority_revision
       AND receipt.revision_set_id = p_revision_set_id
       AND receipt.invocation_id = p_invocation_id
       AND receipt.state = 'IN_PROGRESS'
       AND (NOT p_require_current_backend OR receipt.claim_backend_pid = pg_backend_pid())
  )
$is_live_runtime_assurance_claim$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.assert_runtime_application_writer(
  p_helper_oid oid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $assert_runtime_application_writer$
DECLARE
  application_oid oid;
  control_owner_oid oid;
BEGIN
  SELECT oid INTO application_oid FROM pg_catalog.pg_roles
   WHERE rolname = session_user;
  SELECT c.relowner INTO control_owner_oid
    FROM pg_catalog.pg_class AS c
   WHERE c.oid = 'proof_harness_runtime.runtime_assurance_invocation_receipts'::regclass;
  IF application_oid IS NULL OR control_owner_oid IS NULL
     OR application_oid = control_owner_oid
     OR (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
        IS DISTINCT FROM control_owner_oid
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_roles AS caller
        WHERE caller.oid = application_oid
          AND caller.rolcanlogin
          AND NOT caller.rolsuper AND NOT caller.rolbypassrls
          AND NOT caller.rolcreatedb AND NOT caller.rolcreaterole
          AND NOT caller.rolreplication
     )
     OR EXISTS (
       SELECT 1 FROM pg_catalog.pg_auth_members AS membership
        WHERE membership.roleid = application_oid
           OR membership.member = application_oid
     )
     OR pg_has_role(session_user, pg_get_userbyid(control_owner_oid), 'SET')
     OR EXISTS (
       SELECT 1
         FROM unnest(ARRAY[
           'proof_harness_runtime.audit_events'::regclass,
           'proof_harness_runtime.outbox_events'::regclass
         ]) AS secured(relation_oid)
         JOIN pg_catalog.pg_class AS relation ON relation.oid = secured.relation_oid
        WHERE relation.relowner <> control_owner_oid
           OR EXISTS (
             SELECT 1 FROM pg_catalog.pg_attribute AS attribute
              WHERE attribute.attrelid = relation.oid
                AND attribute.attnum > 0 AND NOT attribute.attisdropped
                AND attribute.attacl IS NOT NULL
           )
           OR NOT EXISTS (
             SELECT 1 FROM aclexplode(COALESCE(
               relation.relacl, acldefault('r', relation.relowner)
             )) AS privilege
              WHERE privilege.grantee = application_oid
                AND privilege.privilege_type = 'INSERT'
                AND NOT privilege.is_grantable
           )
           OR EXISTS (
             SELECT 1 FROM aclexplode(COALESCE(
               relation.relacl, acldefault('r', relation.relowner)
             )) AS privilege
              WHERE privilege.privilege_type = 'INSERT'
                AND privilege.grantee NOT IN (control_owner_oid, application_oid)
           )
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_proc AS helper
        WHERE helper.oid = p_helper_oid
          AND helper.proowner = control_owner_oid
          AND helper.prosecdef
          AND helper.proconfig = ARRAY[
            'search_path=pg_catalog, proof_harness_runtime'
          ]::text[]
          AND EXISTS (
            SELECT 1 FROM aclexplode(COALESCE(
              helper.proacl, acldefault('f', helper.proowner)
            )) AS privilege
             WHERE privilege.grantee = application_oid
               AND privilege.privilege_type = 'EXECUTE'
               AND NOT privilege.is_grantable
          )
          AND NOT EXISTS (
            SELECT 1 FROM aclexplode(COALESCE(
              helper.proacl, acldefault('f', helper.proowner)
            )) AS privilege
             WHERE privilege.privilege_type = 'EXECUTE'
               AND privilege.grantee NOT IN (control_owner_oid, application_oid)
          )
     ) THEN
    RAISE EXCEPTION 'runtime mutation requires the exact application writer identity'
      USING ERRCODE = '42501';
  END IF;
END
$assert_runtime_application_writer$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.claim_runtime_assurance_invocation(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_run_id text,
  p_execution_epoch bigint,
  p_fencing_generation bigint,
  p_authority_revision text,
  p_revision_set_id text,
  p_invocation_id text,
  p_request_digest text,
  p_claim_lock_key bigint,
  p_now timestamptz
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $claim_runtime_assurance_invocation$
DECLARE
  helper_oid oid := (
    'proof_harness_runtime.claim_runtime_assurance_invocation('
    'text,text,text,text,bigint,bigint,text,text,text,text,bigint,'
    'timestamp with time zone)'
  )::regprocedure;
  candidate proof_harness_runtime.runtime_assurance_invocation_receipts%ROWTYPE;
  expected_lock_key bigint;
  event_payload jsonb;
  new_event_id text;
  new_payload_sha256 text;
  expected_event_type text;
  expected_event_at timestamptz;
BEGIN
  PERFORM proof_harness_runtime.assert_runtime_application_writer(helper_oid);
  IF p_tenant_id IS DISTINCT FROM current_setting('app.tenant_id', true)
     OR p_project_id IS DISTINCT FROM current_setting('app.project_id', true)
     OR p_actor_id IS DISTINCT FROM current_setting('app.actor_id', true)
     OR p_run_id IS DISTINCT FROM current_setting('app.run_id', true)
     OR p_execution_epoch::text IS DISTINCT FROM current_setting('app.execution_epoch', true)
     OR p_fencing_generation::text IS DISTINCT FROM current_setting('app.fencing_generation', true)
     OR p_authority_revision IS DISTINCT FROM current_setting('app.authority_revision', true)
     OR p_revision_set_id IS DISTINCT FROM current_setting('app.revision_set_id', true)
     OR p_invocation_id IS DISTINCT FROM
       current_setting('app.operation_invocation_id', true) THEN
    RAISE EXCEPTION 'invocation claim scope differs from trusted transaction scope'
      USING ERRCODE = '42501';
  END IF;
  expected_lock_key := (
    ('x' || substr(encode(sha256(
      convert_to('elmos.proof-harness.v1', 'UTF8') || decode('00', 'hex') ||
      convert_to('delta-runtime-invocation-lock', 'UTF8') || decode('00', 'hex') ||
      convert_to(proof_harness_runtime.canonical_jsonb_text(jsonb_build_object(
        'tenantId', p_tenant_id,
        'projectId', p_project_id,
        'runId', p_run_id,
        'actorId', p_actor_id,
        'executionEpoch', p_execution_epoch,
        'fencingGeneration', p_fencing_generation,
        'authorityRevision', p_authority_revision,
        'revisionSetId', p_revision_set_id,
        'invocationId', p_invocation_id
      )), 'UTF8')
    ), 'hex'), 1, 16))::bit(64)::bigint
  );
  IF p_claim_lock_key IS DISTINCT FROM expected_lock_key
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_locks AS held
        WHERE held.locktype = 'advisory'
          AND held.mode = 'ExclusiveLock'
          AND held.database = (
            SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database()
          )
          AND held.pid = pg_backend_pid()
          AND held.classid = (((p_claim_lock_key >> 32) & 4294967295)::oid)
          AND held.objid = ((p_claim_lock_key & 4294967295)::oid)
          AND held.objsubid = 1 AND held.granted
     ) THEN
    RAISE EXCEPTION 'invocation claim requires its deterministic live advisory lock'
      USING ERRCODE = '55000';
  END IF;
  SELECT * INTO candidate
    FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
   WHERE receipt.tenant_id = p_tenant_id
     AND receipt.project_id = p_project_id
     AND receipt.actor_id = p_actor_id
     AND receipt.run_id = p_run_id
     AND receipt.execution_epoch = p_execution_epoch
     AND receipt.fencing_generation = p_fencing_generation
     AND receipt.authority_revision = p_authority_revision
     AND receipt.revision_set_id = p_revision_set_id
     AND receipt.invocation_id = p_invocation_id
   FOR UPDATE;
  IF FOUND THEN
    IF candidate.request_digest IS DISTINCT FROM p_request_digest THEN
      RAISE EXCEPTION 'invocation id is bound to a different request digest'
        USING ERRCODE = '23505';
    END IF;
    IF candidate.state = 'COMPLETED' THEN
      expected_event_type := CASE
        WHEN candidate.recovery_evidence_ref IS NULL THEN 'INVOCATION_COMPLETED'
        ELSE 'INVOCATION_RECOVERY_RECONCILED'
      END;
      event_payload := jsonb_build_object(
        'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
        'fencing_generation', p_fencing_generation,
        'authority_revision', p_authority_revision,
        'revision_set_id', p_revision_set_id,
        'detail', jsonb_build_object(
          'invocation_id', p_invocation_id,
          'request_digest', p_request_digest,
          'claim_epoch', candidate.claim_epoch,
          'result_digest', candidate.result_digest
        ) || CASE WHEN candidate.recovery_evidence_ref IS NULL THEN '{}'::jsonb
                  ELSE jsonb_build_object(
                    'recovery_evidence_ref', candidate.recovery_evidence_ref
                  ) END
      );
      expected_event_at := candidate.completed_at;
      IF NOT proof_harness_runtime.runtime_assurance_event_is_exact(
        p_tenant_id, p_project_id, p_actor_id, expected_event_type,
        p_invocation_id, candidate.mutation_event_id,
        candidate.mutation_payload_sha256, event_payload, expected_event_at
      ) THEN
        RAISE EXCEPTION 'completed invocation replay journal is missing or drifted'
          USING ERRCODE = '55000';
      END IF;
      RETURN 'COMPLETED_REPLAY';
    END IF;
    IF candidate.state = 'RECOVERY_REQUIRED' THEN
      event_payload := jsonb_build_object(
        'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
        'fencing_generation', p_fencing_generation,
        'authority_revision', p_authority_revision,
        'revision_set_id', p_revision_set_id,
        'detail', jsonb_build_object(
          'invocation_id', p_invocation_id,
          'request_digest', p_request_digest,
          'claim_epoch', candidate.claim_epoch
        )
      );
      IF NOT proof_harness_runtime.runtime_assurance_event_is_exact(
        p_tenant_id, p_project_id, p_actor_id,
        'INVOCATION_RECOVERY_REQUIRED', p_invocation_id,
        candidate.mutation_event_id, candidate.mutation_payload_sha256,
        event_payload, candidate.updated_at
      ) THEN
        RAISE EXCEPTION 'recovery-required invocation journal is missing or drifted'
          USING ERRCODE = '55000';
      END IF;
      RETURN 'RECOVERY_REQUIRED';
    END IF;
    IF candidate.state <> 'IN_PROGRESS' THEN
      RAISE EXCEPTION 'invocation claim has an unsupported lifecycle state'
        USING ERRCODE = '55000';
    END IF;
    IF candidate.claim_backend_pid = pg_backend_pid()
       AND candidate.claim_lock_key = p_claim_lock_key THEN
      event_payload := jsonb_build_object(
        'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
        'fencing_generation', p_fencing_generation,
        'authority_revision', p_authority_revision,
        'revision_set_id', p_revision_set_id,
        'detail', jsonb_build_object(
          'invocation_id', p_invocation_id,
          'request_digest', p_request_digest,
          'claim_epoch', candidate.claim_epoch
        )
      );
      IF NOT proof_harness_runtime.runtime_assurance_event_is_exact(
        p_tenant_id, p_project_id, p_actor_id, 'INVOCATION_CLAIMED',
        p_invocation_id, candidate.mutation_event_id,
        candidate.mutation_payload_sha256, event_payload, candidate.claimed_at
      ) THEN
        RAISE EXCEPTION 'active invocation claim journal is missing or drifted'
          USING ERRCODE = '55000';
      END IF;
      RETURN 'ACQUIRED';
    END IF;
    event_payload := jsonb_build_object(
      'run_id', p_run_id,
      'execution_epoch', p_execution_epoch,
      'fencing_generation', p_fencing_generation,
      'authority_revision', p_authority_revision,
      'revision_set_id', p_revision_set_id,
      'detail', jsonb_build_object(
        'invocation_id', p_invocation_id,
        'request_digest', p_request_digest,
        'claim_epoch', candidate.claim_epoch
      )
    );
    new_event_id := proof_harness_runtime.append_runtime_assurance_event(
      p_tenant_id, p_project_id, p_actor_id,
      'INVOCATION_RECOVERY_REQUIRED', p_invocation_id, event_payload, p_now
    );
    SELECT audit.payload_sha256 INTO STRICT new_payload_sha256
      FROM proof_harness_runtime.audit_events AS audit
     WHERE audit.tenant_id = p_tenant_id AND audit.project_id = p_project_id
       AND audit.event_id = new_event_id;
    UPDATE proof_harness_runtime.runtime_assurance_invocation_receipts
       SET state = 'RECOVERY_REQUIRED', updated_at = p_now,
           mutation_event_id = new_event_id,
           mutation_event_type = 'INVOCATION_RECOVERY_REQUIRED',
           mutation_payload_sha256 = new_payload_sha256
     WHERE tenant_id = p_tenant_id AND project_id = p_project_id
       AND actor_id = p_actor_id AND run_id = p_run_id
       AND execution_epoch = p_execution_epoch
       AND fencing_generation = p_fencing_generation
       AND authority_revision = p_authority_revision
       AND revision_set_id = p_revision_set_id
       AND invocation_id = p_invocation_id
       AND request_digest = p_request_digest
       AND claim_epoch = candidate.claim_epoch
       AND state = 'IN_PROGRESS';
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale invocation recovery compare-and-swap failed'
        USING ERRCODE = '40001';
    END IF;
    RETURN 'RECOVERY_REQUIRED';
  END IF;
  event_payload := jsonb_build_object(
    'run_id', p_run_id,
    'execution_epoch', p_execution_epoch,
    'fencing_generation', p_fencing_generation,
    'authority_revision', p_authority_revision,
    'revision_set_id', p_revision_set_id,
    'detail', jsonb_build_object(
      'invocation_id', p_invocation_id,
      'request_digest', p_request_digest,
      'claim_epoch', 1
    )
  );
  new_event_id := proof_harness_runtime.append_runtime_assurance_event(
    p_tenant_id, p_project_id, p_actor_id,
    'INVOCATION_CLAIMED', p_invocation_id, event_payload, p_now
  );
  SELECT audit.payload_sha256 INTO STRICT new_payload_sha256
    FROM proof_harness_runtime.audit_events AS audit
   WHERE audit.tenant_id = p_tenant_id AND audit.project_id = p_project_id
     AND audit.event_id = new_event_id;
  INSERT INTO proof_harness_runtime.runtime_assurance_invocation_receipts(
    tenant_id, project_id, run_id, actor_id, execution_epoch,
    fencing_generation, authority_revision, revision_set_id, invocation_id,
    request_digest, claim_epoch, claim_backend_pid, claim_lock_key, state,
    result_ref, result_digest, claimed_at, updated_at, completed_at,
    recovery_evidence_ref, mutation_event_id, mutation_event_type,
    mutation_payload_sha256
  ) VALUES (
    p_tenant_id, p_project_id, p_run_id, p_actor_id, p_execution_epoch,
    p_fencing_generation, p_authority_revision, p_revision_set_id,
    p_invocation_id, p_request_digest, 1, pg_backend_pid(), p_claim_lock_key,
    'IN_PROGRESS', NULL, NULL, p_now, p_now, NULL, NULL,
    new_event_id, 'INVOCATION_CLAIMED', new_payload_sha256
  );
  RETURN 'ACQUIRED';
END
$claim_runtime_assurance_invocation$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.complete_runtime_assurance_invocation(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_run_id text,
  p_execution_epoch bigint,
  p_fencing_generation bigint,
  p_authority_revision text,
  p_revision_set_id text,
  p_invocation_id text,
  p_request_digest text,
  p_expected_claim_epoch bigint,
  p_result_ref text,
  p_result_digest text,
  p_now timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $complete_runtime_assurance_invocation$
DECLARE
  helper_oid oid := (
    'proof_harness_runtime.complete_runtime_assurance_invocation('
    'text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,'
    'timestamp with time zone)'
  )::regprocedure;
  candidate proof_harness_runtime.runtime_assurance_invocation_receipts%ROWTYPE;
  event_payload jsonb;
  new_event_id text;
  new_payload_sha256 text;
BEGIN
  PERFORM proof_harness_runtime.assert_runtime_application_writer(helper_oid);
  SELECT * INTO candidate
    FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
   WHERE receipt.tenant_id = p_tenant_id AND receipt.project_id = p_project_id
     AND receipt.actor_id = p_actor_id AND receipt.run_id = p_run_id
     AND receipt.execution_epoch = p_execution_epoch
     AND receipt.fencing_generation = p_fencing_generation
     AND receipt.authority_revision = p_authority_revision
     AND receipt.revision_set_id = p_revision_set_id
     AND receipt.invocation_id = p_invocation_id
   FOR UPDATE;
  IF NOT FOUND OR candidate.request_digest IS DISTINCT FROM p_request_digest
     OR candidate.claim_epoch IS DISTINCT FROM p_expected_claim_epoch THEN
    RAISE EXCEPTION 'invocation completion binding is stale'
      USING ERRCODE = '55000';
  END IF;
  IF candidate.state = 'COMPLETED' THEN
    IF candidate.result_ref IS DISTINCT FROM p_result_ref
       OR candidate.result_digest IS DISTINCT FROM p_result_digest
       OR candidate.recovery_evidence_ref IS NOT NULL THEN
      RAISE EXCEPTION 'invocation completion replay diverges'
        USING ERRCODE = '55000';
    END IF;
    event_payload := jsonb_build_object(
      'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
      'fencing_generation', p_fencing_generation,
      'authority_revision', p_authority_revision,
      'revision_set_id', p_revision_set_id,
      'detail', jsonb_build_object(
        'invocation_id', p_invocation_id,
        'request_digest', p_request_digest,
        'claim_epoch', p_expected_claim_epoch,
        'result_digest', p_result_digest
      )
    );
    IF NOT proof_harness_runtime.runtime_assurance_event_is_exact(
      p_tenant_id, p_project_id, p_actor_id, 'INVOCATION_COMPLETED',
      p_invocation_id, candidate.mutation_event_id,
      candidate.mutation_payload_sha256, event_payload, candidate.completed_at
    ) THEN
      RAISE EXCEPTION 'invocation completion replay journal is missing or drifted'
        USING ERRCODE = '55000';
    END IF;
    event_payload := jsonb_build_object(
      'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
      'fencing_generation', p_fencing_generation,
      'authority_revision', p_authority_revision,
      'revision_set_id', p_revision_set_id,
      'detail', jsonb_build_object(
        'invocation_id', p_invocation_id,
        'request_digest', p_request_digest,
        'claim_epoch', p_expected_claim_epoch,
        'result_digest', p_result_digest,
        'recovery_evidence_ref', p_recovery_evidence_ref
      )
    );
    IF NOT proof_harness_runtime.runtime_assurance_event_is_exact(
      p_tenant_id, p_project_id, p_actor_id,
      'INVOCATION_RECOVERY_RECONCILED', p_invocation_id,
      candidate.mutation_event_id, candidate.mutation_payload_sha256,
      event_payload, candidate.completed_at
    ) THEN
      RAISE EXCEPTION 'invocation recovery replay journal is missing or drifted'
        USING ERRCODE = '55000';
    END IF;
    RETURN true;
  END IF;
  IF candidate.state <> 'IN_PROGRESS' THEN
    RAISE EXCEPTION 'invocation completion requires IN_PROGRESS'
      USING ERRCODE = '55000';
  END IF;
  IF p_invocation_id IS DISTINCT FROM
       current_setting('app.operation_invocation_id', true)
     OR NOT proof_harness_runtime.is_live_runtime_assurance_claim(
       p_tenant_id, p_project_id, p_actor_id, p_run_id,
       p_execution_epoch, p_fencing_generation, p_authority_revision,
       p_revision_set_id, p_invocation_id, true
     ) THEN
    RAISE EXCEPTION 'invocation completion requires its live operation claim'
      USING ERRCODE = '55000';
  END IF;
  event_payload := jsonb_build_object(
    'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
    'fencing_generation', p_fencing_generation,
    'authority_revision', p_authority_revision,
    'revision_set_id', p_revision_set_id,
    'detail', jsonb_build_object(
      'invocation_id', p_invocation_id,
      'request_digest', p_request_digest,
      'claim_epoch', p_expected_claim_epoch,
      'result_digest', p_result_digest
    )
  );
  new_event_id := proof_harness_runtime.append_runtime_assurance_event(
    p_tenant_id, p_project_id, p_actor_id,
    'INVOCATION_COMPLETED', p_invocation_id, event_payload, p_now
  );
  SELECT audit.payload_sha256 INTO STRICT new_payload_sha256
    FROM proof_harness_runtime.audit_events AS audit
   WHERE audit.tenant_id = p_tenant_id AND audit.project_id = p_project_id
     AND audit.event_id = new_event_id;
  UPDATE proof_harness_runtime.runtime_assurance_invocation_receipts
     SET state = 'COMPLETED', result_ref = p_result_ref,
         result_digest = p_result_digest, updated_at = p_now,
         completed_at = p_now, mutation_event_id = new_event_id,
         mutation_event_type = 'INVOCATION_COMPLETED',
         mutation_payload_sha256 = new_payload_sha256
   WHERE tenant_id = p_tenant_id AND project_id = p_project_id
     AND actor_id = p_actor_id AND run_id = p_run_id
     AND execution_epoch = p_execution_epoch
     AND fencing_generation = p_fencing_generation
     AND authority_revision = p_authority_revision
     AND revision_set_id = p_revision_set_id
     AND invocation_id = p_invocation_id
     AND request_digest = p_request_digest
     AND claim_epoch = p_expected_claim_epoch AND state = 'IN_PROGRESS';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invocation completion compare-and-swap failed'
      USING ERRCODE = '40001';
  END IF;
  RETURN false;
END
$complete_runtime_assurance_invocation$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.reconcile_runtime_assurance_invocation(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_run_id text,
  p_execution_epoch bigint,
  p_fencing_generation bigint,
  p_authority_revision text,
  p_revision_set_id text,
  p_invocation_id text,
  p_request_digest text,
  p_expected_claim_epoch bigint,
  p_result_ref text,
  p_result_digest text,
  p_recovery_evidence_ref text,
  p_now timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $reconcile_runtime_assurance_invocation$
DECLARE
  helper_oid oid := (
    'proof_harness_runtime.reconcile_runtime_assurance_invocation('
    'text,text,text,text,bigint,bigint,text,text,text,text,bigint,text,text,text,'
    'timestamp with time zone)'
  )::regprocedure;
  candidate proof_harness_runtime.runtime_assurance_invocation_receipts%ROWTYPE;
  event_payload jsonb;
  new_event_id text;
  new_payload_sha256 text;
BEGIN
  PERFORM proof_harness_runtime.assert_runtime_application_writer(helper_oid);
  SELECT * INTO candidate
    FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
   WHERE receipt.tenant_id = p_tenant_id AND receipt.project_id = p_project_id
     AND receipt.actor_id = p_actor_id AND receipt.run_id = p_run_id
     AND receipt.execution_epoch = p_execution_epoch
     AND receipt.fencing_generation = p_fencing_generation
     AND receipt.authority_revision = p_authority_revision
     AND receipt.revision_set_id = p_revision_set_id
     AND receipt.invocation_id = p_invocation_id
   FOR UPDATE;
  IF NOT FOUND OR candidate.request_digest IS DISTINCT FROM p_request_digest
     OR candidate.claim_epoch IS DISTINCT FROM p_expected_claim_epoch THEN
    RAISE EXCEPTION 'invocation recovery binding is stale'
      USING ERRCODE = '55000';
  END IF;
  IF candidate.state = 'COMPLETED' THEN
    IF candidate.result_ref IS DISTINCT FROM p_result_ref
       OR candidate.result_digest IS DISTINCT FROM p_result_digest
       OR candidate.recovery_evidence_ref IS DISTINCT FROM p_recovery_evidence_ref THEN
      RAISE EXCEPTION 'invocation recovery replay diverges'
        USING ERRCODE = '55000';
    END IF;
    RETURN true;
  END IF;
  IF candidate.state <> 'RECOVERY_REQUIRED' THEN
    RAISE EXCEPTION 'invocation is not awaiting recovery reconciliation'
      USING ERRCODE = '55000';
  END IF;
  event_payload := jsonb_build_object(
    'run_id', p_run_id, 'execution_epoch', p_execution_epoch,
    'fencing_generation', p_fencing_generation,
    'authority_revision', p_authority_revision,
    'revision_set_id', p_revision_set_id,
    'detail', jsonb_build_object(
      'invocation_id', p_invocation_id,
      'request_digest', p_request_digest,
      'claim_epoch', p_expected_claim_epoch,
      'result_digest', p_result_digest,
      'recovery_evidence_ref', p_recovery_evidence_ref
    )
  );
  new_event_id := proof_harness_runtime.append_runtime_assurance_event(
    p_tenant_id, p_project_id, p_actor_id,
    'INVOCATION_RECOVERY_RECONCILED', p_invocation_id, event_payload, p_now
  );
  SELECT audit.payload_sha256 INTO STRICT new_payload_sha256
    FROM proof_harness_runtime.audit_events AS audit
   WHERE audit.tenant_id = p_tenant_id AND audit.project_id = p_project_id
     AND audit.event_id = new_event_id;
  UPDATE proof_harness_runtime.runtime_assurance_invocation_receipts
     SET state = 'COMPLETED', result_ref = p_result_ref,
         result_digest = p_result_digest,
         recovery_evidence_ref = p_recovery_evidence_ref,
         updated_at = p_now, completed_at = p_now,
         mutation_event_id = new_event_id,
         mutation_event_type = 'INVOCATION_RECOVERY_RECONCILED',
         mutation_payload_sha256 = new_payload_sha256
   WHERE tenant_id = p_tenant_id AND project_id = p_project_id
     AND actor_id = p_actor_id AND run_id = p_run_id
     AND execution_epoch = p_execution_epoch
     AND fencing_generation = p_fencing_generation
     AND authority_revision = p_authority_revision
     AND revision_set_id = p_revision_set_id
     AND invocation_id = p_invocation_id
     AND request_digest = p_request_digest
     AND claim_epoch = p_expected_claim_epoch AND state = 'RECOVERY_REQUIRED';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invocation recovery compare-and-swap failed'
      USING ERRCODE = '40001';
  END IF;
  RETURN false;
END
$reconcile_runtime_assurance_invocation$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_tool_result_commit()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_tool_result$
DECLARE
  operation_claim proof_harness_runtime.runtime_assurance_invocation_receipts%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'tool result commits cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' OR NEW.recovery_evidence_ref IS NULL THEN
    SELECT * INTO operation_claim
      FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
     WHERE receipt.tenant_id = NEW.tenant_id
       AND receipt.project_id = NEW.project_id
       AND receipt.run_id = NEW.run_id
       AND receipt.actor_id = NEW.actor_id
       AND receipt.execution_epoch = NEW.execution_epoch
       AND receipt.fencing_generation = NEW.fencing_generation
       AND receipt.authority_revision = NEW.authority_revision
       AND receipt.revision_set_id = NEW.revision_set_id
       AND receipt.invocation_id =
         current_setting('app.operation_invocation_id', true)
       AND receipt.state = 'IN_PROGRESS'
     FOR UPDATE;
    IF NOT FOUND
       OR (TG_OP = 'INSERT' AND operation_claim.invocation_id IS DISTINCT FROM NEW.invocation_id)
       OR operation_claim.claim_backend_pid IS DISTINCT FROM pg_backend_pid()
       OR NOT EXISTS (
         SELECT 1 FROM pg_catalog.pg_locks AS held
          WHERE held.locktype = 'advisory'
            AND held.mode = 'ExclusiveLock'
            AND held.database = (
              SELECT oid FROM pg_catalog.pg_database
               WHERE datname = current_database()
            )
            AND held.pid = operation_claim.claim_backend_pid
            AND held.classid = (
              ((operation_claim.claim_lock_key >> 32) & 4294967295)::oid
            )
            AND held.objid = (
              (operation_claim.claim_lock_key & 4294967295)::oid
            )
            AND held.objsubid = 1
            AND held.granted
       ) THEN
      RAISE EXCEPTION 'tool-result mutation requires its live operation claim'
        USING ERRCODE = '55000';
    END IF;
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'RAW_CAPTURED' OR NEW.recovery_evidence_ref IS NOT NULL THEN
      RAISE EXCEPTION 'tool results must be inserted as non-recovery RAW_CAPTURED'
        USING ERRCODE = '55000';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.pending_tool_call_bindings AS pending
       WHERE pending.tenant_id = NEW.tenant_id
         AND pending.project_id = NEW.project_id
         AND pending.run_id = NEW.run_id
         AND pending.execution_epoch = NEW.execution_epoch
         AND pending.fencing_generation = NEW.fencing_generation
         AND pending.authority_revision = NEW.authority_revision
         AND pending.revision_set_id = NEW.revision_set_id
         AND pending.invocation_id = NEW.invocation_id
         AND pending.call_id = NEW.call_id
         AND pending.attempt = NEW.attempt
         AND pending.execution_plan_hash = NEW.execution_plan_hash
         AND pending.environment_id = NEW.environment_id
         AND pending.authority_snapshot_id = NEW.authority_snapshot_id
         AND pending.state = 'PENDING'
    ) THEN
      RAISE EXCEPTION 'tool result requires its exact PENDING tool-call binding'
        USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.invocation_id IS DISTINCT FROM NEW.invocation_id
     OR OLD.call_id IS DISTINCT FROM NEW.call_id
     OR OLD.attempt IS DISTINCT FROM NEW.attempt
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.execution_plan_hash IS DISTINCT FROM NEW.execution_plan_hash
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.raw_result_ref IS DISTINCT FROM NEW.raw_result_ref
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'tool result commit identity and raw result are immutable'
      USING ERRCODE = '55000';
  END IF;
  -- The RAW_CAPTURED branch deliberately admits only INTERCEPTING or a
  -- recovery ABORTED transition; the latter is constrained by the evidence
  -- check immediately below.  Keep the combined transition contract visible
  -- for migration auditors.
  -- OLD.state = 'RAW_CAPTURED' AND NEW.state IN ('INTERCEPTING', 'ABORTED')
  IF NOT ((OLD.state = 'RAW_CAPTURED' AND NEW.state = 'INTERCEPTING')
       OR (OLD.state = 'RAW_CAPTURED' AND NEW.state = 'ABORTED'
           AND NEW.recovery_evidence_ref IS NOT NULL)
       OR (OLD.state = 'INTERCEPTING' AND NEW.state IN ('COMMITTED', 'ABORTED'))
       OR (OLD.state = 'COMMITTED' AND NEW.state IN ('PUBLISHED', 'ABORTED'))) THEN
    RAISE EXCEPTION 'invalid tool result commit state transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state = 'RAW_CAPTURED' AND NEW.state = 'INTERCEPTING'
     AND (OLD.effective_result_ref IS DISTINCT FROM NEW.effective_result_ref
       OR OLD.interceptor_chain IS DISTINCT FROM NEW.interceptor_chain
       OR OLD.mutation_provenance_ref IS DISTINCT FROM NEW.mutation_provenance_ref
       OR OLD.failure_kind IS DISTINCT FROM NEW.failure_kind
       OR OLD.failure_reason IS DISTINCT FROM NEW.failure_reason
       OR OLD.committed_at IS DISTINCT FROM NEW.committed_at
       OR OLD.published_at IS DISTINCT FROM NEW.published_at
       OR OLD.aborted_at IS DISTINCT FROM NEW.aborted_at
       OR OLD.recovery_evidence_ref IS DISTINCT FROM NEW.recovery_evidence_ref) THEN
    RAISE EXCEPTION 'interception claim cannot change captured result content'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state = 'RAW_CAPTURED' AND NEW.state = 'ABORTED'
     AND NEW.recovery_evidence_ref IS NULL
     AND (OLD.effective_result_ref IS DISTINCT FROM NEW.effective_result_ref
       OR OLD.interceptor_chain IS DISTINCT FROM NEW.interceptor_chain
       OR OLD.mutation_provenance_ref IS DISTINCT FROM NEW.mutation_provenance_ref
       OR OLD.committed_at IS DISTINCT FROM NEW.committed_at
       OR OLD.published_at IS DISTINCT FROM NEW.published_at) THEN
    RAISE EXCEPTION 'raw-result abort cannot rewrite captured result content'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state = 'COMMITTED'
     AND (OLD.effective_result_ref IS DISTINCT FROM NEW.effective_result_ref
       OR OLD.interceptor_chain IS DISTINCT FROM NEW.interceptor_chain
       OR OLD.mutation_provenance_ref IS DISTINCT FROM NEW.mutation_provenance_ref
       OR OLD.committed_at IS DISTINCT FROM NEW.committed_at) THEN
    RAISE EXCEPTION 'committed tool result content is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.recovery_evidence_ref IS NOT NULL
     AND OLD.recovery_evidence_ref IS DISTINCT FROM NEW.recovery_evidence_ref THEN
    RAISE EXCEPTION 'tool-result recovery evidence is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NEW.recovery_evidence_ref IS NOT NULL
     AND NOT EXISTS (
       SELECT 1
         FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS receipt
        WHERE receipt.tenant_id = NEW.tenant_id
          AND receipt.project_id = NEW.project_id
          AND receipt.run_id = NEW.run_id
          AND receipt.actor_id = NEW.actor_id
          AND receipt.execution_epoch = NEW.execution_epoch
          AND receipt.fencing_generation = NEW.fencing_generation
          AND receipt.authority_revision = NEW.authority_revision
          AND receipt.revision_set_id = NEW.revision_set_id
          AND receipt.invocation_id = NEW.invocation_id
          AND receipt.state = 'RECOVERY_REQUIRED'
        FOR UPDATE
     ) THEN
    RAISE EXCEPTION 'tool-result recovery requires a RECOVERY_REQUIRED invocation claim'
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_tool_result$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_step_execution_plan()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_step_plan$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'step execution plans cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'CANDIDATE' THEN
      RAISE EXCEPTION 'step execution plans must be inserted as CANDIDATE'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.plan_id IS DISTINCT FROM NEW.plan_id
     OR OLD.step_id IS DISTINCT FROM NEW.step_id
     OR OLD.plan_hash IS DISTINCT FROM NEW.plan_hash
     OR OLD.model_snapshot IS DISTINCT FROM NEW.model_snapshot
     OR OLD.tool_plan IS DISTINCT FROM NEW.tool_plan
     OR OLD.tool_contracts IS DISTINCT FROM NEW.tool_contracts
     OR OLD.handler_digests IS DISTINCT FROM NEW.handler_digests
     OR OLD.capabilities IS DISTINCT FROM NEW.capabilities
     OR OLD.tool_mode IS DISTINCT FROM NEW.tool_mode
     OR OLD.environment_snapshot_id IS DISTINCT FROM NEW.environment_snapshot_id
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'finalized step plan identity and content are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NOT ((OLD.state = 'CANDIDATE' AND NEW.state = 'FINALIZED')
       OR (OLD.state = 'FINALIZED' AND NEW.state = 'ACTIVE')
       OR (OLD.state = 'ACTIVE' AND NEW.state = 'RETIRED')) THEN
    RAISE EXCEPTION 'invalid step plan state transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_step_plan$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_step_plan_tool_binding()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_step_plan_tool_binding$
DECLARE
  parent_plan proof_harness_runtime.step_execution_plans%ROWTYPE;
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'step-plan tool bindings are immutable'
      USING ERRCODE = '55000';
  END IF;
  SELECT * INTO parent_plan
    FROM proof_harness_runtime.step_execution_plans
   WHERE tenant_id = NEW.tenant_id
     AND project_id = NEW.project_id
     AND run_id = NEW.run_id
     AND execution_epoch = NEW.execution_epoch
     AND fencing_generation = NEW.fencing_generation
     AND authority_revision = NEW.authority_revision
     AND revision_set_id = NEW.revision_set_id
     AND plan_hash = NEW.plan_hash
   FOR KEY SHARE;
  IF NOT FOUND
     OR NOT EXISTS (
       SELECT 1 FROM jsonb_array_elements_text(parent_plan.tool_plan -> 'tools') AS planned(tool_id)
        WHERE planned.tool_id = NEW.tool_id
     )
     OR NOT (parent_plan.tool_contracts ? NEW.tool_id)
     OR parent_plan.tool_contracts -> NEW.tool_id IS DISTINCT FROM NEW.tool_contract
     OR parent_plan.handler_digests ->> NEW.tool_id IS DISTINCT FROM NEW.handler_digest THEN
    RAISE EXCEPTION 'step-plan tool binding diverges from its canonical plan'
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END
$guard_step_plan_tool_binding$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_runtime_authority_capability_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_runtime_authority_capability_receipt$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    RAISE EXCEPTION 'runtime authority capability receipts are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NOT proof_harness_runtime.is_live_runtime_assurance_claim(
    NEW.tenant_id, NEW.project_id, NEW.actor_id, NEW.run_id,
    NEW.execution_epoch, NEW.fencing_generation, NEW.authority_revision,
    NEW.revision_set_id, NEW.operation_invocation_id, false
  ) OR NOT EXISTS (
    SELECT 1 FROM proof_harness_runtime.environment_attachments AS attachment
     WHERE attachment.tenant_id = NEW.tenant_id
       AND attachment.project_id = NEW.project_id
       AND attachment.run_id = NEW.run_id
       AND attachment.execution_epoch = NEW.execution_epoch
       AND attachment.fencing_generation = NEW.fencing_generation
       AND attachment.authority_revision = NEW.authority_revision
       AND attachment.revision_set_id = NEW.revision_set_id
       AND attachment.environment_id = NEW.environment_id
       AND attachment.owner_authority_ref = NEW.authority_snapshot_id
       AND attachment.state = 'ACTIVE'
  ) THEN
    RAISE EXCEPTION 'runtime authority receipt lacks active durable parents'
      USING ERRCODE = '23503';
  END IF;
  RETURN NEW;
END
$guard_runtime_authority_capability_receipt$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_pending_tool_call_binding()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_pending_tool_call_binding$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'pending tool-call bindings cannot be deleted'
      USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'PENDING' THEN
      RAISE EXCEPTION 'pending tool-call bindings must be inserted as PENDING'
        USING ERRCODE = '55000';
    END IF;
    IF NOT proof_harness_runtime.is_live_runtime_assurance_claim(
      NEW.tenant_id, NEW.project_id, NEW.actor_id, NEW.run_id,
      NEW.execution_epoch, NEW.fencing_generation, NEW.authority_revision,
      NEW.revision_set_id, NEW.invocation_id, true
    ) OR NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.step_execution_plans AS plan
       WHERE plan.tenant_id = NEW.tenant_id
         AND plan.project_id = NEW.project_id
         AND plan.run_id = NEW.run_id
         AND plan.execution_epoch = NEW.execution_epoch
         AND plan.fencing_generation = NEW.fencing_generation
         AND plan.authority_revision = NEW.authority_revision
         AND plan.revision_set_id = NEW.revision_set_id
         AND plan.plan_hash = NEW.execution_plan_hash
         AND plan.authority_snapshot_id = NEW.authority_snapshot_id
         AND plan.state = 'ACTIVE'
    ) OR NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.environment_attachments AS attachment
       WHERE attachment.tenant_id = NEW.tenant_id
         AND attachment.project_id = NEW.project_id
         AND attachment.run_id = NEW.run_id
         AND attachment.execution_epoch = NEW.execution_epoch
         AND attachment.fencing_generation = NEW.fencing_generation
         AND attachment.authority_revision = NEW.authority_revision
         AND attachment.revision_set_id = NEW.revision_set_id
         AND attachment.environment_id = NEW.environment_id
         AND attachment.owner_authority_ref = NEW.authority_snapshot_id
         AND attachment.state = 'ACTIVE'
    ) THEN
      RAISE EXCEPTION 'pending tool-call binding lacks active durable parents'
        USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.invocation_id IS DISTINCT FROM NEW.invocation_id
     OR OLD.call_id IS DISTINCT FROM NEW.call_id
     OR OLD.attempt IS DISTINCT FROM NEW.attempt
     OR OLD.execution_plan_hash IS DISTINCT FROM NEW.execution_plan_hash
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.tool_id IS DISTINCT FROM NEW.tool_id
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'pending tool-call binding identity is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'PENDING' OR NEW.state <> 'RECONCILED'
     OR OLD.reconciled_at IS NOT NULL OR NEW.reconciled_at IS NULL THEN
    RAISE EXCEPTION 'invalid pending tool-call binding transition % -> %',
      OLD.state, NEW.state USING ERRCODE = '55000';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM proof_harness_runtime.tool_result_commits AS result
     WHERE result.tenant_id = NEW.tenant_id
       AND result.project_id = NEW.project_id
       AND result.run_id = NEW.run_id
       AND result.execution_epoch = NEW.execution_epoch
       AND result.fencing_generation = NEW.fencing_generation
       AND result.authority_revision = NEW.authority_revision
       AND result.revision_set_id = NEW.revision_set_id
       AND result.invocation_id = NEW.invocation_id
       AND result.call_id = NEW.call_id
       AND result.attempt = NEW.attempt
       AND result.execution_plan_hash = NEW.execution_plan_hash
       AND result.environment_id = NEW.environment_id
       AND result.authority_snapshot_id = NEW.authority_snapshot_id
       AND result.state IN ('COMMITTED', 'PUBLISHED', 'ABORTED')
  ) THEN
    RAISE EXCEPTION 'pending tool-call reconciliation requires its exact terminal result'
      USING ERRCODE = '23503';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_pending_tool_call_binding$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_capability_lease()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_capability_lease$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'capability leases cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'ACTIVE' THEN
      RAISE EXCEPTION 'capability leases must be inserted as ACTIVE'
        USING ERRCODE = '55000';
    END IF;
    IF NEW.issued_at > clock_timestamp() + interval '5 seconds'
       OR NEW.expires_at <= clock_timestamp()
       OR NEW.expires_at > NEW.issued_at + interval '15 minutes' THEN
      RAISE EXCEPTION 'capability lease validity window is outside the durable bound'
        USING ERRCODE = '22023';
    END IF;
    IF NOT EXISTS (
      SELECT 1
        FROM proof_harness_runtime.runtime_authority_capability_receipts AS receipt
        JOIN proof_harness_runtime.runtime_assurance_invocation_receipts AS invocation
          ON invocation.tenant_id = receipt.tenant_id
         AND invocation.project_id = receipt.project_id
         AND invocation.run_id = receipt.run_id
         AND invocation.execution_epoch = receipt.execution_epoch
         AND invocation.fencing_generation = receipt.fencing_generation
         AND invocation.authority_revision = receipt.authority_revision
         AND invocation.revision_set_id = receipt.revision_set_id
         AND invocation.invocation_id = receipt.operation_invocation_id
       WHERE receipt.tenant_id = NEW.tenant_id
         AND receipt.project_id = NEW.project_id
         AND receipt.run_id = NEW.run_id
         AND receipt.execution_epoch = NEW.execution_epoch
         AND receipt.fencing_generation = NEW.fencing_generation
         AND receipt.authority_revision = NEW.authority_revision
         AND receipt.revision_set_id = NEW.revision_set_id
         AND receipt.operation_invocation_id = NEW.invocation_id
         AND receipt.environment_id = NEW.environment_id
         AND receipt.authority_snapshot_id = NEW.authority_snapshot_id
         AND (NOT NEW.delegation_allowed OR receipt.delegation_allowed)
        AND proof_harness_runtime.is_live_runtime_assurance_claim(
          NEW.tenant_id, NEW.project_id, NEW.actor_id, NEW.run_id,
          NEW.execution_epoch, NEW.fencing_generation, NEW.authority_revision,
          NEW.revision_set_id, NEW.invocation_id, true
        )
         AND NOT EXISTS (
           SELECT requested.capability
             FROM jsonb_array_elements_text(NEW.capability_set) AS requested(capability)
            WHERE NOT EXISTS (
              SELECT 1
                FROM jsonb_array_elements_text(receipt.capability_set) AS allowed(capability)
               WHERE allowed.capability = requested.capability
            )
         )
    ) THEN
      RAISE EXCEPTION 'capability lease exceeds its active authority receipt'
        USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.lease_id IS DISTINCT FROM NEW.lease_id
     OR OLD.invocation_id IS DISTINCT FROM NEW.invocation_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.capability_set IS DISTINCT FROM NEW.capability_set
     OR OLD.delegation_allowed IS DISTINCT FROM NEW.delegation_allowed
     OR OLD.issued_at IS DISTINCT FROM NEW.issued_at
     OR OLD.expires_at IS DISTINCT FROM NEW.expires_at THEN
    RAISE EXCEPTION 'capability lease scope and authority are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'ACTIVE' OR NEW.state NOT IN ('REVOKED', 'EXPIRED') THEN
    RAISE EXCEPTION 'invalid capability lease state transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_capability_lease$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_executor_generation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_executor_generation$
DECLARE
  replacement_effect_count integer;
  replacement_effect_kind_count integer;
  required_replacement_effect_kind_count integer;
  succeeded_replacement_effect_count integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'executor generations cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'CONNECTING' THEN
      RAISE EXCEPTION 'executor generations must be inserted as CONNECTING'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.executor_identity IS DISTINCT FROM NEW.executor_identity
     OR OLD.executor_generation IS DISTINCT FROM NEW.executor_generation
     OR OLD.connection_epoch IS DISTINCT FROM NEW.connection_epoch
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'executor generation identity and fence are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NOT ((OLD.state = 'CONNECTING' AND NEW.state IN ('ACTIVE', 'FAILED'))
       OR (OLD.state = 'ACTIVE' AND NEW.state IN ('RETIRED', 'FAILED'))) THEN
    RAISE EXCEPTION 'invalid executor generation state transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state = 'ACTIVE'
     AND OLD.live_probe_evidence_ref IS DISTINCT FROM NEW.live_probe_evidence_ref THEN
    RAISE EXCEPTION 'active executor live-probe evidence is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state = 'CONNECTING'
     AND NEW.state = 'ACTIVE'
     AND (NEW.executor_generation, NEW.connection_epoch) <> (1, 1) THEN
    SELECT
      count(*),
      count(DISTINCT effect.kind),
      count(*) FILTER (WHERE effect.kind IN (
        'CAPABILITY_REVOCATION',
        'WORKSPACE_RECONCILIATION',
        'EXTERNAL_EFFECT_RECONCILIATION'
      )),
      count(*) FILTER (WHERE effect.state = 'SUCCEEDED')
      INTO replacement_effect_count,
           replacement_effect_kind_count,
           required_replacement_effect_kind_count,
           succeeded_replacement_effect_count
      FROM proof_harness_runtime.executor_replacement_effects AS effect
     WHERE effect.tenant_id = NEW.tenant_id
       AND effect.project_id = NEW.project_id
       AND effect.actor_id = NEW.actor_id
       AND effect.run_id = NEW.run_id
       AND effect.execution_epoch = NEW.execution_epoch
       AND effect.fencing_generation = NEW.fencing_generation
       AND effect.authority_revision = NEW.authority_revision
       AND effect.revision_set_id = NEW.revision_set_id
       AND effect.environment_id = NEW.environment_id
       AND effect.executor_generation = NEW.executor_generation
       AND effect.connection_epoch = NEW.connection_epoch;
    IF replacement_effect_count <> 3
       OR replacement_effect_kind_count <> 3
       OR required_replacement_effect_kind_count <> 3
       OR succeeded_replacement_effect_count <> 3 THEN
      RAISE EXCEPTION 'advanced executor activation requires exactly three succeeded reconciliation effects'
        USING ERRCODE = '55000';
    END IF;
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_executor_generation$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_environment_attachment()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_environment_attachment$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'environment attachments cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'ACTIVE' THEN
      RAISE EXCEPTION 'environment attachments must be inserted as ACTIVE'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.server_id IS DISTINCT FROM NEW.server_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.snapshot_id IS DISTINCT FROM NEW.snapshot_id
     OR OLD.previous_snapshot_id IS DISTINCT FROM NEW.previous_snapshot_id
     OR OLD.generation IS DISTINCT FROM NEW.generation
     OR OLD.owner_authority_ref IS DISTINCT FROM NEW.owner_authority_ref
     OR OLD.parent_authority_ref IS DISTINCT FROM NEW.parent_authority_ref
     OR OLD.effective_permissions IS DISTINCT FROM NEW.effective_permissions
     OR OLD.settings_authority IS DISTINCT FROM NEW.settings_authority
     OR OLD.settings_digest IS DISTINCT FROM NEW.settings_digest
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'environment attachment snapshot is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'ACTIVE' OR NEW.state <> 'SUPERSEDED' THEN
    RAISE EXCEPTION 'invalid environment attachment transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_environment_attachment$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_executor_replacement_effect()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_executor_replacement_effect$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'executor replacement effects cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'PENDING' THEN
      RAISE EXCEPTION 'executor replacement effects must be inserted as PENDING'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.effect_id IS DISTINCT FROM NEW.effect_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.executor_generation IS DISTINCT FROM NEW.executor_generation
     OR OLD.connection_epoch IS DISTINCT FROM NEW.connection_epoch
     OR OLD.kind IS DISTINCT FROM NEW.kind
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'executor replacement effect identity is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'PENDING' OR NEW.state NOT IN ('SUCCEEDED', 'FAILED', 'UNKNOWN') THEN
    RAISE EXCEPTION 'invalid executor replacement effect transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_executor_replacement_effect$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_workspace_lease()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_workspace_lease$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'workspace leases cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'ACTIVE' THEN
      RAISE EXCEPTION 'workspace leases must be inserted as ACTIVE'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id
     OR OLD.owner_execution_id IS DISTINCT FROM NEW.owner_execution_id
     OR OLD.generation IS DISTINCT FROM NEW.generation
     OR OLD.repository_id IS DISTINCT FROM NEW.repository_id
     OR OLD.base_revision IS DISTINCT FROM NEW.base_revision
     OR OLD.write_scopes IS DISTINCT FROM NEW.write_scopes
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'workspace ownership scope and fence are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.takeover_evidence_ref IS DISTINCT FROM NEW.takeover_evidence_ref
     AND NOT (
       OLD.state = 'ACTIVE'
       AND NEW.state = 'TAKEOVER_PENDING'
       AND OLD.takeover_evidence_ref IS NULL
       AND NEW.takeover_evidence_ref IS NOT NULL
     )
     AND NOT (
       OLD.state = 'TAKEOVER_PENDING'
       AND NEW.state = 'RETIRED'
       AND OLD.takeover_evidence_ref IS NOT NULL
       AND NEW.takeover_evidence_ref IS NULL
     ) THEN
    RAISE EXCEPTION 'workspace takeover evidence is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NOT ((OLD.state = 'ACTIVE' AND NEW.state IN (
         'HANDOFF_PENDING', 'TAKEOVER_PENDING', 'RETIRED'
       ))
       OR (OLD.state = 'HANDOFF_PENDING' AND NEW.state = 'RETIRED')
       OR (OLD.state = 'TAKEOVER_PENDING' AND NEW.state IN ('ACTIVE', 'RETIRED'))) THEN
    RAISE EXCEPTION 'invalid workspace lease state transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_workspace_lease$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_runtime_assurance_invocation_receipt()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_invocation_receipt$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'runtime-assurance invocation receipts cannot be deleted'
      USING ERRCODE = '55000';
  END IF;
  IF (SELECT c.relowner FROM pg_catalog.pg_class AS c WHERE c.oid = TG_RELID)
     IS DISTINCT FROM
       (SELECT r.oid FROM pg_catalog.pg_roles AS r WHERE r.rolname = current_user) THEN
    RAISE EXCEPTION 'invocation receipt lifecycle is helper-only'
      USING ERRCODE = '42501';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'IN_PROGRESS' THEN
      RAISE EXCEPTION 'invocation receipts must be inserted as IN_PROGRESS'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.invocation_id IS DISTINCT FROM NEW.invocation_id
     OR OLD.request_digest IS DISTINCT FROM NEW.request_digest
     OR OLD.claim_epoch IS DISTINCT FROM NEW.claim_epoch
     OR OLD.claim_backend_pid IS DISTINCT FROM NEW.claim_backend_pid
     OR OLD.claim_lock_key IS DISTINCT FROM NEW.claim_lock_key
     OR OLD.claimed_at IS DISTINCT FROM NEW.claimed_at THEN
    RAISE EXCEPTION 'runtime-assurance invocation claim identity is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF NOT (
       (OLD.state = 'IN_PROGRESS'
        AND NEW.state IN ('COMPLETED', 'RECOVERY_REQUIRED'))
       OR (OLD.state = 'RECOVERY_REQUIRED' AND NEW.state = 'COMPLETED')
     ) THEN
    RAISE EXCEPTION 'invalid runtime-assurance invocation receipt transition % -> %',
      OLD.state, NEW.state USING ERRCODE = '55000';
  END IF;
  IF OLD.recovery_evidence_ref IS DISTINCT FROM NEW.recovery_evidence_ref
     AND NOT (
       OLD.state = 'RECOVERY_REQUIRED'
       AND NEW.state = 'COMPLETED'
       AND OLD.recovery_evidence_ref IS NULL
       AND NEW.recovery_evidence_ref IS NOT NULL
     ) THEN
    RAISE EXCEPTION 'runtime-assurance recovery evidence is immutable'
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_invocation_receipt$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_durable_event_instance()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_durable_event_instance$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'durable event instances cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'PENDING' THEN
      RAISE EXCEPTION 'durable event instances must be inserted as PENDING'
        USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.event_id IS DISTINCT FROM NEW.event_id
     OR OLD.event_type IS DISTINCT FROM NEW.event_type
     OR OLD.schema_version IS DISTINCT FROM NEW.schema_version
     OR OLD.payload_ref IS DISTINCT FROM NEW.payload_ref
     OR OLD.payload_digest IS DISTINCT FROM NEW.payload_digest
     OR OLD.causation_id IS DISTINCT FROM NEW.causation_id
     OR OLD.correlation_id IS DISTINCT FROM NEW.correlation_id
     OR OLD.parent_event_id IS DISTINCT FROM NEW.parent_event_id
     OR OLD.source_scope IS DISTINCT FROM NEW.source_scope
     OR OLD.fork_lineage IS DISTINCT FROM NEW.fork_lineage
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'durable event instance identity and payload are immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'PENDING' OR NEW.state NOT IN ('PROCESSED', 'SKIPPED') THEN
    RAISE EXCEPTION 'invalid durable event instance transition % -> %', OLD.state, NEW.state
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_durable_event_instance$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_subagent_budget_reservation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_subagent_budget_reservation$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'subagent budget reservations cannot be deleted'
      USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'RESERVED' THEN
      RAISE EXCEPTION 'subagent budget reservations must be inserted as RESERVED'
        USING ERRCODE = '55000';
    END IF;
    IF NOT proof_harness_runtime.is_live_runtime_assurance_claim(
      NEW.tenant_id, NEW.project_id, NEW.actor_id, NEW.run_id,
      NEW.execution_epoch, NEW.fencing_generation, NEW.authority_revision,
      NEW.revision_set_id, NEW.operation_invocation_id, false
    ) OR NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.step_execution_plans AS plan
       WHERE plan.tenant_id = NEW.tenant_id
         AND plan.project_id = NEW.project_id
         AND plan.run_id = NEW.run_id
         AND plan.execution_epoch = NEW.execution_epoch
         AND plan.fencing_generation = NEW.fencing_generation
         AND plan.authority_revision = NEW.authority_revision
         AND plan.revision_set_id = NEW.revision_set_id
         AND plan.plan_hash = NEW.tool_plan_hash
         AND plan.authority_snapshot_id = NEW.authority_snapshot_id
         AND plan.state = 'ACTIVE'
    ) OR NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.environment_attachments AS attachment
       WHERE attachment.tenant_id = NEW.tenant_id
         AND attachment.project_id = NEW.project_id
         AND attachment.run_id = NEW.run_id
         AND attachment.execution_epoch = NEW.execution_epoch
         AND attachment.fencing_generation = NEW.fencing_generation
         AND attachment.authority_revision = NEW.authority_revision
         AND attachment.revision_set_id = NEW.revision_set_id
         AND attachment.environment_id = NEW.environment_id
         AND attachment.owner_authority_ref = NEW.authority_snapshot_id
         AND attachment.state = 'ACTIVE'
    ) OR NOT EXISTS (
      SELECT 1
        FROM proof_harness_runtime.runtime_authority_capability_receipts AS authority
       WHERE authority.tenant_id = NEW.tenant_id
         AND authority.project_id = NEW.project_id
         AND authority.run_id = NEW.run_id
         AND authority.execution_epoch = NEW.execution_epoch
         AND authority.fencing_generation = NEW.fencing_generation
         AND authority.authority_revision = NEW.authority_revision
         AND authority.revision_set_id = NEW.revision_set_id
         AND authority.operation_invocation_id = NEW.operation_invocation_id
         AND authority.environment_id = NEW.environment_id
         AND authority.authority_snapshot_id = NEW.authority_snapshot_id
         AND authority.host_envelope_digest = NEW.authority_envelope_digest
    ) THEN
      RAISE EXCEPTION 'subagent reservation lacks active durable parents'
        USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.reservation_id IS DISTINCT FROM NEW.reservation_id
     OR OLD.operation_invocation_id IS DISTINCT FROM NEW.operation_invocation_id
     OR OLD.parent_execution_id IS DISTINCT FROM NEW.parent_execution_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.provider IS DISTINCT FROM NEW.provider
     OR OLD.model IS DISTINCT FROM NEW.model
     OR OLD.reasoning_effort IS DISTINCT FROM NEW.reasoning_effort
     OR OLD.child_authority IS DISTINCT FROM NEW.child_authority
     OR OLD.child_tools IS DISTINCT FROM NEW.child_tools
     OR OLD.max_output_tokens IS DISTINCT FROM NEW.max_output_tokens
     OR OLD.max_cost_budget IS DISTINCT FROM NEW.max_cost_budget
     OR OLD.wall_clock_deadline IS DISTINCT FROM NEW.wall_clock_deadline
     OR OLD.tool_plan_hash IS DISTINCT FROM NEW.tool_plan_hash
     OR OLD.authority_envelope_digest IS DISTINCT FROM NEW.authority_envelope_digest
     OR OLD.host_envelope_payload_digest IS DISTINCT FROM NEW.host_envelope_payload_digest
     OR OLD.host_envelope_digest IS DISTINCT FROM NEW.host_envelope_digest
     OR OLD.host_envelope_issuer IS DISTINCT FROM NEW.host_envelope_issuer
     OR OLD.host_envelope_signing_key_id IS DISTINCT FROM NEW.host_envelope_signing_key_id
     OR OLD.host_envelope_signature_algorithm IS DISTINCT FROM NEW.host_envelope_signature_algorithm
     OR OLD.host_envelope_signature IS DISTINCT FROM NEW.host_envelope_signature
     OR OLD.host_envelope_issued_at IS DISTINCT FROM NEW.host_envelope_issued_at
     OR OLD.host_envelope_verifier_id IS DISTINCT FROM NEW.host_envelope_verifier_id
     OR OLD.host_envelope_verification_evidence_ref IS DISTINCT FROM NEW.host_envelope_verification_evidence_ref
     OR OLD.host_envelope_verification_evidence_digest IS DISTINCT FROM NEW.host_envelope_verification_evidence_digest
     OR OLD.host_envelope_verified_at IS DISTINCT FROM NEW.host_envelope_verified_at
     OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
    RAISE EXCEPTION 'subagent budget reservation identity is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'RESERVED' OR NEW.state <> 'CONSUMED'
     OR OLD.consumed_at IS NOT NULL OR NEW.consumed_at IS NULL
     OR OLD.consumer_execution_id IS NOT NULL OR NEW.consumer_execution_id IS NULL
     OR OLD.consume_event_id IS NOT NULL OR NEW.consume_event_id IS NULL
     OR OLD.consume_payload_sha256 IS NOT NULL
     OR NEW.consume_payload_sha256 IS NULL THEN
    RAISE EXCEPTION 'invalid subagent budget reservation transition % -> %',
      OLD.state, NEW.state USING ERRCODE = '55000';
  END IF;
  IF NEW.consumed_at >= OLD.wall_clock_deadline
     OR clock_timestamp() >= OLD.wall_clock_deadline THEN
    RAISE EXCEPTION 'subagent budget reservation deadline has expired'
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_subagent_budget_reservation$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.guard_subagent_execution_spec()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, proof_harness_runtime
AS $guard_subagent_execution_spec$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'subagent execution specs cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'RESERVED' THEN
      RAISE EXCEPTION 'subagent execution specs must be inserted as RESERVED'
        USING ERRCODE = '55000';
    END IF;
    IF NOT proof_harness_runtime.is_live_runtime_assurance_claim(
      NEW.tenant_id, NEW.project_id, NEW.actor_id, NEW.run_id,
      NEW.execution_epoch, NEW.fencing_generation, NEW.authority_revision,
      NEW.revision_set_id, NEW.invocation_id, true
    ) THEN
      RAISE EXCEPTION 'subagent execution spec requires an active invocation claim'
        USING ERRCODE = '23503';
    END IF;
    IF NOT EXISTS (
      SELECT 1
        FROM proof_harness_runtime.subagent_budget_reservation_bindings AS reservation
        JOIN proof_harness_runtime.step_execution_plans AS plan
          ON plan.tenant_id = reservation.tenant_id
         AND plan.project_id = reservation.project_id
         AND plan.run_id = reservation.run_id
         AND plan.execution_epoch = reservation.execution_epoch
         AND plan.fencing_generation = reservation.fencing_generation
         AND plan.authority_revision = reservation.authority_revision
         AND plan.revision_set_id = reservation.revision_set_id
         AND plan.plan_hash = reservation.tool_plan_hash
       WHERE reservation.tenant_id = NEW.tenant_id
         AND reservation.project_id = NEW.project_id
         AND reservation.run_id = NEW.run_id
         AND reservation.execution_epoch = NEW.execution_epoch
         AND reservation.fencing_generation = NEW.fencing_generation
         AND reservation.authority_revision = NEW.authority_revision
         AND reservation.revision_set_id = NEW.revision_set_id
         AND reservation.reservation_id = NEW.budget_reservation_id
         AND reservation.operation_invocation_id = NEW.invocation_id
         AND reservation.parent_execution_id = NEW.parent_execution_id
         AND reservation.environment_id = NEW.environment_id
         AND reservation.authority_snapshot_id = NEW.authority_snapshot_id
         AND reservation.provider = NEW.provider
         AND reservation.model = NEW.model
         AND reservation.reasoning_effort = NEW.reasoning_effort
         AND reservation.tool_plan_hash = NEW.tool_plan_hash
         AND reservation.state = 'RESERVED'
         AND plan.state = 'ACTIVE'
         AND NEW.max_output_tokens <= reservation.max_output_tokens
         AND NEW.cost_budget::numeric <= reservation.max_cost_budget::numeric
         AND NEW.wall_clock_deadline <= reservation.wall_clock_deadline
         AND NOT EXISTS (
           SELECT requested.value
             FROM jsonb_array_elements_text(NEW.child_authority) AS requested(value)
            WHERE NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(reservation.child_authority) AS allowed(value)
               WHERE allowed.value = requested.value
            )
         )
         AND NOT EXISTS (
           SELECT requested.value
             FROM jsonb_array_elements_text(NEW.child_tools) AS requested(value)
            WHERE NOT EXISTS (
              SELECT 1 FROM jsonb_array_elements_text(reservation.child_tools) AS allowed(value)
               WHERE allowed.value = requested.value
            )
         )
    ) THEN
      RAISE EXCEPTION 'subagent execution spec exceeds its durable reservation'
        USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
     OR OLD.project_id IS DISTINCT FROM NEW.project_id
     OR OLD.run_id IS DISTINCT FROM NEW.run_id
     OR OLD.actor_id IS DISTINCT FROM NEW.actor_id
     OR OLD.invocation_id IS DISTINCT FROM NEW.invocation_id
     OR OLD.parent_execution_id IS DISTINCT FROM NEW.parent_execution_id
     OR OLD.provider IS DISTINCT FROM NEW.provider
     OR OLD.model IS DISTINCT FROM NEW.model
     OR OLD.reasoning_effort IS DISTINCT FROM NEW.reasoning_effort
     OR OLD.authority_snapshot_id IS DISTINCT FROM NEW.authority_snapshot_id
     OR OLD.environment_id IS DISTINCT FROM NEW.environment_id
     OR OLD.budget_reservation_id IS DISTINCT FROM NEW.budget_reservation_id
     OR OLD.max_output_tokens IS DISTINCT FROM NEW.max_output_tokens
     OR OLD.tool_plan_hash IS DISTINCT FROM NEW.tool_plan_hash
     OR OLD.child_authority IS DISTINCT FROM NEW.child_authority
     OR OLD.child_tools IS DISTINCT FROM NEW.child_tools
     OR OLD.cost_budget IS DISTINCT FROM NEW.cost_budget
     OR OLD.wall_clock_deadline IS DISTINCT FROM NEW.wall_clock_deadline
     OR OLD.spec_hash IS DISTINCT FROM NEW.spec_hash
     OR OLD.execution_epoch IS DISTINCT FROM NEW.execution_epoch
     OR OLD.fencing_generation IS DISTINCT FROM NEW.fencing_generation
     OR OLD.authority_revision IS DISTINCT FROM NEW.authority_revision
     OR OLD.revision_set_id IS DISTINCT FROM NEW.revision_set_id
     OR OLD.recorded_at IS DISTINCT FROM NEW.recorded_at THEN
    RAISE EXCEPTION 'subagent execution specification is immutable'
      USING ERRCODE = '55000';
  END IF;
  IF OLD.state <> 'RESERVED' OR NEW.state <> 'CONSUMED'
     OR OLD.consumer_execution_id IS NOT NULL
     OR NEW.consumer_execution_id IS NULL
     OR OLD.consumed_at IS NOT NULL
     OR NEW.consumed_at IS NULL THEN
    RAISE EXCEPTION 'invalid subagent budget consumption transition % -> %',
      OLD.state, NEW.state USING ERRCODE = '55000';
  END IF;
  IF NEW.consumed_at >= OLD.wall_clock_deadline
     OR clock_timestamp() >= OLD.wall_clock_deadline THEN
    RAISE EXCEPTION 'subagent budget reservation deadline has expired'
      USING ERRCODE = '55000';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$guard_subagent_execution_spec$;

CREATE OR REPLACE FUNCTION proof_harness_runtime.consume_subagent_reservation_and_spec(
  p_tenant_id text,
  p_project_id text,
  p_actor_id text,
  p_run_id text,
  p_execution_epoch bigint,
  p_fencing_generation bigint,
  p_authority_revision text,
  p_revision_set_id text,
  p_invocation_id text,
  p_reservation_id text,
  p_consumer_execution_id text,
  p_expected_spec_hash text,
  p_expected_authority_envelope_digest text,
  p_consumed_at timestamptz,
  p_event_id text,
  p_payload_json text,
  p_payload_sha256 text
)
RETURNS TABLE(replayed boolean)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, proof_harness_runtime
AS $consume_subagent_reservation_and_spec$
DECLARE
  reservation proof_harness_runtime.subagent_budget_reservation_bindings%ROWTYPE;
  spec proof_harness_runtime.subagent_execution_specs%ROWTYPE;
  claim proof_harness_runtime.runtime_assurance_invocation_receipts%ROWTYPE;
  expected_payload jsonb;
  expected_payload_json text;
  expected_payload_sha256 text;
  reservation_updated integer;
  spec_updated integer;
  authority_writer_oid oid;
  control_owner_oid oid;
  helper_oid oid;
BEGIN
  SELECT oid INTO authority_writer_oid
    FROM pg_catalog.pg_roles
   WHERE rolname = session_user;
  SELECT c.relowner INTO control_owner_oid
    FROM pg_catalog.pg_class AS c
   WHERE c.oid =
     'proof_harness_runtime.runtime_authority_capability_receipts'::regclass;
  helper_oid := (
    'proof_harness_runtime.consume_subagent_reservation_and_spec('
    'text,text,text,text,bigint,bigint,text,text,text,text,text,text,text,'
    'timestamp with time zone,text,text,text)'
  )::regprocedure;
  IF authority_writer_oid IS NULL
     OR control_owner_oid IS NULL
     OR helper_oid IS NULL
     OR authority_writer_oid = control_owner_oid
     OR (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
        IS DISTINCT FROM control_owner_oid
     OR NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles AS caller
     WHERE caller.rolname = session_user
       AND caller.rolcanlogin
       AND NOT caller.rolsuper AND NOT caller.rolbypassrls
       AND NOT caller.rolcreatedb AND NOT caller.rolcreaterole
       AND NOT caller.rolreplication
  )
     OR NOT has_table_privilege(
       session_user,
       'proof_harness_runtime.runtime_authority_capability_receipts',
       'INSERT'
     )
     OR NOT has_table_privilege(
       session_user,
       'proof_harness_runtime.subagent_budget_reservation_bindings',
       'INSERT'
     )
     OR pg_has_role(
       session_user,
       (SELECT pg_get_userbyid(c.relowner) FROM pg_catalog.pg_class AS c
         WHERE c.oid = 'proof_harness_runtime.subagent_execution_specs'::regclass),
       'SET'
     )
     OR EXISTS (
       SELECT 1 FROM pg_catalog.pg_auth_members AS membership
        WHERE membership.roleid = authority_writer_oid
           OR membership.member = authority_writer_oid
     )
     OR EXISTS (
       SELECT 1
         FROM pg_catalog.pg_attribute AS attribute
        WHERE attribute.attrelid IN (
          'proof_harness_runtime.runtime_authority_capability_receipts'::regclass,
          'proof_harness_runtime.subagent_budget_reservation_bindings'::regclass
        )
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
          AND attribute.attacl IS NOT NULL
     )
     OR EXISTS (
       SELECT 1
         FROM unnest(ARRAY[
           'proof_harness_runtime.runtime_authority_capability_receipts'::regclass,
           'proof_harness_runtime.subagent_budget_reservation_bindings'::regclass
         ]) AS secured(relation_oid)
         JOIN pg_catalog.pg_class AS relation
           ON relation.oid = secured.relation_oid
        WHERE relation.relowner <> control_owner_oid
           OR NOT EXISTS (
             SELECT 1
               FROM aclexplode(COALESCE(
                 relation.relacl,
                 acldefault('r', relation.relowner)
               )) AS privilege
              WHERE privilege.privilege_type = 'INSERT'
                AND privilege.grantee = authority_writer_oid
                AND NOT privilege.is_grantable
           )
           OR EXISTS (
             SELECT 1
               FROM aclexplode(COALESCE(
                 relation.relacl,
                 acldefault('r', relation.relowner)
               )) AS privilege
              WHERE privilege.privilege_type = 'INSERT'
                AND privilege.grantee NOT IN (
                  control_owner_oid,
                  authority_writer_oid
                )
           )
     )
     OR NOT EXISTS (
       SELECT 1 FROM pg_catalog.pg_proc AS helper
        WHERE helper.oid = helper_oid
          AND helper.proowner = control_owner_oid
          AND helper.prosecdef
          AND helper.proconfig = ARRAY[
            'search_path=pg_catalog, proof_harness_runtime'
          ]::text[]
          AND EXISTS (
            SELECT 1
              FROM aclexplode(COALESCE(
                helper.proacl,
                acldefault('f', helper.proowner)
              )) AS privilege
             WHERE privilege.privilege_type = 'EXECUTE'
               AND privilege.grantee = authority_writer_oid
               AND NOT privilege.is_grantable
          )
          AND NOT EXISTS (
            SELECT 1
              FROM aclexplode(COALESCE(
                helper.proacl,
                acldefault('f', helper.proowner)
              )) AS privilege
             WHERE privilege.privilege_type = 'EXECUTE'
               AND privilege.grantee NOT IN (
                 control_owner_oid,
                 authority_writer_oid
               )
          )
     ) THEN
    RAISE EXCEPTION 'subagent consume requires the independent authority writer'
      USING ERRCODE = '42501';
  END IF;
  IF p_tenant_id IS DISTINCT FROM current_setting('app.tenant_id', true)
     OR p_project_id IS DISTINCT FROM current_setting('app.project_id', true)
     OR p_actor_id IS DISTINCT FROM current_setting('app.actor_id', true)
     OR p_run_id IS DISTINCT FROM current_setting('app.run_id', true)
     OR p_execution_epoch::text IS DISTINCT FROM current_setting('app.execution_epoch', true)
     OR p_fencing_generation::text IS DISTINCT FROM current_setting('app.fencing_generation', true)
     OR p_authority_revision IS DISTINCT FROM current_setting('app.authority_revision', true)
     OR p_revision_set_id IS DISTINCT FROM current_setting('app.revision_set_id', true) THEN
    RAISE EXCEPTION 'subagent consume scope differs from trusted transaction scope'
      USING ERRCODE = '42501';
  END IF;

  SELECT * INTO claim
    FROM proof_harness_runtime.runtime_assurance_invocation_receipts AS candidate
   WHERE candidate.tenant_id = p_tenant_id
     AND candidate.project_id = p_project_id
     AND candidate.actor_id = p_actor_id
     AND candidate.run_id = p_run_id
     AND candidate.execution_epoch = p_execution_epoch
     AND candidate.fencing_generation = p_fencing_generation
     AND candidate.authority_revision = p_authority_revision
     AND candidate.revision_set_id = p_revision_set_id
     AND candidate.invocation_id = p_invocation_id
     AND candidate.state = 'IN_PROGRESS'
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'subagent consume requires an active operation claim'
      USING ERRCODE = '55000';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_locks AS held
     WHERE held.locktype = 'advisory'
       AND held.mode = 'ExclusiveLock'
       AND held.database = (SELECT oid FROM pg_catalog.pg_database
                             WHERE datname = current_database())
       AND held.pid = claim.claim_backend_pid
       AND held.classid = (((claim.claim_lock_key >> 32) & 4294967295)::oid)
       AND held.objid = ((claim.claim_lock_key & 4294967295)::oid)
       AND held.objsubid = 1
       AND held.granted
  ) THEN
    RAISE EXCEPTION 'subagent consume claim session lock is no longer live'
      USING ERRCODE = '55000';
  END IF;

  SELECT * INTO reservation
    FROM proof_harness_runtime.subagent_budget_reservation_bindings AS candidate
   WHERE candidate.tenant_id = p_tenant_id
     AND candidate.project_id = p_project_id
     AND candidate.actor_id = p_actor_id
     AND candidate.run_id = p_run_id
     AND candidate.execution_epoch = p_execution_epoch
     AND candidate.fencing_generation = p_fencing_generation
     AND candidate.authority_revision = p_authority_revision
     AND candidate.revision_set_id = p_revision_set_id
     AND candidate.reservation_id = p_reservation_id
     AND candidate.operation_invocation_id = p_invocation_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'subagent budget reservation was not found'
      USING ERRCODE = 'P0002';
  END IF;

  SELECT * INTO spec
    FROM proof_harness_runtime.subagent_execution_specs AS candidate
   WHERE candidate.tenant_id = p_tenant_id
     AND candidate.project_id = p_project_id
     AND candidate.actor_id = p_actor_id
     AND candidate.run_id = p_run_id
     AND candidate.execution_epoch = p_execution_epoch
     AND candidate.fencing_generation = p_fencing_generation
     AND candidate.authority_revision = p_authority_revision
     AND candidate.revision_set_id = p_revision_set_id
     AND candidate.invocation_id = p_invocation_id
     AND candidate.budget_reservation_id = p_reservation_id
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'subagent execution specification was not found'
      USING ERRCODE = 'P0002';
  END IF;

  IF spec.spec_hash IS DISTINCT FROM p_expected_spec_hash
     OR reservation.authority_envelope_digest IS DISTINCT FROM
       p_expected_authority_envelope_digest THEN
    RAISE EXCEPTION 'subagent consume binding differs from its signed reservation'
      USING ERRCODE = '55000';
  END IF;

  -- Construct the repository canonical JSON bytes inside the trusted
  -- function.  jsonb semantic equality alone is insufficient because an
  -- attacker-controlled whitespace/key-order variant would otherwise let a
  -- digest describe bytes different from the persisted JSONB value.
  expected_payload_json :=
    '{"authority_revision":' || to_jsonb(p_authority_revision)::text ||
    ',"detail":{"authority_envelope_digest":' ||
      to_jsonb(reservation.authority_envelope_digest)::text ||
    ',"budget_reservation_id":' || to_jsonb(p_reservation_id)::text ||
    ',"consumer_execution_id":' || to_jsonb(p_consumer_execution_id)::text ||
    ',"cost_budget":' || to_jsonb(spec.cost_budget::text)::text ||
    ',"invocation_id":' || to_jsonb(p_invocation_id)::text ||
    ',"max_output_tokens":' || spec.max_output_tokens::text ||
    ',"spec_hash":' || to_jsonb(spec.spec_hash)::text ||
    '},"execution_epoch":' || p_execution_epoch::text ||
    ',"fencing_generation":' || p_fencing_generation::text ||
    ',"revision_set_id":' || to_jsonb(p_revision_set_id)::text ||
    ',"run_id":' || to_jsonb(p_run_id)::text || '}';
  expected_payload := expected_payload_json::jsonb;
  expected_payload_sha256 := 'sha256:' || encode(
    sha256(
      convert_to('elmos.proof-harness.v1', 'UTF8') || decode('00', 'hex') ||
      convert_to('event-payload', 'UTF8') || decode('00', 'hex') ||
      convert_to(expected_payload_json, 'UTF8')
    ),
    'hex'
  );
  IF p_payload_json IS DISTINCT FROM expected_payload_json
     OR p_payload_sha256 IS DISTINCT FROM expected_payload_sha256
     OR p_event_id !~ '^evt-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'subagent consume audit identity, bytes, or digest is invalid'
      USING ERRCODE = '22023';
  END IF;

  IF reservation.state = 'CONSUMED' AND spec.state = 'CONSUMED' THEN
    IF spec.consumer_execution_id IS DISTINCT FROM p_consumer_execution_id
       OR reservation.consumer_execution_id IS DISTINCT FROM p_consumer_execution_id
       OR reservation.consume_event_id IS DISTINCT FROM p_event_id
       OR reservation.consume_payload_sha256 IS DISTINCT FROM p_payload_sha256
       OR reservation.consumed_at IS DISTINCT FROM p_consumed_at THEN
      RAISE EXCEPTION 'subagent reservation was consumed by another execution'
        USING ERRCODE = '55000';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.audit_events AS audit
       WHERE audit.tenant_id = p_tenant_id
         AND audit.project_id = p_project_id
         AND audit.event_id = p_event_id
         AND audit.actor_id = p_actor_id
         AND audit.event_type = 'SUBAGENT_EXECUTION_SPEC_CONSUMED'
         AND audit.subject_id = p_invocation_id
         AND audit.payload_json = expected_payload
         AND audit.payload_sha256 = expected_payload_sha256
         AND audit.created_at = p_consumed_at
    ) OR NOT EXISTS (
      SELECT 1 FROM proof_harness_runtime.outbox_events AS event
       WHERE event.tenant_id = p_tenant_id
         AND event.project_id = p_project_id
         AND event.event_id = p_event_id
         AND event.topic = 'proof-harness.subagent_execution_spec_consumed'
         AND event.aggregate_id = p_invocation_id
         AND event.payload_json = expected_payload
         AND event.payload_sha256 = expected_payload_sha256
         AND event.created_at = p_consumed_at
    ) THEN
      RAISE EXCEPTION 'subagent consume replay evidence is missing or drifted'
        USING ERRCODE = '55000';
    END IF;
    RETURN QUERY SELECT true;
    RETURN;
  END IF;
  IF reservation.state <> 'RESERVED' OR spec.state <> 'RESERVED'
     OR reservation.consumed_at IS NOT NULL
     OR spec.consumer_execution_id IS NOT NULL OR spec.consumed_at IS NOT NULL THEN
    RAISE EXCEPTION 'subagent reservation and specification states diverged'
      USING ERRCODE = '55000';
  END IF;
  IF p_consumed_at >= reservation.wall_clock_deadline
     OR p_consumed_at >= spec.wall_clock_deadline
     OR clock_timestamp() >= reservation.wall_clock_deadline
     OR clock_timestamp() >= spec.wall_clock_deadline THEN
    RAISE EXCEPTION 'subagent budget reservation deadline has expired'
      USING ERRCODE = '55000';
  END IF;

  UPDATE proof_harness_runtime.subagent_budget_reservation_bindings
     SET state = 'CONSUMED', consumed_at = p_consumed_at,
         consumer_execution_id = p_consumer_execution_id,
         consume_event_id = p_event_id,
         consume_payload_sha256 = p_payload_sha256,
         updated_at = p_consumed_at
   WHERE tenant_id = p_tenant_id AND project_id = p_project_id
     AND actor_id = p_actor_id AND run_id = p_run_id
     AND execution_epoch = p_execution_epoch
     AND fencing_generation = p_fencing_generation
     AND authority_revision = p_authority_revision
     AND revision_set_id = p_revision_set_id
     AND reservation_id = p_reservation_id
     AND operation_invocation_id = p_invocation_id
     AND state = 'RESERVED';
  GET DIAGNOSTICS reservation_updated = ROW_COUNT;

  UPDATE proof_harness_runtime.subagent_execution_specs
     SET state = 'CONSUMED', consumer_execution_id = p_consumer_execution_id,
         consumed_at = p_consumed_at, updated_at = p_consumed_at
   WHERE tenant_id = p_tenant_id AND project_id = p_project_id
     AND actor_id = p_actor_id AND run_id = p_run_id
     AND execution_epoch = p_execution_epoch
     AND fencing_generation = p_fencing_generation
     AND authority_revision = p_authority_revision
     AND revision_set_id = p_revision_set_id
     AND invocation_id = p_invocation_id
     AND budget_reservation_id = p_reservation_id
     AND state = 'RESERVED';
  GET DIAGNOSTICS spec_updated = ROW_COUNT;
  IF reservation_updated <> 1 OR spec_updated <> 1 THEN
    RAISE EXCEPTION 'subagent reservation atomic consume compare-and-swap failed'
      USING ERRCODE = '40001';
  END IF;

  INSERT INTO proof_harness_runtime.audit_events(
    tenant_id, project_id, event_id, actor_id, event_type, subject_id,
    payload_json, payload_sha256, created_at
  ) VALUES (
    p_tenant_id, p_project_id, p_event_id, p_actor_id,
    'SUBAGENT_EXECUTION_SPEC_CONSUMED', p_invocation_id,
    expected_payload, expected_payload_sha256, p_consumed_at
  );
  INSERT INTO proof_harness_runtime.outbox_events(
    tenant_id, project_id, event_id, topic, aggregate_id,
    payload_json, payload_sha256, created_at
  ) VALUES (
    p_tenant_id, p_project_id, p_event_id,
    'proof-harness.subagent_execution_spec_consumed', p_invocation_id,
    expected_payload, expected_payload_sha256, p_consumed_at
  );

  RETURN QUERY SELECT false;
END
$consume_subagent_reservation_and_spec$;

CREATE TRIGGER tool_result_commits_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.tool_result_commits
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER step_execution_plans_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.step_execution_plans
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER step_plan_tool_bindings_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.step_plan_tool_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER pending_tool_call_bindings_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.pending_tool_call_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER runtime_authority_capability_receipts_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.runtime_authority_capability_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER subagent_budget_reservation_bindings_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.subagent_budget_reservation_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER capability_leases_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.capability_leases
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER executor_generations_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.executor_generations
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER environment_attachments_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.environment_attachments
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER executor_replacement_effects_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.executor_replacement_effects
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER workspace_leases_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.workspace_leases
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER durable_event_registrations_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.durable_event_registrations
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER durable_event_instances_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.durable_event_instances
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER typed_ingress_records_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.typed_ingress_records
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER subagent_execution_specs_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.subagent_execution_specs
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();
CREATE TRIGGER runtime_assurance_invocation_receipts_scope_guard
BEFORE INSERT OR UPDATE ON proof_harness_runtime.runtime_assurance_invocation_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.assert_runtime_assurance_scope();

CREATE TRIGGER tool_result_commits_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.tool_result_commits
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_tool_result_commit();
CREATE TRIGGER step_execution_plans_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.step_execution_plans
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_step_execution_plan();
CREATE TRIGGER step_plan_tool_bindings_immutable
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.step_plan_tool_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_step_plan_tool_binding();
CREATE TRIGGER pending_tool_call_bindings_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.pending_tool_call_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_pending_tool_call_binding();
CREATE TRIGGER runtime_authority_capability_receipts_immutable
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.runtime_authority_capability_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_runtime_authority_capability_receipt();
CREATE TRIGGER subagent_budget_reservation_bindings_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.subagent_budget_reservation_bindings
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_subagent_budget_reservation();
CREATE TRIGGER capability_leases_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.capability_leases
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_capability_lease();
CREATE TRIGGER executor_generations_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.executor_generations
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_executor_generation();
CREATE TRIGGER environment_attachments_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.environment_attachments
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_environment_attachment();
CREATE TRIGGER executor_replacement_effects_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.executor_replacement_effects
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_executor_replacement_effect();
CREATE TRIGGER workspace_leases_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.workspace_leases
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_workspace_lease();
CREATE TRIGGER durable_event_registrations_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.durable_event_registrations
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER durable_event_instances_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.durable_event_instances
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_durable_event_instance();
CREATE TRIGGER typed_ingress_records_immutable
BEFORE UPDATE OR DELETE ON proof_harness_runtime.typed_ingress_records
FOR EACH ROW EXECUTE FUNCTION proof_harness.reject_immutable_mutation();
CREATE TRIGGER subagent_execution_specs_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.subagent_execution_specs
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_subagent_execution_spec();
CREATE TRIGGER runtime_assurance_invocation_receipts_lifecycle_guard
BEFORE INSERT OR UPDATE OR DELETE ON proof_harness_runtime.runtime_assurance_invocation_receipts
FOR EACH ROW EXECUTE FUNCTION proof_harness_runtime.guard_runtime_assurance_invocation_receipt();

DO $runtime_assurance_rls$
DECLARE
  relation_name text;
BEGIN
  FOREACH relation_name IN ARRAY ARRAY[
    'tool_result_commits',
    'step_execution_plans',
    'step_plan_tool_bindings',
    'pending_tool_call_bindings',
    'runtime_authority_capability_receipts',
    'subagent_budget_reservation_bindings',
    'capability_leases',
    'executor_generations',
    'environment_attachments',
    'executor_replacement_effects',
    'workspace_leases',
    'durable_event_registrations',
    'durable_event_instances',
    'typed_ingress_records',
    'subagent_execution_specs',
    'runtime_assurance_invocation_receipts'
  ] LOOP
    EXECUTE format(
      'ALTER TABLE proof_harness_runtime.%I ENABLE ROW LEVEL SECURITY',
      relation_name
    );
    EXECUTE format(
      'ALTER TABLE proof_harness_runtime.%I FORCE ROW LEVEL SECURITY',
      relation_name
    );
    EXECUTE format(
      'CREATE POLICY runtime_assurance_trusted_scope_isolation ON '
      'proof_harness_runtime.%I USING ('
      'tenant_id = proof_harness.current_tenant_key() AND '
      'project_id = proof_harness.current_project_key() AND '
      'actor_id = current_setting(''app.actor_id'', true) AND '
      'run_id = current_setting(''app.run_id'', true) AND '
      'execution_epoch::text = current_setting(''app.execution_epoch'', true) AND '
      'fencing_generation::text = current_setting(''app.fencing_generation'', true) AND '
      'authority_revision = current_setting(''app.authority_revision'', true) AND '
      'revision_set_id = current_setting(''app.revision_set_id'', true)) WITH CHECK ('
      'tenant_id = proof_harness.current_tenant_key() AND '
      'project_id = proof_harness.current_project_key() AND '
      'actor_id = current_setting(''app.actor_id'', true) AND '
      'run_id = current_setting(''app.run_id'', true) AND '
      'execution_epoch::text = current_setting(''app.execution_epoch'', true) AND '
      'fencing_generation::text = current_setting(''app.fencing_generation'', true) AND '
      'authority_revision = current_setting(''app.authority_revision'', true) AND '
      'revision_set_id = current_setting(''app.revision_set_id'', true))',
      relation_name
    );
  END LOOP;
END
$runtime_assurance_rls$;

REVOKE ALL ON proof_harness_runtime.runtime_assurance_migrations FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.runtime_assurance_migration_digest_ledger FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.tool_result_commits FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.step_execution_plans FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.step_plan_tool_bindings FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.pending_tool_call_bindings FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.runtime_authority_capability_receipts FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.subagent_budget_reservation_bindings FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.capability_leases FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.executor_generations FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.environment_attachments FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.executor_replacement_effects FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.workspace_leases FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.durable_event_registrations FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.durable_event_instances FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.typed_ingress_records FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.subagent_execution_specs FROM PUBLIC;
REVOKE ALL ON proof_harness_runtime.runtime_assurance_invocation_receipts FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.is_bounded_text_array(jsonb, integer, integer)
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.is_valid_interceptor_chain(jsonb)
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.is_valid_workspace_scopes(jsonb)
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.canonical_jsonb_text(jsonb)
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.append_runtime_assurance_event(
  text, text, text, text, text, jsonb, timestamptz
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.runtime_assurance_event_is_exact(
  text, text, text, text, text, text, text, jsonb, timestamptz
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.is_live_runtime_assurance_claim(
  text, text, text, text, bigint, bigint, text, text, text, boolean
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.assert_runtime_application_writer(oid)
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.claim_runtime_assurance_invocation(
  text, text, text, text, bigint, bigint, text, text, text, text, bigint,
  timestamptz
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.complete_runtime_assurance_invocation(
  text, text, text, text, bigint, bigint, text, text, text, text, bigint,
  text, text, timestamptz
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.reconcile_runtime_assurance_invocation(
  text, text, text, text, bigint, bigint, text, text, text, text, bigint,
  text, text, text, timestamptz
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_runtime_run_actor_identity()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.assert_runtime_assurance_scope()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_tool_result_commit() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_step_execution_plan() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_step_plan_tool_binding()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_runtime_authority_capability_receipt()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_pending_tool_call_binding()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_subagent_budget_reservation()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_capability_lease() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_executor_generation() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_environment_attachment() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_executor_replacement_effect() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_workspace_lease() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_runtime_assurance_invocation_receipt()
  FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_durable_event_instance() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.guard_subagent_execution_spec() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION proof_harness_runtime.consume_subagent_reservation_and_spec(
  text, text, text, text, bigint, bigint, text, text, text, text, text,
  text, text, timestamptz, text, text, text
) FROM PUBLIC;
