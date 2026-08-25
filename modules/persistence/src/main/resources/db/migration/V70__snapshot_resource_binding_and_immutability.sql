-- Bind every snapshot row to the repository's tenant, then make immutable snapshot identity and
-- content append-preserving.  Runtime callers may perform only the explicit AVAILABLE -> ARCHIVED
-- lifecycle transition; even an over-privileged owner cannot rewrite content or delete history.

-- V9 introduced tenant columns on the original V2 SCM child tables.  Repair those historical
-- placeholders from their authoritative parents before enforcing resource binding.  Any
-- cross-tenant installation/repository chain deliberately makes this migration fail instead of
-- silently selecting one tenant.
ALTER TABLE github_app_installations NO FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repositories NO FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_connections NO FORCE ROW LEVEL SECURITY;
ALTER TABLE repositories NO FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repository_permissions NO FORCE ROW LEVEL SECURITY;
ALTER TABLE github_app_onboarding_states NO FORCE ROW LEVEL SECURITY;
ALTER TABLE repository_snapshots NO FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM scm_repositories sr
          JOIN github_app_installations gi
            ON gi.installation_id = sr.installation_id
          JOIN scm_connections sc
            ON sc.connection_id = gi.connection_id
          JOIN repositories r
            ON r.repository_id = sr.repository_id
         WHERE sc.organization_id IS DISTINCT FROM r.organization_id
    ) THEN
        RAISE EXCEPTION 'SCM installation and repository tenant bindings conflict';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM github_app_onboarding_states onboarding
          LEFT JOIN scm_connections connection
            ON connection.connection_id = onboarding.connection_id
         WHERE connection.connection_id IS NULL
            OR connection.organization_id IS DISTINCT FROM onboarding.organization_id
    ) THEN
        RAISE EXCEPTION 'GitHub onboarding state and connection tenant bindings conflict';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM repository_snapshots snapshot
          LEFT JOIN repositories repository
            ON repository.repository_id = snapshot.repository_id
         WHERE repository.repository_id IS NULL
            OR repository.organization_id IS DISTINCT FROM snapshot.organization_id
    ) THEN
        RAISE EXCEPTION 'snapshot and repository tenant bindings conflict';
    END IF;
    IF EXISTS (
        SELECT 1 FROM repository_snapshots
         WHERE status NOT IN ('AVAILABLE', 'ARCHIVED')
    ) THEN
        RAISE EXCEPTION 'repository snapshot has an unsupported historical lifecycle status';
    END IF;
END;
$$;

UPDATE github_app_installations gi
   SET organization_id = sc.organization_id
  FROM scm_connections sc
 WHERE sc.connection_id = gi.connection_id
   AND gi.organization_id IS DISTINCT FROM sc.organization_id;

UPDATE scm_repositories sr
   SET organization_id = r.organization_id
  FROM repositories r
 WHERE r.repository_id = sr.repository_id
   AND sr.organization_id IS DISTINCT FROM r.organization_id;

UPDATE scm_repository_permissions permission
   SET organization_id = sr.organization_id
  FROM scm_repositories sr
 WHERE sr.scm_repository_id = permission.scm_repository_id
   AND permission.organization_id IS DISTINCT FROM sr.organization_id;

ALTER TABLE github_app_installations FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repositories FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_connections FORCE ROW LEVEL SECURITY;
ALTER TABLE repositories FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repository_permissions FORCE ROW LEVEL SECURITY;
ALTER TABLE github_app_onboarding_states FORCE ROW LEVEL SECURITY;
ALTER TABLE repository_snapshots FORCE ROW LEVEL SECURITY;

ALTER TABLE scm_connections
    ADD CONSTRAINT scm_connections_organization_connection_uq
    UNIQUE (organization_id, connection_id);

ALTER TABLE github_app_installations
    ADD CONSTRAINT github_app_installations_organization_installation_uq
    UNIQUE (organization_id, installation_id);

ALTER TABLE scm_repositories
    ADD CONSTRAINT scm_repositories_organization_scm_repository_uq
    UNIQUE (organization_id, scm_repository_id);

ALTER TABLE github_app_installations
    ADD CONSTRAINT github_app_installations_organization_connection_fk
    FOREIGN KEY (organization_id, connection_id)
    REFERENCES scm_connections(organization_id, connection_id);

ALTER TABLE scm_repositories
    ADD CONSTRAINT scm_repositories_organization_repository_fk
    FOREIGN KEY (organization_id, repository_id)
    REFERENCES repositories(organization_id, repository_id);

ALTER TABLE scm_repositories
    ADD CONSTRAINT scm_repositories_organization_installation_fk
    FOREIGN KEY (organization_id, installation_id)
    REFERENCES github_app_installations(organization_id, installation_id);

ALTER TABLE github_app_onboarding_states
    ADD CONSTRAINT github_app_onboarding_states_organization_connection_fk
    FOREIGN KEY (organization_id, connection_id)
    REFERENCES scm_connections(organization_id, connection_id);

ALTER TABLE scm_repository_permissions
    ADD CONSTRAINT scm_repository_permissions_organization_repository_fk
    FOREIGN KEY (organization_id, scm_repository_id)
    REFERENCES scm_repositories(organization_id, scm_repository_id);

ALTER TABLE repository_snapshots
    ADD CONSTRAINT repository_snapshots_organization_repository_fk
    FOREIGN KEY (organization_id, repository_id)
    REFERENCES repositories(organization_id, repository_id);

ALTER TABLE repository_snapshots
    ADD CONSTRAINT repository_snapshots_status_ck
    CHECK (status IN ('AVAILABLE', 'ARCHIVED'));

CREATE FUNCTION enforce_repository_snapshot_lifecycle()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'AVAILABLE' THEN
            RAISE EXCEPTION 'repository snapshot must start available';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'repository snapshots are append-preserving';
    END IF;
    IF (to_jsonb(NEW) - 'status') IS DISTINCT FROM
       (to_jsonb(OLD) - 'status') THEN
        RAISE EXCEPTION 'repository snapshot identity and content are immutable';
    END IF;
    IF NEW.status = OLD.status THEN
        RETURN NEW;
    END IF;
    IF OLD.status <> 'AVAILABLE' OR NEW.status <> 'ARCHIVED' THEN
        RAISE EXCEPTION 'invalid repository snapshot lifecycle transition';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER repository_snapshot_lifecycle
BEFORE INSERT OR UPDATE OR DELETE ON repository_snapshots
FOR EACH ROW EXECUTE FUNCTION enforce_repository_snapshot_lifecycle();
