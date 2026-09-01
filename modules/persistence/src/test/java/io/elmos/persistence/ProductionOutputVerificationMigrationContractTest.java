package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

/** Cheap structural guard for the fail-closed production output receipt. */
class ProductionOutputVerificationMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V81__production_output_verification_receipts.sql");

    @Test
    void bindsReceiptToTenantWorkItemAttemptAndImmutableArtifactDigest() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("FOREIGN KEY (tenant_id, work_item_id, attempt_id)"));
        assertTrue(sql.contains("UNIQUE (attempt_id)"));
        assertTrue(sql.contains("artifact_sha256 ~ '^[0-9a-f]{64}$'"));
        assertTrue(sql.contains("checks <> '{}'::jsonb"));
    }

    @Test
    void rejectsCertificationClaimsAndEnforcesTenantIsolation() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("certification_status = 'NOT_CERTIFIED'"));
        assertTrue(sql.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("tenant_id = public.current_tenant_id()"));
        assertTrue(sql.contains("sql-dialect-routine-conversion-v1"));
    }
}
