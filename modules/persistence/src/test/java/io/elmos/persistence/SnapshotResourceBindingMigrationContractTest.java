package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotResourceBindingMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V70__snapshot_resource_binding_and_immutability.sql");

    @Test void migrationBindsTenantRepositoryAndMakesSnapshotContentAppendPreserving()
            throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("ALTER TABLE github_app_installations NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_repositories NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_connections NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE repositories NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_repository_permissions NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE github_app_onboarding_states NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE repository_snapshots NO FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("SCM installation and repository tenant bindings conflict"));
        assertTrue(sql.contains("GitHub onboarding state and connection tenant bindings conflict"));
        assertTrue(sql.contains("snapshot and repository tenant bindings conflict"));
        assertTrue(sql.contains("repository snapshot has an unsupported historical lifecycle status"));
        assertTrue(sql.contains("UPDATE github_app_installations gi"));
        assertTrue(sql.contains("SET organization_id = sc.organization_id"));
        assertTrue(sql.contains("UPDATE scm_repositories sr"));
        assertTrue(sql.contains("SET organization_id = r.organization_id"));
        assertTrue(sql.contains("ALTER TABLE github_app_installations FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_repositories FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_connections FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE repositories FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE scm_repository_permissions FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE github_app_onboarding_states FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("ALTER TABLE repository_snapshots FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("UPDATE scm_repository_permissions permission"));
        assertTrue(sql.contains("FOREIGN KEY (organization_id, connection_id)"));
        assertTrue(sql.contains("REFERENCES scm_connections(organization_id, connection_id)"));
        assertTrue(sql.contains("REFERENCES github_app_installations(organization_id, installation_id)"));
        assertTrue(sql.contains("github_app_onboarding_states_organization_connection_fk"));
        assertTrue(sql.contains("scm_repository_permissions_organization_repository_fk"));
        assertTrue(sql.contains("FOREIGN KEY (organization_id, repository_id)"));
        assertTrue(sql.contains("REFERENCES repositories(organization_id, repository_id)"));
        assertTrue(sql.contains("repository_snapshots_status_ck"));
        assertTrue(sql.contains("CHECK (status IN ('AVAILABLE', 'ARCHIVED'))"));
        assertTrue(sql.contains("NEW.status <> 'AVAILABLE'"));
        assertTrue(sql.contains("to_jsonb(NEW) - 'status'"));
        assertTrue(sql.contains("OLD.status <> 'AVAILABLE' OR NEW.status <> 'ARCHIVED'"));
        assertTrue(sql.contains("repository snapshots are append-preserving"));
        assertTrue(sql.contains("BEFORE INSERT OR UPDATE OR DELETE ON repository_snapshots"));
    }
}
