package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceModels;
import io.elmos.workspace.WorkspaceProvisioningPort;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/workspaces")
class WorkspaceController {
    private final WorkspaceProvisioningPort workspaces;
    private final WorkspaceOwnership ownership;
    WorkspaceController(WorkspaceProvisioningPort workspaces, WorkspaceOwnership ownership) {
        this.workspaces = workspaces;
        this.ownership = ownership;
    }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    WorkspaceProvisioningPort.WorkspaceHandle provision(
            @RequestAttribute(WorkspaceServiceCredentialFilter.PRINCIPAL_ATTRIBUTE)
            WorkspaceServiceCredentialFilter.Principal principal,
            @RequestBody WorkspaceModels.WorkspaceRequest request
    ) {
        if (!principal.organizationId().equals(request.organizationId())) {
            throw new SecurityException("workspace organization must match authenticated tenant");
        }
        ownership.requireProvisionable(request.workspaceId(), principal.organizationId());
        return workspaces.provision(authenticatedRequest(request, principal.organizationId()));
    }
    @PostMapping("/{workspaceId}/commands")
    WorkspaceModels.CommandResult execute(
            @RequestAttribute(WorkspaceServiceCredentialFilter.PRINCIPAL_ATTRIBUTE)
            WorkspaceServiceCredentialFilter.Principal principal,
            @PathVariable String workspaceId,
            @RequestBody WorkspaceModels.WorkspaceCommand command
    ) {
        ownership.requireOwned(workspaceId, principal.organizationId());
        return workspaces.execute(workspaceId, command);
    }
    @DeleteMapping("/{workspaceId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    void terminate(
            @RequestAttribute(WorkspaceServiceCredentialFilter.PRINCIPAL_ATTRIBUTE)
            WorkspaceServiceCredentialFilter.Principal principal,
            @PathVariable String workspaceId
    ) {
        ownership.requireOwned(workspaceId, principal.organizationId());
        workspaces.terminate(workspaceId);
    }

    private static WorkspaceModels.WorkspaceRequest authenticatedRequest(
            WorkspaceModels.WorkspaceRequest request,
            String organizationId
    ) {
        return new WorkspaceModels.WorkspaceRequest(
                request.workspaceId(),
                organizationId,
                request.migrationRunId(),
                request.snapshotId(),
                request.sandboxProfile(),
                request.imageDigest(),
                request.resources(),
                request.networkPolicyId(),
                request.correlationId());
    }
}
