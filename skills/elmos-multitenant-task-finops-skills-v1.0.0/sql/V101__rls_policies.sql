-- Forced RLS reference migration.
-- Execute schema migrations as an isolated owner role; application roles must not own these tables.

SET search_path = elmos, public;

CREATE OR REPLACE FUNCTION current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION current_account_id()
RETURNS uuid
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT NULLIF(current_setting('app.account_id', true), '')::uuid;
$$;

CREATE OR REPLACE FUNCTION current_actor_id()
RETURNS text
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
  SELECT NULLIF(current_setting('app.actor_id', true), '');
$$;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'tenant_runtime_quota',
    'task',
    'task_run',
    'task_node',
    'task_node_attempt',
    'task_event',
    'task_progress_snapshot',
    'task_checkpoint',
    'task_side_effect_receipt',
    'task_input',
    'task_artifact',
    'task_log_segment',
    'outbox_event',
    'usage_event',
    'task_cost_summary',
    'revenue_entry',
    'revenue_allocation',
    'task_financial_summary',
    'tenant_financial_daily'
  ]
  LOOP
    EXECUTE format('ALTER TABLE elmos.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE elmos.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY %I ON elmos.%I USING (tenant_id = elmos.current_tenant_id()) WITH CHECK (tenant_id = elmos.current_tenant_id())',
      'tenant_isolation_' || t,
      t
    );
  END LOOP;
END
$$;

ALTER TABLE account_task_slot ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_task_slot FORCE ROW LEVEL SECURITY;

CREATE POLICY account_slot_owner
ON account_task_slot
USING (account_id = current_account_id())
WITH CHECK (account_id = current_account_id());

ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event FORCE ROW LEVEL SECURITY;

CREATE POLICY audit_tenant_isolation
ON audit_event
USING (tenant_id = current_tenant_id())
WITH CHECK (tenant_id = current_tenant_id());

-- price_book_item is platform reference data. Grant SELECT to runtime roles;
-- restrict INSERT/UPDATE/DELETE to an audited finance administration role.
-- Never grant BYPASSRLS or table ownership to normal application roles.

-- Example least-privilege role plan (adapt names to repository conventions):
--
-- CREATE ROLE elmos_migration_owner NOLOGIN;
-- CREATE ROLE elmos_control_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
-- CREATE ROLE elmos_workflow_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
-- CREATE ROLE elmos_outbox_publisher NOLOGIN NOSUPERUSER NOBYPASSRLS;
-- CREATE ROLE elmos_analytics_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
-- CREATE ROLE elmos_finance_admin NOLOGIN NOSUPERUSER NOBYPASSRLS;
--
-- The migration owner owns tables. Runtime roles receive only explicit
-- SELECT/INSERT/UPDATE/DELETE/EXECUTE grants needed for their module.
-- Test every policy with the actual non-superuser runtime role.
