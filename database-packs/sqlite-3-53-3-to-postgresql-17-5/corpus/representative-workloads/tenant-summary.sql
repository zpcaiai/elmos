SELECT tenant_id, SUM(amount_cents) FROM work_orders GROUP BY tenant_id ORDER BY tenant_id;
