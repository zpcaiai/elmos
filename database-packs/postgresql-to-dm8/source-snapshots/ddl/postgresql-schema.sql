-- PostgreSQL 17.5 Community source candidate for the DM8 Phase-1 pilot.
-- Synthetic/disposable environments only. Real execution remains NOT_RUN.

CREATE SEQUENCE order_id_seq AS bigint START WITH 1 INCREMENT BY 1 NO CYCLE;

CREATE TABLE orders (
    id bigint NOT NULL DEFAULT nextval('order_id_seq'),
    tenant_id varchar(64) NOT NULL,
    amount_cents bigint NOT NULL,
    amount numeric(19, 4) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'NEW',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT ck_orders_amount_cents_nonnegative CHECK (amount_cents >= 0),
    CONSTRAINT ck_orders_amount_nonnegative CHECK (amount >= 0),
    CONSTRAINT ck_orders_status CHECK (status IN ('NEW', 'PAID', 'VOID')),
    CONSTRAINT uq_orders_tenant_id UNIQUE (tenant_id, id)
);

ALTER SEQUENCE order_id_seq OWNED BY orders.id;
CREATE INDEX idx_orders_tenant_created ON orders (tenant_id, created_at DESC);

CREATE TABLE order_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    tenant_id varchar(64) NOT NULL,
    old_amount numeric(19, 4),
    new_amount numeric(19, 4),
    changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE FUNCTION orders_before_update() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_orders_before_update
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION orders_before_update();

CREATE FUNCTION orders_audit_update() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO order_audit(
        order_id, tenant_id, old_amount, new_amount, changed_at
    )
    VALUES (OLD.id, OLD.tenant_id, OLD.amount, NEW.amount, NEW.updated_at);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_orders_audit_update
AFTER UPDATE OF amount ON orders
FOR EACH ROW EXECUTE FUNCTION orders_audit_update();

CREATE ROLE orders_reader NOLOGIN;
CREATE ROLE orders_writer NOLOGIN;
GRANT SELECT ON orders TO orders_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON orders TO orders_writer;
GRANT USAGE, SELECT ON SEQUENCE order_id_seq TO orders_writer;

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
CREATE POLICY orders_tenant_policy ON orders
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
