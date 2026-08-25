package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class ResultSignatureTest {

    private static final String PINNED_IMAGE = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);
    private static final long NOW = 1_800_000_000_000L;

    private final AtomicLong clock = new AtomicLong(NOW);
    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final CasMetrics metrics = new CasMetrics();

    @Test void writePresentationPolicyCannotExceedTheDurableIndexBoundary() {
        assertDoesNotThrow(() -> new ResultSignature.VerificationPolicy(1, 0));
        assertDoesNotThrow(ResultSignature.VerificationPolicy::standard);
        assertThrows(IllegalArgumentException.class,
                () -> new ResultSignature.VerificationPolicy(
                        ResultSignature.VerificationPolicy
                                .PLATFORM_MAXIMUM_SIGNATURE_AGE_MILLIS + 1,
                        0));
        assertThrows(IllegalArgumentException.class,
                () -> new ResultSignature.VerificationPolicy(1,
                        ResultSignature.VerificationPolicy
                                .PLATFORM_MAXIMUM_CLOCK_SKEW_MILLIS + 1));
    }

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    private static KeyPair ed25519() throws Exception {
        return KeyPairGenerator.getInstance("Ed25519").generateKeyPair();
    }

    private static ActionKey key(String tenant) {
        return new ActionKeyBuilder()
                .tenant(tenant, "project-a")
                .sourceTree(digest("source"))
                .toolchainImage(PINNED_IMAGE)
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

    private static CasAccessPolicy.ProducerContext producer() {
        return new CasAccessPolicy.ProducerContext("tenant-a", "project-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                PINNED_IMAGE, Optional.of(digest("provenance")));
    }

    private static ActionCache.WriterIdentity writer() {
        return new ActionCache.WriterIdentity("runner", "elmos.internal", "node-1", true);
    }

    private ActionResultRecord result(String outputContent) {
        CasDigest manifest = digest(outputContent);
        store.put(manifest, outputContent.getBytes(StandardCharsets.UTF_8));
        return ActionResultRecord.succeeded("act-1", "receipt-1", manifest, digest("provenance"),
                new ActionResultRecord.ResourceUsage(10, 512, 100, 50, 0, 20),
                "2026-08-19T06:30:00Z", "2026-08-19T06:35:00Z");
    }

    private static ResultSignature.KeyRegistry registryFor(KeyPair pair, String keyId, long from, long to) {
        return ResultSignature.KeyRegistry.ed25519Only().register(new ResultSignature.SigningKey(
                keyId, ResultSignature.ED25519, pair.getPublic(), from, to));
    }

    @Test void aGenuineSignatureVerifies() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        ActionResultRecord record = result("output");
        var envelope = envelope(actionKey, record, producer(), writer(), ActionCache.RiskTier.STANDARD);
        var signature = ResultSignature.sign(envelope, pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);

        var verifier = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        assertTrue(verifier.verify(envelope, signature, NOW).verified());
    }

    @Test void ed25519SignaturesAreDeterministicSoTheEntryStaysAddressable() throws Exception {
        KeyPair pair = ed25519();
        var envelope = envelope(key("tenant-a"), result("output"), producer(), writer(),
                ActionCache.RiskTier.STANDARD);
        var first = ResultSignature.sign(envelope, pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);
        var second = ResultSignature.sign(envelope, pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);
        assertArrayEquals(first.value(), second.value());
        assertEquals(first.digest(), second.digest());
    }

    @Test void aSignatureCannotBeReplayedOntoADifferentActionKey() throws Exception {
        KeyPair pair = ed25519();
        ActionResultRecord record = result("output");
        var signedEnvelope = envelope(key("tenant-a"), record, producer(), writer(),
                ActionCache.RiskTier.STANDARD);
        var signature = ResultSignature.sign(signedEnvelope, pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);

        ActionKey otherKey = new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("different source"))
                .toolchainImage(PINNED_IMAGE)
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
        var replayed = envelope(otherKey, record, producer(), writer(), ActionCache.RiskTier.STANDARD);

        var verifier = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNATURE_DOES_NOT_VERIFY", verifier.verify(replayed, signature, NOW).reason());
    }

    @Test void aSignatureCannotBeReplayedOntoAWiderPermissionScope() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        ActionResultRecord record = result("output");
        var signature = ResultSignature.sign(
                envelope(actionKey, record, producer(), writer(), ActionCache.RiskTier.STANDARD),
                pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);

        var widened = new CasAccessPolicy.ProducerContext("tenant-a", "project-a",
                Set.of("repo:read", "secret:read"), "eu-west", CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, PINNED_IMAGE, Optional.of(digest("provenance")));
        var envelope = envelope(actionKey, record, widened, writer(), ActionCache.RiskTier.STANDARD);

        var verifier = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNATURE_DOES_NOT_VERIFY", verifier.verify(envelope, signature, NOW).reason());
    }

    @Test void aSignedFailureCannotBeReplayedAsASuccess() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        CasDigest manifest = digest("failure output");
        store.put(manifest, "failure output".getBytes(StandardCharsets.UTF_8));
        var usage = new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1);
        ActionResultRecord failure = ActionResultRecord.failed("act-1", "receipt-1", 1,
                ActionResultRecord.FailureClass.CODE, "does not compile", manifest, digest("provenance"),
                usage, "2026-08-19T06:30:00Z", "2026-08-19T06:30:10Z");
        ActionResultRecord success = ActionResultRecord.succeeded("act-1", "receipt-1", manifest,
                digest("provenance"), usage, "2026-08-19T06:30:00Z", "2026-08-19T06:30:10Z");

        var signature = ResultSignature.sign(
                envelope(actionKey, failure, producer(), writer(), ActionCache.RiskTier.STANDARD),
                pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);
        var verifier = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNATURE_DOES_NOT_VERIFY", verifier.verify(
                envelope(actionKey, success, producer(), writer(), ActionCache.RiskTier.STANDARD),
                signature, NOW).reason());
    }

    @Test void everyResultAndAuthorizationSemanticFieldChangesTheSignedEnvelope() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        CasDigest manifest = digest("failure output");
        store.put(manifest, "failure output".getBytes(StandardCharsets.UTF_8));
        ActionResultRecord base = new ActionResultRecord(
                ActionResultRecord.SCHEMA_VERSION, "act-1", 2, 7, "receipt-1",
                ActionResultRecord.Status.FAILED, "start", "finish", 3, manifest,
                Optional.of(digest("stdout")), Optional.of(digest("stderr")),
                new ActionResultRecord.ResourceUsage(1.25, 512.5, 100, 200, 0.5, 20.75),
                Map.of("usd", 1.5), Optional.of(ActionResultRecord.FailureClass.CODE),
                Optional.of("compile failed"), ActionResultRecord.ValidationStatus.FAIL,
                digest("result provenance"));
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope signedEnvelope = envelope(
                actionKey, base, producer, writer, ActionCache.RiskTier.STANDARD);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(signedEnvelope,
                pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());

        ActionResultRecord otherLease = copyResult(base, 8, base.outputManifestDigest(),
                base.stdoutDigest(), base.stderrDigest(), base.resourceUsage(), base.cost(),
                base.failureClass(), base.failureMessage(), base.validationStatus(),
                base.provenanceDigest());
        ActionResultRecord otherOutput = copyResult(base, base.leaseGeneration(), digest("other output"),
                base.stdoutDigest(), base.stderrDigest(), base.resourceUsage(), base.cost(),
                base.failureClass(), base.failureMessage(), base.validationStatus(),
                base.provenanceDigest());
        ActionResultRecord otherLogs = copyResult(base, base.leaseGeneration(), base.outputManifestDigest(),
                Optional.of(digest("other stdout")), Optional.of(digest("other stderr")),
                base.resourceUsage(), base.cost(), base.failureClass(), base.failureMessage(),
                base.validationStatus(), base.provenanceDigest());
        ActionResultRecord otherFailure = copyResult(base, base.leaseGeneration(),
                base.outputManifestDigest(), base.stdoutDigest(), base.stderrDigest(),
                base.resourceUsage(), base.cost(), Optional.of(ActionResultRecord.FailureClass.POLICY),
                Optional.of("policy failed"), base.validationStatus(), base.provenanceDigest());
        ActionResultRecord otherResources = copyResult(base, base.leaseGeneration(),
                base.outputManifestDigest(), base.stdoutDigest(), base.stderrDigest(),
                new ActionResultRecord.ResourceUsage(9, 1024, 300, 400, 2, 30),
                Map.of("usd", 2.5, "tokens", 17.0), base.failureClass(), base.failureMessage(),
                ActionResultRecord.ValidationStatus.PARTIAL, digest("other result provenance"));

        ActionKey otherKey = new ActionKey(digest("other key"), actionKey.tenantId(),
                actionKey.components());
        Map<String, String> otherComponents = new java.util.LinkedHashMap<>(actionKey.components());
        otherComponents.put("working_directory", "/tampered/source");
        ActionKey sameDigestWithOtherComponents = new ActionKey(
                actionKey.digest(), actionKey.tenantId(), otherComponents);
        CasAccessPolicy.ProducerContext otherSensitivity = new CasAccessPolicy.ProducerContext(
                producer.tenantId(), producer.projectId(), producer.permissionScope(),
                producer.dataResidency(), producer.classification(),
                CasObjectModel.Sensitivity.PRIVATE_SOURCE, producer.toolchainImage(),
                producer.provenanceDigest());
        CasAccessPolicy.ProducerContext otherScope = new CasAccessPolicy.ProducerContext(
                producer.tenantId(), producer.projectId(), Set.of("repo:read", "secret:read"),
                producer.dataResidency(), producer.classification(), producer.sensitivity(),
                producer.toolchainImage(), producer.provenanceDigest());
        CasAccessPolicy.ProducerContext otherProducerProvenance = new CasAccessPolicy.ProducerContext(
                producer.tenantId(), producer.projectId(), producer.permissionScope(),
                producer.dataResidency(), producer.classification(), producer.sensitivity(),
                producer.toolchainImage(), Optional.of(digest("other producer provenance")));

        List<ResultSignature.Envelope> tamperedSubjects = List.of(
                envelope(otherKey, base, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(sameDigestWithOtherComponents, base, producer, writer,
                        ActionCache.RiskTier.STANDARD),
                envelope(actionKey, otherLease, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, otherOutput, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, otherLogs, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, otherFailure, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, otherResources, producer, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, base, otherSensitivity, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, base, otherScope, writer, ActionCache.RiskTier.STANDARD),
                envelope(actionKey, base, otherProducerProvenance, writer,
                        ActionCache.RiskTier.STANDARD),
                envelope(actionKey, base, producer,
                        new ActionCache.WriterIdentity("runner", "elmos.internal", "node-2", true),
                        ActionCache.RiskTier.STANDARD),
                envelope(actionKey, base, producer, writer, ActionCache.RiskTier.HIGH));

        for (ResultSignature.Envelope tampered : tamperedSubjects) {
            assertNotEquals(signedEnvelope.digest(), tampered.digest());
            assertEquals("SIGNATURE_DOES_NOT_VERIFY",
                    verifier.verify(tampered, signature, NOW).reason());
        }
    }

    @Test void aVerifiedReceiptCannotBeReplayedAcrossASubjectBoundary() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        ActionResultRecord record = result("release artifact");
        CasAccessPolicy.ProducerContext producer = producer();
        ActionCache.WriterIdentity writer = writer();
        ResultSignature.Envelope envelope = envelope(
                actionKey, record, producer, writer, ActionCache.RiskTier.STANDARD);
        ResultSignature.DetachedSignature signature = ResultSignature.sign(envelope,
                pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);
        ResultSignature.Verifier verifier = new ResultSignature.Verifier(
                registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        ActionCache.ResultAttestation attestation = verifier.attestation(
                actionKey, record, producer, writer, ActionCache.RiskTier.STANDARD,
                signature, NOW);
        ActionCache.ResultAttestation unknownVersion = ActionCache.ResultAttestation.verified(
                signature.keyId(), signature.algorithm(), signature.digest(), signature.value(),
                "elmos-result-signature/999", envelope.digest(), signature.signedAtEpochMillis());
        ActionCache cache = new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(), ActionCache.SampleRecomputePolicy.disabled(),
                clock::get, metrics);

        assertTrue(cache.put(actionKey, record, producer, writer, ActionCache.RiskTier.STANDARD,
                Optional.of(attestation)).isPresent());
        ActionResultRecord changedLogs = record.withLogs(digest("stdout"), digest("stderr"));
        CasAccessPolicy.ProducerContext widened = new CasAccessPolicy.ProducerContext(
                producer.tenantId(), producer.projectId(), Set.of("repo:read", "secret:read"),
                producer.dataResidency(), producer.classification(), producer.sensitivity(),
                producer.toolchainImage(), producer.provenanceDigest());

        assertSubjectMismatch(() -> cache.put(actionKey, changedLogs, producer, writer,
                ActionCache.RiskTier.STANDARD, Optional.of(attestation)));
        assertSubjectMismatch(() -> cache.put(actionKey, record, widened, writer,
                ActionCache.RiskTier.STANDARD, Optional.of(attestation)));
        assertSubjectMismatch(() -> cache.put(actionKey, record, producer,
                new ActionCache.WriterIdentity("runner", "elmos.internal", "node-2", true),
                ActionCache.RiskTier.STANDARD, Optional.of(attestation)));
        assertSubjectMismatch(() -> cache.put(actionKey, record, producer, writer,
                ActionCache.RiskTier.HIGH, Optional.of(attestation)));
        assertSubjectMismatch(() -> cache.put(actionKey, record, producer, writer,
                ActionCache.RiskTier.STANDARD, Optional.of(unknownVersion)));
    }

    @Test void unknownKeysExpiredKeysAndStaleSignaturesAreAllRefused() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        ActionResultRecord record = result("output");
        var envelope = envelope(actionKey, record, producer(), writer(), ActionCache.RiskTier.STANDARD);
        var signature = ResultSignature.sign(envelope, pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);

        var empty = new ResultSignature.Verifier(ResultSignature.KeyRegistry.ed25519Only(),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNING_KEY_UNKNOWN", empty.verify(envelope, signature, NOW).reason());

        var rotatedOut = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 10_000, NOW - 5_000),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNING_KEY_NOT_VALID_AT_SIGNING_TIME", rotatedOut.verify(envelope, signature, NOW).reason());

        var fresh = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNATURE_TOO_OLD", fresh.verify(envelope, signature, NOW + 3_600_000).reason());
        assertEquals("SIGNATURE_FROM_THE_FUTURE", fresh.verify(envelope, signature, NOW - 3_600_000).reason());
    }

    @Test void anAlgorithmOutsideTheAllowlistIsRefusedAtRegistrationAndAtVerification() throws Exception {
        KeyPair pair = ed25519();
        var registry = ResultSignature.KeyRegistry.ed25519Only();
        assertThrows(IllegalArgumentException.class, () -> registry.register(new ResultSignature.SigningKey(
                "weak", "SHA1withDSA", pair.getPublic(), NOW - 1, NOW + 1)));

        registry.register(new ResultSignature.SigningKey("kms-1", ResultSignature.ED25519, pair.getPublic(),
                NOW - 1000, NOW + 1_000_000));
        assertThrows(IllegalArgumentException.class, () -> registry.register(new ResultSignature.SigningKey(
                "kms-1", ResultSignature.ED25519, pair.getPublic(), NOW - 1000, NOW + 1_000_000)));

        var envelope = ResultSignature.envelope(key("tenant-a"), result("output"), producer(), writer(),
                ActionCache.RiskTier.STANDARD, "kms-1", "SHA256withRSA", NOW);
        var mislabelled = new ResultSignature.DetachedSignature("kms-1", "SHA256withRSA", new byte[64], NOW);
        var verifier = new ResultSignature.Verifier(registry, ResultSignature.VerificationPolicy.standard());
        assertEquals("SIGNATURE_ALGORITHM_NOT_ALLOWED", verifier.verify(envelope, mislabelled, NOW).reason());
    }

    @Test void theActionCacheAcceptsAHighRiskResultOnlyWithARealVerifiedSignature() throws Exception {
        KeyPair pair = ed25519();
        ActionKey actionKey = key("tenant-a");
        ActionResultRecord record = result("release artifact");
        var producer = producer();
        var verifier = new ResultSignature.Verifier(registryFor(pair, "kms-1", NOW - 1000, NOW + 1_000_000),
                ResultSignature.VerificationPolicy.standard());
        var signature = ResultSignature.sign(
                envelope(actionKey, record, producer, writer(), ActionCache.RiskTier.HIGH),
                pair.getPrivate(), "kms-1", ResultSignature.ED25519, NOW);

        ActionCache cache = new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(), ActionCache.SampleRecomputePolicy.disabled(),
                clock::get, metrics);
        var writer = writer();

        var attestation = verifier.attestation(actionKey, record, producer, writer,
                ActionCache.RiskTier.HIGH, signature, NOW);
        assertTrue(attestation.verified());
        assertTrue(cache.put(actionKey, record, producer, writer, ActionCache.RiskTier.HIGH,
                Optional.of(attestation)).isPresent());

        var forged = new ResultSignature.DetachedSignature("kms-1", ResultSignature.ED25519, new byte[64], NOW);
        var error = assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> verifier.attestation(actionKey, record, producer, writer,
                        ActionCache.RiskTier.HIGH, forged, NOW));
        assertEquals("RESULT_SIGNATURE_REJECTED", error.reason());
    }

    private static ResultSignature.Envelope envelope(ActionKey key, ActionResultRecord result,
                                                      CasAccessPolicy.ProducerContext producer,
                                                      ActionCache.WriterIdentity writer,
                                                      ActionCache.RiskTier riskTier) {
        return ResultSignature.envelope(key, result, producer, writer, riskTier,
                "kms-1", ResultSignature.ED25519, NOW);
    }

    private static ActionResultRecord copyResult(ActionResultRecord base, int leaseGeneration,
                                                 CasDigest outputManifest,
                                                 Optional<CasDigest> stdout,
                                                 Optional<CasDigest> stderr,
                                                 ActionResultRecord.ResourceUsage resourceUsage,
                                                 Map<String, Double> cost,
                                                 Optional<ActionResultRecord.FailureClass> failureClass,
                                                 Optional<String> failureMessage,
                                                 ActionResultRecord.ValidationStatus validationStatus,
                                                 CasDigest provenance) {
        return new ActionResultRecord(base.schemaVersion(), base.actionId(), base.attempt(),
                leaseGeneration, base.receiptId(), base.status(), base.startedAt(), base.finishedAt(),
                base.exitCode(), outputManifest, stdout, stderr, resourceUsage, cost, failureClass,
                failureMessage, validationStatus, provenance);
    }

    private static void assertSubjectMismatch(org.junit.jupiter.api.function.Executable write) {
        CasExceptions.CasAccessDeniedException error = assertThrows(
                CasExceptions.CasAccessDeniedException.class, write);
        assertEquals("RESULT_ATTESTATION_SUBJECT_MISMATCH", error.reason());
    }
}
