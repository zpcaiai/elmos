package io.elmos.secret;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class SecretInjectionService {
    public record SecretRequest(String workspaceId, SecretLease.SecretType type, Duration requestedTtl) {
        public SecretRequest {
            if (workspaceId == null || workspaceId.isBlank()) throw new IllegalArgumentException("workspaceId is required");
            Objects.requireNonNull(type, "secret type is required");
            Objects.requireNonNull(requestedTtl, "requestedTtl is required");
        }
    }
    public record ProviderLease(String providerLeaseId, SecretValue value, Instant issuedAt, Instant expiresAt) {}
    public interface SecretProviderPort {
        ProviderLease issue(SecretRequest request);
        void revoke(String providerLeaseId);
    }
    public interface SecretMaterializerPort {
        void materializeReadOnlyTmpfs(String workspaceId, String leaseId, SecretValue value);
        void remove(String workspaceId, String leaseId);
    }
    public interface SecretLeaseStore { void save(SecretLease metadata); SecretLease find(String leaseId); }

    private static final Duration MAX_TTL = Duration.ofHours(1);
    private final SecretProviderPort provider; private final SecretMaterializerPort materializer;
    private final SecretLeaseStore store; private final Clock clock;

    public SecretInjectionService(SecretProviderPort provider, SecretMaterializerPort materializer, SecretLeaseStore store, Clock clock) {
        this.provider = Objects.requireNonNull(provider); this.materializer = Objects.requireNonNull(materializer);
        this.store = Objects.requireNonNull(store); this.clock = Objects.requireNonNull(clock);
    }

    public SecretLease inject(String leaseId, SecretRequest request) {
        if (leaseId == null || !leaseId.matches("[A-Za-z0-9._:-]{1,64}")) throw new IllegalArgumentException("leaseId is invalid");
        Objects.requireNonNull(request, "secret request is required");
        if (request.requestedTtl().isNegative() || request.requestedTtl().isZero() || request.requestedTtl().compareTo(MAX_TTL) > 0) {
            throw new SecurityException("secret lease TTL is outside policy");
        }
        ProviderLease issued = Objects.requireNonNull(provider.issue(request), "provider lease is required");
        Objects.requireNonNull(issued.providerLeaseId(), "provider lease id is required");
        Objects.requireNonNull(issued.value(), "provider secret value is required");
        Objects.requireNonNull(issued.issuedAt(), "provider issuedAt is required");
        Objects.requireNonNull(issued.expiresAt(), "provider expiresAt is required");
        try (SecretValue value = issued.value()) {
            if (issued.issuedAt().isAfter(clock.instant().plusSeconds(30)) || !issued.expiresAt().isAfter(clock.instant())
                    || Duration.between(issued.issuedAt(), issued.expiresAt()).compareTo(request.requestedTtl()) > 0) {
                throw new SecurityException("provider returned an invalid secret lifetime");
            }
            SecretLease metadata = new SecretLease(leaseId, issued.providerLeaseId(), request.type(), request.workspaceId(),
                    issued.issuedAt(), issued.expiresAt(), SecretLease.Status.ISSUED);
            store.save(metadata);
            materializer.materializeReadOnlyTmpfs(request.workspaceId(), leaseId, value);
            SecretLease injected = new SecretLease(leaseId, issued.providerLeaseId(), request.type(), request.workspaceId(),
                    issued.issuedAt(), issued.expiresAt(), SecretLease.Status.INJECTED);
            store.save(injected); return injected;
        } catch (RuntimeException failure) {
            try { provider.revoke(issued.providerLeaseId()); }
            catch (RuntimeException revokeFailure) { failure.addSuppressed(revokeFailure); }
            store.save(new SecretLease(leaseId, issued.providerLeaseId(), request.type(), request.workspaceId(),
                    issued.issuedAt(), issued.expiresAt(), SecretLease.Status.FAILED));
            throw failure;
        }
    }

    public void revoke(String leaseId) {
        revoke(leaseId, null);
    }

    public void revoke(String leaseId, String expectedWorkspaceId) {
        SecretLease lease = store.find(leaseId);
        if (expectedWorkspaceId != null && !expectedWorkspaceId.equals(lease.workspaceId())) throw new SecurityException("secret lease does not belong to workspace");
        RuntimeException failure = null;
        try { materializer.remove(lease.workspaceId(), lease.leaseId()); } catch (RuntimeException error) { failure = error; }
        try { provider.revoke(lease.providerLeaseId()); } catch (RuntimeException error) { if (failure == null) failure = error; else failure.addSuppressed(error); }
        SecretLease.Status status = failure == null ? SecretLease.Status.REVOKED : SecretLease.Status.FAILED;
        store.save(new SecretLease(lease.leaseId(), lease.providerLeaseId(), lease.secretType(), lease.workspaceId(),
                lease.issuedAt(), lease.expiresAt(), status));
        if (failure != null) throw failure;
    }
}
