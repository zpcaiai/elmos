-- GitHub delivers webhooks before an authenticated ELMOS principal exists. Resolve the tenant
-- only after signature verification through two minimal, migration-owned routing indexes. The
-- runtime role has EXECUTE on the resolver but no direct table privilege, so the global index
-- cannot become a general cross-tenant directory.

CREATE TABLE github_webhook_installation_tenant_routes (
    github_installation_id bigint PRIMARY KEY,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    active boolean NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE github_webhook_repository_tenant_routes (
    github_repository_id bigint PRIMARY KEY,
    github_installation_id bigint NOT NULL,
    organization_id varchar(64) NOT NULL REFERENCES organizations(organization_id),
    active boolean NOT NULL,
    updated_at timestamptz NOT NULL,
    FOREIGN KEY (github_installation_id)
        REFERENCES github_webhook_installation_tenant_routes(github_installation_id)
);

REVOKE ALL ON TABLE github_webhook_installation_tenant_routes FROM PUBLIC;
REVOKE ALL ON TABLE github_webhook_repository_tenant_routes FROM PUBLIC;

ALTER TABLE github_app_installations NO FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repositories NO FORCE ROW LEVEL SECURITY;

INSERT INTO github_webhook_installation_tenant_routes(
    github_installation_id, organization_id, active, updated_at)
SELECT github_installation_id, organization_id, status = 'ACTIVE', last_synced_at
  FROM github_app_installations;

INSERT INTO github_webhook_repository_tenant_routes(
    github_repository_id, github_installation_id, organization_id, active, updated_at)
SELECT repository.github_repository_id,
       installation.github_installation_id,
       repository.organization_id,
       repository.authorization_status = 'AUTHORIZED'
           AND NOT repository.archived
           AND NOT repository.disabled,
       repository.synced_at
  FROM scm_repositories repository
  JOIN github_app_installations installation
    ON installation.organization_id = repository.organization_id
   AND installation.installation_id = repository.installation_id;

ALTER TABLE github_app_installations FORCE ROW LEVEL SECURITY;
ALTER TABLE scm_repositories FORCE ROW LEVEL SECURITY;

CREATE FUNCTION public.elmos_sync_github_installation_tenant_route()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE public.github_webhook_installation_tenant_routes
           SET active = false, updated_at = now()
         WHERE github_installation_id = OLD.github_installation_id;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND NEW.github_installation_id IS DISTINCT FROM OLD.github_installation_id THEN
        UPDATE public.github_webhook_installation_tenant_routes
           SET active = false, updated_at = now()
         WHERE github_installation_id = OLD.github_installation_id;
    END IF;
    INSERT INTO public.github_webhook_installation_tenant_routes(
        github_installation_id, organization_id, active, updated_at)
    VALUES (
        NEW.github_installation_id, NEW.organization_id,
        NEW.status = 'ACTIVE', NEW.last_synced_at)
    ON CONFLICT (github_installation_id) DO UPDATE
        SET organization_id = excluded.organization_id,
            active = excluded.active,
            updated_at = excluded.updated_at;
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.elmos_sync_github_repository_tenant_route()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    installation_external_id bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE public.github_webhook_repository_tenant_routes
           SET active = false, updated_at = now()
         WHERE github_repository_id = OLD.github_repository_id;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE'
       AND NEW.github_repository_id IS DISTINCT FROM OLD.github_repository_id THEN
        UPDATE public.github_webhook_repository_tenant_routes
           SET active = false, updated_at = now()
         WHERE github_repository_id = OLD.github_repository_id;
    END IF;
    SELECT installation.github_installation_id
      INTO STRICT installation_external_id
      FROM public.github_app_installations installation
     WHERE installation.organization_id = NEW.organization_id
       AND installation.installation_id = NEW.installation_id;
    INSERT INTO public.github_webhook_repository_tenant_routes(
        github_repository_id, github_installation_id, organization_id, active, updated_at)
    VALUES (
        NEW.github_repository_id, installation_external_id, NEW.organization_id,
        NEW.authorization_status = 'AUTHORIZED' AND NOT NEW.archived AND NOT NEW.disabled,
        NEW.synced_at)
    ON CONFLICT (github_repository_id) DO UPDATE
        SET github_installation_id = excluded.github_installation_id,
            organization_id = excluded.organization_id,
            active = excluded.active,
            updated_at = excluded.updated_at;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.elmos_sync_github_installation_tenant_route() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.elmos_sync_github_repository_tenant_route() FROM PUBLIC;

CREATE TRIGGER github_installation_tenant_route_sync
AFTER INSERT OR UPDATE OR DELETE ON github_app_installations
FOR EACH ROW EXECUTE FUNCTION public.elmos_sync_github_installation_tenant_route();

CREATE TRIGGER github_repository_tenant_route_sync
AFTER INSERT OR UPDATE OR DELETE ON scm_repositories
FOR EACH ROW EXECUTE FUNCTION public.elmos_sync_github_repository_tenant_route();

CREATE FUNCTION public.elmos_resolve_github_webhook_organization(
    requested_installation_id bigint,
    requested_repository_id bigint
)
RETURNS varchar(64)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    installation_organization varchar(64);
    repository_organization varchar(64);
BEGIN
    IF requested_installation_id IS NULL AND requested_repository_id IS NULL THEN
        RAISE EXCEPTION 'GitHub webhook has no routable resource identity';
    END IF;
    IF requested_installation_id IS NOT NULL THEN
        SELECT route.organization_id
          INTO STRICT installation_organization
          FROM public.github_webhook_installation_tenant_routes route
         WHERE route.github_installation_id = requested_installation_id
           AND route.active;
    END IF;
    IF requested_repository_id IS NOT NULL THEN
        SELECT repository_route.organization_id
          INTO STRICT repository_organization
          FROM public.github_webhook_repository_tenant_routes repository_route
          JOIN public.github_webhook_installation_tenant_routes installation_route
            ON installation_route.github_installation_id =
               repository_route.github_installation_id
           AND installation_route.organization_id = repository_route.organization_id
           AND installation_route.active
         WHERE repository_route.github_repository_id = requested_repository_id
           AND repository_route.active;
    END IF;
    IF installation_organization IS NOT NULL
       AND repository_organization IS NOT NULL
       AND installation_organization IS DISTINCT FROM repository_organization THEN
        RAISE EXCEPTION 'GitHub webhook resource identities cross tenant boundaries';
    END IF;
    RETURN COALESCE(installation_organization, repository_organization);
EXCEPTION
    WHEN NO_DATA_FOUND OR TOO_MANY_ROWS THEN
        RAISE EXCEPTION 'GitHub webhook resource identity is unavailable';
END;
$$;

REVOKE ALL ON FUNCTION
    public.elmos_resolve_github_webhook_organization(bigint, bigint)
FROM PUBLIC;
