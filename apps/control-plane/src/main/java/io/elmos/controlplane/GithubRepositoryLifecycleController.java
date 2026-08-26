package io.elmos.controlplane;

import io.elmos.cas.CasCatalog;
import io.elmos.integrations.CasBackedArtifactStore;
import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import io.elmos.snapshot.SnapshotPorts;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Explicit control-plane caller for the CAS repository lifecycle protocol.
 *
 * <p>Provider webhooks begin retirement through the verified lifecycle sink. This endpoint is the
 * governed operator/reconciliation path for the two remaining transitions: it accepts only a
 * lifecycle token returned by the catalogue, binds it to the authenticated tenant and repository,
 * and never guesses around active roots or stale epochs.</p>
 */
@RestController
@RequestMapping("/api/v1/github/repositories")
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
@ConditionalOnProperty(name = "elmos.snapshot.cas.enabled", havingValue = "true")
final class GithubRepositoryLifecycleController {

    private final CasBackedArtifactStore cas;
    private final JdbcGitHubRepositoryCatalog repositories;

    GithubRepositoryLifecycleController(
            CasBackedArtifactStore cas,
            JdbcGitHubRepositoryCatalog repositories
    ) {
        this.cas = cas;
        this.repositories = repositories;
    }

    @PostMapping("/{repositoryId}/retirement")
    ResponseEntity<CasCatalog.ResourceLifecycle> beginRetirement(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String repositoryId
    ) {
        requirePermission(organizationId, "repository:write");
        repositories.requireKnown(organizationId, repositoryId);
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(
                cas.beginRepositoryRetirement(
                        new SnapshotPorts.ArtifactResourceContext(
                                organizationId, repositoryId)));
    }

    @PostMapping("/{repositoryId}/retirement/finalize")
    ResponseEntity<CasCatalog.ResourceLifecycle> finalizeRetirement(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @PathVariable String repositoryId,
            @RequestBody FinalizeRequest request
    ) {
        requirePermission(organizationId, "repository:write");
        repositories.requireKnown(organizationId, repositoryId);
        if (request == null || request.lifecycle() == null
                || !organizationId.equals(request.lifecycle().tenantId())
                || !repositoryId.equals(request.lifecycle().resourceId())
                || request.lifecycle().resourceKind() != CasCatalog.ResourceKind.REPOSITORY) {
            throw new SecurityException("retirement token is not bound to this repository");
        }
        return ResponseEntity.ok(cas.finalizeRepositoryRetirement(request.lifecycle()));
    }

    record FinalizeRequest(CasCatalog.ResourceLifecycle lifecycle) {}

    @ExceptionHandler(SecurityException.class)
    ResponseEntity<Map<String, String>> forbidden(SecurityException ignored) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("code", "CAS_REPOSITORY_RETIREMENT_FORBIDDEN"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ignored) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "CAS_REPOSITORY_RETIREMENT_REQUEST_INVALID"));
    }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<Map<String, String>> conflict(IllegalStateException ignored) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("code", "CAS_REPOSITORY_RETIREMENT_NOT_RECONCILED"));
    }

    private static void requirePermission(String organizationId, String permission) {
        if (organizationId == null || organizationId.isBlank()) {
            throw new SecurityException("trusted organization is required");
        }
        ControlPlanePrincipal.requireDatabaseBound(organizationId, permission);
    }
}
