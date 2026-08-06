package io.elmos.proofloop;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Conservative boundary between repository engineering evidence and external
 * production authority for Batches 105-108.
 *
 * <p>This gate never calls a cloud, SCM, deployment, customer or certification
 * provider. Those effects belong to separately authorized adapters. It only
 * verifies byte-bound receipts from independent producers and therefore cannot
 * turn caller booleans, local tests or an OCI build into external success.</p>
 */
public final class ExternalClosureGate {
    private static final Pattern IMMUTABLE_IMAGE = Pattern.compile(
            "^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$");
    private static final Duration MAXIMUM_EVIDENCE_AGE = Duration.ofDays(30);

    public enum ExternalOperation {
        REAL_CLOUD_PROVIDER,
        SCM_DRAFT_PULL_REQUEST,
        CUSTOMER_ACCEPTANCE,
        INDEPENDENT_REVIEW,
        PRODUCTION_DEPLOYMENT,
        EXTERNAL_CERTIFICATION
    }

    public enum Decision { BLOCKED, NOT_RUN, READY_FOR_EXTERNAL_GATE }

    public record ExternalReceipt(
            ProofLoopModels.EvidenceState state,
            String subjectDigest,
            String producerId,
            String verifierId,
            Instant observedAt,
            boolean signatureVerified,
            boolean bytesRecomputed,
            List<String> artifactRefs,
            String providerReceiptId
    ) {
        public ExternalReceipt {
            ProofLoopModels.required(state, "state");
            ProofLoopModels.digest(subjectDigest, "subjectDigest");
            ProofLoopModels.identifier(producerId, "producerId");
            ProofLoopModels.identifier(verifierId, "verifierId");
            ProofLoopModels.required(observedAt, "observedAt");
            artifactRefs = ProofLoopModels.copy(artifactRefs);
            ProofLoopModels.identifier(providerReceiptId, "providerReceiptId");
        }

        boolean independentlyVerified(String expectedSubject, Instant now) {
            return state == ProofLoopModels.EvidenceState.VERIFIED
                    && subjectDigest.equals(expectedSubject)
                    && !producerId.equals(verifierId)
                    && signatureVerified
                    && bytesRecomputed
                    && !artifactRefs.isEmpty()
                    && !observedAt.isAfter(now)
                    && !observedAt.isBefore(now.minus(MAXIMUM_EVIDENCE_AGE));
        }
    }

    public record Request(
            String runnerImage,
            String subjectDigest,
            Instant evaluatedAt,
            Map<ExternalOperation, ExternalReceipt> receipts
    ) {
        public Request {
            ProofLoopModels.required(runnerImage, "runnerImage");
            ProofLoopModels.digest(subjectDigest, "subjectDigest");
            ProofLoopModels.required(evaluatedAt, "evaluatedAt");
            receipts = receipts == null ? Map.of() : Map.copyOf(receipts);
        }
    }

    public record Result(
            Decision decision,
            Map<ExternalOperation, ProofLoopModels.EvidenceState> operationStates,
            List<String> blockers,
            boolean deploymentAuthorized,
            boolean productionApproved,
            boolean certified
    ) {
        public Result {
            ProofLoopModels.required(decision, "decision");
            operationStates = Map.copyOf(operationStates);
            blockers = List.copyOf(blockers);
            if (deploymentAuthorized || productionApproved || certified) {
                throw new IllegalArgumentException("repository external gate cannot grant external authority");
            }
        }
    }

    public Result evaluate(Request request) {
        EnumMap<ExternalOperation, ProofLoopModels.EvidenceState> states =
                new EnumMap<>(ExternalOperation.class);
        List<String> blockers = new ArrayList<>();

        if (!IMMUTABLE_IMAGE.matcher(request.runnerImage()).matches()) {
            blockers.add("runner_image_not_digest_pinned");
        }

        int notRun = 0;
        for (ExternalOperation operation : ExternalOperation.values()) {
            ExternalReceipt receipt = request.receipts().get(operation);
            if (receipt == null || receipt.state() == ProofLoopModels.EvidenceState.NOT_RUN) {
                states.put(operation, ProofLoopModels.EvidenceState.NOT_RUN);
                notRun++;
                continue;
            }
            if (receipt.independentlyVerified(request.subjectDigest(), request.evaluatedAt())) {
                states.put(operation, ProofLoopModels.EvidenceState.VERIFIED);
            } else {
                states.put(operation, ProofLoopModels.EvidenceState.BLOCKED);
                blockers.add("external_receipt_not_independently_verified:" + operation.name());
            }
        }

        Decision decision;
        if (!blockers.isEmpty()) {
            decision = Decision.BLOCKED;
        } else if (notRun > 0) {
            decision = Decision.NOT_RUN;
        } else {
            decision = Decision.READY_FOR_EXTERNAL_GATE;
        }
        return new Result(decision, states, blockers, false, false, false);
    }
}
