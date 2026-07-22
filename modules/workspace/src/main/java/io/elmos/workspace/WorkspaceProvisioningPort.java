package io.elmos.workspace;

public interface WorkspaceProvisioningPort {
    record WorkspaceHandle(String workspaceId, String containerId, String networkId) {}
    WorkspaceHandle provision(WorkspaceModels.WorkspaceRequest request);
    WorkspaceModels.CommandResult execute(String workspaceId, WorkspaceModels.WorkspaceCommand command);
    void terminate(String workspaceId);
}
