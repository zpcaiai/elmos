package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class ActionCacheTest {

    private static final String PINNED_IMAGE = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);

    private final AtomicLong clock = new AtomicLong(1_000_000);
    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final CasMetrics metrics = new CasMetrics();

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    private ActionCache cache(ActionCache.FailureCachePolicy failurePolicy,
                              ActionCache.SampleRecomputePolicy samplePolicy) {
        return new ActionCache(store, new CasAccessPolicy(), failurePolicy, samplePolicy, clock::get, metrics);
    }

    private ActionCache cache(ActionCacheIndex index) {
        return new ActionCache(TenantCasStore.global(store), new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(), ActionCache.SampleRecomputePolicy.disabled(),
                clock::get, metrics, index, CasTelemetry.noop(),
                ActionCache.TrustRevalidator.persistedDecisionCompatibility());
    }

    private ActionCache cache() {
        return cache(ActionCache.FailureCachePolicy.none(), ActionCache.SampleRecomputePolicy.disabled());
    }

    private static ActionKey key(String tenant, Set<String> scope) {
        return new ActionKeyBuilder()
                .tenant(tenant, "project-a")
                .sourceTree(digest("source"))
                .toolchainImage(PINNED_IMAGE)
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

    private static ActionKey legacyV1(ActionKey canonical) {
        CasManifest.CanonicalEncoder encoder =
                new CasManifest.CanonicalEncoder("elmos-action-key/1");
        canonical.components().forEach(encoder::field);
        return new ActionKey(CasDigest.of(encoder.bytes()), canonical.tenantId(),
                canonical.components());
    }

    private static ActionKey forgedDigest(ActionKey canonical) {
        return new ActionKey(digest("forged-action-key-digest"), canonical.tenantId(),
                canonical.components());
    }

    private CasAccessPolicy.ProducerContext producer(String tenant, Set<String> scope,
                                                     CasAccessPolicy.SecurityTier tier,
                                                     CasObjectModel.Sensitivity sensitivity) {
        return new CasAccessPolicy.ProducerContext(tenant, "project-a", scope, "eu-west", tier, sensitivity,
                PINNED_IMAGE, Optional.of(digest("provenance")));
    }

    private CasAccessPolicy.ReaderContext reader(String tenant, Set<String> scope,
                                                 CasAccessPolicy.SecurityTier clearance, boolean sharing) {
        return new CasAccessPolicy.ReaderContext(tenant, scope, "eu-west", clearance, sharing);
    }

    private ActionResultRecord storedSuccess(String outputContent) {
        CasDigest manifest = digest(outputContent);
        store.put(manifest, outputContent.getBytes(StandardCharsets.UTF_8));
        return ActionResultRecord.succeeded("act-1", "receipt-1", manifest, digest("provenance"),
                new ActionResultRecord.ResourceUsage(120, 2048, 1_000, 500, 0, 300),
                "2026-08-19T06:30:00Z", "2026-08-19T06:35:00Z");
    }

    private static ActionCache.WriterIdentity writer(String nodeId) {
        return new ActionCache.WriterIdentity("runner", "elmos.internal", nodeId, true);
    }

    @Test void cacheAndInMemoryIndexRejectLegacyAndForgedKeysAtEveryKeyBoundary() {
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        ActionCache cache = cache(index);
        ActionKey canonical = key("tenant-a", Set.of("repo:read"));
        ActionResultRecord result = storedSuccess("canonical-only output");
        CasAccessPolicy.ProducerContext producer = producer(
                "tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        CasAccessPolicy.ReaderContext reader = reader(
                "tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, false);

        for (ActionKey invalid : List.of(legacyV1(canonical), forgedDigest(canonical))) {
            ActionCache.Entry invalidEntry = new ActionCache.Entry(
                    invalid, result, producer, writer("node-invalid"), Optional.empty(),
                    ActionCache.RiskTier.STANDARD, clock.get(), Optional.empty());

            assertThrows(IllegalArgumentException.class,
                    () -> cache.put(invalid, result, producer, writer("node-invalid"),
                            ActionCache.RiskTier.STANDARD, Optional.empty()));
            assertThrows(IllegalArgumentException.class,
                    () -> cache.get(invalid, reader, false));
            assertThrows(IllegalArgumentException.class,
                    () -> cache.get(invalid, reader, true));
            assertThrows(IllegalArgumentException.class,
                    () -> cache.confirmRecompute(invalid, result.outputManifestDigest()));
            assertThrows(IllegalArgumentException.class,
                    () -> cache.invalidate(invalid, "INVALID_KEY_MUST_NOT_MUTATE"));

            assertThrows(IllegalArgumentException.class, () -> index.find(invalid));
            assertThrows(IllegalArgumentException.class, () -> index.store(invalidEntry));
            assertThrows(IllegalArgumentException.class,
                    () -> index.invalidate(invalid, "INVALID_KEY_MUST_NOT_MUTATE", clock.get()));
        }
        assertEquals(0, index.size("tenant-a"));
    }

    @Test void unchangedRerunReusesTheResult() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        cache.put(actionKey, storedSuccess("output"), producer("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        var lookup = cache.get(actionKey, reader("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, false), false);
        assertEquals(ActionCache.CacheOutcome.HIT, lookup.outcome());
        assertEquals("receipt-1", lookup.result().orElseThrow().receiptId());
        assertEquals(1, metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.HIT));
        assertEquals(300_000, metrics.wallMillisAvoided());
    }

    @Test void aChangedInputCannotHitTheOldOutput() {
        ActionCache cache = cache();
        ActionKey original = key("tenant-a", Set.of("repo:read"));
        cache.put(original, storedSuccess("output"), producer("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        ActionKey newToolchain = new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("source"))
                .toolchainImage("registry.internal/elmos/java21@sha256:" + "b".repeat(64))
                .command(List.of("./mvnw", "verify"))
                .workingDirectory("/workspace/source")
                .declaredOutputs(List.of("target"))
                .policy(digest("policy"))
                .permissionScope(Set.of("repo:read"))
                .sandbox("S2", digest("sandbox"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                .environment(Map.of())
                .build();

        var lookup = cache.get(newToolchain, reader("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, false), false);
        assertEquals(ActionCache.CacheOutcome.MISS, lookup.outcome());
        assertEquals(List.of("toolchain_image"), original.explainDifference(newToolchain));
    }

    @Test void aReaderWithFewerPermissionsIsDeniedRatherThanServed() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read", "secret:read"));
        cache.put(actionKey, storedSuccess("privileged output"),
                producer("tenant-a", Set.of("repo:read", "secret:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        var lookup = cache.get(actionKey, reader("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, false), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals("PERMISSION_DOWNGRADE", lookup.reason());
        assertTrue(lookup.result().isEmpty());
    }

    @Test void anotherTenantCannotReadGeneratedOutput() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        cache.put(actionKey, storedSuccess("private output"),
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        var lookup = cache.get(actionKey, reader("tenant-b", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.RESTRICTED, true), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals("CROSS_TENANT_REUSE_DISABLED", lookup.reason());
    }

    @Test void publicDependencyContentIsShareableOnlyWithExplicitOptIn() {
        CasAccessPolicy policy = new CasAccessPolicy();
        var shared = producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.PUBLIC,
                CasObjectModel.Sensitivity.PUBLIC_DEPENDENCY);
        assertEquals("CROSS_TENANT_SHARING_NOT_ENABLED", policy.evaluateRead(
                reader("tenant-b", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, false), shared).reason());
        assertTrue(policy.evaluateRead(
                reader("tenant-b", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, true), shared).allowed());
    }

    @Test void aReaderBelowTheClassificationIsDenied() {
        CasAccessPolicy policy = new CasAccessPolicy();
        var restricted = producer("tenant-a", Set.of(), CasAccessPolicy.SecurityTier.RESTRICTED,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        assertEquals("SECURITY_TIER_TOO_LOW", policy.evaluateRead(
                reader("tenant-a", Set.of(), CasAccessPolicy.SecurityTier.INTERNAL, false), restricted).reason());
    }

    @Test void residencyIsEnforcedOnRead() {
        CasAccessPolicy policy = new CasAccessPolicy();
        var euProducer = producer("tenant-a", Set.of(), CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        var usReader = new CasAccessPolicy.ReaderContext("tenant-a", Set.of(), "us-east",
                CasAccessPolicy.SecurityTier.RESTRICTED, true);
        assertEquals("DATA_RESIDENCY_MISMATCH", policy.evaluateRead(usReader, euProducer).reason());
    }

    @Test void transientFailuresAreNeverRememberedAsResults() {
        ActionCache cache = cache(ActionCache.FailureCachePolicy.deterministicOnly(60_000),
                ActionCache.SampleRecomputePolicy.disabled());
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        CasDigest manifest = digest("empty output");
        store.put(manifest, "empty output".getBytes(StandardCharsets.UTF_8));

        ActionResultRecord environmentFailure = ActionResultRecord.failed("act-1", "receipt-2", 1,
                ActionResultRecord.FailureClass.ENVIRONMENT, "runner disk full", manifest, digest("provenance"),
                new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1),
                "2026-08-19T06:30:00Z", "2026-08-19T06:30:10Z");

        assertTrue(cache.put(actionKey, environmentFailure,
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty()).isEmpty());
        assertEquals(0, cache.size());
        assertThrows(IllegalArgumentException.class, () -> new ActionCache.FailureCachePolicy(
                Set.of(ActionResultRecord.FailureClass.CAPACITY), 1_000));
        assertThrows(IllegalArgumentException.class,
                () -> ActionCache.FailureCachePolicy.deterministicOnly(0));
        assertThrows(IllegalArgumentException.class,
                () -> ActionCache.FailureCachePolicy.deterministicOnly(-1));
    }

    @Test void deterministicFailuresAreCachedButExpire() {
        ActionCache cache = cache(ActionCache.FailureCachePolicy.deterministicOnly(60_000),
                ActionCache.SampleRecomputePolicy.disabled());
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        CasDigest manifest = digest("compile errors");
        store.put(manifest, "compile errors".getBytes(StandardCharsets.UTF_8));
        ActionResultRecord codeFailure = ActionResultRecord.failed("act-1", "receipt-3", 1,
                ActionResultRecord.FailureClass.CODE, "does not compile", manifest, digest("provenance"),
                new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1),
                "2026-08-19T06:30:00Z", "2026-08-19T06:30:10Z");
        cache.put(actionKey, codeFailure, producer("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        var reader = reader("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, false);
        assertEquals(ActionCache.CacheOutcome.HIT, cache.get(actionKey, reader, false).outcome());

        clock.addAndGet(120_000);
        var stale = cache.get(actionKey, reader, false);
        assertEquals(ActionCache.CacheOutcome.STALE, stale.outcome());
        assertEquals("FAILURE_TTL_EXPIRED", stale.reason());
        assertEquals(ActionCache.CacheOutcome.MISS, cache.get(actionKey, reader, false).outcome());
    }

    @Test void unattestedWritersAndQuarantinedNodesCannotWrite() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var context = producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        ActionResultRecord result = storedSuccess("output");

        assertThrows(CasExceptions.CasAccessDeniedException.class, () -> cache.put(actionKey, result, context,
                new ActionCache.WriterIdentity("runner", "elmos.internal", "node-1", false),
                ActionCache.RiskTier.STANDARD, Optional.empty()));

        cache.quarantineNode("node-2", "suspected poisoning");
        assertThrows(CasExceptions.CasAccessDeniedException.class, () -> cache.put(actionKey, result, context,
                writer("node-2"), ActionCache.RiskTier.STANDARD, Optional.empty()));
    }

    @Test void highRiskResultsRejectUnsignedAndCallerConstructedUnverifiedAttestations() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var context = producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        ActionResultRecord result = storedSuccess("release artifact");

        assertThrows(CasExceptions.CasAccessDeniedException.class, () -> cache.put(actionKey, result, context,
                writer("node-1"), ActionCache.RiskTier.HIGH, Optional.empty()));
        assertThrows(CasExceptions.CasAccessDeniedException.class, () -> cache.put(actionKey, result, context,
                writer("node-1"), ActionCache.RiskTier.HIGH,
                Optional.of(ActionCache.ResultAttestation.unverified(
                        "kms", ResultSignature.ED25519, digest("sig"),
                        ResultSignature.ENVELOPE_FORMAT, digest("envelope"), clock.get()))));
        assertEquals(0, ActionCache.ResultAttestation.class.getConstructors().length,
                "no public constructor may mint a verified receipt");
    }

    @Test void aResultWhoseOutputIsNotStoredIsRefused() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        ActionResultRecord dangling = ActionResultRecord.succeeded("act-1", "receipt-9", digest("never stored"),
                digest("provenance"), new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1),
                "2026-08-19T06:30:00Z", "2026-08-19T06:35:00Z");
        assertThrows(CasExceptions.CasNotFoundException.class, () -> cache.put(actionKey, dangling,
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty()));
    }

    @Test void sampledRecomputeMismatchQuarantinesTheProducingNode() {
        ActionCache cache = cache(ActionCache.FailureCachePolicy.none(), new ActionCache.SampleRecomputePolicy(1));
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        cache.put(actionKey, storedSuccess("deterministic output"),
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-7"), ActionCache.RiskTier.STANDARD, Optional.empty());
        var reader = reader("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, false);

        var hit = cache.get(actionKey, reader, false);
        assertEquals(ActionCache.CacheOutcome.HIT, hit.outcome());
        var recompute = hit.recompute().orElseThrow();
        assertEquals(digest("deterministic output"), recompute.expectedOutputManifestDigest());

        assertTrue(cache.confirmRecompute(actionKey, digest("deterministic output")));
        assertFalse(cache.confirmRecompute(actionKey, digest("something else")));
        assertTrue(cache.isNodeQuarantined("tenant-a", "node-7"));
        assertEquals(0, cache.size());
        assertEquals(1, cache.nondeterminismIncidents().size());
    }

    @Test void twoInstancesSharingAnIndexObserveTheSameHit() {
        InMemoryActionCacheIndex durableIndex = new InMemoryActionCacheIndex();
        ActionCache writerCache = cache(durableIndex);
        ActionCache readerCache = cache(durableIndex);
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        writerCache.put(actionKey, storedSuccess("shared output"),
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        ActionCache.Lookup lookup = readerCache.get(actionKey,
                reader("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, false), false);

        assertEquals(ActionCache.CacheOutcome.HIT, lookup.outcome());
        assertEquals("receipt-1", lookup.result().orElseThrow().receiptId());
        assertEquals(1, readerCache.size("tenant-a"));
    }

    @Test void durableQuarantineIsTenantScopedAcrossInstances() {
        InMemoryActionCacheIndex durableIndex = new InMemoryActionCacheIndex();
        ActionCache first = cache(durableIndex);
        ActionCache second = cache(durableIndex);
        first.quarantineNode("tenant-a", "shared-node-name", "attestation revoked");

        ActionResultRecord output = storedSuccess("tenant-scoped output");
        assertThrows(CasExceptions.CasAccessDeniedException.class, () -> second.put(
                key("tenant-a", Set.of("repo:read")), output,
                producer("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("shared-node-name"), ActionCache.RiskTier.STANDARD, Optional.empty()));

        assertDoesNotThrow(() -> second.put(key("tenant-b", Set.of("repo:read")), output,
                producer("tenant-b", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("shared-node-name"), ActionCache.RiskTier.STANDARD, Optional.empty()));
    }

    @Test void anActiveActionKeyCannotBeReboundToDifferentOutput() {
        InMemoryActionCacheIndex durableIndex = new InMemoryActionCacheIndex();
        ActionCache cache = cache(durableIndex);
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var context = producer("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        cache.put(actionKey, storedSuccess("first output"), context, writer("node-1"),
                ActionCache.RiskTier.STANDARD, Optional.empty());

        CasExceptions.CasAccessDeniedException conflict = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> cache.put(actionKey, storedSuccess("different output"), context,
                        writer("node-2"), ActionCache.RiskTier.STANDARD, Optional.empty()));
        assertTrue(conflict.getMessage().contains("ACTION_KEY_RESULT_CONFLICT"));
    }

    @Test void anActiveActionKeyAcceptsOnlyAnExactSemanticReplay() {
        InMemoryActionCacheIndex durableIndex = new InMemoryActionCacheIndex();
        ActionCache cache = cache(durableIndex);
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var context = producer("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT);
        ActionResultRecord result = storedSuccess("same output");

        cache.put(actionKey, result, context, writer("node-1"),
                ActionCache.RiskTier.STANDARD, Optional.empty());
        assertDoesNotThrow(() -> cache.put(actionKey, result, context, writer("node-1"),
                ActionCache.RiskTier.STANDARD, Optional.empty()));
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> cache.put(actionKey, result, context, writer("node-2"),
                        ActionCache.RiskTier.STANDARD, Optional.empty()));
    }

    @Test void bypassIsRecordedSeparatelyFromMisses() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var lookup = cache.get(actionKey, reader("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, false), true);
        assertEquals(ActionCache.CacheOutcome.BYPASS, lookup.outcome());
        assertEquals(0d, metrics.exactHitRate(CasMetrics.Layer.ACTION));
        assertEquals(0, metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.MISS));
    }

    @Test void aCollectedOutputInvalidatesItsCacheEntry() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        ActionResultRecord result = storedSuccess("collectable output");
        cache.put(actionKey, result, producer("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());

        store.delete(result.outputManifestDigest());
        var lookup = cache.get(actionKey, reader("tenant-a", Set.of("repo:read"),
                CasAccessPolicy.SecurityTier.INTERNAL, false), false);
        assertEquals(ActionCache.CacheOutcome.INVALIDATED, lookup.outcome());
        assertEquals("OUTPUT_MANIFEST_MISSING", lookup.reason());
    }

    @Test void aPoisonedOutputManifestIsNeverReportedAsAHit() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        ActionResultRecord result = storedSuccess("trusted output manifest");
        cache.put(actionKey, result, producer("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL,
                        CasObjectModel.Sensitivity.GENERATED_OUTPUT),
                writer("node-1"), ActionCache.RiskTier.STANDARD, Optional.empty());
        store.corruptForFaultInjection(result.outputManifestDigest(),
                "poisoned output manifest".getBytes(StandardCharsets.UTF_8));

        ActionCache.Lookup lookup = cache.get(actionKey,
                reader("tenant-a", Set.of("repo:read"),
                        CasAccessPolicy.SecurityTier.INTERNAL, false), false);

        assertEquals(ActionCache.CacheOutcome.INVALIDATED, lookup.outcome());
        assertEquals("OUTPUT_MANIFEST_CORRUPT", lookup.reason());
        assertTrue(lookup.result().isEmpty());
    }

    @Test void missReasonsAreCountedSoUnexpectedMissesCanBeExplained() {
        ActionCache cache = cache();
        ActionKey actionKey = key("tenant-a", Set.of("repo:read"));
        var reader = reader("tenant-a", Set.of("repo:read"), CasAccessPolicy.SecurityTier.INTERNAL, false);
        cache.get(actionKey, reader, false);
        cache.get(actionKey, reader, false);
        assertEquals(Long.valueOf(2), metrics.explain().get("ACTION/MISS/NO_ENTRY"));
    }
}
