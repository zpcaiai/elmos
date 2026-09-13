-- DM8 8.1.3.140 Enterprise target candidate for the Phase-1 pilot.
-- Oracle-compatible mode, UTF-8/BINARY/Asia-Shanghai, single-instance non-MPP.
-- Candidate only: real DM8 execution and independent verification are NOT_RUN.

CREATE SEQUENCE order_id_seq START WITH 1 INCREMENT BY 1 NOCYCLE;

CREATE TABLE orders (
    id BIGINT DEFAULT order_id_seq.NEXTVAL NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    amount_cents BIGINT NOT NULL,
    amount NUMBER(19, 4) NOT NULL,
    status VARCHAR(16) DEFAULT 'NEW' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT ck_orders_amount_cents_nonnegative CHECK (amount_cents >= 0),
    CONSTRAINT ck_orders_amount_nonnegative CHECK (amount >= 0),
    CONSTRAINT ck_orders_status CHECK (status IN ('NEW', 'PAID', 'VOID')),
    CONSTRAINT uq_orders_tenant_id UNIQUE (tenant_id, id)
);

CREATE INDEX idx_orders_tenant_created ON orders (tenant_id, created_at DESC);

CREATE TABLE order_audit (
    audit_id BIGINT IDENTITY(1, 1) NOT NULL,
    order_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    old_amount NUMBER(19, 4),
    new_amount NUMBER(19, 4),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT pk_order_audit PRIMARY KEY (audit_id)
);

CREATE TABLE elmos_cdc_event_ledger (
    target_id VARCHAR(64) NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    source_lsn BIGINT NOT NULL,
    event_digest VARCHAR(64) NOT NULL,
    tx_id VARCHAR(128) NOT NULL,
    applied_at DOUBLE NOT NULL,
    CONSTRAINT pk_elmos_cdc_event_ledger PRIMARY KEY (target_id, table_name, source_lsn),
    CONSTRAINT uq_elmos_cdc_event_digest UNIQUE (event_digest)
);

CREATE OR REPLACE PROCEDURE mark_order_paid(p_order_id IN BIGINT) AS
BEGIN
    UPDATE orders SET status = 'PAID' WHERE id = p_order_id;
END;
/

CREATE OR REPLACE TRIGGER trg_orders_before_update
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
    :NEW.updated_at := CURRENT_TIMESTAMP;
END;
/

CREATE OR REPLACE TRIGGER trg_orders_audit_update
AFTER UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit(order_id, tenant_id, old_amount, new_amount)
    VALUES (:OLD.id, :OLD.tenant_id, :OLD.amount, :NEW.amount);
END;
/
