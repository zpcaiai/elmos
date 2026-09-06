package io.elmos.persistence;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** Host-internal V87 adapter. No caller-selected tenant and no provider I/O in JDBC transactions. */
public final class JdbcTenantObjectRetentionStore {
    public static final int MAX_TENANTS = 8;
    public static final int METADATA_BUDGET = 256;
    public static final int DELETE_BUDGET = 128;

    private final JdbcClient jdbc;
    private final TransactionTemplate transactions;

    public JdbcTenantObjectRetentionStore(JdbcClient jdbc, TransactionTemplate transactions) {
        this.jdbc = Objects.requireNonNull(jdbc);
        this.transactions = new TransactionTemplate(Objects.requireNonNull(transactions.getTransactionManager()));
        // V86 rechecks roots with a fresh command snapshot after taking the object lock.
        this.transactions.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
    }

    public record Purge(String runId, String organizationId, String contentObjectId,
                        String contentSha256, String backendId, String storageKey) { }

    /** Return normally ONLY after an exact provider DELETE was confirmed (2xx/404). */
    @FunctionalInterface public interface ConfirmedDeleter {
        void delete(Purge purge);
    }

    public record RoundResult(int attempted, int confirmed, int unknown) { }

    public RoundResult collect(ConfirmedDeleter deleter) {
        Objects.requireNonNull(deleter);
        requireNoTransaction();
        List<Purge> pending = transactions.execute(status -> jdbc.sql("""
                SELECT * FROM elmos_object_gc_host_prepare(:round,:tenants,:metadata,:deletes)
                """).param("round", UUID.randomUUID().toString()).param("tenants", MAX_TENANTS)
                .param("metadata", METADATA_BUDGET).param("deletes", DELETE_BUDGET)
                .query((row, index) -> new Purge(row.getString("run_id"),row.getString("organization_id"),
                        row.getString("content_object_id"),row.getString("content_sha256"),
                        row.getString("backend_id"),row.getString("storage_key"))).list());
        int confirmed = 0;
        int unknown = 0;
        for (Purge purge : Objects.requireNonNull(pending)) {
            // A REQUIRED/ambient transaction would keep its connection during provider I/O.
            requireNoTransaction();
            try {
                deleter.delete(purge);
            } catch (RuntimeException providerFailure) {
                unknown++;
                transactions.executeWithoutResult(status -> jdbc.sql(
                        "SELECT elmos_object_gc_host_unknown(:run,:object)")
                        .param("run",purge.runId()).param("object",purge.contentObjectId()).query(Boolean.class).single());
                continue;
            }
            // If this commit fails, leave the exact item unresolved. Never retry
            // a metadata transaction around the external call or invent success.
            Boolean accepted = transactions.execute(status -> jdbc.sql("""
                    SELECT elmos_object_gc_host_confirm(:run,:object,:org,:sha,:backend,:key)
                    """).param("run",purge.runId()).param("object",purge.contentObjectId())
                    .param("org",purge.organizationId()).param("sha",purge.contentSha256())
                    .param("backend",purge.backendId()).param("key",purge.storageKey()).query(Boolean.class).single());
            if (!Boolean.TRUE.equals(accepted)) {
                throw new IllegalStateException("ELMOS_OBJECT_GC_HOST_CONFIRM_UNACKNOWLEDGED");
            }
            confirmed++;
        }
        return new RoundResult(pending.size(), confirmed, unknown);
    }

    private static void requireNoTransaction() {
        if (TransactionSynchronizationManager.isActualTransactionActive()
                || TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException("ELMOS_OBJECT_GC_PROVIDER_REQUIRES_NO_TRANSACTION");
        }
    }
}
