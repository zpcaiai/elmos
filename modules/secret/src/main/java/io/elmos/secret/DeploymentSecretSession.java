package io.elmos.secret;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.function.Function;

/** Bounded deployment secret lifecycle over the existing secret materializer/store. */
public final class DeploymentSecretSession {
    public record Request(String invocationId, String tenantId, String accountId, String projectId,
                          String workspaceId, String environmentId, String capabilityDigest,
                          SecretLease.SecretType secretType, Instant expiresAt) {
        public Request {
            for (String value : new String[]{invocationId, tenantId, accountId, projectId, workspaceId, environmentId}) {
                if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
                    throw new IllegalArgumentException("DEPLOYMENT_SECRET_SCOPE");
                }
            }
            if (capabilityDigest == null || !capabilityDigest.matches("sha256:[0-9a-f]{64}")) {
                throw new IllegalArgumentException("DEPLOYMENT_SECRET_CAPABILITY");
            }
            Objects.requireNonNull(secretType);
            Objects.requireNonNull(expiresAt);
        }
    }

    /** Must resolve authenticated workload, exact resource ownership and current capability/revocation. */
    public interface Authorization { void require(Request request); }
    private final SecretInjectionService secrets;
    private final Authorization authorization;
    private final Clock clock;

    public DeploymentSecretSession(SecretInjectionService secrets, Authorization authorization, Clock clock) {
        this.secrets = Objects.requireNonNull(secrets);
        this.authorization = Objects.requireNonNull(authorization);
        this.clock = Objects.requireNonNull(clock);
    }

    /** Called only inside a claimed canonical tool invocation. Returns metadata, never secret values. */
    public <T> T execute(Request request, Function<SecretLease, T> operation) {
        authorization.require(request);
        Duration ttl = Duration.between(clock.instant(), request.expiresAt());
        if (ttl.isNegative() || ttl.isZero() || ttl.compareTo(Duration.ofMinutes(1)) > 0) {
            throw new SecurityException("DEPLOYMENT_SECRET_LEASE_EXPIRED_OR_TOO_LONG");
        }
        SecretLease lease = secrets.inject(request.invocationId(), new SecretInjectionService.SecretRequest(
                request.workspaceId(), request.secretType(), ttl));
        Throwable primary = null;
        try {
            authorization.require(request);
            if (!clock.instant().isBefore(request.expiresAt())) throw new SecurityException("DEPLOYMENT_SECRET_LEASE_EXPIRED");
            return operation.apply(lease);
        } catch (RuntimeException | Error failure) {
            primary = failure;
            throw failure;
        } finally {
            try { secrets.revoke(lease.leaseId(), request.workspaceId()); }
            catch (RuntimeException cleanup) {
                if (primary != null) primary.addSuppressed(cleanup);
                else throw cleanup;
            }
        }
    }
}
