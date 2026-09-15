-- OceanBase Distributed Target Initialization for CDC
-- Supports distributed primary key hashing and table groups

CREATE DATABASE IF NOT EXISTS ecommerce;
USE ecommerce;

-- Table 1: Users (Target - MySQL Mode with HASH Partitioning)
CREATE TABLE IF NOT EXISTS ecommerce.users (
    id BIGINT AUTO_INCREMENT NOT NULL,
    username VARCHAR(64) NOT NULL,
    email VARCHAR(128) NOT NULL,
    phone VARCHAR(32),
    status VARCHAR(20) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username)
) PARTITION BY HASH(id) PARTITIONS 16;

-- Table 2: Orders (Target - MySQL Mode with HASH Partitioning)
CREATE TABLE IF NOT EXISTS ecommerce.orders (
    id BIGINT AUTO_INCREMENT NOT NULL,
    user_id BIGINT NOT NULL,
    order_no VARCHAR(64) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'CNY' NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING' NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_orders_order_no (order_no),
    KEY idx_orders_user (user_id)
) PARTITION BY HASH(id) PARTITIONS 16;
