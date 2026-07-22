package io.elmos.workspaceservice;

import io.elmos.secret.SecretInjectionService;
import io.elmos.workspace.WorkspaceInfrastructurePorts;
import org.springframework.jdbc.core.simple.JdbcClient;

final class JdbcWorkspaceSecretFinalizer implements WorkspaceInfrastructurePorts.WorkspaceSecretFinalizer {
    private final JdbcClient jdbc;private final SecretInjectionService secrets;private final WorkspaceSecretRegistry registry;
    JdbcWorkspaceSecretFinalizer(JdbcClient jdbc,SecretInjectionService secrets,WorkspaceSecretRegistry registry){this.jdbc=jdbc;this.secrets=secrets;this.registry=registry;}
    @Override public void revokeAll(String workspaceId){RuntimeException failure=null;for(String lease:jdbc.sql("select lease_id from secret_leases where workspace_id=:workspace and status not in ('REVOKED') order by issued_at").param("workspace",workspaceId).query(String.class).list())try{secrets.revoke(lease,workspaceId);}catch(RuntimeException error){if(failure==null)failure=error;else failure.addSuppressed(error);}registry.clear(workspaceId);if(failure!=null)throw failure;}
}
