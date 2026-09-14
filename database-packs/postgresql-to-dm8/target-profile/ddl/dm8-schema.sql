-- DM8 8.1.4.6 rev244896 Enterprise target candidate for the Phase-1 pilot.
-- Oracle-compatible mode, UTF-8/BINARY/Asia-Shanghai, single-instance non-MPP.
-- Candidate only: real DM8 execution and independent verification are NOT_RUN.

CREATE SEQUENCE order_id_seq START WITH 1 INCREMENT BY 1 NOCYCLE;

CREATE TABLE orders (
    -- DM8 resolves an unqualified sequence in a column default against the
    -- invoking user's schema. Qualify the owner so role-based inserts use the
    -- same generator as owner inserts.
    id BIGINT DEFAULT ELMOS_APP.order_id_seq.NEXTVAL NOT NULL,
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

CREATE TABLE elmos_target_window_journal (
    event_id VARCHAR(64) NOT NULL,
    generation BIGINT NOT NULL,
    table_name VARCHAR(128) NOT NULL,
    operation VARCHAR(16) NOT NULL,
    primary_key VARCHAR(256) NOT NULL,
    payload VARCHAR(2048) NOT NULL,
    payload_digest VARCHAR(64) NOT NULL,
    committed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    replayed_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_elmos_target_window_journal PRIMARY KEY (event_id),
    CONSTRAINT uq_elmos_target_window_payload UNIQUE (payload_digest),
    CONSTRAINT ck_elmos_target_window_operation
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE'))
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
    -- Application updates leave UPDATED_AT unchanged and receive the target
    -- statement timestamp. CDC supplies the source timestamp explicitly; in
    -- that case preserve it so field-level reconciliation remains exact.
    IF :NEW.updated_at = :OLD.updated_at THEN
        :NEW.updated_at := CURRENT_TIMESTAMP;
    END IF;
END;
/

CREATE OR REPLACE TRIGGER trg_orders_audit_update
AFTER UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    -- CDC replays PostgreSQL's audit event with its original identity. Normal
    -- application principals still receive target-side trigger auditing.
    IF USER <> 'ELMOS_CDC' THEN
        INSERT INTO order_audit(
            order_id, tenant_id, old_amount, new_amount, changed_at
        )
        VALUES (
            :OLD.id, :OLD.tenant_id, :OLD.amount, :NEW.amount, :NEW.updated_at
        );
    END IF;
END;
/
