package io.elmos.persistence;

import io.elmos.snapshot.SnapshotReconciliationWorkQueue;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Objects;

/** JDBC adapter for the private, cross-tenant V72 reconciliation work queue. */
@Repository
public class JdbcSnapshotReconciliationWorkQueue
        implements SnapshotReconciliationWorkQueue {
    private final JdbcClient jdbc;

    public JdbcSnapshotReconciliationWorkQueue(JdbcClient jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Override
    @Transactional
    public List<WorkLease> claim(
            String workerId,
            int limit,
            Duration leaseDuration
    ) {
        return jdbc.sql("""
                select * from public.elmos_claim_snapshot_reconciliation_work(
                    cast(:worker as varchar), :limit, :duration)
                """)
                .param("worker", workerId)
                .param("limit", limit)
                .param("duration", seconds(leaseDuration, 15, 900))
                .query(JdbcSnapshotReconciliationWorkQueue::map)
                .list();
    }

    @Override
    @Transactional
    public boolean complete(
            WorkLease lease,
            boolean successful,
            Duration retryDelay
    ) {
        Objects.requireNonNull(lease, "lease");
        return jdbc.sql("""
                select public.elmos_complete_snapshot_reconciliation_work(
                    cast(:organization as varchar), cast(:worker as varchar),
                    :fence, :successful, :retry)
                """)
                .param("organization", lease.organizationId())
                .param("worker", lease.workerId())
                .param("fence", lease.fencingToken())
                .param("successful", successful)
                .param("retry", seconds(retryDelay, 0, 86_400))
                .query(Boolean.class)
                .single();
    }

    private static WorkLease map(ResultSet result, int row) throws SQLException {
        return new WorkLease(
                result.getString("work_organization_id"),
                result.getString("work_worker_id"),
                result.getLong("work_fencing_token"),
                result.getObject("work_expires_at", OffsetDateTime.class).toInstant());
    }

    private static int seconds(Duration duration, int minimum, int maximum) {
        Objects.requireNonNull(duration, "duration");
        long seconds = duration.toSeconds();
        if (duration.getNano() != 0 || seconds < minimum || seconds > maximum) {
            throw new IllegalArgumentException("snapshot reconciliation duration is invalid");
        }
        return Math.toIntExact(seconds);
    }
}
