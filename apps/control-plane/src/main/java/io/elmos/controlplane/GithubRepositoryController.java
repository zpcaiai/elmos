package io.elmos.controlplane;

import io.elmos.persistence.JdbcGitHubRepositoryCatalog;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/github/repositories")
@ConditionalOnProperty(name = "elmos.github.app.enabled", havingValue = "true")
final class GithubRepositoryController {
    private final JdbcGitHubRepositoryCatalog repositories;

    GithubRepositoryController(JdbcGitHubRepositoryCatalog repositories) {
        this.repositories = repositories;
    }

    @GetMapping
    Map<String, Object> list(
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId
    ) {
        ControlPlanePrincipal.requireDatabaseBound(
                organizationId, "repository:read");
        List<JdbcGitHubRepositoryCatalog.AuthorizedRepository> values =
                repositories.listAuthorized(organizationId);
        return Map.of(
                "status", values.isEmpty() ? "NO_AUTHORIZED_REPOSITORIES" : "READY",
                "repositories", values
        );
    }
}
