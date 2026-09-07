package io.elmos.controlplane;

import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import io.elmos.snapshot.SnapshotArchiveService;
import io.elmos.snapshot.SnapshotCaptureService;
import io.elmos.snapshot.SnapshotMaterializationService;
import io.elmos.snapshot.SnapshotModel;
import io.elmos.snapshot.SnapshotProvisionalRootReconciler;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/repository-snapshots")
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
class SnapshotController {
    record CaptureRequest(
            String repositoryId,
            String requestedRef,
            String correlationId,
            String idempotencyKey
    ) { }
    record SpringMaterializationRequest(
            String repositoryId,
            String requestedRef,
            String correlationId,
            String idempotencyKey
    ) { }
    record ArchiveRequest(String repositoryId, String idempotencyKey) { }
    private final SnapshotCaptureService snapshots;
    private final SnapshotMaterializationService materializations;
    private final JdbcGitHubRepositoryCatalog repositories;
    private final SnapshotArchiveService archives;
    private final SnapshotProvisionalRootReconciler reconciler;
    SnapshotController(
            SnapshotCaptureService snapshots,
            SnapshotMaterializationService materializations,
            JdbcGitHubRepositoryCatalog repositories,
            SnapshotArchiveService archives,
            SnapshotProvisionalRootReconciler reconciler
    ) {
        this.snapshots = snapshots;
        this.materializations = materializations;
        this.repositories = repositories;
        this.archives = archives;
        this.reconciler = reconciler;
    }

    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    SnapshotModel.RepositorySnapshot capture(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @RequestBody CaptureRequest request
    ) {
        requireTrustedOrganization(trustedOrganizationId);
        ControlPlanePrincipal.requireDatabaseBound(
                trustedOrganizationId, "repository:read");
        JdbcGitHubRepositoryCatalog.AuthorizedRepository repository =
                repositories.requireAuthorized(
                        trustedOrganizationId, request.repositoryId());
        String requestedRef = request.requestedRef() == null
                || request.requestedRef().isBlank()
                ? repository.defaultBranch()
                : request.requestedRef();
        return snapshots.capture(new SnapshotCaptureService.CaptureRequest(
                trustedOrganizationId, repository.repositoryId(),
                repository.repositoryExternalId(), repository.installationExternalId(),
                repository.fullName(), requestedRef,
                request.correlationId(), request.idempotencyKey()));
    }

    @PostMapping("/spring-materializations")
    @ResponseStatus(HttpStatus.CREATED)
    CaptureAndMaterializeResponse captureAndMaterialize(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @RequestBody SpringMaterializationRequest request
    ) {
        ControlPlanePrincipal.requireDatabaseBound(
                trustedOrganizationId, "repository:read");
        JdbcGitHubRepositoryCatalog.AuthorizedRepository repository =
                repositories.requireAuthorized(
                        trustedOrganizationId, request.repositoryId());
        String requestedRef = request.requestedRef() == null
                || request.requestedRef().isBlank()
                ? repository.defaultBranch()
                : request.requestedRef();
        SnapshotModel.RepositorySnapshot snapshot = capture(
                trustedOrganizationId,
                new CaptureRequest(repository.repositoryId(), requestedRef,
                        request.correlationId(), request.idempotencyKey()));
        return new CaptureAndMaterializeResponse(
                repository.fullName(),
                snapshot,
                materializations.materialize(trustedOrganizationId, snapshot));
    }

    @PostMapping("/{snapshotId}/archive")
    SnapshotArchiveService.ArchiveResult archive(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @PathVariable String snapshotId,
            @RequestBody ArchiveRequest request
    ) {
        requireTrustedOrganization(trustedOrganizationId);
        ControlPlanePrincipal.requireDatabaseBound(
                trustedOrganizationId, "repository:write");
        return archives.archive(new SnapshotArchiveService.ArchiveRequest(
                trustedOrganizationId, request.repositoryId(), snapshotId,
                request.idempotencyKey()));
    }

    @PostMapping("/root-reconciliations")
    SnapshotProvisionalRootReconciler.ReconciliationReport reconcileRoots(
            @RequestHeader("X-ELMOS-Organization-ID") String trustedOrganizationId,
            @RequestParam(defaultValue = "100") int limit
    ) {
        requireTrustedOrganization(trustedOrganizationId);
        ControlPlanePrincipal.requireDatabaseBound(
                trustedOrganizationId, "admin:operate");
        return reconciler.reconcile(trustedOrganizationId, limit);
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

    private static void requireTrustedOrganization(String organizationId) {
        if (organizationId == null || organizationId.isBlank()) {
            throw new SecurityException("trusted organization is required");
        }
    }
}
