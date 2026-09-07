-- Production workload-pack stage lifecycle.
--
-- V77 created the stage/work-item graph, but a caller could still insert a
-- later-stage work item as READY and nothing advanced a completed stage.  The
-- function below is the single database-owned transition point for stage
-- activation, dependency release, job status and terminal failure.

CREATE OR REPLACE FUNCTION orchestration.advance_job_stages(
    p_tenant_id uuid,
    p_job_id uuid
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = orchestration, public
AS $$
DECLARE
    current_stage record;
    changed_count integer := 0;
    changed boolean := true;
    stage_items bigint;
    incomplete_items bigint;
    active_items bigint;
BEGIN
    IF p_tenant_id IS NULL OR p_job_id IS NULL
       OR public.current_tenant_id() IS DISTINCT FROM p_tenant_id
    THEN
        RAISE EXCEPTION 'STAGE_TENANT_CONTEXT_REQUIRED';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM orchestration.jobs
         WHERE tenant_id = p_tenant_id AND id = p_job_id
    ) THEN
        RAISE EXCEPTION 'JOB_NOT_FOUND';
    END IF;

    -- Empty stages are intentionally not auto-completed: a producer may add
    -- their work items after job creation.  Once a stage has real work,
    -- completion and downstream activation converge in this bounded loop.
    WHILE changed LOOP
        changed := false;
        FOR current_stage IN
            SELECT js.id, js.status, js.sequence_no
              FROM orchestration.job_stages js
             WHERE js.tenant_id = p_tenant_id AND js.job_id = p_job_id
             ORDER BY js.sequence_no, js.id
             FOR UPDATE
        LOOP
            IF current_stage.status = 'BLOCKED'
               AND NOT EXISTS (
                   SELECT 1
                     FROM orchestration.job_stages previous
                    WHERE previous.tenant_id = p_tenant_id
                      AND previous.job_id = p_job_id
                      AND previous.sequence_no < current_stage.sequence_no
                      AND previous.status <> 'SUCCEEDED'
               ) THEN
                UPDATE orchestration.job_stages
                   SET status = 'READY'
                 WHERE tenant_id = p_tenant_id AND id = current_stage.id
                   AND status = 'BLOCKED';
                UPDATE orchestration.work_items wi
                   SET status = CASE
                       WHEN NOT EXISTS (
                           SELECT 1
                             FROM orchestration.work_item_dependencies dep
                             JOIN orchestration.work_items blocker
                               ON blocker.tenant_id = dep.tenant_id
                              AND blocker.id = dep.depends_on_work_item_id
                            WHERE dep.tenant_id = p_tenant_id
                              AND dep.work_item_id = wi.id
                              AND blocker.status <> 'SUCCEEDED'
                       ) THEN 'READY'
                       ELSE 'PENDING'
                       END,
                       ready_at = CASE
                           WHEN NOT EXISTS (
                               SELECT 1
                                 FROM orchestration.work_item_dependencies dep
                                 JOIN orchestration.work_items blocker
                                   ON blocker.tenant_id = dep.tenant_id
                                  AND blocker.id = dep.depends_on_work_item_id
                                WHERE dep.tenant_id = p_tenant_id
                                  AND dep.work_item_id = wi.id
                                  AND blocker.status <> 'SUCCEEDED'
                           ) THEN now()
                           ELSE NULL
                       END,
                       updated_at = now()
                 WHERE wi.tenant_id = p_tenant_id
                   AND wi.stage_id = current_stage.id
                   AND wi.status = 'PENDING';
                changed_count := changed_count + 1;
                changed := true;
            END IF;

            SELECT count(*)::bigint,
                   count(*) FILTER (WHERE wi.status <> 'SUCCEEDED')::bigint,
                   count(*) FILTER (WHERE wi.status IN (
                       'RESERVING', 'WAITING_FOR_CREDIT', 'RESERVED',
                       'DISPATCHING', 'RUNNING'))::bigint
              INTO stage_items, incomplete_items, active_items
              FROM orchestration.work_items wi
             WHERE wi.tenant_id = p_tenant_id AND wi.stage_id = current_stage.id;

            IF current_stage.status IN ('READY', 'RUNNING') AND stage_items > 0 THEN
                IF incomplete_items = 0 THEN
                    UPDATE orchestration.job_stages
                       SET status = 'SUCCEEDED'
                     WHERE tenant_id = p_tenant_id AND id = current_stage.id
                       AND status IN ('READY', 'RUNNING');
                    changed_count := changed_count + 1;
                    changed := true;
                ELSIF active_items > 0 AND current_stage.status = 'READY' THEN
                    UPDATE orchestration.job_stages
                       SET status = 'RUNNING'
                     WHERE tenant_id = p_tenant_id AND id = current_stage.id
                       AND status = 'READY';
                    changed_count := changed_count + 1;
                    changed := true;
                END IF;
            END IF;

            IF current_stage.status IN ('READY', 'RUNNING')
               AND EXISTS (
                   SELECT 1
                     FROM orchestration.work_items wi
                    WHERE wi.tenant_id = p_tenant_id
                      AND wi.stage_id = current_stage.id
                      AND wi.status IN ('FAILED', 'CANCELLED')
               ) THEN
                UPDATE orchestration.job_stages
                   SET status = 'FAILED'
                 WHERE tenant_id = p_tenant_id AND id = current_stage.id
                   AND status IN ('READY', 'RUNNING');
                changed_count := changed_count + 1;
                changed := true;
            END IF;
        END LOOP;
    END LOOP;

    UPDATE orchestration.jobs j
       SET status = CASE
           WHEN EXISTS (
               SELECT 1 FROM orchestration.job_stages js
                WHERE js.tenant_id = p_tenant_id AND js.job_id = p_job_id
                  AND js.status IN ('FAILED', 'CANCELLED')
           ) THEN 'FAILED'
           WHEN EXISTS (
               SELECT 1 FROM orchestration.job_stages js
                WHERE js.tenant_id = p_tenant_id AND js.job_id = p_job_id
           ) AND NOT EXISTS (
               SELECT 1 FROM orchestration.job_stages js
                WHERE js.tenant_id = p_tenant_id AND js.job_id = p_job_id
                  AND js.status <> 'SUCCEEDED'
           ) THEN 'SUCCEEDED'
           WHEN EXISTS (
               SELECT 1 FROM orchestration.work_items wi
                WHERE wi.tenant_id = p_tenant_id AND wi.job_id = p_job_id
                  AND wi.status NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
           ) OR EXISTS (
               SELECT 1 FROM orchestration.job_stages js
                WHERE js.tenant_id = p_tenant_id AND js.job_id = p_job_id
                  AND js.status IN ('READY', 'RUNNING')
           ) THEN 'RUNNING'
           ELSE j.status
           END,
           updated_at = now()
     WHERE j.tenant_id = p_tenant_id AND j.id = p_job_id;

    RETURN changed_count;
END;
$$;

REVOKE ALL ON FUNCTION orchestration.advance_job_stages(uuid, uuid) FROM PUBLIC;
