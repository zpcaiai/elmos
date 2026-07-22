package io.elmos.workspaceservice;

import io.elmos.workspace.WorkspaceModels;
import io.elmos.workspace.WorkspaceProvisioningPort;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/workspaces")
class WorkspaceController {
    private final WorkspaceProvisioningPort workspaces;
    WorkspaceController(WorkspaceProvisioningPort workspaces) { this.workspaces = workspaces; }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    WorkspaceProvisioningPort.WorkspaceHandle provision(@RequestBody WorkspaceModels.WorkspaceRequest request) {
        return workspaces.provision(request);
    }
    @PostMapping("/{workspaceId}/commands")
    WorkspaceModels.CommandResult execute(@PathVariable String workspaceId, @RequestBody WorkspaceModels.WorkspaceCommand command) {
        return workspaces.execute(workspaceId, command);
    }
    @DeleteMapping("/{workspaceId}") @ResponseStatus(HttpStatus.NO_CONTENT)
    void terminate(@PathVariable String workspaceId) { workspaces.terminate(workspaceId); }
}
