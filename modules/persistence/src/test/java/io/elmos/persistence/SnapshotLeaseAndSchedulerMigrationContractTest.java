package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SnapshotLeaseAndSchedulerMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/"
                    + "V72__snapshot_materialization_leases_and_global_reconciliation.sql");

    @Test void materializationLeaseIsTenantBoundDurableAndFenced() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CREATE TABLE snapshot_materialization_leases"));
        assertTrue(sql.contains("CREATE TABLE snapshot_materialization_fences"));
        assertTrue(sql.contains("fencing_token bigint NOT NULL"));
        assertTrue(sql.contains("FOREIGN KEY (organization_id, repository_id, snapshot_id)"));
        assertTrue(sql.contains("ENABLE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("snapshot_materialization_lease_tenant_isolation"));
        assertTrue(sql.contains("current_setting('app.organization_id', true)"));
        assertTrue(sql.contains(
                "snapshot materialization tenant context is missing or conflicting"));
        assertTrue(sql.contains("released snapshot materialization lease is immutable"));
        assertTrue(sql.contains("snapshot materialization lease history is append-preserving"));
        assertTrue(sql.contains("EXPIRED_RECLAIM"));
        assertTrue(sql.contains("elmos_renew_snapshot_materialization_lease"));
        assertTrue(sql.contains("elmos_require_active_snapshot_materialization_lease"));
        assertTrue(sql.contains("requested_fencing_token"));
        assertFalse(sql.contains("GRANT SELECT ON TABLE snapshot_materialization"));
    }

    @Test void archiveAndAcquisitionSerializeOnTheSameSnapshotRow() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("FROM public.repository_snapshots snapshot"));
        assertTrue(sql.contains("FOR UPDATE"));
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION public.enforce_repository_snapshot_lifecycle"));
        assertTrue(sql.contains("snapshot has an active materialization lease"));
        assertTrue(sql.contains("lease.expires_at > clock_timestamp()"));
        assertTrue(sql.contains("USING ERRCODE = '55006'"));
    }

    @Test void globalSchedulerUsesPrivateBoundedSkipLockedFencedWork() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CREATE TABLE snapshot_reconciliation_tenant_work"));
        assertTrue(sql.contains("REVOKE ALL ON TABLE snapshot_reconciliation_tenant_work FROM PUBLIC"));
        assertTrue(sql.contains("FOR UPDATE SKIP LOCKED"));
        assertTrue(sql.contains("requested_limit > 64"));
        assertTrue(sql.contains("requested_lease_seconds > 900"));
        assertTrue(sql.contains("fencing_token = work.fencing_token + 1"));
        assertTrue(sql.contains("last_completed_fencing_token"));
        assertTrue(sql.contains("last_completed_by"));
        assertTrue(sql.contains(
                "current_work.last_completed_by IS NOT DISTINCT FROM requested_worker_id"));
        assertTrue(sql.contains("current_work.lease_until <= database_now"));
        assertTrue(sql.contains("snapshot_reconciliation_global_work_sync"));
        assertTrue(sql.contains("reconciliation.phase <> 'RESOLVED'"));
        assertTrue(sql.contains("requested_retry_seconds > 86400"));
    }

    @Test void callableSurfaceIsExactAndNotPublic() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("SECURITY DEFINER"));
        assertTrue(sql.contains("SET search_path = pg_catalog, public"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION public.elmos_acquire_snapshot_materialization_lease"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION public.elmos_release_snapshot_materialization_lease"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION public.elmos_claim_snapshot_reconciliation_work"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION public.elmos_complete_snapshot_reconciliation_work"));
    }
}
