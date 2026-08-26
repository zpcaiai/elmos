package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CheckpointForkPolicyTest {
    private static final String A = "a".repeat(64);
    private static final String B = "b".repeat(64);
    private static final String C = "c".repeat(64);
    private static final String D = "d".repeat(64);

    @Test
    void compatibleCheckpointResumesWithoutCreatingANewRun() {
        var request = request(fingerprint(A, "commit-a", B, C, "1"),
                fingerprint(A, "commit-a", B, C, "1"), "fork-2");

        var decision = CheckpointForkPolicy.evaluate(request, null);

        assertEquals(CheckpointForkPolicy.DecisionType.RESUME_EXISTING_RUN,
                decision.decisionType());
        assertEquals(List.of(CheckpointForkPolicy.ReasonCode.COMPATIBLE),
                decision.reasonCodes());
        assertTrue(decision.mayResumeExistingRun());
        assertFalse(decision.mayCreateFork());
        assertEquals(64, decision.canonicalPayloadDigest().length());
    }

    @Test
    void incompatibleCheckpointProducesTypedReasonsInStableOrder() {
        var checkpoint = fingerprint(A, "commit-a", B, C, "1");
        var required = fingerprint(D, "commit-b", A, null, "2");

        var decision = CheckpointForkPolicy.evaluate(
                request(checkpoint, required, "fork-2"), null);

        assertEquals(CheckpointForkPolicy.DecisionType.CREATE_FORK_RUN,
                decision.decisionType());
        assertEquals(List.of(
                CheckpointForkPolicy.ReasonCode.INPUT_MANIFEST_MISMATCH,
                CheckpointForkPolicy.ReasonCode.REPOSITORY_REVISION_MISMATCH,
                CheckpointForkPolicy.ReasonCode.TOOLCHAIN_MISMATCH,
                CheckpointForkPolicy.ReasonCode.MODEL_MISMATCH,
                CheckpointForkPolicy.ReasonCode.SCHEMA_VERSION_MISMATCH),
                decision.reasonCodes());
        assertEquals("fork-2", decision.forkRunId());
        assertTrue(decision.mayCreateFork());
    }

    @Test
    void exactReplayReturnsTheStoredForkWithoutAnotherMutation() {
        var request = request(
                fingerprint(A, "commit-a", B, C, "1"),
                fingerprint(D, "commit-a", B, C, "1"),
                "fork-2");
        var stored = new CheckpointForkPolicy.StoredForkRequest(
                request.idempotencyKey(), request.canonicalPayloadDigest(),
                "fork-2", CheckpointForkPolicy.StoredOutcome.COMMITTED);

        var decision = CheckpointForkPolicy.evaluate(request, stored);

        assertEquals(CheckpointForkPolicy.DecisionType.RETURN_EXISTING_FORK,
                decision.decisionType());
        assertEquals(List.of(
                CheckpointForkPolicy.ReasonCode.INPUT_MANIFEST_MISMATCH,
                CheckpointForkPolicy.ReasonCode.IDEMPOTENT_REPLAY),
                decision.reasonCodes());
        assertEquals("fork-2", decision.forkRunId());
        assertFalse(decision.mayCreateFork());
    }

    @Test
    void reusingAKeyForDifferentPayloadFailsClosed() {
        var original = request(
                fingerprint(A, "commit-a", B, C, "1"),
                fingerprint(D, "commit-a", B, C, "1"),
                "fork-2");
        var changed = request(
                original.checkpointFingerprint(), original.requiredFingerprint(),
                "fork-3");
        var stored = new CheckpointForkPolicy.StoredForkRequest(
                original.idempotencyKey(), original.canonicalPayloadDigest(),
                "fork-2", CheckpointForkPolicy.StoredOutcome.COMMITTED);

        var decision = CheckpointForkPolicy.evaluate(changed, stored);

        assertEquals(CheckpointForkPolicy.DecisionType.REJECT_IDEMPOTENCY_CONFLICT,
                decision.decisionType());
        assertEquals(List.of(
                CheckpointForkPolicy.ReasonCode.IDEMPOTENCY_PAYLOAD_CONFLICT),
                decision.reasonCodes());
        assertFalse(decision.mayCreateFork());
    }

    @Test
    void unknownStoredOutcomeRequiresManualReconciliation() {
        var request = request(
                fingerprint(A, "commit-a", B, C, "1"),
                fingerprint(D, "commit-a", B, C, "1"),
                "fork-2");
        var stored = new CheckpointForkPolicy.StoredForkRequest(
                request.idempotencyKey(), request.canonicalPayloadDigest(),
                "fork-2", CheckpointForkPolicy.StoredOutcome.UNKNOWN);

        var decision = CheckpointForkPolicy.evaluate(request, stored);

        assertEquals(CheckpointForkPolicy.DecisionType.REQUIRE_MANUAL_RECONCILIATION,
                decision.decisionType());
        assertTrue(decision.reasonCodes().contains(
                CheckpointForkPolicy.ReasonCode.STORED_OUTCOME_UNKNOWN));
        assertFalse(decision.mayCreateFork());
    }

    @Test
    void malformedFingerprintsAndSameRunForksAreRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                fingerprint("not-a-digest", "commit-a", B, C, "1"));
        var fingerprint = fingerprint(A, "commit-a", B, C, "1");
        assertThrows(IllegalArgumentException.class, () ->
                new CheckpointForkPolicy.ForkRequest(
                        "task-a", "run-1", "run-1", "idem-a",
                        fingerprint, fingerprint));
    }

    private static CheckpointForkPolicy.ForkRequest request(
            CheckpointForkPolicy.CompatibilityFingerprint checkpoint,
            CheckpointForkPolicy.CompatibilityFingerprint required,
            String proposedForkRunId
    ) {
        return new CheckpointForkPolicy.ForkRequest(
                "task-a", "run-1", proposedForkRunId, "idem-fork-a",
                checkpoint, required);
    }

    private static CheckpointForkPolicy.CompatibilityFingerprint fingerprint(
            String input,
            String revision,
            String toolchain,
            String model,
            String schemaVersion
    ) {
        return new CheckpointForkPolicy.CompatibilityFingerprint(
                input, revision, toolchain, model, schemaVersion);
    }
}
