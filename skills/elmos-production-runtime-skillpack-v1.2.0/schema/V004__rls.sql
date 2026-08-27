CREATE OR REPLACE FUNCTION public.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
SELECT NULLIF(current_setting('app.tenant_id', true), '')::uuid
$$;

ALTER TABLE project.projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY project_tenant_policy ON project.projects
USING(tenant_id = public.current_tenant_id())
WITH CHECK(tenant_id = public.current_tenant_id());

ALTER TABLE orchestration.jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY jobs_tenant_policy ON orchestration.jobs
USING(tenant_id = public.current_tenant_id())
WITH CHECK(tenant_id = public.current_tenant_id());

ALTER TABLE orchestration.work_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY work_tenant_policy ON orchestration.work_items
USING(tenant_id = public.current_tenant_id())
WITH CHECK(tenant_id = public.current_tenant_id());

ALTER TABLE billing.wallets ENABLE ROW LEVEL SECURITY;
CREATE POLICY wallets_tenant_policy ON billing.wallets
USING(tenant_id = public.current_tenant_id())
WITH CHECK(tenant_id = public.current_tenant_id());

ALTER TABLE billing.ledger_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY ledger_tenant_policy ON billing.ledger_entries
USING(tenant_id = public.current_tenant_id())
WITH CHECK(tenant_id = public.current_tenant_id());
