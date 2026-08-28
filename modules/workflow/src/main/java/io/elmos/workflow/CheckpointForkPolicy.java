package io.elmos.workflow;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;

/**
 * Pure decision boundary for resuming a compatible checkpoint or forking an
 * incompatible run.
 *
 * <p>The policy neither starts a workflow nor writes a checkpoint. It produces
 * a deterministic, digest-bound decision that a durable adapter may apply. A
 * previously stored request with an unknown outcome always requires manual
 * reconciliation; it is never retried as a new fork.</p>
 */
public final class CheckpointForkPolicy {
    private static final String DIGEST_FORMAT = "ELMOS_MTF_CHECKPOINT_FORK_REQUEST_V1";

    public enum DecisionType {
        RESUME_EXISTING_RUN,
        CREATE_FORK_RUN,
        RETURN_EXISTING_FORK,
        REQUIRE_MANUAL_RECONCILIATION,
        REJECT_IDEMPOTENCY_CONFLICT
    }

    public enum ReasonCode {
        COMPATIBLE,
        INPUT_MANIFEST_MISMATCH,
        REPOSITORY_REVISION_MISMATCH,
        TOOLCHAIN_MISMATCH,
        MODEL_MISMATCH,
        SCHEMA_VERSION_MISMATCH,
        IDEMPOTENT_REPLAY,
        IDEMPOTENCY_PAYLOAD_CONFLICT,
        IDEMPOTENCY_SCOPE_MISMATCH,
        STORED_OUTCOME_UNKNOWN
    }

    public enum StoredOutcome {
        COMMITTED,
        UNKNOWN
    }

    /** Exact inputs that determine whether checkpoint state may be reused. */
    public record CompatibilityFingerprint(
            String inputManifestDigest,
            String repositoryRevision,
            String toolchainDigest,
            String modelDigest,
            String schemaVersion
    ) {
        public CompatibilityFingerprint {
            inputManifestDigest = requireDigest(inputManifestDigest, "INPUT_MANIFEST");
            repositoryRevision = requireIdentifier(repositoryRevision, "REPOSITORY_REVISION");
            toolchainDigest = requireDigest(toolchainDigest, "TOOLCHAIN");
            if (modelDigest != null) {
                modelDigest = requireDigest(modelDigest, "MODEL");
            }
            schemaVersion = requireIdentifier(schemaVersion, "SCHEMA_VERSION");
        }
    }

    /**
     * A proposed fork. The idempotency key is storage identity; the canonical
     * payload digest is independently derived from every semantic field.
     */
    public record ForkRequest(
            String taskId,
            String sourceRunId,
            String proposedForkRunId,
            String idempotencyKey,
            CompatibilityFingerprint checkpointFingerprint,
            CompatibilityFingerprint requiredFingerprint
    ) {
        public ForkRequest {
            taskId = requireIdentifier(taskId, "TASK");
            sourceRunId = requireIdentifier(sourceRunId, "SOURCE_RUN");
            proposedForkRunId = requireIdentifier(proposedForkRunId, "PROPOSED_FORK_RUN");
            idempotencyKey = requireIdentifier(idempotencyKey, "IDEMPOTENCY_KEY");
            Objects.requireNonNull(checkpointFingerprint, "checkpointFingerprint");
            Objects.requireNonNull(requiredFingerprint, "requiredFingerprint");
            if (sourceRunId.equals(proposedForkRunId)) {
                throw new IllegalArgumentException("ELMOS_MTF_FORK_RUN_MUST_BE_NEW");
            }
        }

        public String canonicalPayloadDigest() {
            MessageDigest digest = sha256();
            update(digest, DIGEST_FORMAT);
            update(digest, taskId);
            update(digest, sourceRunId);
            update(digest, proposedForkRunId);
            update(digest, checkpointFingerprint.inputManifestDigest());
            update(digest, checkpointFingerprint.repositoryRevision());
            update(digest, checkpointFingerprint.toolchainDigest());
            update(digest, checkpointFingerprint.modelDigest());
            update(digest, checkpointFingerprint.schemaVersion());
            update(digest, requiredFingerprint.inputManifestDigest());
            update(digest, requiredFingerprint.repositoryRevision());
            update(digest, requiredFingerprint.toolchainDigest());
            update(digest, requiredFingerprint.modelDigest());
            update(digest, requiredFingerprint.schemaVersion());
            return HexFormat.of().formatHex(digest.digest());
        }
    }

    /** Durable result previously stored under an idempotency key. */
    public record StoredForkRequest(
            String idempotencyKey,
            String canonicalPayloadDigest,
            String forkRunId,
            StoredOutcome outcome
    ) {
        public StoredForkRequest {
            idempotencyKey = requireIdentifier(idempotencyKey, "IDEMPOTENCY_KEY");
            canonicalPayloadDigest = requireDigest(
                    canonicalPayloadDigest, "FORK_REQUEST_PAYLOAD");
            forkRunId = requireIdentifier(forkRunId, "FORK_RUN");
            Objects.requireNonNull(outcome, "outcome");
        }
    }

    public record ForkDecision(
            DecisionType decisionType,
            List<ReasonCode> reasonCodes,
            String canonicalPayloadDigest,
            String forkRunId
    ) {
        public ForkDecision {
            Objects.requireNonNull(decisionType, "decisionType");
            reasonCodes = List.copyOf(Objects.requireNonNull(reasonCodes, "reasonCodes"));
            if (reasonCodes.isEmpty()) {
                throw new IllegalArgumentException("ELMOS_MTF_FORK_REASON_REQUIRED");
            }
            canonicalPayloadDigest = requireDigest(
                    canonicalPayloadDigest, "FORK_REQUEST_PAYLOAD");
            boolean requiresRunId = decisionType == DecisionType.CREATE_FORK_RUN
                    || decisionType == DecisionType.RETURN_EXISTING_FORK
                    || decisionType == DecisionType.REQUIRE_MANUAL_RECONCILIATION;
            if (requiresRunId) {
                forkRunId = requireIdentifier(forkRunId, "FORK_RUN");
            } else if (forkRunId != null) {
                throw new IllegalArgumentException("ELMOS_MTF_UNEXPECTED_FORK_RUN");
            }
        }

        public boolean mayCreateFork() {
            return decisionType == DecisionType.CREATE_FORK_RUN;
        }

        public boolean mayResumeExistingRun() {
            return decisionType == DecisionType.RESUME_EXISTING_RUN;
        }
    }

    private CheckpointForkPolicy() {}

    /**
     * Evaluates a request against an optional durable idempotency record.
     * Passing {@code null} means no record exists for this idempotency key.
     */
    public static ForkDecision evaluate(
            ForkRequest request,
            StoredForkRequest storedRequest
    ) {
        Objects.requireNonNull(request, "request");
        String payloadDigest = request.canonicalPayloadDigest();

        if (storedRequest != null) {
            if (!request.idempotencyKey().equals(storedRequest.idempotencyKey())) {
                return new ForkDecision(
                        DecisionType.REJECT_IDEMPOTENCY_CONFLICT,
                        List.of(ReasonCode.IDEMPOTENCY_SCOPE_MISMATCH),
                        payloadDigest,
                        null);
            }
            if (!payloadDigest.equals(storedRequest.canonicalPayloadDigest())) {
                return new ForkDecision(
                        DecisionType.REJECT_IDEMPOTENCY_CONFLICT,
                        List.of(ReasonCode.IDEMPOTENCY_PAYLOAD_CONFLICT),
                        payloadDigest,
                        null);
            }

            List<ReasonCode> replayReasons = incompatibilities(
                    request.checkpointFingerprint(), request.requiredFingerprint());
            if (storedRequest.outcome() == StoredOutcome.UNKNOWN) {
                replayReasons.add(ReasonCode.STORED_OUTCOME_UNKNOWN);
                return new ForkDecision(
                        DecisionType.REQUIRE_MANUAL_RECONCILIATION,
                        replayReasons,
                        payloadDigest,
                        storedRequest.forkRunId());
            }
            replayReasons.add(ReasonCode.IDEMPOTENT_REPLAY);
            return new ForkDecision(
                    DecisionType.RETURN_EXISTING_FORK,
                    replayReasons,
                    payloadDigest,
                    storedRequest.forkRunId());
        }

        List<ReasonCode> reasons = incompatibilities(
                request.checkpointFingerprint(), request.requiredFingerprint());
        if (reasons.isEmpty()) {
            return new ForkDecision(
                    DecisionType.RESUME_EXISTING_RUN,
                    List.of(ReasonCode.COMPATIBLE),
                    payloadDigest,
                    null);
        }
        return new ForkDecision(
                DecisionType.CREATE_FORK_RUN,
                reasons,
                payloadDigest,
                request.proposedForkRunId());
    }

    private static List<ReasonCode> incompatibilities(
            CompatibilityFingerprint checkpoint,
            CompatibilityFingerprint required
    ) {
        List<ReasonCode> reasons = new ArrayList<>();
        if (!checkpoint.inputManifestDigest().equals(required.inputManifestDigest())) {
            reasons.add(ReasonCode.INPUT_MANIFEST_MISMATCH);
        }
        if (!checkpoint.repositoryRevision().equals(required.repositoryRevision())) {
            reasons.add(ReasonCode.REPOSITORY_REVISION_MISMATCH);
        }
        if (!checkpoint.toolchainDigest().equals(required.toolchainDigest())) {
            reasons.add(ReasonCode.TOOLCHAIN_MISMATCH);
        }
        if (!Objects.equals(checkpoint.modelDigest(), required.modelDigest())) {
            reasons.add(ReasonCode.MODEL_MISMATCH);
        }
        if (!checkpoint.schemaVersion().equals(required.schemaVersion())) {
            reasons.add(ReasonCode.SCHEMA_VERSION_MISMATCH);
        }
        return reasons;
    }

    private static MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("ELMOS_MTF_SHA256_UNAVAILABLE", exception);
        }
    }

    private static void update(MessageDigest digest, String value) {
        if (value == null) {
            digest.update(ByteBuffer.allocate(Integer.BYTES).putInt(-1).array());
            return;
        }
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(Integer.BYTES).putInt(bytes.length).array());
        digest.update(bytes);
    }

    private static String requireDigest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return value;
    }

    private static String requireIdentifier(String value, String field) {
        if (value == null || value.isBlank() || value.length() > 160
                || !value.matches("[A-Za-z0-9][A-Za-z0-9._:@/-]*")) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }
}
