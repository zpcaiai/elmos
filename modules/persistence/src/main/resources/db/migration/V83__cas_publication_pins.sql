-- Physical publication no longer borrows a connection or holds lifecycle locks.
-- A durable pin fences deletion until the live owner confirms its synchronous I/O has ended.
-- Expiry prevents publication, but DOES NOT prove writer quiescence and never permits GC.
CREATE TABLE cas_object_publication_pins (
    organization_id varchar(64) NOT NULL REFERENCES cas_tenant_lifecycles (organization_id),
    publication_id varchar(36) NOT NULL CHECK (publication_id ~ '^[0-9a-f-]{36}$'),
    digest_hex varchar(64) NOT NULL CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    tenant_epoch bigint NOT NULL CHECK (tenant_epoch >= 1),
    resource_kind varchar(16) CHECK (resource_kind IN ('REPOSITORY', 'PROJECT')),
    resource_id varchar(128),
    resource_epoch bigint CHECK (resource_epoch >= 1),
    pin_state varchar(24) NOT NULL DEFAULT 'ACTIVE'
        CHECK (pin_state IN ('ACTIVE', 'OUTCOME_UNKNOWN', 'RELEASED')),
    lease_expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (organization_id, publication_id, digest_hex),
    CHECK ((resource_kind IS NULL AND resource_id IS NULL AND resource_epoch IS NULL)
        OR (resource_kind IS NOT NULL AND resource_id IS NOT NULL
            AND btrim(resource_id) <> '' AND resource_epoch IS NOT NULL))
);
CREATE INDEX cas_publication_pins_live_object_idx
    ON cas_object_publication_pins (organization_id, digest_hex) WHERE pin_state <> 'RELEASED';
CREATE INDEX cas_publication_pins_maintenance_idx
    ON cas_object_publication_pins (organization_id, pin_state, updated_at);
ALTER TABLE cas_object_publication_pins ENABLE ROW LEVEL SECURITY;
ALTER TABLE cas_object_publication_pins FORCE ROW LEVEL SECURITY;
CREATE POLICY cas_object_publication_pins_tenant_isolation ON cas_object_publication_pins
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
REVOKE ALL ON TABLE cas_object_publication_pins FROM PUBLIC;

-- Enforce the GC fence for direct SQL callers as well as JdbcCasCatalog.
CREATE FUNCTION public.elmos_guard_cas_deletion_publication_pin()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.deletion_state IN ('PENDING', 'OUTCOME_UNKNOWN') THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_object_lifecycle_lock_key(NEW.organization_id, NEW.digest_hex), 0));
        IF EXISTS (SELECT 1 FROM public.cas_object_publication_pins pin
                    WHERE pin.organization_id = NEW.organization_id AND pin.digest_hex = NEW.digest_hex
                      AND pin.pin_state <> 'RELEASED') THEN
            RAISE EXCEPTION 'CAS deletion is blocked by an active or unreconciled publication';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER cas_object_deletion_publication_pin_guard
BEFORE INSERT OR UPDATE ON cas_object_deletion_tombstones
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_deletion_publication_pin();

CREATE FUNCTION public.elmos_guard_cas_publication_pin_transition()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.pin_state <> 'RELEASED' THEN
            RAISE EXCEPTION 'CAS publication pin cannot be pruned before safe release';
        END IF;
        RETURN OLD;
    END IF;
    IF (NEW.organization_id, NEW.publication_id, NEW.digest_hex, NEW.size_bytes,
        NEW.tenant_epoch, NEW.resource_kind, NEW.resource_id, NEW.resource_epoch, NEW.created_at, NEW.lease_expires_at)
       IS DISTINCT FROM
       (OLD.organization_id, OLD.publication_id, OLD.digest_hex, OLD.size_bytes,
        OLD.tenant_epoch, OLD.resource_kind, OLD.resource_id, OLD.resource_epoch, OLD.created_at, OLD.lease_expires_at)
       OR OLD.pin_state = 'RELEASED'
       OR NEW.pin_state NOT IN ('OUTCOME_UNKNOWN', 'RELEASED')
       OR (OLD.pin_state = 'OUTCOME_UNKNOWN' AND NEW.pin_state <> 'RELEASED') THEN
        RAISE EXCEPTION 'CAS publication pin identity and terminal history are immutable';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER cas_publication_pin_transition_guard
BEFORE UPDATE OR DELETE ON cas_object_publication_pins
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_publication_pin_transition();
