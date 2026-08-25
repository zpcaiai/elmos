-- Prevent a live CAS reference from racing a physical delete.
--
-- The tombstone is committed before bytes are touched. Root activation and legal-hold
-- publication acquire the same tenant/digest advisory lock and reject every unresolved
-- tombstone. PENDING and OUTCOME_UNKNOWN are persistent fences: a publisher must fail before
-- writing bytes. Only a terminal DELETED/MISSING/FAILED row may be removed while the publisher
-- owns the lock and after it has re-established authoritative bytes; if its transaction rolls
-- back, the tombstone remains.

ALTER TABLE cas_deletion_manifests
    DROP CONSTRAINT cas_deletion_manifests_dry_run_reclaims_nothing;
ALTER TABLE cas_deletion_manifests
    ADD CONSTRAINT cas_deletion_manifests_dry_run_reclaims_nothing CHECK (
        dry_run = false OR (reclaimed_bytes = 0 AND collected_objects = 0)
    );

CREATE TABLE cas_object_deletion_tombstones (
    organization_id varchar(64) NOT NULL,
    digest_hex varchar(64) NOT NULL
        CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    deletion_state varchar(24) NOT NULL
        CHECK (deletion_state IN (
            'PENDING', 'DELETED', 'MISSING', 'FAILED', 'OUTCOME_UNKNOWN')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, digest_hex),
    FOREIGN KEY (organization_id, digest_hex)
        REFERENCES cas_object_catalog (organization_id, digest_hex),
    CONSTRAINT cas_object_deletion_tombstone_time_ck CHECK (updated_at >= created_at)
);

CREATE INDEX cas_object_deletion_tombstone_state_idx
    ON cas_object_deletion_tombstones (deletion_state, updated_at);

ALTER TABLE cas_object_deletion_tombstones ENABLE ROW LEVEL SECURITY;
ALTER TABLE cas_object_deletion_tombstones FORCE ROW LEVEL SECURITY;
CREATE POLICY cas_object_deletion_tombstones_tenant_isolation
ON cas_object_deletion_tombstones
USING (organization_id = current_setting('app.organization_id', true))
WITH CHECK (organization_id = current_setting('app.organization_id', true));

REVOKE ALL ON TABLE cas_object_deletion_tombstones FROM PUBLIC;

-- Resource bindings are deliberately longer lived than any one snapshot.  Their lifecycle is
-- therefore an explicit, epoch-bound state machine rather than a side effect of root release.
CREATE TABLE cas_tenant_lifecycles (
    organization_id varchar(64) PRIMARY KEY,
    tenant_epoch bigint NOT NULL CHECK (tenant_epoch >= 1),
    lifecycle_state varchar(16) NOT NULL
        CHECK (lifecycle_state IN ('ACTIVE', 'RETIRING', 'RETIRED')),
    transitioned_at timestamptz NOT NULL
);

INSERT INTO cas_tenant_lifecycles (
    organization_id, tenant_epoch, lifecycle_state, transitioned_at)
SELECT organization_id, 1, 'ACTIVE', min(created_at)
  FROM cas_object_catalog
 GROUP BY organization_id;

CREATE TABLE cas_resource_lifecycles (
    organization_id varchar(64) NOT NULL,
    resource_kind varchar(16) NOT NULL
        CHECK (resource_kind IN ('REPOSITORY', 'PROJECT')),
    resource_id varchar(128) NOT NULL CHECK (btrim(resource_id) <> ''),
    tenant_epoch bigint NOT NULL CHECK (tenant_epoch >= 1),
    resource_epoch bigint NOT NULL CHECK (resource_epoch >= 1),
    lifecycle_state varchar(16) NOT NULL
        CHECK (lifecycle_state IN ('ACTIVE', 'RETIRING', 'RETIRED')),
    transitioned_at timestamptz NOT NULL,
    released_binding_count bigint NOT NULL DEFAULT 0
        CHECK (released_binding_count >= 0),
    PRIMARY KEY (organization_id, resource_kind, resource_id),
    FOREIGN KEY (organization_id)
        REFERENCES cas_tenant_lifecycles (organization_id)
);

INSERT INTO cas_resource_lifecycles (
    organization_id, resource_kind, resource_id, tenant_epoch, resource_epoch,
    lifecycle_state, transitioned_at)
SELECT organization_id, resource_kind, resource_id, 1, 1, 'ACTIVE', min(bound_at)
  FROM cas_resource_bindings
 GROUP BY organization_id, resource_kind, resource_id;

ALTER TABLE cas_resource_bindings
    ADD COLUMN tenant_epoch bigint NOT NULL DEFAULT 1 CHECK (tenant_epoch >= 1),
    ADD COLUMN resource_epoch bigint NOT NULL DEFAULT 1 CHECK (resource_epoch >= 1);

-- New snapshot roots carry the authoritative resource edge.  Historical roots remain NULL and
-- conservatively block finalization when they overlap the resource's bindings.
ALTER TABLE cas_reference_roots
    ADD COLUMN resource_kind varchar(16)
        CHECK (resource_kind IS NULL OR resource_kind IN ('REPOSITORY', 'PROJECT')),
    ADD COLUMN resource_id varchar(128),
    ADD COLUMN tenant_epoch bigint CHECK (tenant_epoch IS NULL OR tenant_epoch >= 1),
    ADD COLUMN resource_epoch bigint CHECK (resource_epoch IS NULL OR resource_epoch >= 1),
    ADD CONSTRAINT cas_reference_roots_resource_edge_complete CHECK (
        (resource_kind IS NULL AND resource_id IS NULL
            AND tenant_epoch IS NULL AND resource_epoch IS NULL)
        OR
        (resource_kind IS NOT NULL AND btrim(resource_id) <> ''
            AND tenant_epoch IS NOT NULL AND resource_epoch IS NOT NULL)
    );

CREATE INDEX cas_reference_roots_active_resource_idx
    ON cas_reference_roots (
        organization_id, resource_kind, resource_id, tenant_epoch, resource_epoch)
    WHERE released_at IS NULL AND resource_kind IS NOT NULL;

ALTER TABLE cas_tenant_lifecycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cas_tenant_lifecycles FORCE ROW LEVEL SECURITY;
CREATE POLICY cas_tenant_lifecycles_tenant_isolation ON cas_tenant_lifecycles
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
REVOKE ALL ON TABLE cas_tenant_lifecycles FROM PUBLIC;

ALTER TABLE cas_resource_lifecycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cas_resource_lifecycles FORCE ROW LEVEL SECURITY;
CREATE POLICY cas_resource_lifecycles_tenant_isolation ON cas_resource_lifecycles
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
REVOKE ALL ON TABLE cas_resource_lifecycles FROM PUBLIC;

CREATE FUNCTION public.elmos_cas_tenant_lifecycle_lock_key(
    requested_organization_id varchar
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT 'elmos-cas-tenant-lifecycle/1' || chr(10) || requested_organization_id
$$;

CREATE FUNCTION public.elmos_cas_resource_lifecycle_lock_key(
    requested_organization_id varchar,
    requested_resource_kind varchar,
    requested_resource_id varchar
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT 'elmos-cas-resource-lifecycle/1' || chr(10)
        || requested_organization_id || chr(10)
        || requested_resource_kind || chr(10) || requested_resource_id
$$;

CREATE FUNCTION public.elmos_cas_object_lifecycle_lock_key(
    requested_organization_id varchar,
    requested_digest_hex varchar
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT 'elmos-cas-object-lifecycle/1' || chr(10)
        || requested_organization_id || chr(10) || requested_digest_hex
$$;

CREATE FUNCTION public.elmos_guard_cas_deletion_tombstone()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.deletion_state = 'PENDING' THEN
        IF TG_OP = 'UPDATE'
           AND OLD.deletion_state IN ('PENDING', 'OUTCOME_UNKNOWN') THEN
            RAISE EXCEPTION 'CAS deletion attempt is already active or ambiguous';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_object_lifecycle_lock_key(
                NEW.organization_id, NEW.digest_hex), 0));
        IF NOT EXISTS (
            SELECT 1
              FROM public.cas_object_catalog catalog_object
             WHERE catalog_object.organization_id = NEW.organization_id
               AND catalog_object.digest_hex = NEW.digest_hex
               AND catalog_object.size_bytes = NEW.size_bytes
               AND catalog_object.legal_hold = false
        ) OR EXISTS (
            SELECT 1
              FROM public.cas_reference_roots root
             WHERE root.organization_id = NEW.organization_id
               AND root.digest_hex = NEW.digest_hex
               AND root.size_bytes = NEW.size_bytes
               AND root.released_at IS NULL
        ) OR EXISTS (
            SELECT 1
              FROM public.cas_resource_bindings binding
             WHERE binding.organization_id = NEW.organization_id
               AND binding.digest_hex = NEW.digest_hex
               AND binding.released_at IS NULL
        ) THEN
            RAISE EXCEPTION 'CAS deletion tombstone requires an unreferenced exact object';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER cas_object_deletion_tombstone_guard
BEFORE INSERT OR UPDATE ON cas_object_deletion_tombstones
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_deletion_tombstone();

CREATE FUNCTION public.elmos_guard_cas_root_activation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.released_at IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_tenant_lifecycle_lock_key(NEW.organization_id), 0));
        IF NOT EXISTS (
            SELECT 1 FROM public.cas_tenant_lifecycles tenant_lifecycle
             WHERE tenant_lifecycle.organization_id = NEW.organization_id
               AND tenant_lifecycle.tenant_epoch = COALESCE(
                    NEW.tenant_epoch, tenant_lifecycle.tenant_epoch)
               AND tenant_lifecycle.lifecycle_state = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION 'CAS root activation requires an ACTIVE tenant incarnation';
        END IF;
        IF NEW.resource_kind IS NOT NULL THEN
            PERFORM pg_advisory_xact_lock(hashtextextended(
                public.elmos_cas_resource_lifecycle_lock_key(
                    NEW.organization_id, NEW.resource_kind, NEW.resource_id), 0));
            IF NOT EXISTS (
                SELECT 1 FROM public.cas_resource_lifecycles resource_lifecycle
                 WHERE resource_lifecycle.organization_id = NEW.organization_id
                   AND resource_lifecycle.resource_kind = NEW.resource_kind
                   AND resource_lifecycle.resource_id = NEW.resource_id
                   AND resource_lifecycle.tenant_epoch = NEW.tenant_epoch
                   AND resource_lifecycle.resource_epoch = NEW.resource_epoch
                   AND resource_lifecycle.lifecycle_state = 'ACTIVE'
            ) THEN
                RAISE EXCEPTION 'CAS root activation requires an ACTIVE resource incarnation';
            END IF;
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_object_lifecycle_lock_key(
                NEW.organization_id, NEW.digest_hex), 0));
        IF EXISTS (
            SELECT 1
              FROM public.cas_object_deletion_tombstones tombstone
             WHERE tombstone.organization_id = NEW.organization_id
               AND tombstone.digest_hex = NEW.digest_hex
        ) THEN
            RAISE EXCEPTION 'CAS root activation is blocked by unresolved deletion';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER cas_reference_roots_guard_activation
BEFORE INSERT OR UPDATE ON cas_reference_roots
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_root_activation();

CREATE FUNCTION public.elmos_guard_cas_resource_binding_activation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.released_at IS NULL THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_tenant_lifecycle_lock_key(NEW.organization_id), 0));
        IF NOT EXISTS (
            SELECT 1 FROM public.cas_tenant_lifecycles tenant_lifecycle
             WHERE tenant_lifecycle.organization_id = NEW.organization_id
               AND tenant_lifecycle.tenant_epoch = NEW.tenant_epoch
               AND tenant_lifecycle.lifecycle_state = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION 'CAS resource binding requires an ACTIVE tenant incarnation';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_resource_lifecycle_lock_key(
                NEW.organization_id, NEW.resource_kind, NEW.resource_id), 0));
        IF NOT EXISTS (
            SELECT 1 FROM public.cas_resource_lifecycles resource_lifecycle
             WHERE resource_lifecycle.organization_id = NEW.organization_id
               AND resource_lifecycle.resource_kind = NEW.resource_kind
               AND resource_lifecycle.resource_id = NEW.resource_id
               AND resource_lifecycle.tenant_epoch = NEW.tenant_epoch
               AND resource_lifecycle.resource_epoch = NEW.resource_epoch
               AND resource_lifecycle.lifecycle_state = 'ACTIVE'
        ) THEN
            RAISE EXCEPTION 'CAS resource binding requires an ACTIVE resource incarnation';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_object_lifecycle_lock_key(
                NEW.organization_id, NEW.digest_hex), 0));
        IF EXISTS (
            SELECT 1
              FROM public.cas_object_deletion_tombstones tombstone
             WHERE tombstone.organization_id = NEW.organization_id
               AND tombstone.digest_hex = NEW.digest_hex
        ) THEN
            RAISE EXCEPTION 'CAS resource binding is blocked by unresolved deletion';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER cas_resource_bindings_guard_activation
BEFORE INSERT OR UPDATE ON cas_resource_bindings
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_resource_binding_activation();

CREATE FUNCTION public.elmos_guard_cas_legal_hold_publication()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.legal_hold
       AND (TG_OP = 'INSERT' OR OLD.legal_hold = false) THEN
        -- Holds outrank retirement.  Take the tenant fence for ordering, but deliberately do not
        -- require ACTIVE: an investigator may place a hold while deletion is draining.
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_tenant_lifecycle_lock_key(NEW.organization_id), 0));
        PERFORM pg_advisory_xact_lock(hashtextextended(
            public.elmos_cas_object_lifecycle_lock_key(
                NEW.organization_id, NEW.digest_hex), 0));
        IF EXISTS (
            SELECT 1
              FROM public.cas_object_deletion_tombstones tombstone
             WHERE tombstone.organization_id = NEW.organization_id
               AND tombstone.digest_hex = NEW.digest_hex
        ) THEN
            RAISE EXCEPTION 'CAS legal hold is blocked by unresolved deletion';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER cas_object_catalog_guard_legal_hold
BEFORE INSERT OR UPDATE ON cas_object_catalog
FOR EACH ROW EXECUTE FUNCTION public.elmos_guard_cas_legal_hold_publication();
