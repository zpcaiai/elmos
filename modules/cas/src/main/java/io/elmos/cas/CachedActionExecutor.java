package io.elmos.cas;

import java.util.Objects;
import java.util.Optional;

/**
 * Typed caller that composes ActionCache lookup with an independently authorized execution.
 *
 * <p>A miss, bypass, stale entry or invalidation may fall back to execution only after a fresh
 * EXECUTE authorization decision. A cache denial never falls back, and DENY/UNKNOWN/provider
 * failure never becomes success. This class does not publish results back into the cache: doing so
 * requires the caller's producer identity, attested writer, evidence and durable output manifest.
 */
public final class CachedActionExecutor {

    public enum Operation {
        CACHE_READ,
        EXECUTE
    }

    public enum AuthorizationStatus {
        ALLOW,
        DENY,
        UNKNOWN
    }

    public enum Mode {
        CACHE_ONLY,
        CACHE_OR_EXECUTE
    }

    public enum OutcomeKind {
        CACHE_HIT,
        EXECUTED,
        NOT_EXECUTED,
        BLOCKED
    }

    public record AuthorizationDecision(AuthorizationStatus status, String reason) {
        public AuthorizationDecision {
            Objects.requireNonNull(status, "status");
            reason = boundedReason(reason);
        }

        public static AuthorizationDecision allow(String reason) {
            return new AuthorizationDecision(AuthorizationStatus.ALLOW, reason);
        }

        public static AuthorizationDecision deny(String reason) {
            return new AuthorizationDecision(AuthorizationStatus.DENY, reason);
        }

        public static AuthorizationDecision unknown(String reason) {
            return new AuthorizationDecision(AuthorizationStatus.UNKNOWN, reason);
        }
    }

    public record Request(ActionKey key, CasAccessPolicy.ReaderContext reader,
                          boolean bypassCache, Mode mode) {
        public Request {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(reader, "reader");
            Objects.requireNonNull(mode, "mode");
        }
    }

    public record Outcome(OutcomeKind kind, String reason,
                          Optional<ActionResultRecord> result,
                          Optional<ActionCache.CacheOutcome> cacheOutcome) {
        public Outcome {
            Objects.requireNonNull(kind, "kind");
            reason = boundedReason(reason);
            result = Objects.requireNonNull(result, "result");
            cacheOutcome = Objects.requireNonNull(cacheOutcome, "cacheOutcome");
            if ((kind == OutcomeKind.CACHE_HIT || kind == OutcomeKind.EXECUTED)
                    != result.isPresent()) {
                throw new IllegalArgumentException(
                        "only cache-hit/executed outcomes may contain an action result");
            }
            if (kind == OutcomeKind.CACHE_HIT
                    && cacheOutcome.filter(value -> value == ActionCache.CacheOutcome.HIT).isEmpty()) {
                throw new IllegalArgumentException("cache-hit outcome requires HIT cache outcome");
            }
        }

        /** A failed action is executed evidence, but is not reported as a successful result. */
        public boolean successful() {
            return result.filter(value -> value.status() == ActionResultRecord.Status.SUCCEEDED)
                    .isPresent();
        }

        private static Outcome blocked(String reason,
                                       Optional<ActionCache.CacheOutcome> cacheOutcome) {
            return new Outcome(OutcomeKind.BLOCKED, reason, Optional.empty(), cacheOutcome);
        }
    }

    @FunctionalInterface
    public interface Authorizer {
        AuthorizationDecision authorize(Request request, Operation operation);
    }

    @FunctionalInterface
    public interface ActionRunner {
        ActionResultRecord execute(Request request);
    }

    private final ActionCache cache;
    private final Authorizer authorizer;
    private final ActionRunner runner;

    public CachedActionExecutor(ActionCache cache, Authorizer authorizer, ActionRunner runner) {
        this.cache = Objects.requireNonNull(cache, "cache");
        this.authorizer = Objects.requireNonNull(authorizer, "authorizer");
        this.runner = Objects.requireNonNull(runner, "runner");
    }

    public Outcome execute(Request request) {
        Objects.requireNonNull(request, "request");
        if (request.bypassCache()) {
            // Record an explicit bypass without reading the index or requiring CACHE_READ rights.
            ActionCache.Lookup bypass = cache.get(request.key(), request.reader(), true);
            return executeAfterAuthorization(request, Optional.of(bypass.outcome()), bypass.reason());
        }

        AuthorizationDecision cacheRead = authorize(request, Operation.CACHE_READ);
        if (cacheRead.status() != AuthorizationStatus.ALLOW) {
            return Outcome.blocked(authorizationReason(Operation.CACHE_READ, cacheRead),
                    Optional.empty());
        }

        ActionCache.Lookup lookup;
        try {
            lookup = cache.get(request.key(), request.reader(), false);
        } catch (CasExceptions.CasAccessDeniedException denied) {
            return Outcome.blocked("CACHE_ACCESS_DENIED:" + denied.reason(), Optional.empty());
        }
        if (lookup.outcome() == ActionCache.CacheOutcome.HIT) {
            return new Outcome(OutcomeKind.CACHE_HIT, lookup.reason(), lookup.result(),
                    Optional.of(lookup.outcome()));
        }
        if (lookup.outcome() == ActionCache.CacheOutcome.DENIED) {
            return Outcome.blocked("CACHE_LOOKUP_DENIED:" + lookup.reason(),
                    Optional.of(lookup.outcome()));
        }
        if (request.mode() == Mode.CACHE_ONLY) {
            return new Outcome(OutcomeKind.NOT_EXECUTED,
                    "CACHE_ONLY:" + lookup.reason(), Optional.empty(), Optional.of(lookup.outcome()));
        }
        return executeAfterAuthorization(request, Optional.of(lookup.outcome()), lookup.reason());
    }

    private Outcome executeAfterAuthorization(Request request,
                                              Optional<ActionCache.CacheOutcome> cacheOutcome,
                                              String cacheReason) {
        if (request.mode() == Mode.CACHE_ONLY) {
            return new Outcome(OutcomeKind.NOT_EXECUTED,
                    "CACHE_ONLY:" + cacheReason, Optional.empty(), cacheOutcome);
        }
        // An action key is a tenant-owned execution request. Cross-tenant public cache reads may
        // be legitimate, but executing the producer tenant's key as the reader is not.
        if (!request.key().tenantId().equals(request.reader().tenantId())) {
            return Outcome.blocked("EXECUTION_TENANT_MISMATCH", cacheOutcome);
        }
        AuthorizationDecision execution = authorize(request, Operation.EXECUTE);
        if (execution.status() != AuthorizationStatus.ALLOW) {
            return Outcome.blocked(authorizationReason(Operation.EXECUTE, execution), cacheOutcome);
        }
        ActionResultRecord result = Objects.requireNonNull(
                runner.execute(request), "action runner result");
        return new Outcome(OutcomeKind.EXECUTED, "EXECUTED_AFTER:" + cacheReason,
                Optional.of(result), cacheOutcome);
    }

    private AuthorizationDecision authorize(Request request, Operation operation) {
        try {
            AuthorizationDecision decision = authorizer.authorize(request, operation);
            return decision == null
                    ? AuthorizationDecision.unknown("AUTHORIZER_RETURNED_NO_DECISION")
                    : decision;
        } catch (RuntimeException unavailable) {
            return AuthorizationDecision.unknown("AUTHORIZATION_PROVIDER_UNAVAILABLE");
        }
    }

    private static String authorizationReason(Operation operation,
                                              AuthorizationDecision decision) {
        return operation.name() + "_AUTHORIZATION_" + decision.status().name()
                + ":" + decision.reason();
    }

    private static String boundedReason(String reason) {
        String value = CasText.required(reason, "reason");
        if (value.length() > 512) {
            throw new IllegalArgumentException("reason exceeds 512 characters");
        }
        for (int index = 0; index < value.length(); index++) {
            if (Character.isISOControl(value.charAt(index))) {
                throw new IllegalArgumentException("reason contains control characters");
            }
        }
        return value;
    }
}
