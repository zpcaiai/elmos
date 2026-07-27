SELECT id, tenant_id, amount_cents, created_at FROM work_orders WHERE tenant_id = :tenant_id ORDER BY id;
