SELECT tenant_id, SUM(balance) AS total_balance
FROM accounts
GROUP BY tenant_id;
