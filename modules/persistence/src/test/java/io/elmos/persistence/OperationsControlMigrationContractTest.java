package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OperationsControlMigrationContractTest {
    @Test
    void migrationSeparatesRetentionManagedTelemetryFromImmutableAudit() throws Exception {
        Path migration = Path.of(
                System.getProperty("basedir"),
                "src", "main", "resources", "db", "migration",
                "V51__production_operations_control.sql");
        String sql = Files.readString(migration);

        for (String table : new String[] {
                "product_telemetry_events",
                "operations_slo_policies",
                "operations_alerts",
                "operations_incidents",
                "operations_remediation_proposals",
                "operations_workflow_events",
                "operations_notification_outbox",
                "operations_retention_runs"
        }) {
            assertTrue(sql.contains("CREATE TABLE " + table), table);
        }
        assertTrue(sql.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("operations_workflow_events_append_only"));
        assertTrue(sql.contains("operations_retention_runs_append_only"));
        assertTrue(sql.contains("Raw source, prompts, input values"));
        assertFalse(sql.contains("DROP TABLE audit_events"));
        assertFalse(sql.contains("DELETE FROM audit_events"));
    }
}
