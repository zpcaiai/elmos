package io.elmos.workspaceservice;

import org.springframework.jdbc.core.simple.JdbcClient;

import java.util.Optional;

interface WorkspaceOwnership {
    void requireProvisionable(String workspaceId, String organizationId);
    void requireOwned(String workspaceId, String organizationId);
}

final class JdbcWorkspaceOwnership implements WorkspaceOwnership {
    private final JdbcClient jdbc;

    JdbcWorkspaceOwnership(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void requireProvisionable(String workspaceId, String organizationId) {
        Optional<String> owner = owner(workspaceId);
        if (owner.isPresent() && !owner.get().equals(organizationId)) {
            throw denied();
        }
    }

    @Override
    public void requireOwned(String workspaceId, String organizationId) {
        if (owner(workspaceId).filter(organizationId::equals).isEmpty()) {
            throw denied();
        }
    }

    private Optional<String> owner(String workspaceId) {
        if (workspaceId == null
                || !workspaceId.matches("[A-Za-z0-9._:-]{1,64}")) {
            throw denied();
        }
        return jdbc.sql("""
                        select organization_id
                        from workspace_instances
                        where workspace_id = :workspaceId
                        """)
                .param("workspaceId", workspaceId)
                .query(String.class)
                .optional();
    }

    private static SecurityException denied() {
        return new SecurityException("workspace tenant ownership was not established");
    }
}
