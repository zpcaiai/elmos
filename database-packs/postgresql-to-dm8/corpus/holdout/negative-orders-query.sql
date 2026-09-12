-- Holdout: Negative validation on amount constraint
INSERT INTO orders (id, tenant_id, amount_cents, created_at) VALUES (99999, 'tenant-test', -500, CURRENT_TIMESTAMP);
