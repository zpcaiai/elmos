-- KingbaseES (人大金仓) Target Initialization for CDC
-- Schema supporting both PG and Oracle compatibility modes

CREATE SCHEMA IF NOT EXISTS ecommerce;

-- Table 1: Users (Target)
CREATE TABLE IF NOT EXISTS ecommerce.users (
    id BIGSERIAL NOT NULL,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(128) NOT NULL,
    phone VARCHAR(32),
    status VARCHAR(20) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_username UNIQUE (username)
);

-- Table 2: Orders (Target)
CREATE TABLE IF NOT EXISTS ecommerce.orders (
    id BIGSERIAL NOT NULL,
    user_id BIGINT NOT NULL,
    order_no VARCHAR(64) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'CNY' NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
    payload BYTEA,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT uq_orders_order_no UNIQUE (order_no),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES ecommerce.users(id)
);
