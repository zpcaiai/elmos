SELECT tenant_id, catalog_version, plan_id, status FROM subscriptions WHERE tenant_id = :tenant_id ORDER BY tenant_id ASC;
