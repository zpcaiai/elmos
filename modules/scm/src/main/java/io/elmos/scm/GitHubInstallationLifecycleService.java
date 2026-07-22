package io.elmos.scm;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class GitHubInstallationLifecycleService {
    public enum Status { ACTIVE, SUSPENDED, DELETED }
    public record Installation(String installationId, String connectionId, String organizationId, long githubInstallationId,
                               long accountExternalId, String accountLogin, String targetType, String repositorySelection,
                               Map<String, String> permissions, Status status, Instant installedAt, Instant synchronizedAt) {
        public Installation { permissions = Map.copyOf(permissions); }
    }
    public record Repository(String repositoryId, long githubRepositoryId, String owner, String name, String fullName,
                             String cloneUrl, String htmlUrl, String defaultBranch, String visibility,
                             boolean archived, boolean disabled, boolean fork, Long parentRepositoryId) {}
    public interface Store {
        boolean bindIfUnclaimed(Installation installation);
        Installation findByExternalId(long githubInstallationId);
        void updateStatus(long githubInstallationId, Status status, Instant changedAt);
        void replaceAuthorizedRepositories(long githubInstallationId, Set<Repository> repositories, Instant synchronizedAt);
    }

    private static final Map<String,String> REQUIRED_APP_PERMISSIONS = Map.of(
            "metadata", "read", "contents", "write", "pull_requests", "write", "checks", "write");
    private final Store store;
    public GitHubInstallationLifecycleService(Store store) { this.store = Objects.requireNonNull(store); }

    public Installation bind(Installation installation) {
        validatePermissions(installation.permissions());
        if (installation.status() != Status.ACTIVE) throw new IllegalArgumentException("new installation must be active");
        if (!store.bindIfUnclaimed(installation)) {
            Installation existing = store.findByExternalId(installation.githubInstallationId());
            if (existing == null || !existing.organizationId().equals(installation.organizationId()))
                throw new SecurityException("GitHub installation is already bound to another organization");
            return existing;
        }
        return installation;
    }

    public void synchronize(long githubInstallationId, Set<Repository> repositories, Instant synchronizedAt) {
        Installation installation = requireActive(githubInstallationId);
        for (Repository repository : repositories) {
            if (repository.repositoryId() == null || repository.repositoryId().isBlank() || repository.fullName() == null
                    || !repository.fullName().equals(repository.owner() + "/" + repository.name()))
                throw new IllegalArgumentException("repository identity is inconsistent");
        }
        store.replaceAuthorizedRepositories(installation.githubInstallationId(), Set.copyOf(repositories), synchronizedAt);
    }

    public void suspend(long githubInstallationId, Instant changedAt) { store.updateStatus(githubInstallationId, Status.SUSPENDED, changedAt); }
    public void unsuspend(long githubInstallationId, Instant changedAt) { store.updateStatus(githubInstallationId, Status.ACTIVE, changedAt); }
    public void delete(long githubInstallationId, Instant changedAt) { store.updateStatus(githubInstallationId, Status.DELETED, changedAt); }

    public Installation requireActive(long githubInstallationId) {
        Installation installation = store.findByExternalId(githubInstallationId);
        if (installation == null || installation.status() == Status.DELETED) throw new SecurityException("GitHub App installation is not installed");
        if (installation.status() == Status.SUSPENDED) throw new SecurityException("GitHub App installation is suspended");
        return installation;
    }

    private static void validatePermissions(Map<String,String> granted) {
        REQUIRED_APP_PERMISSIONS.forEach((name, access) -> {
            if (!access.equalsIgnoreCase(granted.get(name))) throw new SecurityException("GitHub App permission is missing: " + name + "=" + access);
        });
    }
}
