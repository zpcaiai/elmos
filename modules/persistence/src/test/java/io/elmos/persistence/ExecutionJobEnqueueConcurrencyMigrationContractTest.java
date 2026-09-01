package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

/** Deterministic guard for the forward-only V80 hosted-queue admission repair. */
class ExecutionJobEnqueueConcurrencyMigrationContractTest {

    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V80__execution_job_enqueue_concurrency.sql");

    @Test
    void serializesIdempotencyAndCapacityWithoutDroppingWalletOrTenantGuards() throws Exception {
        String sql = Files.readString(MIGRATION);

        int tenantGuard = sql.indexOf("ELMOS_EXECUTION_TENANT_CONTEXT_MISMATCH");
        int tenantBinding = sql.indexOf("set_config('app.organization_id'");
        int advisoryLock = sql.indexOf("pg_advisory_xact_lock");
        int idempotencyLookup = sql.indexOf("SELECT * INTO v_existing");
        int counterLock = sql.indexOf("INTO STRICT v_queued");
        int capacityDecision = sql.indexOf("ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED");
        int walletAdmission = sql.indexOf("elmos_wallet_admit_job");
        int jobInsert = sql.indexOf("INSERT INTO public.execution_jobs");
        int counterIncrement = sql.indexOf("SET queued_count = c.queued_count + 1");

        assertTrue(tenantGuard >= 0 && tenantGuard < tenantBinding);
        assertTrue(tenantBinding < advisoryLock);
        assertTrue(advisoryLock < idempotencyLookup,
                "the missing-row idempotency decision must happen inside the tenant lock");
        assertTrue(idempotencyLookup < counterLock);
        assertTrue(counterLock < capacityDecision,
                "capacity must be checked while the tenant counter row is locked");
        assertTrue(capacityDecision < walletAdmission && walletAdmission < jobInsert,
                "V74 wallet admission must remain after idempotency/capacity and before insertion");
        assertTrue(jobInsert < counterIncrement,
                "the counter increment and job rows must commit in the same transaction");
        assertTrue(sql.contains("FOR UPDATE"));
        assertTrue(sql.contains("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT"));
        assertTrue(sql.contains("ELMOS_EXECUTION_STORAGE_CONFLICT"));
        assertTrue(sql.contains("WHEN unique_violation"));
        assertTrue(sql.contains("REVOKE EXECUTE ON FUNCTION elmos_enqueue_execution_job"));
    }
}
