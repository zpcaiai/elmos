package com.acme.migration.app.api;

import com.acme.migration.app.persistence.RunnerRepository;
import com.acme.migration.contracts.ApiContracts.*;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

import static com.acme.migration.app.support.TenantContext.LOCAL_TENANT_ID;

@RestController
@RequestMapping("/internal/v1")
public class RunnerController {
    private final RunnerRepository runners;

    public RunnerController(RunnerRepository runners) { this.runners = runners; }

    @PostMapping("/runners/register")
    public RunnerRegisterResponse register(@Valid @RequestBody RunnerRegisterRequest request) {
        var id = runners.register(LOCAL_TENANT_ID, request.name(), request.version(), request.capabilities());
        return new RunnerRegisterResponse(id, "online");
    }

    @PostMapping("/runners/{runnerId}/heartbeat")
    public ResponseEntity<Void> heartbeat(@PathVariable UUID runnerId,
                                          @Valid @RequestBody RunnerHeartbeatRequest request) {
        runners.heartbeat(LOCAL_TENANT_ID, runnerId, request.status());
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/runners/{runnerId}/claim")
    public ResponseEntity<ClaimJobResponse> claim(@PathVariable UUID runnerId) {
        return runners.claim(LOCAL_TENANT_ID, runnerId)
                .map(task -> ResponseEntity.ok(new ClaimJobResponse(task.taskId(), task.taskType(),
                        task.payload(), task.leaseExpiresAt(), task.commitToken())))
                .orElseGet(() -> ResponseEntity.noContent().build());
    }

    @PostMapping("/jobs/{jobId}/complete")
    public ResponseEntity<Void> complete(@PathVariable UUID jobId,
                                         @Valid @RequestBody JobCompleteRequest request) {
        runners.complete(LOCAL_TENANT_ID, jobId, request.commitToken(), request.status(),
                request.outputPayload(), request.artifactPath());
        return ResponseEntity.noContent().build();
    }
}
