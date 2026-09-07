package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.LongSupplier;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ActionCacheTrustRevalidationTest {

    private static final long NOW = 2_000_000L;
    private static final String IMAGE = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);

    @Test void aCurrentSignerRevocationInvalidatesAnOtherwiseValidDurableHit() throws Exception {
        InMemoryCasStore store = new InMemoryCasStore("objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 100_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        ActionCache.ResultAttestation attestation = verifier.attestation(
                key, result, producer, writer, ActionCache.RiskTier.HIGH, signature, NOW);
        byte[] callerOwnedSignature = signature.value();
        ActionCache.ResultAttestation copiedAttestation =
                ActionCache.ResultAttestation.verified(
                        signature.keyId(), signature.algorithm(), signature.digest(),
                        callerOwnedSignature, envelope.version(), envelope.digest(),
                        signature.signedAtEpochMillis());
        callerOwnedSignature[0] ^= 1;
        assertEquals(attestation, copiedAttestation,
                "attestation must clone signature bytes supplied by its caller");
        byte[] exposedSignature = attestation.signatureValue().orElseThrow();
        assertArrayEquals(signature.value(), exposedSignature);
        exposedSignature[0] ^= 1;
        assertArrayEquals(signature.value(), attestation.signatureValue().orElseThrow(),
                "attestation must not expose its owned signature bytes");
        cache.put(key, result, producer, writer, ActionCache.RiskTier.HIGH,
                Optional.of(attestation));

        assertEquals(ActionCache.CacheOutcome.HIT,
                cache.get(key, reader(), false).outcome());
        assertTrue(registry.revoke("signer-v1"));
        ActionCache.Lookup revoked = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.INVALIDATED, revoked.outcome());
        assertEquals("CURRENT_TRUST_REVOKED", revoked.reason());
        assertEquals(ActionCache.CacheOutcome.MISS,
                cache.get(key, reader(), false).outcome());
    }

    @Test void currentTrustCryptographicallyRejectsTamperedDetachedSignatureBytes()
            throws Exception {
        InMemoryCasStore store = new InMemoryCasStore("tampered-signature-objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 100_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        byte[] tampered = signature.value();
        tampered[tampered.length - 1] ^= 1;
        ActionCache.ResultAttestation forgedPersistedReceipt =
                ActionCache.ResultAttestation.verified(
                        signature.keyId(), signature.algorithm(), CasDigest.of(tampered), tampered,
                        envelope.version(), envelope.digest(), signature.signedAtEpochMillis());
        index.store(new ActionCache.Entry(key, result, producer, writer,
                Optional.of(forgedPersistedReceipt), ActionCache.RiskTier.HIGH,
                NOW, Optional.empty()));

        ActionCache.Lookup lookup = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals("CURRENT_TRUST_DENIED:CURRENT_SIGNATURE_DOES_NOT_VERIFY",
                lookup.reason());
        assertEquals(1, index.size("tenant-a"),
                "a denied cryptographic receipt must never become a hit");
    }

    @Test void malformedDetachedSignatureIsDeniedInsteadOfReportedAsProviderOutage()
            throws Exception {
        InMemoryCasStore store = new InMemoryCasStore("malformed-signature-objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 100_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        byte[] truncated = Arrays.copyOf(signature.value(), signature.value().length - 1);
        ActionCache.ResultAttestation malformed = ActionCache.ResultAttestation.verified(
                signature.keyId(), signature.algorithm(), CasDigest.of(truncated), truncated,
                envelope.version(), envelope.digest(), signature.signedAtEpochMillis());
        index.store(new ActionCache.Entry(key, result, producer, writer, Optional.of(malformed),
                ActionCache.RiskTier.HIGH, NOW, Optional.empty()));

        ActionCache.Lookup lookup = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals("CURRENT_TRUST_DENIED:CURRENT_SIGNATURE_MALFORMED", lookup.reason());
    }

    @Test void aVerifiedReceiptCannotBeHeldPastItsWritePresentationWindow()
            throws Exception {
        AtomicLong now = new AtomicLong(NOW);
        InMemoryCasStore store = new InMemoryCasStore("delayed-write-objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 10_000_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, now::get, verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        ActionCache.ResultAttestation attestation = verifier.attestation(
                key, result, producer, writer, ActionCache.RiskTier.HIGH, signature, NOW);

        now.set(NOW + 16 * 60 * 1000L);
        CasExceptions.CasAccessDeniedException delayed = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> cache.put(key, result, producer, writer, ActionCache.RiskTier.HIGH,
                        Optional.of(attestation)));
        assertEquals("RESULT_ATTESTATION_PRESENTATION_EXPIRED", delayed.reason());
        assertEquals(0, index.size("tenant-a"));
    }

    @Test void legacyDigestOnlyAttestationIsUnknownAndCannotBeWrittenAsNewEvidence()
            throws Exception {
        InMemoryCasStore store = new InMemoryCasStore("legacy-signature-objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 100_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        ActionCache.ResultAttestation legacy =
                ActionCache.ResultAttestation.legacyVerifiedWithoutSignatureBytes(
                        signature.keyId(), signature.algorithm(), signature.digest(),
                        envelope.version(), envelope.digest(), signature.signedAtEpochMillis());

        CasExceptions.CasAccessDeniedException rejected = assertThrows(
                CasExceptions.CasAccessDeniedException.class,
                () -> cache.put(key, result, producer, writer, ActionCache.RiskTier.HIGH,
                        Optional.of(legacy)));
        assertEquals("RESULT_ATTESTATION_SIGNATURE_BYTES_MISSING", rejected.reason());

        index.store(new ActionCache.Entry(key, result, producer, writer, Optional.of(legacy),
                ActionCache.RiskTier.HIGH, NOW, Optional.empty()));
        ActionCache.Lookup lookup = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals(
                "CURRENT_TRUST_UNKNOWN:LEGACY_ATTESTATION_SIGNATURE_BYTES_MISSING",
                lookup.reason());
        assertEquals(1, index.size("tenant-a"));
    }

    @Test void durableLookupDoesNotReuseTheWritePresentationReplayWindow()
            throws Exception {
        AtomicLong now = new AtomicLong(NOW);
        InMemoryCasStore store = new InMemoryCasStore("long-lived-signature-objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        KeyPair pair = KeyPairGenerator.getInstance(ResultSignature.ED25519).generateKeyPair();
        ResultSignature.KeyRegistry registry = ResultSignature.KeyRegistry.ed25519Only()
                .register(new ResultSignature.SigningKey("signer-v1", ResultSignature.ED25519,
                        pair.getPublic(), NOW - 1000, NOW + 10_000_000));
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registry, ResultSignature.VerificationPolicy.standard());
        ActionCache cache = cache(store, index, now::get,
                verifier.currentTrustRevalidator());
        ActionKey key = key();
        ActionResultRecord result = result(store);
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = ResultSignature.envelope(
                key, result, producer, writer, ActionCache.RiskTier.HIGH,
                "signer-v1", ResultSignature.ED25519, NOW);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(
                envelope, pair.getPrivate(), "signer-v1", ResultSignature.ED25519, NOW);
        cache.put(key, result, producer, writer, ActionCache.RiskTier.HIGH,
                Optional.of(verifier.attestation(key, result, producer, writer,
                        ActionCache.RiskTier.HIGH, signature, NOW)));

        now.set(NOW + 16 * 60 * 1000L);
        assertEquals(ActionCache.CacheOutcome.HIT, cache.get(key, reader(), false).outcome(),
                "the 15-minute write anti-replay policy is not a cache-entry TTL");
    }

    @Test void unknownAndUnavailableTrustStateNeverBecomeHitsOrDeleteRecoverableEntries() {
        InMemoryCasStore store = new InMemoryCasStore("objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        AtomicReference<ActionCache.TrustDecision> current = new AtomicReference<>(
                ActionCache.TrustDecision.unknown("TRUST_SERVICE_TIMEOUT"));
        ActionCache cache = cache(store, index, (entry, now) -> current.get());
        ActionKey key = key();
        cache.put(key, result(store), producer(), writer(), ActionCache.RiskTier.STANDARD,
                Optional.empty());

        ActionCache.Lookup unknown = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, unknown.outcome());
        assertEquals("CURRENT_TRUST_UNKNOWN:TRUST_SERVICE_TIMEOUT", unknown.reason());
        assertEquals(1, index.size("tenant-a"));

        current.set(ActionCache.TrustDecision.trusted("CURRENT_WRITER_TRUSTED"));
        assertEquals(ActionCache.CacheOutcome.HIT, cache.get(key, reader(), false).outcome());

        ActionCache unavailableCache = cache(store, index, (entry, now) -> {
            throw new IllegalStateException("provider unavailable");
        });
        ActionCache.Lookup unavailable = unavailableCache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, unavailable.outcome());
        assertEquals("CURRENT_TRUST_UNKNOWN:CURRENT_TRUST_PROVIDER_UNAVAILABLE",
                unavailable.reason());
        assertEquals(1, index.size("tenant-a"));
    }

    @Test void durableIndexConstructorDefaultsToFailClosedCurrentTrust() {
        InMemoryCasStore store = new InMemoryCasStore("objects");
        InMemoryActionCacheIndex index = new InMemoryActionCacheIndex();
        ActionCache cache = new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), () -> NOW,
                new CasMetrics(), index, CasTelemetry.noop());
        ActionKey key = key();
        cache.put(key, result(store), producer(), writer(), ActionCache.RiskTier.STANDARD,
                Optional.empty());

        ActionCache.Lookup lookup = cache.get(key, reader(), false);
        assertEquals(ActionCache.CacheOutcome.DENIED, lookup.outcome());
        assertEquals("CURRENT_TRUST_UNKNOWN:CURRENT_TRUST_PROVIDER_NOT_CONFIGURED",
                lookup.reason());
        assertEquals(1, index.size("tenant-a"));
    }

    private static ActionCache cache(InMemoryCasStore store, ActionCacheIndex index,
                                     ActionCache.TrustRevalidator trustRevalidator) {
        return cache(store, index, () -> NOW, trustRevalidator);
    }

    private static ActionCache cache(InMemoryCasStore store, ActionCacheIndex index,
                                     LongSupplier clock,
                                     ActionCache.TrustRevalidator trustRevalidator) {
        return new ActionCache(TenantCasStore.global(store), new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), clock,
                new CasMetrics(), index, CasTelemetry.noop(), trustRevalidator);
    }

    private static ActionKey key() {
        return new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("source"))
                .toolchainImage(IMAGE)
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
    }

    private static ActionResultRecord result(InMemoryCasStore store) {
        byte[] bytes = "output manifest".getBytes(StandardCharsets.UTF_8);
        CasDigest manifest = CasDigest.of(bytes);
        store.put(manifest, bytes);
        return ActionResultRecord.succeeded("action-1", "receipt-1", manifest,
                digest("provenance"), new ActionResultRecord.ResourceUsage(
                        1, 128, 10, 20, 0, 2), "start", "finish");
    }

    private static CasAccessPolicy.ProducerContext producer() {
        return new CasAccessPolicy.ProducerContext(
                "tenant-a", "project-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, IMAGE,
                Optional.of(digest("producer provenance")));
    }

    private static CasAccessPolicy.ReaderContext reader() {
        return new CasAccessPolicy.ReaderContext(
                "tenant-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false);
    }

    private static ActionCache.WriterIdentity writer() {
        return new ActionCache.WriterIdentity(
                "runner", "elmos.internal", "node-1", true);
    }

    private static CasDigest digest(String value) {
        return CasDigest.ofUtf8(value);
    }
}
