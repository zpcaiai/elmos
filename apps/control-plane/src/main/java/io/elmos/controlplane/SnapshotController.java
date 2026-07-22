package io.elmos.controlplane;

import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotModel;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/repository-snapshots")
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
class SnapshotController {
    record CaptureRequest(String organizationId, String repositoryId, long repositoryExternalId,
                          long installationExternalId, String repositoryFullName, String requestedRef,
                          String correlationId, String idempotencyKey) { }
    private final SnapshotCaptureService snapshots;
    SnapshotController(SnapshotCaptureService snapshots) { this.snapshots = snapshots; }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    SnapshotModel.RepositorySnapshot capture(@RequestBody CaptureRequest request) {
        return snapshots.capture(new SnapshotCaptureService.CaptureRequest(request.organizationId(), request.repositoryId(),
                request.repositoryExternalId(), request.installationExternalId(), request.repositoryFullName(),
                request.requestedRef(), request.correlationId(), request.idempotencyKey()));
    }

    @ExceptionHandler({IllegalArgumentException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) ErrorResponse invalid(RuntimeException error) {
        return new ErrorResponse(error instanceof SecurityException ? "SNAPSHOT_POLICY_REJECTED" : "SNAPSHOT_REQUEST_INVALID");
    }
    @ExceptionHandler(IllegalStateException.class) @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    ErrorResponse unavailable() { return new ErrorResponse("SNAPSHOT_CAPTURE_UNAVAILABLE"); }
    record ErrorResponse(String code) { }
}
