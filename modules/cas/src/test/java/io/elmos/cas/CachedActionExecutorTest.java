package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CachedActionExecutorTest {

    private static final String IMAGE = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);

    @Test void trustedCacheHitNeverInvokesTheRunner() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.persistedDecisionCompatibility());
        fixture.store(fixture.key, Set.of("repo:read"));
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor executor = new CachedActionExecutor(
                fixture.cache, (request, operation) -> allow(operation), request -> {
                    executions.incrementAndGet();
                    return fixture.success("executed");
                });

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                fixture.key, fixture.reader(Set.of("repo:read")), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.CACHE_HIT, outcome.kind());
        assertTrue(outcome.successful());
        assertEquals(0, executions.get());
    }

    @Test void missRequiresAFreshExecuteAuthorizationAndUnknownIsBlocked() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.persistedDecisionCompatibility());
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor executor = new CachedActionExecutor(fixture.cache,
                (request, operation) -> operation == CachedActionExecutor.Operation.CACHE_READ
                        ? allow(operation)
                        : CachedActionExecutor.AuthorizationDecision.unknown("PDP_TIMEOUT"),
                request -> {
                    executions.incrementAndGet();
                    return fixture.success("executed");
                });

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                fixture.key, fixture.reader(Set.of("repo:read")), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("EXECUTE_AUTHORIZATION_UNKNOWN:PDP_TIMEOUT", outcome.reason());
        assertFalse(outcome.successful());
        assertEquals(0, executions.get());
    }

    @Test void cacheDenialNeverFallsBackToExecution() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.persistedDecisionCompatibility());
        ActionKey privileged = Fixture.key(Set.of("repo:read", "secret:read"));
        fixture.store(privileged, Set.of("repo:read", "secret:read"));
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor executor = new CachedActionExecutor(
                fixture.cache, (request, operation) -> allow(operation), request -> {
                    executions.incrementAndGet();
                    return fixture.success("executed");
                });

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                privileged, fixture.reader(Set.of("repo:read")), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("CACHE_LOOKUP_DENIED:PERMISSION_DOWNGRADE", outcome.reason());
        assertEquals(0, executions.get());
    }

    @Test void unknownCurrentTrustCannotBeBypassedByAnAllowedExecutionDecision() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.failClosedNotConfigured());
        fixture.store(fixture.key, Set.of("repo:read"));
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor executor = new CachedActionExecutor(
                fixture.cache, (request, operation) -> allow(operation), request -> {
                    executions.incrementAndGet();
                    return fixture.success("executed");
                });

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                fixture.key, fixture.reader(Set.of("repo:read")), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.BLOCKED, outcome.kind());
        assertTrue(outcome.reason().startsWith("CACHE_LOOKUP_DENIED:CURRENT_TRUST_UNKNOWN:"));
        assertEquals(0, executions.get());
    }

    @Test void anAuthorizedMissExecutesButAFailedActionIsNotReportedAsSuccess() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.persistedDecisionCompatibility());
        CachedActionExecutor executor = new CachedActionExecutor(
                fixture.cache, (request, operation) -> allow(operation),
                request -> fixture.failure());

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                fixture.key, fixture.reader(Set.of("repo:read")), false,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.EXECUTED, outcome.kind());
        assertEquals(ActionResultRecord.Status.FAILED,
                outcome.result().orElseThrow().status());
        assertFalse(outcome.successful());
    }

    @Test void explicitBypassStillRequiresExecuteAuthorization() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.persistedDecisionCompatibility());
        AtomicInteger executions = new AtomicInteger();
        CachedActionExecutor executor = new CachedActionExecutor(fixture.cache,
                (request, operation) -> CachedActionExecutor.AuthorizationDecision.deny(
                        "EXECUTION_DISABLED"), request -> {
                    executions.incrementAndGet();
                    return fixture.success("executed");
                });

        CachedActionExecutor.Outcome outcome = executor.execute(fixture.request(
                fixture.key, fixture.reader(Set.of("repo:read")), true,
                CachedActionExecutor.Mode.CACHE_OR_EXECUTE));

        assertEquals(CachedActionExecutor.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("EXECUTE_AUTHORIZATION_DENY:EXECUTION_DISABLED", outcome.reason());
        assertEquals(0, executions.get());
    }

    private static CachedActionExecutor.AuthorizationDecision allow(
            CachedActionExecutor.Operation operation) {
        return CachedActionExecutor.AuthorizationDecision.allow(operation.name() + "_ALLOWED");
    }

    private static final class Fixture {
        private final InMemoryCasStore store = new InMemoryCasStore("objects");
        private final ActionCache cache;
        private final ActionKey key = key(Set.of("repo:read"));

        private Fixture(ActionCache.TrustRevalidator trustRevalidator) {
            cache = new ActionCache(TenantCasStore.global(store), new CasAccessPolicy(),
                    ActionCache.FailureCachePolicy.none(),
                    ActionCache.SampleRecomputePolicy.disabled(), () -> 1_000_000L,
                    new CasMetrics(), new InMemoryActionCacheIndex(), CasTelemetry.noop(),
                    trustRevalidator);
        }

        private void store(ActionKey actionKey, Set<String> scope) {
            cache.put(actionKey, success("cached"), producer(scope),
                    new ActionCache.WriterIdentity("runner", "elmos.internal", "node-1", true),
                    ActionCache.RiskTier.STANDARD, Optional.empty());
        }

        private ActionResultRecord success(String value) {
            byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
            CasDigest output = CasDigest.of(bytes);
            store.put(output, bytes);
            return ActionResultRecord.succeeded("action-1", "receipt-1", output,
                    digest("provenance"), new ActionResultRecord.ResourceUsage(
                            1, 128, 10, 20, 0, 2), "start", "finish");
        }

        private ActionResultRecord failure() {
            byte[] bytes = "compile diagnostics".getBytes(StandardCharsets.UTF_8);
            CasDigest output = CasDigest.of(bytes);
            store.put(output, bytes);
            return ActionResultRecord.failed("action-1", "receipt-failed", 1,
                    ActionResultRecord.FailureClass.CODE, "does not compile", output,
                    digest("provenance"), new ActionResultRecord.ResourceUsage(
                            1, 128, 10, 20, 0, 2), "start", "finish");
        }

        private CasAccessPolicy.ProducerContext producer(Set<String> scope) {
            return new CasAccessPolicy.ProducerContext(
                    "tenant-a", "project-a", scope, "eu-west",
                    CasAccessPolicy.SecurityTier.INTERNAL,
                    CasObjectModel.Sensitivity.GENERATED_OUTPUT, IMAGE,
                    Optional.of(digest("producer provenance")));
        }

        private CasAccessPolicy.ReaderContext reader(Set<String> scope) {
            return new CasAccessPolicy.ReaderContext(
                    "tenant-a", scope, "eu-west",
                    CasAccessPolicy.SecurityTier.INTERNAL, false);
        }

        private CachedActionExecutor.Request request(
                ActionKey actionKey, CasAccessPolicy.ReaderContext reader,
                boolean bypass, CachedActionExecutor.Mode mode) {
            return new CachedActionExecutor.Request(actionKey, reader, bypass, mode);
        }

        private static ActionKey key(Set<String> scope) {
            return new ActionKeyBuilder()
                    .tenant("tenant-a", "project-a")
                    .sourceTree(digest("source"))
                    .toolchainImage(IMAGE)
                    .command(List.of("./mvnw", "verify"))
                    .workingDirectory("/workspace/source")
                    .declaredOutputs(List.of("target"))
                    .policy(digest("policy"))
                    .permissionScope(scope)
                    .sandbox("S2", digest("sandbox"))
                    .dataResidency("eu-west")
                    .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                    .environment(Map.of())
                    .build();
        }
    }

    private static CasDigest digest(String value) {
        return CasDigest.ofUtf8(value);
    }
}
