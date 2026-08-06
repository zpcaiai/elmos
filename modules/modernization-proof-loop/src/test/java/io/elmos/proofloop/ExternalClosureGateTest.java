package io.elmos.proofloop;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ExternalClosureGateTest {
    private static final Instant NOW = Instant.parse("2026-08-06T00:00:00Z");
    private static final String SUBJECT = "sha256:" + "a".repeat(64);
    private static final String IMAGE =
            "registry.example.test/elmos/modernization-proof-worker@sha256:" + "b".repeat(64);
    private final ExternalClosureGate gate = new ExternalClosureGate();

    @Test
    void digestPinnedWorkerDoesNotTurnMissingExternalWorkIntoSuccess() {
        var result = gate.evaluate(new ExternalClosureGate.Request(IMAGE, SUBJECT, NOW, Map.of()));
        assertEquals(ExternalClosureGate.Decision.NOT_RUN, result.decision());
        assertEquals(6, result.operationStates().size());
        assertTrue(result.operationStates().values().stream()
                .allMatch(state -> state == ProofLoopModels.EvidenceState.NOT_RUN));
        assertFalse(result.deploymentAuthorized());
        assertFalse(result.productionApproved());
        assertFalse(result.certified());
    }

    @Test
    void mutableWorkerImageBlocksEvenBeforeExternalExecution() {
        var result = gate.evaluate(new ExternalClosureGate.Request(
                "registry.example.test/elmos/modernization-proof-worker:latest",
                SUBJECT, NOW, Map.of()));
        assertEquals(ExternalClosureGate.Decision.BLOCKED, result.decision());
        assertTrue(result.blockers().contains("runner_image_not_digest_pinned"));
        assertTrue(result.operationStates().values().stream()
                .allMatch(state -> state == ProofLoopModels.EvidenceState.NOT_RUN));
    }

    @Test
    void selfVerificationCannotAdvanceAnExternalBoundary() {
        var receipts = Map.of(
                ExternalClosureGate.ExternalOperation.REAL_CLOUD_PROVIDER,
                receipt("executor", "executor", SUBJECT));
        var result = gate.evaluate(new ExternalClosureGate.Request(IMAGE, SUBJECT, NOW, receipts));
        assertEquals(ExternalClosureGate.Decision.BLOCKED, result.decision());
        assertEquals(ProofLoopModels.EvidenceState.BLOCKED,
                result.operationStates().get(ExternalClosureGate.ExternalOperation.REAL_CLOUD_PROVIDER));
        assertFalse(result.certified());
    }

    @Test
    void wrongSubjectCannotBeReusedAcrossAProductionCandidate() {
        var receipts = Map.of(
                ExternalClosureGate.ExternalOperation.SCM_DRAFT_PULL_REQUEST,
                receipt("scm-provider", "independent-verifier", "sha256:" + "c".repeat(64)));
        var result = gate.evaluate(new ExternalClosureGate.Request(IMAGE, SUBJECT, NOW, receipts));
        assertEquals(ExternalClosureGate.Decision.BLOCKED, result.decision());
        assertFalse(result.productionApproved());
    }

    @Test
    void evenCompleteReceiptsOnlyPrepareASeparateExternalGate() {
        EnumMap<ExternalClosureGate.ExternalOperation, ExternalClosureGate.ExternalReceipt> receipts =
                new EnumMap<>(ExternalClosureGate.ExternalOperation.class);
        for (ExternalClosureGate.ExternalOperation operation : ExternalClosureGate.ExternalOperation.values()) {
            receipts.put(operation, receipt("provider-" + operation.ordinal(),
                    "verifier-" + operation.ordinal(), SUBJECT));
        }
        var result = gate.evaluate(new ExternalClosureGate.Request(IMAGE, SUBJECT, NOW, receipts));
        assertEquals(ExternalClosureGate.Decision.READY_FOR_EXTERNAL_GATE, result.decision());
        assertTrue(result.operationStates().values().stream()
                .allMatch(state -> state == ProofLoopModels.EvidenceState.VERIFIED));
        assertFalse(result.deploymentAuthorized());
        assertFalse(result.productionApproved());
        assertFalse(result.certified());
    }

    private ExternalClosureGate.ExternalReceipt receipt(
            String producer, String verifier, String subject) {
        return new ExternalClosureGate.ExternalReceipt(
                ProofLoopModels.EvidenceState.VERIFIED,
                subject,
                producer,
                verifier,
                NOW.minusSeconds(60),
                true,
                true,
                List.of("evidence/receipt.json"),
                "receipt-" + producer);
    }
}
