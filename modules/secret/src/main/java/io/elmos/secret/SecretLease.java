package io.elmos.secret;

import java.time.Instant;
import java.util.Objects;

public record SecretLease(String leaseId, String providerLeaseId, SecretType secretType, String workspaceId,
                          Instant issuedAt, Instant expiresAt, Status status) {
    public enum SecretType { GITHUB_INSTALLATION_TOKEN, GITHUB_BRANCH_WRITE_TOKEN, MAVEN_SERVER_USERNAME_PASSWORD,
        MAVEN_SERVER_TOKEN, NEXUS_READ_TOKEN, ARTIFACTORY_READ_TOKEN, CUSTOM_CA_CERTIFICATE }
    public enum Status { REQUESTED, ISSUED, INJECTED, REVOKING, REVOKED, EXPIRED, FAILED }
    public SecretLease {
        if (leaseId == null || leaseId.isBlank() || providerLeaseId == null || providerLeaseId.isBlank()
                || workspaceId == null || workspaceId.isBlank()) throw new IllegalArgumentException("lease identity is required");
        Objects.requireNonNull(secretType); Objects.requireNonNull(issuedAt); Objects.requireNonNull(expiresAt); Objects.requireNonNull(status);
        if (!expiresAt.isAfter(issuedAt)) throw new IllegalArgumentException("secret lease expiry must follow issue time");
    }
}
