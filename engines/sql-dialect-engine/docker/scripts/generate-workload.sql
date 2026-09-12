-- Mixed DML Workload Generator for CDC Reconciliation Testing
-- Generates batch INSERT, UPDATE, and DELETE operations

-- 1. Batch Insert new users
INSERT INTO ecommerce.users (id, username, email, phone, bio, is_active, status, created_at, updated_at) VALUES
(6, 'frank_zhao', 'frank@example.com', '+8613800000006', 'Security auditor from Wuhan', TRUE, 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(7, 'grace_qian', 'grace@example.com', '+8613800000007', 'Data engineer from Nanjing', TRUE, 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(8, 'henry_sun', 'henry@example.com', '+8613800000008', 'DevOps from Xi''an', FALSE, 'INACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;

-- 2. Batch Insert orders for new and existing users
INSERT INTO ecommerce.orders (id, user_id, order_no, amount, currency, status, created_at, updated_at) VALUES
(106, 6, 'ORD-2026-0006', 4999.00, 'CNY', 'PROCESSING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(107, 7, 'ORD-2026-0007', 79.00, 'CNY', 'PENDING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
(108, 1, 'ORD-2026-0008', 320.00, 'CNY', 'PENDING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (id) DO NOTHING;

-- 3. Batch Updates (status transitions, updated_at refresh)
UPDATE ecommerce.orders
SET status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP
WHERE id = 103;

UPDATE ecommerce.orders
SET status = 'SHIPPED', amount = 850.00, updated_at = CURRENT_TIMESTAMP
WHERE id = 102;

UPDATE ecommerce.users
SET phone = '+8613999999999', updated_at = CURRENT_TIMESTAMP
WHERE id = 2;

-- 4. Delete operation (cancelled or purged orders)
DELETE FROM ecommerce.orders
WHERE id = 104;
