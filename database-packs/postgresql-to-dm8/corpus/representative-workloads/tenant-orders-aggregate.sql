-- Representative Workload: Orders count and volume per tenant
SELECT tenant_id, COUNT(*) AS order_count, SUM(amount_cents) AS total_amount FROM orders GROUP BY tenant_id ORDER BY total_amount DESC;
