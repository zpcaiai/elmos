-- ELMOS V77.2: generation-bound task analytics projection publication.
--
-- Source events and financial facts remain immutable.  A rebuild writes a new
-- content-addressed generation and atomically advances one account-scoped head;
-- readers never observe a half-published generation.  Local checksums are
-- engineering integrity only: external evidence remains NOT_RUN and production
-- certification remains NOT_CERTIFIED.

CREATE TABLE task_finops_projection_rebuilds (
    rebuild_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    event_count bigint NOT NULL CHECK (event_count >= 0),
    fact_count bigint NOT NULL CHECK (fact_count >= 0),
    run_count bigint NOT NULL CHECK (run_count >= 0),
    bucket_count bigint NOT NULL CHECK (bucket_count >= 0),
    journal_checksum char(64) NOT NULL CHECK (journal_checksum ~ '^[0-9a-f]{64}$'),
    hourly_checksum char(64) NOT NULL CHECK (hourly_checksum ~ '^[0-9a-f]{64}$'),
    daily_checksum char(64) NOT NULL CHECK (daily_checksum ~ '^[0-9a-f]{64}$'),
    run_payload_digest char(64) NOT NULL CHECK (run_payload_digest ~ '^[0-9a-f]{64}$'),
    bucket_payload_digest char(64) NOT NULL CHECK (bucket_payload_digest ~ '^[0-9a-f]{64}$'),
    storage_payload_digest char(64) NOT NULL CHECK (storage_payload_digest ~ '^[0-9a-f]{64}$'),
    source_as_of timestamptz NOT NULL,
    input_continuity varchar(24) NOT NULL CHECK (input_continuity IN ('COMPLETE', 'UNKNOWN')),
    external_evidence_state varchar(24) NOT NULL DEFAULT 'NOT_RUN'
        CHECK (external_evidence_state = 'NOT_RUN'),
    provider_outcome varchar(24) NOT NULL DEFAULT 'UNKNOWN'
        CHECK (provider_outcome = 'UNKNOWN'),
    production_certification varchar(24) NOT NULL DEFAULT 'NOT_CERTIFIED'
        CHECK (production_certification = 'NOT_CERTIFIED'),
    request_digest char(64) NOT NULL CHECK (request_digest ~ '^[0-9a-f]{64}$'),
    idempotency_key varchar(160) NOT NULL,
    published_by_actor_id varchar(128) NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    expected_generation bigint NOT NULL CHECK (expected_generation >= 0),
    generation_version bigint NOT NULL CHECK (generation_version >= 1),
    UNIQUE (organization_id, account_id, idempotency_key),
    UNIQUE (rebuild_id, organization_id, account_id),
    UNIQUE (rebuild_id, organization_id, account_id, generation_version),
    CONSTRAINT task_finops_rebuild_generation_step CHECK (
        generation_version = expected_generation + 1
    ),
    CONSTRAINT task_finops_rebuild_window CHECK (
        window_end > window_start
        AND window_end <= window_start + interval '366 days'
    )
);

CREATE TRIGGER task_finops_projection_rebuilds_append_only
BEFORE UPDATE OR DELETE ON task_finops_projection_rebuilds
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_finops_run_projections (
    rebuild_id varchar(96) NOT NULL REFERENCES task_finops_projection_rebuilds(rebuild_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    task_id varchar(96) NOT NULL,
    run_number bigint NOT NULL CHECK (run_number >= 1),
    task_state varchar(24) NOT NULL CHECK (task_state IN (
        'WAITING_FOR_SLOT', 'ADMITTED', 'RUNNING', 'PAUSE_REQUESTED',
        'PAUSED', 'RESUME_REQUESTED', 'UNKNOWN_RESULT', 'RECONCILING',
        'SUCCEEDED', 'FAILED', 'CANCELLED'
    )),
    progress_percent smallint NOT NULL CHECK (progress_percent BETWEEN 0 AND 100),
    last_event_sequence bigint NOT NULL CHECK (last_event_sequence >= 1),
    last_occurred_at timestamptz NOT NULL,
    run_checksum char(64) NOT NULL CHECK (run_checksum ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (rebuild_id, task_id, run_number),
    CONSTRAINT task_finops_run_rebuild_scope_fk
        FOREIGN KEY (rebuild_id, organization_id, account_id)
        REFERENCES task_finops_projection_rebuilds(
            rebuild_id, organization_id, account_id),
    CONSTRAINT task_finops_run_progress_state CHECK (
        (task_state = 'SUCCEEDED' AND progress_percent = 100)
        OR (task_state <> 'SUCCEEDED' AND progress_percent < 100)
    )
);

CREATE TRIGGER task_finops_run_projections_append_only
BEFORE UPDATE OR DELETE ON task_finops_run_projections
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_finops_aggregate_buckets (
    rebuild_id varchar(96) NOT NULL REFERENCES task_finops_projection_rebuilds(rebuild_id),
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    grain varchar(8) NOT NULL CHECK (grain IN ('HOUR', 'DAY')),
    task_id varchar(96) NOT NULL,
    run_number bigint NOT NULL CHECK (run_number >= 1),
    workload_class varchar(32) NOT NULL CHECK (workload_class IN (
        'PARSING', 'GENERATION', 'CONVERSION', 'VALIDATION', 'RENDERING', 'MODEL_GPU'
    )),
    bucket_start timestamptz NOT NULL,
    bucket_end timestamptz NOT NULL,
    currency char(3) NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    allocation_basis varchar(32) NOT NULL CHECK (allocation_basis IN (
        'DIRECT_TASK', 'DIRECT_PROJECT', 'MILESTONE', 'USAGE',
        'SUBSCRIPTION_POLICY', 'MANUAL_APPROVED'
    )),
    cost_delta_minor numeric(30,6) NOT NULL,
    revenue_delta_minor numeric(30,6) NOT NULL,
    gross_delta_minor numeric(30,6) NOT NULL,
    fact_count bigint NOT NULL CHECK (fact_count >= 1),
    completeness varchar(24) NOT NULL CHECK (completeness IN ('COMPLETE', 'PARTIAL', 'UNKNOWN')),
    reconciliation_status varchar(24) NOT NULL CHECK (
        reconciliation_status IN ('PENDING', 'RECONCILED', 'REJECTED', 'UNKNOWN', 'INCONCLUSIVE')
    ),
    PRIMARY KEY (
        rebuild_id, grain, task_id, run_number, workload_class,
        bucket_start, currency, allocation_basis
    ),
    CONSTRAINT task_finops_bucket_rebuild_scope_fk
        FOREIGN KEY (rebuild_id, organization_id, account_id)
        REFERENCES task_finops_projection_rebuilds(
            rebuild_id, organization_id, account_id),
    CONSTRAINT task_finops_aggregate_window CHECK (
        (grain = 'HOUR'
            AND bucket_start = date_trunc('hour', bucket_start, 'UTC')
            AND bucket_end = bucket_start + interval '1 hour')
        OR (grain = 'DAY'
            AND bucket_start = date_trunc('day', bucket_start, 'UTC')
            AND bucket_end = bucket_start + interval '1 day')
    ),
    CONSTRAINT task_finops_aggregate_conservation CHECK (
        gross_delta_minor = revenue_delta_minor - cost_delta_minor
    )
);

CREATE TRIGGER task_finops_aggregate_buckets_append_only
BEFORE UPDATE OR DELETE ON task_finops_aggregate_buckets
FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation();

CREATE TABLE task_finops_projection_heads (
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    account_id varchar(96) NOT NULL REFERENCES accounts(account_id),
    rebuild_id varchar(96) NOT NULL,
    generation_version bigint NOT NULL CHECK (generation_version >= 1),
    advanced_by_actor_id varchar(128) NOT NULL,
    advanced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, account_id),
    CONSTRAINT task_finops_projection_head_exact_generation_fk
        FOREIGN KEY (rebuild_id, organization_id, account_id, generation_version)
        REFERENCES task_finops_projection_rebuilds (
            rebuild_id, organization_id, account_id, generation_version
        )
);

DO $$
DECLARE v_table text;
BEGIN
    FOREACH v_table IN ARRAY ARRAY[
        'task_finops_projection_rebuilds',
        'task_finops_run_projections',
        'task_finops_aggregate_buckets',
        'task_finops_projection_heads'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', v_table);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', v_table);
        EXECUTE format(
            'CREATE POLICY %I ON %I ' ||
            'USING (elmos_mtf_context_matches(organization_id, account_id)) ' ||
            'WITH CHECK (elmos_mtf_context_matches(organization_id, account_id))',
            v_table || '_scope', v_table);
        EXECUTE format('REVOKE ALL ON %I FROM PUBLIC', v_table);
    END LOOP;
END;
$$;

-- Exact, account-bound source views for the Java reducer.  Request code can
-- bound time and row count but cannot select a different tenant in payload.
CREATE VIEW mtf_task_journal_for_rebuild AS
SELECT event.organization_id, event.account_id, event.job_id AS task_id,
       event.run_number::bigint, event.sequence_no::bigint AS event_sequence,
       event.job_event_id AS event_id,
       CASE
           WHEN event.to_status IN ('WAITING_FOR_SLOT', 'QUEUED') THEN 'WAITING_FOR_SLOT'
           WHEN event.to_status IN ('ADMITTED', 'CLAIMED') THEN 'ADMITTED'
           WHEN event.to_status = 'RUNNING' THEN 'RUNNING'
           WHEN event.to_status = 'PAUSE_REQUESTED' THEN 'PAUSE_REQUESTED'
           WHEN event.to_status = 'PAUSED' THEN 'PAUSED'
           WHEN event.to_status = 'RESUME_REQUESTED' THEN 'RESUME_REQUESTED'
           WHEN event.to_status = 'UNKNOWN_RESULT' THEN 'UNKNOWN_RESULT'
           WHEN event.to_status = 'RECONCILING' THEN 'RECONCILING'
           WHEN event.to_status = 'SUCCEEDED' THEN 'SUCCEEDED'
           WHEN event.to_status IN ('PARTIAL', 'FAILED', 'LOST') THEN 'FAILED'
           WHEN event.to_status = 'CANCELLED' THEN 'CANCELLED'
           ELSE CASE
               WHEN job.status = 'QUEUED' THEN 'WAITING_FOR_SLOT'
               WHEN job.status = 'CLAIMED' THEN 'ADMITTED'
               WHEN job.status IN ('PARTIAL', 'LOST') THEN 'FAILED'
               ELSE job.status
           END
       END::varchar AS task_state,
       CASE WHEN coalesce(event.to_status, job.status) = 'SUCCEEDED' THEN 100
            ELSE least(coalesce(event.progress, job.progress), 99) END::smallint
            AS progress_percent,
       event.occurred_at
  FROM execution_job_events event
 JOIN execution_jobs job ON job.job_id = event.job_id
 WHERE elmos_mtf_context_matches(event.organization_id, event.account_id)
   AND job.tenant_tombstoned_at IS NULL
   AND event.run_number IS NOT NULL;

CREATE VIEW mtf_task_financial_facts_for_rebuild AS
SELECT usage.organization_id, usage.account_id, usage.job_id AS task_id,
       usage.run_number::bigint, usage.usage_event_id AS fact_id,
       job.workload_class, usage.base_currency AS currency,
       'DIRECT_TASK'::varchar AS allocation_basis,
       usage.base_cost_minor::numeric(30,6) AS cost_delta_minor,
       0::numeric(30,6) AS revenue_delta_minor,
       usage.occurred_at,
       CASE
           WHEN usage.reconciliation_status = 'RECONCILED' THEN 'COMPLETE'
           WHEN usage.reconciliation_status IN ('UNKNOWN', 'INCONCLUSIVE') THEN 'UNKNOWN'
           ELSE 'PARTIAL' END::varchar AS completeness,
       usage.reconciliation_status
  FROM usage_events usage
 JOIN execution_jobs job ON job.job_id = usage.job_id
 WHERE elmos_mtf_context_matches(usage.organization_id, usage.account_id)
   AND job.tenant_tombstoned_at IS NULL
   AND usage.job_id IS NOT NULL
   AND usage.run_number IS NOT NULL
   AND job.workload_class IS NOT NULL
UNION ALL
SELECT revenue.organization_id, revenue.account_id, revenue.job_id AS task_id,
       revenue.run_number::bigint, revenue.revenue_entry_id AS fact_id,
       job.workload_class, revenue.currency,
       coalesce((
           SELECT allocation.allocation_basis
             FROM task_revenue_allocations allocation
            WHERE allocation.revenue_entry_id = revenue.revenue_entry_id
            ORDER BY allocation.effective_at, allocation.revenue_allocation_id
            LIMIT 1
       ), 'DIRECT_TASK')::varchar AS allocation_basis,
       0::numeric(30,6) AS cost_delta_minor,
       revenue.amount_minor::numeric(30,6) AS revenue_delta_minor,
       revenue.effective_at AS occurred_at,
       CASE
           WHEN revenue.reconciliation_status = 'RECONCILED' THEN 'COMPLETE'
           WHEN revenue.reconciliation_status IN ('UNKNOWN', 'INCONCLUSIVE') THEN 'UNKNOWN'
           ELSE 'PARTIAL' END::varchar AS completeness,
       revenue.reconciliation_status
  FROM task_revenue_ledger_entries revenue
 JOIN execution_jobs job ON job.job_id = revenue.job_id
 WHERE elmos_mtf_context_matches(revenue.organization_id, revenue.account_id)
   AND job.tenant_tombstoned_at IS NULL
   AND job.workload_class IS NOT NULL;

CREATE OR REPLACE FUNCTION elmos_mtf_publish_analytics_projection(
    p_rebuild_id varchar,
    p_window_start timestamptz,
    p_window_end timestamptz,
    p_expected_generation bigint,
    p_event_count bigint,
    p_fact_count bigint,
    p_journal_checksum varchar,
    p_hourly_checksum varchar,
    p_daily_checksum varchar,
    p_source_as_of timestamptz,
    p_input_continuity varchar,
    p_runs jsonb,
    p_buckets jsonb,
    p_idempotency_key varchar,
    p_request_digest varchar
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
SET row_security = on
AS $$
DECLARE
    v_existing task_finops_projection_rebuilds%ROWTYPE;
    v_head task_finops_projection_heads%ROWTYPE;
    v_organization_id varchar(96);
    v_account_id varchar(96);
    v_actor_id varchar(128);
    v_run_payload_digest varchar(64);
    v_bucket_payload_digest varchar(64);
    v_payload_digest varchar(64);
    v_generation bigint;
    v_run_count bigint;
    v_bucket_count bigint;
BEGIN
    PERFORM elmos_mtf_require_member_role(ARRAY['OWNER', 'ADMIN', 'MAINTAINER']);
    SELECT elmos_mtf_bound_organization_id(), elmos_mtf_bound_account_id(),
           nullif(current_setting('app.actor_id', true), '')
      INTO v_organization_id, v_account_id, v_actor_id;
    IF v_organization_id IS NULL OR v_account_id IS NULL OR v_actor_id IS NULL
       OR NOT elmos_mtf_context_matches(v_organization_id, v_account_id) THEN
        RAISE EXCEPTION 'ELMOS_MTF_IDENTITY_CONTEXT_INVALID';
    END IF;

    IF p_rebuild_id IS NULL OR length(p_rebuild_id) NOT BETWEEN 1 AND 96
       OR p_window_start IS NULL OR p_window_end IS NULL
       OR p_window_end <= p_window_start
       OR p_window_end > p_window_start + interval '366 days'
       OR p_expected_generation IS NULL OR p_expected_generation < 0
       OR p_event_count IS NULL OR p_event_count < 1 OR p_event_count > 10000
       OR p_fact_count IS NULL OR p_fact_count < 0 OR p_fact_count > 10000
       OR p_journal_checksum IS NULL OR p_journal_checksum !~ '^[0-9a-f]{64}$'
       OR p_hourly_checksum IS NULL OR p_hourly_checksum !~ '^[0-9a-f]{64}$'
       OR p_daily_checksum IS NULL OR p_daily_checksum !~ '^[0-9a-f]{64}$'
       OR p_source_as_of IS NULL OR p_source_as_of >= p_window_end
       OR p_input_continuity IS NULL
       OR p_input_continuity NOT IN ('COMPLETE', 'UNKNOWN')
       OR p_runs IS NULL OR p_buckets IS NULL
       OR jsonb_typeof(p_runs) <> 'array' OR jsonb_typeof(p_buckets) <> 'array'
       OR jsonb_array_length(p_runs) > 10000
       OR jsonb_array_length(p_buckets) > 50000
       OR p_idempotency_key IS NULL
       OR length(p_idempotency_key) NOT BETWEEN 1 AND 160
       OR p_request_digest IS NULL OR p_request_digest !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_PUBLICATION_INVALID';
    END IF;
    IF p_input_continuity <> 'COMPLETE' THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_CONTINUITY_INCOMPLETE';
    END IF;

    v_run_count := jsonb_array_length(p_runs);
    v_bucket_count := jsonb_array_length(p_buckets);
    IF v_run_count < 1 THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_CONTINUITY_INCOMPLETE';
    END IF;
    v_run_payload_digest := encode(sha256(convert_to(p_runs::text, 'UTF8')), 'hex');
    v_bucket_payload_digest := encode(sha256(convert_to(p_buckets::text, 'UTF8')), 'hex');
    v_payload_digest := encode(sha256(convert_to(jsonb_build_object(
        'schema', 'elmos.task-finops.analytics.v2',
        'run_count', v_run_count,
        'run_payload_digest', v_run_payload_digest,
        'bucket_count', v_bucket_count,
        'bucket_payload_digest', v_bucket_payload_digest
    )::text, 'UTF8')), 'hex');

    -- Serialize the idempotency lookup with head advancement.  The trusted
    -- context helpers, rather than request payload or mutable GUC values,
    -- select the account-scoped lock domain.
    PERFORM pg_advisory_xact_lock(hashtextextended(jsonb_build_array(
        v_organization_id, v_account_id, 'ANALYTICS_PROJECTION_HEAD'
    )::text, 7721));
    SELECT * INTO v_existing FROM task_finops_projection_rebuilds
     WHERE organization_id = v_organization_id
       AND account_id = v_account_id
       AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.rebuild_id IS DISTINCT FROM p_rebuild_id
           OR v_existing.request_digest IS DISTINCT FROM p_request_digest::char(64)
           OR v_existing.window_start IS DISTINCT FROM p_window_start
           OR v_existing.window_end IS DISTINCT FROM p_window_end
           OR v_existing.event_count IS DISTINCT FROM p_event_count
           OR v_existing.fact_count IS DISTINCT FROM p_fact_count
           OR v_existing.expected_generation IS DISTINCT FROM p_expected_generation
           OR v_existing.run_count IS DISTINCT FROM v_run_count
           OR v_existing.bucket_count IS DISTINCT FROM v_bucket_count
           OR v_existing.journal_checksum IS DISTINCT FROM p_journal_checksum::char(64)
           OR v_existing.hourly_checksum IS DISTINCT FROM p_hourly_checksum::char(64)
           OR v_existing.daily_checksum IS DISTINCT FROM p_daily_checksum::char(64)
           OR v_existing.run_payload_digest IS DISTINCT FROM v_run_payload_digest::char(64)
           OR v_existing.bucket_payload_digest IS DISTINCT FROM v_bucket_payload_digest::char(64)
           OR v_existing.storage_payload_digest IS DISTINCT FROM v_payload_digest::char(64)
           OR v_existing.source_as_of IS DISTINCT FROM p_source_as_of
           OR v_existing.input_continuity IS DISTINCT FROM p_input_continuity THEN
            RAISE EXCEPTION 'ELMOS_MTF_IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_existing.generation_version;
    END IF;

    SELECT * INTO v_head FROM task_finops_projection_heads
     WHERE organization_id = v_organization_id
       AND account_id = v_account_id
     FOR UPDATE;
    IF coalesce(v_head.generation_version, 0) <> p_expected_generation THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_GENERATION_CONFLICT';
    END IF;
    v_generation := coalesce(v_head.generation_version, 0) + 1;

    INSERT INTO task_finops_projection_rebuilds (
        rebuild_id, organization_id, account_id, window_start, window_end,
        event_count, fact_count, run_count, bucket_count, journal_checksum,
        hourly_checksum, daily_checksum, run_payload_digest,
        bucket_payload_digest, storage_payload_digest, source_as_of,
        input_continuity, request_digest, idempotency_key,
        published_by_actor_id, expected_generation, generation_version
    ) VALUES (
        p_rebuild_id, v_organization_id, v_account_id,
        p_window_start, p_window_end,
        p_event_count, p_fact_count, v_run_count, v_bucket_count,
        p_journal_checksum, p_hourly_checksum, p_daily_checksum,
        v_run_payload_digest, v_bucket_payload_digest, v_payload_digest,
        p_source_as_of, p_input_continuity,
        p_request_digest, p_idempotency_key, v_actor_id,
        p_expected_generation, v_generation
    );

    INSERT INTO task_finops_run_projections (
        rebuild_id, organization_id, account_id, task_id, run_number,
        task_state, progress_percent, last_event_sequence, last_occurred_at,
        run_checksum
    )
    SELECT p_rebuild_id, v_organization_id, v_account_id,
           row.task_id, row.run_number,
           row.task_state, row.progress_percent, row.last_event_sequence,
           row.last_occurred_at, row.checksum
      FROM jsonb_to_recordset(p_runs) AS row(
          organization_id varchar, account_id varchar, task_id varchar,
          run_number bigint, task_state varchar, progress_percent smallint,
          last_event_sequence bigint, last_occurred_at timestamptz, checksum varchar
      )
     WHERE row.organization_id = v_organization_id
       AND row.account_id = v_account_id
       AND length(row.task_id) BETWEEN 1 AND 96
       AND row.run_number >= 1
       AND row.progress_percent BETWEEN 0 AND 100
       AND row.last_event_sequence >= 1
       AND row.last_occurred_at < p_window_end
       AND row.last_occurred_at <= p_source_as_of
       AND row.checksum ~ '^[0-9a-f]{64}$';
    IF (SELECT count(*) FROM task_finops_run_projections
         WHERE rebuild_id = p_rebuild_id) <> v_run_count
       OR (SELECT coalesce(sum(last_event_sequence), 0)
             FROM task_finops_run_projections
            WHERE rebuild_id = p_rebuild_id) <> p_event_count THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_RUN_SCOPE_OR_SHAPE_INVALID';
    END IF;

    INSERT INTO task_finops_aggregate_buckets (
        rebuild_id, organization_id, account_id, grain, task_id, run_number,
        workload_class, bucket_start, bucket_end, currency, allocation_basis,
        cost_delta_minor, revenue_delta_minor, gross_delta_minor, fact_count,
        completeness, reconciliation_status
    )
    SELECT p_rebuild_id, v_organization_id, v_account_id,
           row.grain, row.task_id,
           row.run_number, row.workload_class, row.bucket_start, row.bucket_end,
           row.currency, row.allocation_basis, row.cost_delta_minor,
           row.revenue_delta_minor, row.gross_delta_minor, row.fact_count,
           row.completeness, row.reconciliation_status
      FROM jsonb_to_recordset(p_buckets) AS row(
          organization_id varchar, account_id varchar, task_id varchar,
          run_number bigint, workload_class varchar, grain varchar,
          bucket_start timestamptz, bucket_end timestamptz, currency varchar,
          allocation_basis varchar, cost_delta_minor numeric,
          revenue_delta_minor numeric, gross_delta_minor numeric,
          fact_count bigint, completeness varchar, reconciliation_status varchar
      )
     WHERE row.organization_id = v_organization_id
       AND row.account_id = v_account_id
       AND row.bucket_start < p_window_end
       AND row.bucket_end > p_window_start
       AND row.bucket_start <= p_source_as_of
       AND scale(row.cost_delta_minor) <= 6
       AND scale(row.revenue_delta_minor) <= 6
       AND scale(row.gross_delta_minor) <= 6
       AND abs(row.cost_delta_minor) < 1000000000000000000000000::numeric
       AND abs(row.revenue_delta_minor) < 1000000000000000000000000::numeric
       AND abs(row.gross_delta_minor) < 1000000000000000000000000::numeric;
    IF (SELECT count(*) FROM task_finops_aggregate_buckets
         WHERE rebuild_id = p_rebuild_id) <> v_bucket_count
       OR (SELECT coalesce(sum(fact_count) FILTER (WHERE grain = 'HOUR'), 0)
             FROM task_finops_aggregate_buckets
            WHERE rebuild_id = p_rebuild_id) <> p_fact_count
       OR (SELECT coalesce(sum(fact_count) FILTER (WHERE grain = 'DAY'), 0)
             FROM task_finops_aggregate_buckets
            WHERE rebuild_id = p_rebuild_id) <> p_fact_count THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_BUCKET_SCOPE_OR_SHAPE_INVALID';
    END IF;
    IF EXISTS (
        WITH grain_totals AS (
            SELECT task_id, run_number, workload_class, currency,
                   allocation_basis, grain,
                   sum(cost_delta_minor) AS cost_delta_minor,
                   sum(revenue_delta_minor) AS revenue_delta_minor,
                   sum(gross_delta_minor) AS gross_delta_minor,
                   sum(fact_count) AS fact_count
              FROM task_finops_aggregate_buckets
             WHERE rebuild_id = p_rebuild_id
             GROUP BY task_id, run_number, workload_class, currency,
                      allocation_basis, grain
        ), hourly AS (
            SELECT * FROM grain_totals WHERE grain = 'HOUR'
        ), daily AS (
            SELECT * FROM grain_totals WHERE grain = 'DAY'
        )
        SELECT 1
          FROM hourly
          FULL JOIN daily
            ON daily.task_id = hourly.task_id
           AND daily.run_number = hourly.run_number
           AND daily.workload_class = hourly.workload_class
           AND daily.currency = hourly.currency
           AND daily.allocation_basis = hourly.allocation_basis
         WHERE hourly.task_id IS NULL OR daily.task_id IS NULL
            OR hourly.cost_delta_minor IS DISTINCT FROM daily.cost_delta_minor
            OR hourly.revenue_delta_minor IS DISTINCT FROM daily.revenue_delta_minor
            OR hourly.gross_delta_minor IS DISTINCT FROM daily.gross_delta_minor
            OR hourly.fact_count IS DISTINCT FROM daily.fact_count
    ) THEN
        RAISE EXCEPTION 'ELMOS_MTF_ANALYTICS_CROSS_GRAIN_CONSERVATION_FAILED';
    END IF;

    INSERT INTO task_finops_projection_heads (
        organization_id, account_id, rebuild_id, generation_version,
        advanced_by_actor_id
    ) VALUES (
        v_organization_id, v_account_id,
        p_rebuild_id, v_generation, v_actor_id
    ) ON CONFLICT (organization_id, account_id)
      DO UPDATE SET rebuild_id = excluded.rebuild_id,
                    generation_version = excluded.generation_version,
                    advanced_by_actor_id = excluded.advanced_by_actor_id,
                    advanced_at = now();
    RETURN v_generation;
END;
$$;

CREATE VIEW mtf_current_task_run_projections
WITH (security_barrier = true, security_invoker = true) AS
SELECT projection.*,
       rebuild.input_continuity,
       rebuild.external_evidence_state,
       rebuild.provider_outcome,
       rebuild.production_certification,
       head.generation_version,
       false AS externally_qualified
  FROM task_finops_projection_heads head
  JOIN task_finops_projection_rebuilds rebuild
    ON rebuild.rebuild_id = head.rebuild_id
   AND rebuild.organization_id = head.organization_id
   AND rebuild.account_id = head.account_id
   AND rebuild.generation_version = head.generation_version
  JOIN task_finops_run_projections projection
    ON projection.rebuild_id = head.rebuild_id
   AND projection.organization_id = head.organization_id
   AND projection.account_id = head.account_id
 WHERE elmos_mtf_context_matches(head.organization_id, head.account_id)
   AND rebuild.input_continuity = 'COMPLETE'
   AND rebuild.external_evidence_state = 'NOT_RUN'
   AND rebuild.provider_outcome = 'UNKNOWN'
   AND rebuild.production_certification = 'NOT_CERTIFIED';

CREATE VIEW mtf_current_task_aggregate_buckets
WITH (security_barrier = true, security_invoker = true) AS
SELECT bucket.*,
       rebuild.input_continuity,
       rebuild.external_evidence_state,
       rebuild.provider_outcome,
       rebuild.production_certification,
       head.generation_version,
       false AS externally_qualified
  FROM task_finops_projection_heads head
  JOIN task_finops_projection_rebuilds rebuild
    ON rebuild.rebuild_id = head.rebuild_id
   AND rebuild.organization_id = head.organization_id
   AND rebuild.account_id = head.account_id
   AND rebuild.generation_version = head.generation_version
  JOIN task_finops_aggregate_buckets bucket
    ON bucket.rebuild_id = head.rebuild_id
   AND bucket.organization_id = head.organization_id
   AND bucket.account_id = head.account_id
 WHERE elmos_mtf_context_matches(head.organization_id, head.account_id)
   AND rebuild.input_continuity = 'COMPLETE'
   AND rebuild.external_evidence_state = 'NOT_RUN'
   AND rebuild.provider_outcome = 'UNKNOWN'
   AND rebuild.production_certification = 'NOT_CERTIFIED';

REVOKE ALL ON mtf_task_journal_for_rebuild FROM PUBLIC;
REVOKE ALL ON mtf_task_financial_facts_for_rebuild FROM PUBLIC;
REVOKE ALL ON mtf_current_task_run_projections FROM PUBLIC;
REVOKE ALL ON mtf_current_task_aggregate_buckets FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION elmos_mtf_publish_analytics_projection(
    varchar, timestamptz, timestamptz, bigint, bigint, bigint, varchar,
    varchar, varchar, timestamptz, varchar, jsonb, jsonb, varchar, varchar
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION elmos_mtf_publish_analytics_projection(
    varchar, timestamptz, timestamptz, bigint, bigint, bigint, varchar,
    varchar, varchar, timestamptz, varchar, jsonb, jsonb, varchar, varchar
) TO elmos_mtf_application, elmos_mtf_analytics;
GRANT SELECT ON task_finops_projection_rebuilds, task_finops_run_projections,
    task_finops_aggregate_buckets, task_finops_projection_heads,
    mtf_task_journal_for_rebuild, mtf_task_financial_facts_for_rebuild,
    mtf_current_task_run_projections, mtf_current_task_aggregate_buckets
    TO elmos_mtf_application, elmos_mtf_workflow, elmos_mtf_analytics;

COMMENT ON TABLE task_finops_projection_rebuilds IS
    'Digest-bound local projection generations. COMPLETE continuity is bounded to supplied rows and never upgrades external evidence, provider outcome or production certification.';
COMMENT ON VIEW mtf_current_task_run_projections IS
    'Current COMPLETE generation with explicit NOT_RUN external evidence, UNKNOWN provider outcome and NOT_CERTIFIED production state; externally_qualified remains false.';
COMMENT ON VIEW mtf_current_task_aggregate_buckets IS
    'Current COMPLETE generation with explicit NOT_RUN external evidence, UNKNOWN provider outcome and NOT_CERTIFIED production state; externally_qualified remains false.';
