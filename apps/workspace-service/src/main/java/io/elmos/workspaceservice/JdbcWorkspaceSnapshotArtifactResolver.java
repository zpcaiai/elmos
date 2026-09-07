package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceInfrastructurePorts;
import io.elmos.workspace.WorkspaceModels;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

/** Resolves one AVAILABLE archive only through its complete workspace resource binding. */
final class JdbcWorkspaceSnapshotArtifactResolver
        implements WorkspaceInfrastructurePorts.SnapshotArtifactResolver {

    static final String TENANT_SCOPE_SQL =
            "SELECT set_config('app.organization_id', ?, true)";
    static final String SNAPSHOT_SQL = """
            select snapshot.organization_id,
                   snapshot.repository_id,
                   migration.migration_run_id,
                   snapshot.snapshot_id,
                   snapshot.archive_artifact_ref,
                   snapshot.archive_sha256,
                   snapshot.archive_size
              from repository_snapshots snapshot
              join repositories repository
                on repository.organization_id = snapshot.organization_id
               and repository.repository_id = snapshot.repository_id
              join migration_runs migration
                on migration.organization_id = snapshot.organization_id
               and migration.snapshot_id = snapshot.snapshot_id
             where snapshot.organization_id = ?
               and snapshot.snapshot_id = ?
               and migration.migration_run_id = ?
               and snapshot.status = 'AVAILABLE'
            """;

    private final DataSource dataSource;

    JdbcWorkspaceSnapshotArtifactResolver(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    @Override
    public WorkspaceInfrastructurePorts.SnapshotArtifact resolve(
            WorkspaceModels.WorkspaceRequest request
    ) {
        Objects.requireNonNull(request, "request");
        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            boolean originalReadOnly = connection.isReadOnly();
            if (!originalAutoCommit) {
                throw new IllegalStateException(
                        "workspace snapshot lookup requires a fresh auto-commit connection");
            }
            Throwable failure = null;
            try {
                connection.setReadOnly(true);
                connection.setAutoCommit(false);
                bindTenant(connection, request.organizationId());
                WorkspaceInfrastructurePorts.SnapshotArtifact artifact =
                        findBoundSnapshot(connection, request);
                connection.commit();
                return artifact;
            } catch (SQLException sqlFailure) {
                failure = sqlFailure;
                rollback(connection, sqlFailure);
                throw new IllegalStateException(
                        "workspace snapshot lookup failed", sqlFailure);
            } catch (RuntimeException runtimeFailure) {
                failure = runtimeFailure;
                rollback(connection, runtimeFailure);
                throw runtimeFailure;
            } finally {
                restoreConnection(
                        connection, originalAutoCommit, originalReadOnly, failure);
            }
        } catch (SQLException connectionFailure) {
            throw new IllegalStateException(
                    "workspace snapshot database connection failed", connectionFailure);
        }
    }

    private static void bindTenant(Connection connection, String organizationId)
            throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(TENANT_SCOPE_SQL)) {
            statement.setString(1, organizationId);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()
                        || !organizationId.equals(result.getString(1))
                        || result.next()) {
                    throw new SecurityException(
                            "workspace snapshot tenant context was not established");
                }
            }
        }
    }

    private static WorkspaceInfrastructurePorts.SnapshotArtifact findBoundSnapshot(
            Connection connection,
            WorkspaceModels.WorkspaceRequest request
    ) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(SNAPSHOT_SQL)) {
            statement.setString(1, request.organizationId());
            statement.setString(2, request.snapshotId());
            statement.setString(3, request.migrationRunId());
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw unavailable();
                }
                WorkspaceInfrastructurePorts.SnapshotArtifact artifact =
                        new WorkspaceInfrastructurePorts.SnapshotArtifact(
                                result.getString("organization_id"),
                                result.getString("repository_id"),
                                result.getString("migration_run_id"),
                                result.getString("snapshot_id"),
                                result.getString("archive_artifact_ref"),
                                result.getString("archive_sha256"),
                                requiredSize(result.getObject("archive_size", Long.class)));
                if (result.next()) {
                    throw unavailable();
                }
                return artifact;
            }
        }
    }

    private static long requiredSize(Long size) {
        if (size == null) {
            throw unavailable();
        }
        return size;
    }

    private static void rollback(Connection connection, Throwable failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }

    private static void restoreConnection(
            Connection connection,
            boolean autoCommit,
            boolean readOnly,
            Throwable failure
    ) {
        SQLException restoreFailure = null;
        try {
            connection.setAutoCommit(autoCommit);
        } catch (SQLException autoCommitFailure) {
            restoreFailure = autoCommitFailure;
        }
        try {
            connection.setReadOnly(readOnly);
        } catch (SQLException readOnlyFailure) {
            if (restoreFailure == null) {
                restoreFailure = readOnlyFailure;
            } else {
                restoreFailure.addSuppressed(readOnlyFailure);
            }
        }
        if (restoreFailure != null) {
            if (failure != null) {
                failure.addSuppressed(restoreFailure);
            } else {
                throw new IllegalStateException(
                        "workspace snapshot connection state could not be restored",
                        restoreFailure);
            }
        }
    }

    private static SecurityException unavailable() {
        return new SecurityException(
                "snapshot is unavailable for authenticated workspace resource context");
    }
}
