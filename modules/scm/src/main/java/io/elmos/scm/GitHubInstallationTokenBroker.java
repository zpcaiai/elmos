package io.elmos.scm;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class GitHubInstallationTokenBroker {
    public enum Operation { READ_REPOSITORY, CAPTURE_SNAPSHOT, PUSH_MIGRATION_BRANCH, CREATE_PULL_REQUEST, PUBLISH_CHECK }
    public enum Access { READ, WRITE }
    public record Permission(String name, Access access) {}
    public static final class TokenGrant implements AutoCloseable {
        private final char[] value; private final Instant issuedAt; private final Instant expiresAt; private final Set<Permission> permissions;
        public TokenGrant(char[] value, Instant issuedAt, Instant expiresAt, Set<Permission> permissions) {
            this.value = value.clone(); java.util.Arrays.fill(value, '\0'); this.issuedAt = issuedAt; this.expiresAt = expiresAt;
            this.permissions = Set.copyOf(permissions);
        }
        public char[] value() { return value.clone(); }
        public Instant issuedAt() { return issuedAt; } public Instant expiresAt() { return expiresAt; }
        public Set<Permission> permissions() { return permissions; }
        @Override public void close() { java.util.Arrays.fill(value, '\0'); }
        @Override public String toString() { return "TokenGrant[REDACTED," + expiresAt + "]"; }
    }
    public record LeaseMetadata(String repositoryId, long repositoryExternalId, long installationExternalId,
                                Operation operation, Instant issuedAt, Instant expiresAt, Set<Permission> permissions) {}
    public interface RepositoryAuthorizationPort {
        boolean isAuthorized(String repositoryId, long repositoryExternalId, long installationExternalId);
    }
    public interface InstallationTokenIssuer {
        TokenGrant issue(long installationExternalId, long repositoryExternalId, Set<Permission> permissions);
        default void revoke(char[] token) {}
    }
    public interface CredentialLeaseAuditPort { void issued(LeaseMetadata metadata); }

    private static final Duration MAX_TTL = Duration.ofHours(1);
    private static final Map<Operation, Set<Permission>> REQUIRED = Map.of(
            Operation.READ_REPOSITORY, Set.of(new Permission("contents", Access.READ), new Permission("metadata", Access.READ)),
            Operation.CAPTURE_SNAPSHOT, Set.of(new Permission("contents", Access.READ), new Permission("metadata", Access.READ)),
            Operation.PUSH_MIGRATION_BRANCH, Set.of(new Permission("contents", Access.WRITE), new Permission("metadata", Access.READ)),
            Operation.CREATE_PULL_REQUEST, Set.of(new Permission("pull_requests", Access.WRITE), new Permission("contents", Access.READ), new Permission("metadata", Access.READ)),
            Operation.PUBLISH_CHECK, Set.of(new Permission("checks", Access.WRITE), new Permission("metadata", Access.READ))
    );

    private final RepositoryAuthorizationPort authorization;
    private final InstallationTokenIssuer issuer;
    private final CredentialLeaseAuditPort audit;
    private final Clock clock;

    public GitHubInstallationTokenBroker(RepositoryAuthorizationPort authorization, InstallationTokenIssuer issuer,
                                         CredentialLeaseAuditPort audit, Clock clock) {
        this.authorization = Objects.requireNonNull(authorization);
        this.issuer = Objects.requireNonNull(issuer);
        this.audit = Objects.requireNonNull(audit);
        this.clock = Objects.requireNonNull(clock);
    }

    public EphemeralCredential issue(String repositoryId, long repositoryExternalId,
                                     long installationExternalId, Operation operation) {
        if (!authorization.isAuthorized(repositoryId, repositoryExternalId, installationExternalId)) {
            throw new SecurityException("repository is not authorized for the installation");
        }
        Set<Permission> required = REQUIRED.get(Objects.requireNonNull(operation));
        try (TokenGrant grant = issuer.issue(installationExternalId, repositoryExternalId, required)) {
            Instant now = clock.instant();
            if (grant.issuedAt().isAfter(now.plusSeconds(30)) || !grant.expiresAt().isAfter(now)
                    || Duration.between(grant.issuedAt(), grant.expiresAt()).compareTo(MAX_TTL) > 0) {
                throw new SecurityException("installation token has an invalid lifetime");
            }
            if (!grant.permissions().equals(required)) {
                throw new SecurityException("installation token permissions differ from the requested minimum");
            }
            LeaseMetadata metadata = new LeaseMetadata(repositoryId, repositoryExternalId, installationExternalId,
                    operation, grant.issuedAt(), grant.expiresAt(), grant.permissions());
            audit.issued(metadata);
            char[] raw = grant.value();
            try { return new EphemeralCredential(raw, issuer::revoke); }
            finally { java.util.Arrays.fill(raw, '\0'); }
        }
    }
}
