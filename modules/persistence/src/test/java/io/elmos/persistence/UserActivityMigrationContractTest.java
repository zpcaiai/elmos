package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UserActivityMigrationContractTest {
    @Test
    void migrationExtendsTheExistingAppendOnlyTenantAuditChain() throws Exception {
        Path migration = Path.of(
                System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration",
                "V50__user_activity_observability.sql");
        String sql = Files.readString(migration);
        String auditFoundation = Files.readString(Path.of(
                System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration",
                "V9__enterprise_identity_tenant_and_private_execution.sql"));

        assertTrue(sql.contains("ALTER TABLE audit_events"));
        assertTrue(sql.contains("business_line varchar(64)"));
        assertTrue(sql.contains("session_id varchar(96)"));
        assertTrue(sql.contains("duration_ms integer"));
        assertTrue(sql.contains("error_code varchar(96)"));
        assertTrue(sql.contains("metadata jsonb"));
        assertTrue(sql.contains("idx_audit_events_org_occurred"));
        assertTrue(sql.contains("idx_audit_events_org_business_line"));
        assertTrue(sql.contains("idx_audit_events_org_result"));
        assertTrue(sql.contains("idx_audit_events_org_session"));
        assertTrue(sql.contains("input values, tokens, request bodies, query strings"));
        assertTrue(auditFoundation.contains(
                "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events"));
        assertFalse(sql.toLowerCase().contains("authorization varchar"));
        assertFalse(sql.toLowerCase().contains("cookie varchar"));
    }
}
