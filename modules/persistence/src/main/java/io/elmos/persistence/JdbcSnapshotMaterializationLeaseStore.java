package io.elmos.persistence;

import io.elmos.snapshot.SnapshotMaterializationLease;
import io.elmos.snapshot.SnapshotPorts;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Objects;

/** Least-privilege adapter for V72's exact snapshot materialization lease functions. */
@Repository
public class JdbcSnapshotMaterializationLeaseStore
        implements SnapshotMaterializationLease.Store {
    private final JdbcClient jdbc;

    public JdbcSnapshotMaterializationLeaseStore(JdbcClient jdbc) {
        this.jdbc = Objects.requireNonNull(jdbc, "jdbc");
    }

    @Override
    @Transactional
    public SnapshotMaterializationLease acquire(
            SnapshotPorts.ArtifactResourceContext resource,
            String snapshotId,
            String leaseId,
            String holderId,
            Duration duration
    ) {
        Objects.requireNonNull(resource, "resource");
        setTenant(resource.organizationId());
        return jdbc.sql("""
                select * from public.elmos_acquire_snapshot_materialization_lease(
                    cast(:organization as varchar), cast(:repository as varchar),
                    cast(:snapshot as varchar), cast(:lease as varchar),
                    cast(:holder as varchar), :duration)
                """)
                .param("organization", resource.organizationId())
                .param("repository", resource.repositoryId())
                .param("snapshot", snapshotId)
                .param("lease", leaseId)
                .param("holder", holderId)
                .param("duration", seconds(duration, 15, 3_600))
                .query(JdbcSnapshotMaterializationLeaseStore::map)
                .single();
    }

    @Override
    @Transactional
    public SnapshotMaterializationLease renew(
            SnapshotMaterializationLease lease,
            Duration duration
    ) {
        Objects.requireNonNull(lease, "lease");
        setTenant(lease.organizationId());
        return jdbc.sql("""
                select * from public.elmos_renew_snapshot_materialization_lease(
                    cast(:organization as varchar), cast(:repository as varchar),
                    cast(:snapshot as varchar), cast(:lease as varchar),
                    cast(:holder as varchar), :fence, :duration)
                """)
                .param("organization", lease.organizationId())
                .param("repository", lease.repositoryId())
                .param("snapshot", lease.snapshotId())
                .param("lease", lease.leaseId())
                .param("holder", lease.holderId())
                .param("fence", lease.fencingToken())
                .param("duration", seconds(duration, 15, 3_600))
                .query(JdbcSnapshotMaterializationLeaseStore::map)
                .single();
    }

    @Override
    @Transactional
    public SnapshotMaterializationLease requireActive(
            SnapshotMaterializationLease lease
    ) {
        Objects.requireNonNull(lease, "lease");
        setTenant(lease.organizationId());
        return jdbc.sql("""
                select * from public.elmos_require_active_snapshot_materialization_lease(
                    cast(:organization as varchar), cast(:repository as varchar),
                    cast(:snapshot as varchar), cast(:lease as varchar),
                    cast(:holder as varchar), :fence)
                """)
                .param("organization", lease.organizationId())
                .param("repository", lease.repositoryId())
                .param("snapshot", lease.snapshotId())
                .param("lease", lease.leaseId())
                .param("holder", lease.holderId())
                .param("fence", lease.fencingToken())
                .query(JdbcSnapshotMaterializationLeaseStore::map)
                .single();
    }

    @Override
    @Transactional
    public void release(SnapshotMaterializationLease lease) {
        Objects.requireNonNull(lease, "lease");
        setTenant(lease.organizationId());
        boolean released = jdbc.sql("""
                select public.elmos_release_snapshot_materialization_lease(
                    cast(:organization as varchar), cast(:repository as varchar),
                    cast(:snapshot as varchar), cast(:lease as varchar),
                    cast(:holder as varchar), :fence)
                """)
                .param("organization", lease.organizationId())
                .param("repository", lease.repositoryId())
                .param("snapshot", lease.snapshotId())
                .param("lease", lease.leaseId())
                .param("holder", lease.holderId())
                .param("fence", lease.fencingToken())
                .query(Boolean.class)
                .single();
        if (!released) {
            throw new IllegalStateException("snapshot materialization lease was not released");
        }
    }

    private static SnapshotMaterializationLease map(ResultSet result, int row)
            throws SQLException {
        return new SnapshotMaterializationLease(
                result.getString("lease_organization_id"),
                result.getString("lease_repository_id"),
                result.getString("lease_snapshot_id"),
                result.getString("lease_identifier"),
                result.getString("lease_holder_id"),
                result.getLong("lease_fencing_token"),
                result.getObject("lease_acquired_at", OffsetDateTime.class).toInstant(),
                result.getObject("lease_expires_at", OffsetDateTime.class).toInstant());
    }

    private static int seconds(Duration duration, int minimum, int maximum) {
        Objects.requireNonNull(duration, "duration");
        long seconds = duration.toSeconds();
        if (duration.getNano() != 0 || seconds < minimum || seconds > maximum) {
            throw new IllegalArgumentException("snapshot materialization lease duration is invalid");
        }
        return Math.toIntExact(seconds);
    }

    private void setTenant(String organizationId) {
        jdbc.sql("select set_config('app.organization_id', :organization, true)")
                .param("organization", organizationId)
                .query(String.class)
                .single();
    }
}
