package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class GithubWebhookTenantRouteMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V71__github_webhook_tenant_routes.sql");

    @Test void resolverUsesPrivateActiveInstallationAndRepositoryRoutes() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("github_webhook_installation_tenant_routes"));
        assertTrue(sql.contains("github_webhook_repository_tenant_routes"));
        assertTrue(sql.contains("REVOKE ALL ON TABLE github_webhook_installation_tenant_routes FROM PUBLIC"));
        assertTrue(sql.contains("REVOKE ALL ON TABLE github_webhook_repository_tenant_routes FROM PUBLIC"));
        assertTrue(sql.contains("elmos_sync_github_installation_tenant_route"));
        assertTrue(sql.contains("elmos_sync_github_repository_tenant_route"));
        assertTrue(sql.contains("elmos_resolve_github_webhook_organization"));
        assertTrue(sql.contains("installation_route.active"));
        assertTrue(sql.contains("repository_route.active"));
        assertTrue(sql.contains("resource identities cross tenant boundaries"));
        assertTrue(sql.contains("SECURITY DEFINER"));
        assertTrue(sql.contains("SET search_path = pg_catalog, public"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION"));
    }
}
