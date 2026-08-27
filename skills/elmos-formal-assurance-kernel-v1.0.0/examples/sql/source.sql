SELECT tenant_id, SUM(balance) AS total_balance
FROM accounts
WHERE balance >= 0
GROUP BY tenant_id;
