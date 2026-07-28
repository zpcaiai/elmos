package io.elmos.controlplane;

import io.elmos.integrations.GitRepositoryWorkspaceService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

@Configuration
@ConditionalOnProperty(name = "elmos.repository-workspace.enabled", havingValue = "true")
class RepositoryWorkspaceConfiguration {
    @Bean
    GitRepositoryWorkspaceService gitRepositoryWorkspaceService(
            @Value("${elmos.repository-workspace.root:}") String root,
            @Value("${elmos.repository-workspace.max-files:100000}") int maximumFiles,
            @Value("${elmos.repository-workspace.max-bytes:2147483648}") long maximumBytes,
            @Value("${elmos.repository-workspace.allow-file-repositories:false}") boolean allowFileRepositories,
            @Value("${elmos.repository-workspace.allowed-generic-hosts:}") String allowedGenericHosts,
            @Value("${elmos.repository-workspace.max-workspaces:1000}") int maximumWorkspaces,
            @Value("${elmos.repository-workspace.ttl-hours:168}") long ttlHours
    ) {
        if (root == null || root.isBlank()) {
            throw new IllegalStateException("repository workspace root is required");
        }
        return new GitRepositoryWorkspaceService(
                Path.of(root),
                maximumFiles,
                maximumBytes,
                allowFileRepositories,
                parseHosts(allowedGenericHosts),
                maximumWorkspaces,
                Duration.ofHours(ttlHours));
    }

    @Bean
    RepositoryWorkspaceCredentialStore repositoryWorkspaceCredentialStore(
            @Value("${elmos.repository-workspace.credential-root:}") String root
    ) {
        if (root == null || root.isBlank()) {
            throw new IllegalStateException("repository workspace credential root is required");
        }
        return new RepositoryWorkspaceCredentialStore(Path.of(root));
    }

    private static Set<String> parseHosts(String value) {
        if (value == null || value.isBlank()) return Set.of();
        return Arrays.stream(value.split(","))
                .map(String::trim)
                .filter(item -> !item.isBlank())
                .collect(Collectors.toUnmodifiableSet());
    }
}
