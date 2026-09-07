-- ELMOS V66: separate tenant object metadata from resource authorization and make
-- every persisted digest round-trip with its exact byte size.
--
-- This migration intentionally fails if a V65 provenance digest cannot be resolved
-- to a tenant-local catalog object. Writing size 0 (or guessing a size) would turn an
-- incomplete legacy row into apparently complete authorization metadata. Operators
-- must catalog the exact provenance object before retrying the migration.

-- V65 forces RLS even for the table owner. Flyway's schema owner needs a complete
-- tenant-spanning view for this one bounded backfill; the transaction restores FORCE
-- before commit, and any exception rolls the temporary change back with the migration.
ALTER TABLE cas_object_catalog NO FORCE ROW LEVEL SECURITY;

ALTER TABLE cas_object_catalog
    ADD COLUMN provenance_size_bytes bigint
        CHECK (provenance_size_bytes IS NULL OR provenance_size_bytes >= 0);

UPDATE cas_object_catalog target
   SET provenance_size_bytes = provenance.size_bytes
  FROM cas_object_catalog provenance
 WHERE target.organization_id = provenance.organization_id
   AND target.provenance_digest_hex = provenance.digest_hex
   AND target.provenance_digest_hex IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM cas_object_catalog
         WHERE provenance_digest_hex IS NOT NULL
           AND provenance_size_bytes IS NULL
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'CAS V66 cannot infer provenance size without the exact tenant-local provenance object',
            HINT = 'Catalog each referenced provenance object with its exact size before retrying V66.';
    END IF;
END;
$$;

ALTER TABLE cas_object_catalog
    ADD CONSTRAINT cas_object_catalog_provenance_digest_complete CHECK (
        (provenance_digest_hex IS NULL) = (provenance_size_bytes IS NULL)
    );

ALTER TABLE cas_reference_roots
    ADD CONSTRAINT cas_reference_roots_release_after_create CHECK (
        released_at IS NULL OR released_at >= created_at
    );

CREATE TABLE cas_resource_bindings (
    organization_id varchar(64) NOT NULL,
    resource_kind varchar(16) NOT NULL
        CHECK (resource_kind IN ('REPOSITORY', 'PROJECT')),
    resource_id varchar(128) NOT NULL CHECK (btrim(resource_id) <> ''),
    digest_hex varchar(64) NOT NULL
        CHECK (digest_hex ~ '^[0-9a-f]{64}$'),
    bound_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    PRIMARY KEY (organization_id, resource_kind, resource_id, digest_hex),
    FOREIGN KEY (organization_id, digest_hex)
        REFERENCES cas_object_catalog (organization_id, digest_hex) ON DELETE CASCADE,
    CONSTRAINT cas_resource_bindings_release_after_bind CHECK (
        released_at IS NULL OR released_at >= bound_at
    )
);

-- V65 named this column project_id, so it is migrated as PROJECT. It is not silently
-- reinterpreted as a repository authorization: deployments that historically stored a
-- repository ID in project_id must explicitly create a REPOSITORY binding after validating
-- that trusted resource identity.
INSERT INTO cas_resource_bindings (
    organization_id, resource_kind, resource_id, digest_hex, bound_at)
SELECT organization_id, 'PROJECT', project_id, digest_hex, created_at
  FROM cas_object_catalog;

ALTER TABLE cas_object_catalog DROP COLUMN project_id;
ALTER TABLE cas_object_catalog FORCE ROW LEVEL SECURITY;

CREATE INDEX cas_resource_bindings_resource_idx
    ON cas_resource_bindings (organization_id, resource_kind, resource_id)
    WHERE released_at IS NULL;
CREATE INDEX cas_resource_bindings_digest_idx
    ON cas_resource_bindings (organization_id, digest_hex)
    WHERE released_at IS NULL;

ALTER TABLE cas_resource_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE cas_resource_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY cas_b66_tenant_isolation ON cas_resource_bindings
    USING (organization_id = current_setting('app.organization_id', true))
    WITH CHECK (organization_id = current_setting('app.organization_id', true));
