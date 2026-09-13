-- Host-only scheduling authority; tenant data keeps FORCE RLS. No tenant id
-- is accepted by the scheduler. These private tables are deliberately not RLS
-- filtered: the finite global admission bound must include every tenant.
CREATE TABLE object_gc_host_cursor (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    last_organization_id varchar(96) NOT NULL DEFAULT ''
);
INSERT INTO object_gc_host_cursor(singleton) VALUES(true);
CREATE INDEX content_objects_gc_tenant_pending_idx
    ON content_objects(organization_id,created_at,content_object_id) WHERE object_state='PURGE_PENDING';
CREATE TABLE object_gc_host_runs (
    run_id varchar(96) PRIMARY KEY,
    organization_id varchar(96) NOT NULL REFERENCES organizations(organization_id),
    run_state varchar(16) NOT NULL CHECK (run_state IN ('UNRESOLVED','COMPLETED')),
    last_object_id varchar(96) NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz
);
CREATE UNIQUE INDEX object_gc_host_one_unresolved_tenant
    ON object_gc_host_runs(organization_id) WHERE run_state='UNRESOLVED';
CREATE INDEX object_gc_host_history ON object_gc_host_runs(run_state,created_at,run_id);
CREATE TABLE object_gc_host_items (
    run_id varchar(96) NOT NULL REFERENCES object_gc_host_runs(run_id) ON DELETE CASCADE,
    organization_id varchar(96) NOT NULL,
    content_object_id varchar(96) NOT NULL,
    content_sha256 varchar(64) NOT NULL,
    backend_id varchar(64) NOT NULL,
    storage_key varchar(512) NOT NULL,
    item_state varchar(16) NOT NULL DEFAULT 'UNRESOLVED'
        CHECK (item_state IN ('UNRESOLVED','UNKNOWN','CONFIRMED')),
    unknown_count integer NOT NULL DEFAULT 0 CHECK (unknown_count >= 0),
    first_unknown_at timestamptz,
    last_unknown_at timestamptz,
    confirmed_at timestamptz,
    PRIMARY KEY(run_id,content_object_id)
);
REVOKE ALL ON object_gc_host_cursor,object_gc_host_runs,object_gc_host_items FROM PUBLIC;

CREATE FUNCTION elmos_object_gc_host_prepare(
    p_round_id varchar, p_tenant_limit integer, p_metadata_budget integer, p_delete_budget integer
) RETURNS TABLE(run_id varchar,organization_id varchar,content_object_id varchar,
    content_sha256 varchar,backend_id varchar,storage_key varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    v_previous text := coalesce(current_setting('app.organization_id',true),'');
    v_cursor varchar; v_org varchar; v_orgs varchar[]; v_wrap varchar[];
    v_run varchar; v_item_cursor varchar; v_items varchar[]; v_more varchar[];
    v_metadata integer; v_deletes integer; v_count integer;
BEGIN
    IF p_round_id IS NULL OR length(p_round_id) NOT BETWEEN 1 AND 64
      OR p_tenant_limit IS NULL OR p_tenant_limit NOT BETWEEN 1 AND 8
      OR p_metadata_budget IS NULL OR p_metadata_budget NOT BETWEEN p_tenant_limit AND 256
      OR p_delete_budget IS NULL OR p_delete_budget NOT BETWEEN p_tenant_limit AND 128 THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_BUDGET_INVALID';
    END IF;
    IF row_security_active('public.organizations') OR row_security_active('public.object_gc_host_runs')
      OR row_security_active('public.object_gc_host_items') OR row_security_active('public.object_gc_host_cursor') THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_AUTHORITY_FILTERED';
    END IF;
    SELECT c.last_organization_id INTO v_cursor FROM public.object_gc_host_cursor c
      WHERE c.singleton FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        IF NOT EXISTS(SELECT 1 FROM public.object_gc_host_cursor) THEN
            RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_CURSOR_UNKNOWN';
        END IF;
        RETURN;
    END IF;
    -- At most 32 known-terminal private ledgers are pruned. The existing
    -- append-only object_gc_runs audit is intentionally NOT deleted or weakened.
    IF (SELECT count(*) FROM public.object_gc_host_runs) >= 4000 THEN
        DELETE FROM public.object_gc_host_runs WHERE object_gc_host_runs.run_id IN (
            SELECT r.run_id FROM public.object_gc_host_runs r WHERE r.run_state='COMPLETED'
            ORDER BY r.created_at,r.run_id LIMIT 32);
    END IF;
    SELECT coalesce(array_agg(s.organization_id ORDER BY s.organization_id),'{}'::varchar[])
      INTO v_orgs FROM (SELECT o.organization_id FROM public.organizations o
        WHERE o.organization_id>v_cursor ORDER BY o.organization_id LIMIT p_tenant_limit) s;
    SELECT coalesce(array_agg(s.organization_id ORDER BY s.organization_id),'{}'::varchar[])
      INTO v_wrap FROM (SELECT o.organization_id FROM public.organizations o
        WHERE o.organization_id<=v_cursor ORDER BY o.organization_id
        LIMIT p_tenant_limit-cardinality(v_orgs)) s;
    v_orgs:=v_orgs||v_wrap;
    v_metadata:=p_metadata_budget/p_tenant_limit;
    v_deletes:=p_delete_budget/p_tenant_limit;
    FOREACH v_org IN ARRAY v_orgs LOOP
        UPDATE public.object_gc_host_cursor SET last_organization_id=v_org WHERE singleton;
        PERFORM set_config('app.organization_id',v_org,true);
        SELECT r.run_id,r.last_object_id INTO v_run,v_item_cursor FROM public.object_gc_host_runs r
          WHERE r.organization_id=v_org AND r.run_state='UNRESOLVED' FOR UPDATE;
        IF NOT FOUND THEN
            IF (SELECT count(*) FROM public.object_gc_host_runs WHERE run_state='UNRESOLVED') >= 256
              OR (SELECT count(*) FROM public.object_gc_host_runs) >= 4096 THEN
                CONTINUE; -- unknown work is never evicted to admit new work
            END IF;
            v_run:='gch-'||md5(p_round_id||':'||v_org);
            INSERT INTO public.object_gc_host_runs(run_id,organization_id,run_state)
              VALUES(v_run,v_org,'UNRESOLVED');
            -- V88 scopes both root snapshots and updates explicitly, including
            -- when that legacy function's owner can bypass RLS.
            PERFORM public.elmos_expire_artifacts(v_run,v_metadata);
            INSERT INTO public.object_gc_host_items(run_id,organization_id,content_object_id,
                content_sha256,backend_id,storage_key)
              SELECT v_run,o.organization_id,o.content_object_id,o.content_sha256,o.backend_id,o.storage_key
              FROM public.content_objects o WHERE o.organization_id=v_org AND o.object_state='PURGE_PENDING'
              ORDER BY o.created_at,o.content_object_id LIMIT v_deletes FOR UPDATE SKIP LOCKED;
            GET DIAGNOSTICS v_count=ROW_COUNT;
            IF v_count=0 THEN
                UPDATE public.object_gc_host_runs SET run_state='COMPLETED',finished_at=clock_timestamp()
                  WHERE object_gc_host_runs.run_id=v_run;
                PERFORM public.elmos_finish_object_gc(v_run,0,0);
                CONTINUE;
            END IF;
            v_item_cursor:='';
        END IF;
        -- Retrying an uncertain DELETE uses the SAME immutable tombstone item;
        -- no TTL authorizes release, and no new run/item is appended on failure.
        SELECT coalesce(array_agg(s.content_object_id ORDER BY s.content_object_id),'{}'::varchar[])
          INTO v_items FROM (SELECT i.content_object_id FROM public.object_gc_host_items i
            WHERE i.run_id=v_run AND i.item_state<>'CONFIRMED' AND i.content_object_id>v_item_cursor
            ORDER BY i.content_object_id LIMIT v_deletes) s;
        SELECT coalesce(array_agg(s.content_object_id ORDER BY s.content_object_id),'{}'::varchar[])
          INTO v_more FROM (SELECT i.content_object_id FROM public.object_gc_host_items i
            WHERE i.run_id=v_run AND i.item_state<>'CONFIRMED' AND i.content_object_id<=v_item_cursor
            ORDER BY i.content_object_id LIMIT v_deletes-cardinality(v_items)) s;
        v_items:=v_items||v_more;
        IF cardinality(v_items)>0 THEN
            UPDATE public.object_gc_host_runs SET last_object_id=v_items[cardinality(v_items)]
              WHERE object_gc_host_runs.run_id=v_run;
            RETURN QUERY SELECT i.run_id,i.organization_id,i.content_object_id,i.content_sha256,i.backend_id,i.storage_key
              FROM public.object_gc_host_items i WHERE i.run_id=v_run AND i.content_object_id=ANY(v_items)
              ORDER BY i.content_object_id;
        END IF;
    END LOOP;
    PERFORM set_config('app.organization_id',v_previous,true);
END $$;

CREATE FUNCTION elmos_object_gc_host_confirm(p_run varchar,p_object varchar,p_org varchar,
    p_sha varchar,p_backend varchar,p_key varchar) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE v_previous text:=coalesce(current_setting('app.organization_id',true),'');
    v_item public.object_gc_host_items%ROWTYPE; v_state varchar; v_confirmed integer;
BEGIN
    PERFORM 1 FROM public.object_gc_host_runs r WHERE r.run_id=p_run FOR UPDATE;
    SELECT * INTO v_item FROM public.object_gc_host_items i WHERE i.run_id=p_run AND i.content_object_id=p_object;
    IF NOT FOUND OR v_item.organization_id IS DISTINCT FROM p_org OR v_item.content_sha256 IS DISTINCT FROM p_sha
      OR v_item.backend_id IS DISTINCT FROM p_backend OR v_item.storage_key IS DISTINCT FROM p_key THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_BINDING_MISMATCH';
    END IF;
    PERFORM set_config('app.organization_id',v_item.organization_id,true);
    SELECT o.object_state INTO v_state FROM public.content_objects o
      WHERE o.organization_id=v_item.organization_id AND o.content_object_id=v_item.content_object_id
        AND o.content_sha256=v_item.content_sha256 AND o.backend_id=v_item.backend_id AND o.storage_key=v_item.storage_key
      FOR UPDATE;
    IF NOT FOUND OR v_state NOT IN ('PURGE_PENDING','PURGED') THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_OBJECT_CHANGED';
    END IF;
    IF v_state='PURGE_PENDING' THEN
        IF NOT public.elmos_confirm_object_purged(v_item.organization_id,v_item.content_object_id) THEN
            RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_CONFIRM_FAILED';
        END IF;
    END IF;
    UPDATE public.object_gc_host_items SET item_state='CONFIRMED',confirmed_at=coalesce(confirmed_at,clock_timestamp())
      WHERE run_id=p_run AND content_object_id=p_object;
    IF NOT EXISTS(SELECT 1 FROM public.object_gc_host_items WHERE run_id=p_run AND item_state<>'CONFIRMED') THEN
        UPDATE public.object_gc_host_runs SET run_state='COMPLETED',finished_at=clock_timestamp()
          WHERE run_id=p_run AND run_state='UNRESOLVED';
        IF FOUND THEN
            SELECT count(*) INTO v_confirmed FROM public.object_gc_host_items WHERE run_id=p_run;
            PERFORM public.elmos_finish_object_gc(p_run,v_confirmed,0);
        END IF;
    END IF;
    PERFORM set_config('app.organization_id',v_previous,true);
    RETURN true;
END $$;

CREATE FUNCTION elmos_object_gc_host_unknown(p_run varchar,p_object varchar) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    PERFORM 1 FROM public.object_gc_host_runs r WHERE r.run_id=p_run FOR UPDATE;
    UPDATE public.object_gc_host_items SET item_state='UNKNOWN',
        unknown_count=least(unknown_count::bigint+1,2147483647)::integer,
        first_unknown_at=coalesce(first_unknown_at,clock_timestamp()),last_unknown_at=clock_timestamp()
      WHERE run_id=p_run AND content_object_id=p_object AND item_state<>'CONFIRMED';
    -- A racing successful confirmation cannot be downgraded by a late timeout.
    RETURN FOUND;
END $$;

DO $$ BEGIN
    IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='elmos_object_gc_host') THEN
        CREATE ROLE elmos_object_gc_host NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
    ELSIF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='elmos_object_gc_host' AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolinherit))
      OR EXISTS(SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname='elmos_object_gc_host') THEN
        RAISE EXCEPTION 'ELMOS_OBJECT_GC_HOST_ROLE_UNSAFE';
    END IF;
END $$;
REVOKE ALL ON FUNCTION elmos_object_gc_host_prepare(varchar,integer,integer,integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_object_gc_host_confirm(varchar,varchar,varchar,varchar,varchar,varchar) FROM PUBLIC;
REVOKE ALL ON FUNCTION elmos_object_gc_host_unknown(varchar,varchar) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION elmos_object_gc_host_prepare(varchar,integer,integer,integer),
    elmos_object_gc_host_confirm(varchar,varchar,varchar,varchar,varchar,varchar),
    elmos_object_gc_host_unknown(varchar,varchar) TO elmos_object_gc_host;
-- No membership is granted here. Deployment must explicitly grant this group
-- to the trusted host scheduler login, never to an ordinary tenant role.
