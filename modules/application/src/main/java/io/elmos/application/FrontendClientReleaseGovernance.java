package io.elmos.application;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/** Control-plane authority for Batch 14 release progression; it never runs client code. */
public final class FrontendClientReleaseGovernance {
    public enum Stage { NONE, INTERNAL, CANARY, PROGRESSIVE, FULL, DECOMMISSION }
    public enum Decision { PROMOTE, HOLD, HUMAN_REVIEW, BLOCKED }

    public record EvidenceExtension(
            String organizationId, String schema, String artifactRef, String contentHash,
            List<String> evidenceRefs, Instant createdAt) {
        public EvidenceExtension {
            require(organizationId, "organizationId"); require(schema, "schema");
            require(artifactRef, "artifactRef"); require(contentHash, "contentHash");
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs, "evidenceRefs"));
            if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("frontend evidence references are required");
            Objects.requireNonNull(createdAt, "createdAt");
        }
    }

    public record ReleaseEvidence(
            String organizationId, Stage currentStage, Stage requestedStage,
            boolean webPassed, boolean desktopPassed, boolean androidPassed, boolean iosPassed,
            boolean bffPassed, boolean backendPassed, boolean visualPassed,
            boolean accessibilityPassed, boolean performancePassed, boolean securityPassed,
            List<String> evidenceRefs, String approvedBy) {
        public ReleaseEvidence {
            require(organizationId, "organizationId");
            Objects.requireNonNull(currentStage, "currentStage");
            Objects.requireNonNull(requestedStage, "requestedStage");
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs, "evidenceRefs"));
        }
    }

    public record ReleaseDecision(Decision decision, boolean automatic, List<String> blockers,
                                  List<String> evidenceRefs) {}

    public ReleaseDecision evaluate(ReleaseEvidence evidence) {
        Objects.requireNonNull(evidence, "evidence");
        if (evidence.requestedStage().ordinal() != evidence.currentStage().ordinal() + 1) {
            return decision(Decision.BLOCKED, false, List.of("CLIENT_RELEASE_STAGE_SKIP"), evidence);
        }
        if (evidence.evidenceRefs().isEmpty()) {
            return decision(Decision.HOLD, false, List.of("CLIENT_RELEASE_EVIDENCE_MISSING"), evidence);
        }
        var blockers = new java.util.ArrayList<String>();
        if (!evidence.webPassed()) blockers.add("WEB_GATE_FAILED");
        if (!evidence.desktopPassed()) blockers.add("DESKTOP_GATE_FAILED");
        if (!evidence.androidPassed()) blockers.add("ANDROID_GATE_FAILED");
        if (!evidence.iosPassed()) blockers.add("IOS_GATE_FAILED");
        if (!evidence.bffPassed()) blockers.add("BFF_GATE_FAILED");
        if (!evidence.backendPassed()) blockers.add("BACKEND_GATE_FAILED");
        if (!evidence.visualPassed()) blockers.add("VISUAL_GATE_FAILED");
        if (!evidence.accessibilityPassed()) blockers.add("ACCESSIBILITY_GATE_FAILED");
        if (!evidence.performancePassed()) blockers.add("PERFORMANCE_GATE_FAILED");
        if (!evidence.securityPassed()) blockers.add("SECURITY_GATE_FAILED");
        if (!blockers.isEmpty()) return decision(Decision.HOLD, false, blockers, evidence);
        if ((evidence.requestedStage() == Stage.FULL || evidence.requestedStage() == Stage.DECOMMISSION)
                && (evidence.approvedBy() == null || evidence.approvedBy().isBlank())) {
            return decision(Decision.HUMAN_REVIEW, false, List.of("NAMED_HUMAN_APPROVAL_REQUIRED"), evidence);
        }
        return decision(Decision.PROMOTE, evidence.requestedStage().ordinal() < Stage.FULL.ordinal(),
                List.of(), evidence);
    }

    private ReleaseDecision decision(Decision decision, boolean automatic, List<String> blockers,
                                     ReleaseEvidence evidence) {
        return new ReleaseDecision(decision, automatic, List.copyOf(blockers), evidence.evidenceRefs());
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
