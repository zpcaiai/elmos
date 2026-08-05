INSERT INTO accounts (account_id, tenant_id, account_code, currency, created_at) VALUES
    (1, '11111111-1111-4111-8111-111111111111', 'operating', 'USD', '2026-01-01T00:00:00Z'),
    (2, '22222222-2222-4222-8222-222222222222', 'reserve', 'CNY', '2026-01-02T00:00:00Z');

INSERT INTO ledger_entries
    (entry_id, account_id, amount, idempotency_key, description, occurred_at)
VALUES
    (1, 1, 100.1250, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1', 'initial-credit', '2026-01-03T00:00:00Z'),
    (2, 1, -20.0250, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2', '订单-001', '2026-01-04T00:00:00Z'),
    (3, 2, 999999999999.9999, 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3', 'precision-boundary', '2026-01-05T00:00:00Z');

SELECT setval(pg_get_serial_sequence('accounts', 'account_id'), 2, true);
SELECT setval(pg_get_serial_sequence('ledger_entries', 'entry_id'), 3, true);
