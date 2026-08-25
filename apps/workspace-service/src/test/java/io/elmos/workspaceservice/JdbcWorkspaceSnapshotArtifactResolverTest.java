package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceModels;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class JdbcWorkspaceSnapshotArtifactResolverTest {

    private DataSource dataSource;
    private Connection connection;
    private PreparedStatement tenantStatement;
    private PreparedStatement snapshotStatement;
    private ResultSet tenantResult;
    private ResultSet snapshotResult;
    private JdbcWorkspaceSnapshotArtifactResolver resolver;

    @BeforeEach
    void setUp() throws Exception {
        dataSource = mock(DataSource.class);
        connection = mock(Connection.class);
        tenantStatement = mock(PreparedStatement.class);
        snapshotStatement = mock(PreparedStatement.class);
        tenantResult = mock(ResultSet.class);
        snapshotResult = mock(ResultSet.class);
        when(dataSource.getConnection()).thenReturn(connection);
        when(connection.getAutoCommit()).thenReturn(true);
        when(connection.isReadOnly()).thenReturn(false);
        when(connection.prepareStatement(
                JdbcWorkspaceSnapshotArtifactResolver.TENANT_SCOPE_SQL))
                .thenReturn(tenantStatement);
        when(connection.prepareStatement(
                JdbcWorkspaceSnapshotArtifactResolver.SNAPSHOT_SQL))
                .thenReturn(snapshotStatement);
        when(tenantStatement.executeQuery()).thenReturn(tenantResult);
        when(snapshotStatement.executeQuery()).thenReturn(snapshotResult);
        when(tenantResult.next()).thenReturn(true, false);
        when(tenantResult.getString(1)).thenReturn("tenant-a");
        resolver = new JdbcWorkspaceSnapshotArtifactResolver(dataSource);
    }

    @Test
    void tenantScopePrecedesCompleteResourceBoundLookupAndCommits() throws Exception {
        availableSnapshot();

        var artifact = resolver.resolve(request());

        assertEquals("tenant-a", artifact.organizationId());
        assertEquals("repo-a", artifact.repositoryId());
        assertEquals("run-a", artifact.migrationRunId());
        assertEquals("snapshot-a", artifact.snapshotId());
        assertEquals("a".repeat(64), artifact.sha256());
        assertEquals(10, artifact.sizeBytes());

        var order = inOrder(connection, tenantStatement, snapshotStatement);
        order.verify(connection).setReadOnly(true);
        order.verify(connection).setAutoCommit(false);
        order.verify(connection).prepareStatement(
                JdbcWorkspaceSnapshotArtifactResolver.TENANT_SCOPE_SQL);
        order.verify(tenantStatement).setString(1, "tenant-a");
        order.verify(tenantStatement).executeQuery();
        order.verify(connection).prepareStatement(
                JdbcWorkspaceSnapshotArtifactResolver.SNAPSHOT_SQL);
        order.verify(snapshotStatement).setString(1, "tenant-a");
        order.verify(snapshotStatement).setString(2, "snapshot-a");
        order.verify(snapshotStatement).setString(3, "run-a");
        order.verify(snapshotStatement).executeQuery();
        order.verify(connection).commit();
        order.verify(connection).setAutoCommit(true);
        order.verify(connection).setReadOnly(false);
        verify(connection).close();
    }

    @Test
    void missingOrCrossBoundSnapshotRollsBackAndClearsConnectionState() throws Exception {
        when(snapshotResult.next()).thenReturn(false);

        assertThrows(SecurityException.class, () -> resolver.resolve(request()));

        verify(connection).rollback();
        verify(connection).setAutoCommit(true);
        verify(connection).setReadOnly(false);
        verify(connection).close();
    }

    @Test
    void tenantContextMismatchFailsBeforeSnapshotLookup() throws Exception {
        when(tenantResult.getString(1)).thenReturn("tenant-b");

        assertThrows(SecurityException.class, () -> resolver.resolve(request()));

        verify(connection).rollback();
        verify(connection).setAutoCommit(true);
        verify(connection).setReadOnly(false);
        verify(connection).close();
    }

    private void availableSnapshot() throws Exception {
        when(snapshotResult.next()).thenReturn(true, false);
        when(snapshotResult.getString("organization_id")).thenReturn("tenant-a");
        when(snapshotResult.getString("repository_id")).thenReturn("repo-a");
        when(snapshotResult.getString("migration_run_id")).thenReturn("run-a");
        when(snapshotResult.getString("snapshot_id")).thenReturn("snapshot-a");
        when(snapshotResult.getString("archive_artifact_ref"))
                .thenReturn("cas://sha256/" + "a".repeat(64) + "/10");
        when(snapshotResult.getString("archive_sha256")).thenReturn("a".repeat(64));
        when(snapshotResult.getObject("archive_size", Long.class)).thenReturn(10L);
    }

    private static WorkspaceModels.WorkspaceRequest request() {
        return new WorkspaceModels.WorkspaceRequest(
                "workspace-a", "tenant-a", "run-a", "snapshot-a", "java-21",
                "sha256:" + "b".repeat(64),
                new WorkspaceModels.ResourceLimits(
                        1, 1024, 64, 2048, Duration.ofMinutes(30)),
                "network-a", "correlation-a");
    }
}
