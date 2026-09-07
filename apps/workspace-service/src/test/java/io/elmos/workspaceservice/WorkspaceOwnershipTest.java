package io.elmos.workspaceservice;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.simple.JdbcClient;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class WorkspaceOwnershipTest {
    private JdbcClient jdbc;
    private JdbcClient.MappedQuerySpec<String> query;
    private JdbcWorkspaceOwnership ownership;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        jdbc = mock(JdbcClient.class);
        JdbcClient.StatementSpec statement = mock(JdbcClient.StatementSpec.class);
        query = mock(JdbcClient.MappedQuerySpec.class);
        when(jdbc.sql(anyString())).thenReturn(statement);
        when(statement.param("workspaceId", "ws-1")).thenReturn(statement);
        when(statement.query(String.class)).thenReturn(query);
        ownership = new JdbcWorkspaceOwnership(jdbc);
    }

    @Test
    void existingWorkspaceMustBelongToTheAuthenticatedTenant() {
        when(query.optional()).thenReturn(Optional.of("tenant-a"));
        assertDoesNotThrow(() -> ownership.requireOwned("ws-1", "tenant-a"));
        assertThrows(SecurityException.class,
                () -> ownership.requireOwned("ws-1", "tenant-b"));
    }

    @Test
    void missingWorkspaceIsDeniedForMutationButAllowedForProvisioning() {
        when(query.optional()).thenReturn(Optional.empty());
        assertThrows(SecurityException.class,
                () -> ownership.requireOwned("ws-1", "tenant-a"));
        assertDoesNotThrow(() -> ownership.requireProvisionable("ws-1", "tenant-a"));
    }

    @Test
    void provisioningCannotReuseAnotherTenantsWorkspaceIdentity() {
        when(query.optional()).thenReturn(Optional.of("tenant-b"));
        assertThrows(SecurityException.class,
                () -> ownership.requireProvisionable("ws-1", "tenant-a"));
    }

    @Test
    void malformedWorkspaceIdentityIsRejectedBeforeDatabaseAccess() {
        var isolatedJdbc = mock(JdbcClient.class);
        var isolatedOwnership = new JdbcWorkspaceOwnership(isolatedJdbc);

        assertThrows(SecurityException.class,
                () -> isolatedOwnership.requireOwned("../workspace", "tenant-a"));
        verifyNoInteractions(isolatedJdbc);
    }
}
