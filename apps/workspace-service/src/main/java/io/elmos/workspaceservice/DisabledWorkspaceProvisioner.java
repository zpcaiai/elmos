package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceModels;
import io.elmos.workspace.WorkspaceProvisioningPort;

final class DisabledWorkspaceProvisioner implements WorkspaceProvisioningPort {
    private static IllegalStateException disabled() { return new IllegalStateException("rootless Docker workspace provisioning is disabled"); }
    public WorkspaceHandle provision(WorkspaceModels.WorkspaceRequest request) { throw disabled(); }
    public WorkspaceModels.CommandResult execute(String workspaceId, WorkspaceModels.WorkspaceCommand command) { throw disabled(); }
    public void terminate(String workspaceId) { throw disabled(); }
}
