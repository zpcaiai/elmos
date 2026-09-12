-- PostgreSQL Source Initialization for CDC
-- Logical replication configuration & publication

CREATE USER cdc_repl WITH REPLICATION ENCRYPTED PASSWORD 'cdc_repl_password';
GRANT ALL PRIVILEGES ON DATABASE source_db TO cdc_repl;

CREATE SCHEMA IF NOT EXISTS ecommerce;
GRANT ALL ON SCHEMA ecommerce TO cdc_user;
GRANT ALL ON SCHEMA ecommerce TO cdc_repl;

-- Table 1: Users
CREATE TABLE IF NOT EXISTS ecommerce.users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(128) NOT NULL,
    phone VARCHAR(32),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: Orders
CREATE TABLE IF NOT EXISTS ecommerce.orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES ecommerce.users(id),
    order_no VARCHAR(64) NOT NULL UNIQUE,
    amount DECIMAL(12, 2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'CNY',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Publication for logical replication
CREATE PUBLICATION cdc_publication FOR ALL TABLES;

-- Seed Data
INSERT INTO ecommerce.users (id, username, email, phone, status, created_at, updated_at) VALUES
(1, 'alice_zhang', 'alice@example.com', '+8613800000001', 'ACTIVE', '2026-01-01 10:00:00+08', '2026-01-01 10:00:00+08'),
(2, 'bob_li', 'bob@example.com', '+8613800000002', 'ACTIVE', '2026-01-02 11:30:00+08', '2026-01-02 11:30:00+08'),
(3, 'charlie_wang', 'charlie@example.com', '+8613800000003', 'INACTIVE', '2026-01-03 15:20:00+08', '2026-01-03 15:20:00+08'),
(4, 'david_liu', 'david@example.com', '+8613800000004', 'ACTIVE', '2026-01-04 09:15:00+08', '2026-01-04 09:15:00+08'),
(5, 'eva_chen', 'eva@example.com', '+8613800000005', 'ACTIVE', '2026-01-05 14:40:00+08', '2026-01-05 14:40:00+08')
ON CONFLICT (id) DO NOTHING;

SELECT setval('ecommerce.users_id_seq', 5);

INSERT INTO ecommerce.orders (id, user_id, order_no, amount, currency, status, created_at, updated_at) VALUES
(101, 1, 'ORD-2026-0001', 199.50, 'CNY', 'COMPLETED', '2026-01-02 12:00:00+08', '2026-01-02 12:05:00+08'),
(102, 1, 'ORD-2026-0002', 899.00, 'CNY', 'PROCESSING', '2026-01-03 13:10:00+08', '2026-01-03 13:10:00+08'),
(103, 2, 'ORD-2026-0003', 49.90, 'CNY', 'PENDING', '2026-01-03 16:00:00+08', '2026-01-03 16:00:00+08'),
(104, 3, 'ORD-2026-0004', 1250.00, 'CNY', 'CANCELLED', '2026-01-04 10:30:00+08', '2026-01-04 11:00:00+08'),
(105, 4, 'ORD-2026-0005', 368.80, 'CNY', 'COMPLETED', '2026-01-05 18:20:00+08', '2026-01-05 18:25:00+08')
ON CONFLICT (id) DO NOTHING;

SELECT setval('ecommerce.orders_id_seq', 105);
