package io.elmos.cas;

import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * ELMOS-CAS-027. Real detached signatures over cached results, and real verification of them.
 *
 * <p>{@link ActionCache} refuses to store a high-risk result whose attestation is not
 * {@code verified}. Producing that boolean is this class's job.
 *
 * <p>The envelope is the security-relevant part, more than the algorithm. A signature over "the
 * output manifest digest" alone is nearly useless: an attacker who can write to the cache
 * replays a genuine signature from a low-privilege action onto a high-privilege key and the
 * signature checks out. So the envelope binds, in one canonical string:
 *
 * <ul>
 *   <li>the complete action key — which exact work this result is for;</li>
 *   <li>every {@link ActionResultRecord} field, including output/log/provenance digests, lease
 *       generation, failure detail, validation, resource usage and cost;</li>
 *   <li>the complete producer authorization context, result risk tier and attested writer;</li>
 *   <li>the key id and the signing instant — so a rotated or backdated key is detectable.</li>
 * </ul>
 *
 * <p>Ed25519 is the default because the JDK has had it since 15, it needs no parameter choices
 * that can be got wrong, and its signatures are deterministic — two signings of one envelope
 * produce identical bytes, which keeps the cache entry itself content addressable.
 */
public final class ResultSignature {

    public static final String ED25519 = "Ed25519";
    public static final String ENVELOPE_FORMAT = "elmos-result-signature/2";

    private ResultSignature() {
    }

    /** The exact bytes that get signed. Instances can be built only through {@link #envelope}. */
    public static final class Envelope {
        private final String canonical;
        private final String keyId;
        private final String algorithm;
        private final long signedAtEpochMillis;

        private Envelope(String canonical, String keyId, String algorithm,
                         long signedAtEpochMillis) {
            this.canonical = CasText.required(canonical, "canonical");
            this.keyId = CasText.required(keyId, "keyId");
            this.algorithm = CasText.required(algorithm, "algorithm");
            if (signedAtEpochMillis < 0) {
                throw new IllegalArgumentException("signedAtEpochMillis must not be negative");
            }
            this.signedAtEpochMillis = signedAtEpochMillis;
        }

        public byte[] bytes() {
            return canonical.getBytes(java.nio.charset.StandardCharsets.UTF_8);
        }

        public CasDigest digest() {
            return CasDigest.of(bytes());
        }

        public String version() {
            return ENVELOPE_FORMAT;
        }

        public String keyId() {
            return keyId;
        }

        public String algorithm() {
            return algorithm;
        }

        public long signedAtEpochMillis() {
            return signedAtEpochMillis;
        }
    }

    public record SigningKey(String keyId, String algorithm, PublicKey publicKey,
                             long notBeforeEpochMillis, long notAfterEpochMillis) {
        public SigningKey {
            keyId = CasText.required(keyId, "keyId");
            algorithm = CasText.required(algorithm, "algorithm");
            Objects.requireNonNull(publicKey, "publicKey");
            if (notAfterEpochMillis <= notBeforeEpochMillis) {
                throw new IllegalArgumentException("signing key validity window is empty");
            }
        }

        boolean validAt(long epochMillis) {
            return epochMillis >= notBeforeEpochMillis && epochMillis <= notAfterEpochMillis;
        }
    }

    public record DetachedSignature(String keyId, String algorithm, byte[] value, long signedAtEpochMillis) {
        public DetachedSignature {
            keyId = CasText.required(keyId, "keyId");
            algorithm = CasText.required(algorithm, "algorithm");
            value = Objects.requireNonNull(value, "value").clone();
            if (value.length == 0) {
                throw new IllegalArgumentException("signature value must not be empty");
            }
            if (signedAtEpochMillis < 0) {
                throw new IllegalArgumentException("signedAtEpochMillis must not be negative");
            }
        }

        @Override
        public byte[] value() {
            return value.clone();
        }

        public CasDigest digest() {
            return CasDigest.of(value);
        }

        public String hex() {
            return HexFormat.of().formatHex(value);
        }
    }

    public record Verdict(boolean verified, String reason) {
        static Verdict deny(String reason) {
            return new Verdict(false, reason);
        }
    }

    public static Envelope envelope(ActionKey key, ActionResultRecord result,
                                    CasAccessPolicy.ProducerContext producer,
                                    ActionCache.WriterIdentity writer,
                                    ActionCache.RiskTier riskTier,
                                    String keyId, String algorithm,
                                    long signedAtEpochMillis) {
        Objects.requireNonNull(key, "key");
        Objects.requireNonNull(result, "result");
        Objects.requireNonNull(producer, "producer");
        Objects.requireNonNull(writer, "writer");
        Objects.requireNonNull(riskTier, "riskTier");
        keyId = CasText.required(keyId, "keyId");
        algorithm = CasText.required(algorithm, "algorithm");
        if (signedAtEpochMillis < 0) {
            throw new IllegalArgumentException("signedAtEpochMillis must not be negative");
        }

        CasManifest.CanonicalEncoder encoder = new CasManifest.CanonicalEncoder(ENVELOPE_FORMAT);
        encoder.field("action_key_digest", key.digest().compact());
        encoder.field("action_tenant", key.tenantId());
        encoder.map("action_components", key.components());

        encoder.field("result_schema_version", result.schemaVersion());
        encoder.field("result_action_id", result.actionId());
        encoder.field("result_attempt", Integer.toString(result.attempt()));
        encoder.field("result_lease_generation", Integer.toString(result.leaseGeneration()));
        encoder.field("result_receipt_id", result.receiptId());
        encoder.field("result_status", result.status().name());
        encoder.field("result_started_at", result.startedAt());
        encoder.field("result_finished_at", result.finishedAt());
        encoder.field("result_exit_code", Integer.toString(result.exitCode()));
        encoder.field("result_output_manifest", result.outputManifestDigest().compact());
        optionalDigest(encoder, "result_stdout", result.stdoutDigest());
        optionalDigest(encoder, "result_stderr", result.stderrDigest());
        encoder.field("result_cpu_seconds_hex", doubleHex(result.resourceUsage().cpuSeconds()));
        encoder.field("result_max_memory_mb_hex", doubleHex(result.resourceUsage().maxMemoryMb()));
        encoder.field("result_read_bytes", Long.toString(result.resourceUsage().readBytes()));
        encoder.field("result_written_bytes", Long.toString(result.resourceUsage().writtenBytes()));
        encoder.field("result_gpu_seconds_hex", doubleHex(result.resourceUsage().gpuSeconds()));
        encoder.field("result_wall_seconds_hex", doubleHex(result.resourceUsage().wallSeconds()));
        Map<String, String> canonicalCost = new java.util.TreeMap<>(MerkleTree::compareUtf8);
        result.cost().forEach((name, value) -> canonicalCost.put(name, doubleHex(value)));
        encoder.map("result_cost_hex", canonicalCost);
        encoder.field("result_failure_class_present", Boolean.toString(result.failureClass().isPresent()));
        encoder.field("result_failure_class", result.failureClass().map(Enum::name).orElse(""));
        encoder.field("result_failure_message_present", Boolean.toString(result.failureMessage().isPresent()));
        encoder.field("result_failure_message", result.failureMessage().orElse(""));
        encoder.field("result_validation_status", result.validationStatus().name());
        encoder.field("result_provenance", result.provenanceDigest().compact());

        encoder.field("producer_tenant", producer.tenantId());
        encoder.field("producer_project", producer.projectId());
        encoder.field("producer_residency", producer.dataResidency());
        encoder.field("producer_classification", producer.classification().name());
        encoder.field("producer_sensitivity", producer.sensitivity().name());
        encoder.field("producer_toolchain", producer.toolchainImage());
        encoder.list("producer_scope", new java.util.ArrayList<>(new java.util.TreeSet<>(producer.permissionScope())));
        optionalDigest(encoder, "producer_provenance", producer.provenanceDigest());

        encoder.field("risk_tier", riskTier.name());
        encoder.field("writer_service_id", writer.serviceId());
        encoder.field("writer_trust_domain", writer.trustDomain());
        encoder.field("writer_node_id", writer.nodeId());
        encoder.field("writer_attested", Boolean.toString(writer.attested()));
        encoder.field("key_id", keyId);
        encoder.field("algorithm", algorithm);
        encoder.field("signed_at", Long.toString(signedAtEpochMillis));
        return new Envelope(new String(encoder.bytes(), java.nio.charset.StandardCharsets.UTF_8),
                keyId, algorithm, signedAtEpochMillis);
    }

    static boolean binds(ActionCache.ResultAttestation attestation, ActionKey key,
                         ActionResultRecord result, CasAccessPolicy.ProducerContext producer,
                         ActionCache.WriterIdentity writer, ActionCache.RiskTier riskTier) {
        if (!ENVELOPE_FORMAT.equals(attestation.envelopeVersion())) {
            return false;
        }
        Envelope expected = envelope(key, result, producer, writer, riskTier,
                attestation.signerId(), attestation.algorithm(),
                attestation.signedAtEpochMillis());
        return expected.digest().equals(attestation.envelopeDigest());
    }

    private static void optionalDigest(CasManifest.CanonicalEncoder encoder, String name,
                                       Optional<CasDigest> digest) {
        encoder.field(name + "_present", Boolean.toString(digest.isPresent()));
        encoder.field(name, digest.map(CasDigest::compact).orElse(""));
    }

    private static String doubleHex(double value) {
        return Double.toHexString(value);
    }

    /** Signing side. Lives next to verification so the two can never drift out of agreement. */
    public static DetachedSignature sign(Envelope envelope, PrivateKey privateKey, String keyId,
                                         String algorithm, long signedAtEpochMillis) {
        Objects.requireNonNull(envelope, "envelope");
        Objects.requireNonNull(privateKey, "privateKey");
        if (!envelope.keyId().equals(keyId)
                || !envelope.algorithm().equals(algorithm)
                || envelope.signedAtEpochMillis() != signedAtEpochMillis) {
            throw new IllegalArgumentException(
                    "detached signature metadata does not match the signed envelope");
        }
        try {
            Signature signature = Signature.getInstance(algorithm);
            signature.initSign(privateKey);
            signature.update(envelope.bytes());
            return new DetachedSignature(keyId, algorithm, signature.sign(), signedAtEpochMillis);
        } catch (java.security.GeneralSecurityException error) {
            throw new IllegalStateException("cannot sign result envelope with " + algorithm, error);
        }
    }

    public static final class KeyRegistry {

        private final Map<String, SigningKey> keys = new LinkedHashMap<>();
        private final Set<String> allowedAlgorithms;

        public KeyRegistry(Set<String> allowedAlgorithms) {
            CasText.requireNonEmpty(allowedAlgorithms, "allowedAlgorithms");
            this.allowedAlgorithms = Set.copyOf(allowedAlgorithms);
        }

        public static KeyRegistry ed25519Only() {
            return new KeyRegistry(Set.of(ED25519));
        }

        public KeyRegistry register(SigningKey key) {
            if (!allowedAlgorithms.contains(key.algorithm())) {
                throw new IllegalArgumentException("algorithm not allowed: " + key.algorithm());
            }
            if (keys.putIfAbsent(key.keyId(), key) != null) {
                // Rebinding a key id to different key material silently invalidates every
                // signature already made under it, so it is refused rather than merged.
                throw new IllegalArgumentException("key id already registered: " + key.keyId());
            }
            return this;
        }

        public Optional<SigningKey> find(String keyId) {
            return Optional.ofNullable(keys.get(keyId));
        }

        Set<String> allowedAlgorithms() {
            return allowedAlgorithms;
        }
    }

    /**
     * @param maximumSignatureAgeMillis how old a signature may be when it is presented. A cached
     *                                  result is long lived, but the act of writing it is not; an
     *                                  ancient signature on a fresh write is a replay.
     */
    public record VerificationPolicy(long maximumSignatureAgeMillis, long maximumClockSkewMillis) {
        public VerificationPolicy {
            CasText.requirePositive(maximumSignatureAgeMillis, "maximumSignatureAgeMillis");
            if (maximumClockSkewMillis < 0) {
                throw new IllegalArgumentException("maximumClockSkewMillis must not be negative");
            }
        }

        public static VerificationPolicy standard() {
            return new VerificationPolicy(15 * 60 * 1000L, 60 * 1000L);
        }
    }

    public static final class Verifier {

        private final KeyRegistry registry;
        private final VerificationPolicy policy;

        public Verifier(KeyRegistry registry, VerificationPolicy policy) {
            this.registry = registry;
            this.policy = policy;
        }

        public Verdict verify(Envelope envelope, DetachedSignature signature, long nowEpochMillis) {
            if (!envelope.keyId().equals(signature.keyId())
                    || !envelope.algorithm().equals(signature.algorithm())
                    || envelope.signedAtEpochMillis() != signature.signedAtEpochMillis()) {
                return Verdict.deny("SIGNATURE_METADATA_DOES_NOT_MATCH_ENVELOPE");
            }
            Optional<SigningKey> key = registry.find(signature.keyId());
            if (key.isEmpty()) {
                return Verdict.deny("SIGNING_KEY_UNKNOWN");
            }
            if (!registry.allowedAlgorithms().contains(signature.algorithm())
                    || !key.get().algorithm().equals(signature.algorithm())) {
                return Verdict.deny("SIGNATURE_ALGORITHM_NOT_ALLOWED");
            }
            if (!key.get().validAt(signature.signedAtEpochMillis())) {
                return Verdict.deny("SIGNING_KEY_NOT_VALID_AT_SIGNING_TIME");
            }
            if (signature.signedAtEpochMillis() > nowEpochMillis + policy.maximumClockSkewMillis()) {
                return Verdict.deny("SIGNATURE_FROM_THE_FUTURE");
            }
            if (nowEpochMillis - signature.signedAtEpochMillis() > policy.maximumSignatureAgeMillis()) {
                return Verdict.deny("SIGNATURE_TOO_OLD");
            }
            try {
                Signature verifier = Signature.getInstance(signature.algorithm());
                verifier.initVerify(key.get().publicKey());
                verifier.update(envelope.bytes());
                if (!verifier.verify(signature.value())) {
                    return Verdict.deny("SIGNATURE_DOES_NOT_VERIFY");
                }
            } catch (java.security.GeneralSecurityException error) {
                return Verdict.deny("SIGNATURE_VERIFICATION_FAILED:" + error.getClass().getSimpleName());
            }
            return new Verdict(true, "VERIFIED");
        }

        /**
         * The only supported way to obtain a {@code verified} attestation for
         * {@link ActionCache#put}. Everything else hands the cache an unverified one, which it
         * refuses for high-risk results.
         */
        public ActionCache.ResultAttestation attestation(ActionKey key, ActionResultRecord result,
                                                         CasAccessPolicy.ProducerContext producer,
                                                         ActionCache.WriterIdentity writer,
                                                         ActionCache.RiskTier riskTier,
                                                         DetachedSignature signature, long nowEpochMillis) {
            Envelope envelope = envelope(key, result, producer, writer, riskTier,
                    signature.keyId(), signature.algorithm(), signature.signedAtEpochMillis());
            Verdict verdict = verify(envelope, signature, nowEpochMillis);
            if (!verdict.verified()) {
                throw new CasExceptions.CasAccessDeniedException("RESULT_SIGNATURE_REJECTED", verdict.reason());
            }
            return ActionCache.ResultAttestation.verified(signature.keyId(), signature.algorithm(),
                    signature.digest(), envelope.version(), envelope.digest(),
                    signature.signedAtEpochMillis());
        }
    }
}
