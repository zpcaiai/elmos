package io.elmos.controlplane;

import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
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
    record SpringMaterializationRequest(
            String repositoryId,
            String requestedRef,
            String correlationId,
            String idempotencyKey
    ) { }
    private final SnapshotCaptureService snapshots;
    private final SnapshotMaterializationService materializations;
    private final JdbcGitHubRepositoryCatalog repositories;
    SnapshotController(
            SnapshotCaptureService snapshots,
            SnapshotMaterializationService materializations,
            JdbcGitHubRepositoryCatalog repositories
    ) {
        this.snapshots = snapshots;
        this.materializations = materializations;
        this.repositories = repositories;
    }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    SnapshotModel.RepositorySnapshot capture(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @RequestBody CaptureRequest request
    ) {
        if (trustedOrganizationId == null || trustedOrganizationId.isBlank()
                || (request.organizationId() != null
                && !request.organizationId().isBlank()
                && !trustedOrganizationId.equals(request.organizationId()))) {
            throw new SecurityException("request organization does not match trusted identity");
        }
        return snapshots.capture(new SnapshotCaptureService.CaptureRequest(
                trustedOrganizationId, request.repositoryId(),
                request.repositoryExternalId(), request.installationExternalId(), request.repositoryFullName(),
                request.requestedRef(), request.correlationId(), request.idempotencyKey()));
    }

    @PostMapping("/spring-materializations")
    @ResponseStatus(HttpStatus.CREATED)
    CaptureAndMaterializeResponse captureAndMaterialize(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @RequestBody SpringMaterializationRequest request
    ) {
        JdbcGitHubRepositoryCatalog.AuthorizedRepository repository =
                repositories.requireAuthorized(
                        trustedOrganizationId, request.repositoryId());
        String requestedRef = request.requestedRef() == null
                || request.requestedRef().isBlank()
                ? repository.defaultBranch()
                : request.requestedRef();
        SnapshotModel.RepositorySnapshot snapshot = capture(
                trustedOrganizationId,
                new CaptureRequest(
                        null,
                        repository.repositoryId(),
                        repository.repositoryExternalId(),
                        repository.installationExternalId(),
                        repository.fullName(),
                        requestedRef,
                        request.correlationId(),
                        request.idempotencyKey()));
        return new CaptureAndMaterializeResponse(
                repository.fullName(),
                snapshot,
                materializations.materialize(trustedOrganizationId, snapshot));
    }

    @ExceptionHandler({IllegalArgumentException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) ErrorResponse invalid(RuntimeException error) {
        return new ErrorResponse(error instanceof SecurityException ? "SNAPSHOT_POLICY_REJECTED" : "SNAPSHOT_REQUEST_INVALID");
    }
    @ExceptionHandler(IllegalStateException.class) @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    ErrorResponse unavailable() { return new ErrorResponse("SNAPSHOT_CAPTURE_UNAVAILABLE"); }
    record CaptureAndMaterializeResponse(
            String repositoryFullName,
            SnapshotModel.RepositorySnapshot snapshot,
            SnapshotMaterializationService.Materialization materialization
    ) { }
    record ErrorResponse(String code) { }
}
