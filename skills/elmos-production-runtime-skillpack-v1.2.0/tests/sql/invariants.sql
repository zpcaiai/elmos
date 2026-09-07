-- No negative wallet.
SELECT * FROM billing.wallet_balances
WHERE available_balance < 0 OR reserved_balance < 0;

-- No duplicate provider usage where identity exists.
SELECT provider, provider_usage_id, COUNT(*)
FROM billing.token_usage_events
WHERE provider_usage_id IS NOT NULL
GROUP BY provider, provider_usage_id
HAVING COUNT(*) > 1;

-- Journal balance.
SELECT journal_id, currency, SUM(debit), SUM(credit)
FROM billing.billing_journal_lines
GROUP BY journal_id, currency
HAVING SUM(debit) <> SUM(credit);

-- No stale active reservation after expiry window.
SELECT * FROM billing.credit_reservations
WHERE status='ACTIVE' AND expires_at < now();

-- No running attempt without lease.
SELECT ea.*
FROM runtime.execution_attempts ea
LEFT JOIN runtime.worker_leases wl ON wl.attempt_id = ea.id
WHERE ea.status='RUNNING' AND wl.attempt_id IS NULL;

-- No running work without matching lease.
SELECT wi.*
FROM orchestration.work_items wi
LEFT JOIN runtime.worker_leases wl ON wl.work_item_id = wi.id
WHERE wi.status='RUNNING' AND wl.work_item_id IS NULL;

-- Idempotency same key must map to one request hash.
SELECT tenant_id, operation_type, idempotency_key, COUNT(DISTINCT request_hash)
FROM billing.idempotency_records
GROUP BY tenant_id, operation_type, idempotency_key
HAVING COUNT(DISTINCT request_hash) > 1;

-- Final usage must not have duplicate finalization.
SELECT model_call_id, COUNT(*)
FROM billing.token_usage_events
GROUP BY model_call_id
HAVING COUNT(*) > 1;
