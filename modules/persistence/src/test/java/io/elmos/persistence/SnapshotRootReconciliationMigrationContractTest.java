package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotRootReconciliationMigrationContractTest {
    private static String migration() throws Exception {
        Path root = Path.of(System.getProperty("basedir"), "src", "main", "resources",
                "db", "migration");
        return Files.readString(root.resolve(
                "V68__snapshot_root_reconciliation.sql"));
    }

    @Test void usesDedicatedTenantIsolatedStateInsteadOfOutboxPublication() throws Exception {
        String v68 = migration();
        assertTrue(v68.contains("CREATE TABLE snapshot_root_reconciliations"));
        assertTrue(v68.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(v68.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(v68.contains("current_setting('app.organization_id', true)"));
        assertFalse(v68.contains("outbox_events"));
        assertFalse(v68.contains("published_at"));
    }

    @Test void separatesLogicalIdempotencyFromUniqueAttempts() throws Exception {
        String v68 = migration();
        assertTrue(v68.contains("attempt_id varchar(64)"));
        assertTrue(v68.contains("logical_operation_id varchar(64)"));
        assertTrue(v68.contains("PRIMARY KEY (organization_id, attempt_id)"));
        assertTrue(v68.contains(
                "UNIQUE (organization_id, logical_operation_id, attempt_id)"));
        assertTrue(v68.contains("snapshot_root_reconciliation_operation_idx"));
    }

    @Test void phaseAndGenerationIdentityCannotBeRewrittenOrSkipped() throws Exception {
        String v68 = migration();
        assertTrue(v68.contains("retention_generations jsonb NOT NULL"));
        assertTrue(v68.contains("snapshot_root_reconciliation_payload_scope"));
        assertTrue(v68.contains("snapshot_root_reconciliation_payload_field_types"));
        assertTrue(v68.contains("snapshot_root_reconciliation_retention_identity"));
        assertTrue(v68.contains(
                "CREATE FUNCTION public.elmos_valid_snapshot_retention_generations"));
        assertTrue(v68.contains("generation_name !~ '^[a-z][a-z0-9.-]{0,63}$'"));
        assertTrue(v68.contains("generation_value::text::numeric > 9223372036854775807"));
        assertTrue(v68.contains("'{snapshot,treeSha}') ~ '^[0-9a-f]{40}$'"));
        assertTrue(v68.contains(
                "public.elmos_valid_snapshot_retention_generations(retention_generations)"));
        assertTrue(v68.contains("snapshot_root_reconciliation_durable_shape"));
        assertTrue(v68.contains("snapshot_root_reconciliation_time_identity"));
        assertTrue(v68.contains("updated_at >= recorded_at"));
        assertTrue(v68.contains("enforce_snapshot_root_reconciliation_transition"));
        assertTrue(v68.contains("snapshot root reconciliation identity is immutable"));
        assertTrue(v68.contains("OLD.phase = 'PENDING'"));
        assertTrue(v68.contains("NEW.phase = 'RESOLVED'"));
        assertTrue(v68.contains("NEW IS DISTINCT FROM OLD"));
        assertTrue(v68.contains("NEW.durable_snapshot_id IS DISTINCT FROM OLD.durable_snapshot_id"));
        assertTrue(v68.contains("OLD.resolved_at IS NOT NULL OR NEW.resolved_at IS NULL"));
    }

    @Test void missingJsonIdentityCannotPassAsSqlUnknown() throws Exception {
        String v68 = migration();
        assertTrue(v68.contains(
                "snapshot_root_reconciliation_payload_required_keys"));
        assertTrue(v68.contains(
                "'snapshot', 'retention', 'durableSnapshotId', 'recordedAt'"));
        assertTrue(v68.contains(
                "'manifestSha256', 'snapshotSchemaVersion', 'status', 'capturedAt'"));
        assertTrue(v68.contains(
                "'snapshotId', 'generations'"));
        assertTrue(v68.contains(
                "IS NOT DISTINCT FROM organization_id"));
        assertTrue(v68.contains(
                "IS NOT DISTINCT FROM logical_operation_id"));
        assertTrue(v68.contains(
                "IS NOT DISTINCT FROM reconciliation_kind"));
        assertTrue(v68.contains(
                "IS NOT DISTINCT FROM retention_generations"));
        assertFalse(v68.contains(
                "coalesce(reconciliation_payload ->> 'durableSnapshotId', '')"));
    }

    @Test void everyJournalRowMustEnterThroughPendingPhase() throws Exception {
        String v68 = migration();
        assertTrue(v68.contains("IF TG_OP = 'INSERT' THEN"));
        assertTrue(v68.contains("NEW.phase <> 'PENDING'"));
        assertTrue(v68.contains("NEW.durable_snapshot_id IS NOT NULL"));
        assertTrue(v68.contains("NEW.resolved_at IS NOT NULL"));
        assertTrue(v68.contains(
                "NEW.updated_at IS DISTINCT FROM NEW.recorded_at"));
        assertTrue(v68.contains(
                "BEFORE INSERT OR UPDATE OR DELETE ON snapshot_root_reconciliations"));
    }

    @Test void repositoryAndDurableSnapshotForeignKeysIncludeTenantScope()
            throws Exception {
        String v68 = migration();
        assertTrue(v68.contains(
                "UNIQUE (organization_id, repository_id)"));
        assertTrue(v68.contains(
                "UNIQUE (organization_id, repository_id, snapshot_id)"));
        assertTrue(v68.contains(
                "FOREIGN KEY (organization_id, repository_id)"));
        assertTrue(v68.contains(
                "FOREIGN KEY (organization_id, repository_id, durable_snapshot_id)"));
    }
}
