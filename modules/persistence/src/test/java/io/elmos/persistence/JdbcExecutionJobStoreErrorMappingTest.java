package io.elmos.persistence;

import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.Test;

import java.sql.SQLException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JdbcExecutionJobStoreErrorMappingTest {

    @Test
    void mapsRawUniqueViolationWithoutLeakingConstraintDetails() {
        RuntimeException raw = new RuntimeException("jdbc wrapper", new SQLException(
                "duplicate key value ELMOS_CALLER_CONTROLLED violates unique constraint "
                        + "execution_jobs_pkey",
                "23505"));

        RuntimeException translated = JdbcExecutionJobStore.translateDomainError(raw);

        assertTrue(translated instanceof ExecutionJobPort.ExecutionStateException);
        assertEquals("ELMOS_EXECUTION_STORAGE_CONFLICT",
                ((ExecutionJobPort.ExecutionStateException) translated).code());
        assertFalse(translated.getMessage().contains("execution_jobs_pkey"));
        assertFalse(translated.getMessage().contains("ELMOS_CALLER_CONTROLLED"));
    }

    @Test
    void extractsOnlyTheStableDomainCodeFromPostgresDetail() {
        RuntimeException raw = new RuntimeException(new SQLException(
                "ERROR: ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT\n"
                        + "  Where: PL/pgSQL function elmos_enqueue_execution_job",
                "P0001"));

        RuntimeException translated = JdbcExecutionJobStore.translateDomainError(raw);

        assertEquals("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT",
                ((ExecutionJobPort.ExecutionStateException) translated).code());
        assertFalse(translated.getMessage().contains("PL/pgSQL"));
    }

    @Test
    void preservesNonDomainNonUniqueFailures() {
        RuntimeException raw = new RuntimeException("connection unavailable");
        assertSame(raw, JdbcExecutionJobStore.translateDomainError(raw));
    }
}
