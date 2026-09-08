package io.elmos.liveworkbench;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class LiveWorkbenchMigrationContractTest {
    private static final Path MIGRATION = Path.of("src/main/resources/db/migration/V83__live_workbench_production.sql");

    @Test void migrationPreservesTenantQuotaFencingEvidenceAndFixedWindow() throws Exception {
        String sql = Files.readString(MIGRATION);
        assertAll(
                () -> assertTrue(sql.contains("UNIQUE (tenant_id, account_id, idempotency_key)")),
                () -> assertTrue(sql.contains("expires_at_epoch = first_ready_at_epoch + 600")),
                () -> assertTrue(sql.contains("UNIQUE (tenant_id, session_id, idempotency_key)")),
                () -> assertTrue(sql.contains("PRIMARY KEY (tenant_id, session_id, generation, sequence)")),
                () -> assertTrue(sql.contains("FORCE ROW LEVEL SECURITY")),
                () -> assertTrue(sql.contains("lw_outbox")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_deliveries")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_source_anchors")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_claims")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_missions")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_attempts")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_resource_members")),
                () -> assertTrue(sql.contains("CREATE TABLE lw_cleanup_receipts")),
                () -> assertTrue(sql.contains("previous_hash")),
                () -> assertFalse(sql.toLowerCase().contains("drop table"))
        );
    }
}
