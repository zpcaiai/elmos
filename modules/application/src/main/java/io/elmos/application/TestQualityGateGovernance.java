package io.elmos.application;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** Independent, deterministic quality decision kernel. It cannot execute tests or change a gate. */
public final class TestQualityGateGovernance {
    public enum Decision { PASS, PASS_WITH_WARNINGS, CONDITIONAL_PASS, FAIL, NOT_RUN, INCONCLUSIVE, STALE }
    public enum Confidence { HIGH, MODERATE, LOW, INSUFFICIENT, UNKNOWN }

    public record Evidence(String sourceCommit, String evaluatedCommit, boolean discoveryComplete,
                           int baselineTestCount, int discoveredTestCount, int executedTestCount,
                           int reportedTestCount, int skippedTestCount, int criticalRiskUncovered,
                           int contractBreaking, int criticalJourneyFlaky, double mutationScoreRegression,
                           boolean environmentFidelitySufficient, boolean evidenceFresh,
                           List<String> evidenceRefs, Map<String, String> conditions) {
        public Evidence {
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
            conditions = conditions == null ? Map.of() : Map.copyOf(conditions);
        }
    }

    public record Result(Decision decision, Confidence confidence, List<String> blockers,
                         List<String> warnings, List<String> unknowns, boolean releaseAuthorized,
                         boolean gateModifiedByWorker, Instant evaluatedAt, List<String> evidenceRefs) {}

    public Result evaluate(Evidence evidence, Instant now) {
        if (evidence == null) throw new IllegalArgumentException("quality evidence is required");
        var blockers = new ArrayList<String>();
        var warnings = new ArrayList<String>();
        var unknowns = new ArrayList<String>();
        if (!evidence.evidenceFresh() || !same(evidence.sourceCommit(), evidence.evaluatedCommit())) blockers.add("QUALITY_EVIDENCE_STALE");
        if (!evidence.discoveryComplete()) blockers.add("TEST_DISCOVERY_INCOMPLETE");
        if (evidence.discoveredTestCount() < evidence.baselineTestCount()) blockers.add("TEST_COUNT_REGRESSION");
        if (evidence.executedTestCount() > evidence.discoveredTestCount() || evidence.reportedTestCount() != evidence.executedTestCount()) blockers.add("TEST_COUNT_RECONCILIATION_FAILED");
        if (evidence.executedTestCount() == 0) blockers.add("TESTS_NOT_RUN");
        if (evidence.skippedTestCount() > 0) warnings.add("SKIPPED_TESTS_VISIBLE");
        if (evidence.criticalRiskUncovered() > 0) blockers.add("QUALITY_RISK_UNCOVERED");
        if (evidence.contractBreaking() > 0) blockers.add("CONTRACT_VERIFICATION_FAILED");
        if (evidence.criticalJourneyFlaky() > 0) blockers.add("CRITICAL_JOURNEY_FLAKY");
        if (evidence.mutationScoreRegression() > .02d) blockers.add("MUTATION_SCORE_REGRESSION");
        if (!evidence.environmentFidelitySufficient()) unknowns.add("ENVIRONMENT_FIDELITY_INSUFFICIENT");
        if (evidence.evidenceRefs().isEmpty()) unknowns.add("QUALITY_EVIDENCE_MISSING");
        Decision decision;
        Confidence confidence;
        if (blockers.contains("QUALITY_EVIDENCE_STALE")) { decision = Decision.STALE; confidence = Confidence.INSUFFICIENT; }
        else if (!blockers.isEmpty()) { decision = Decision.FAIL; confidence = Confidence.INSUFFICIENT; }
        else if (!unknowns.isEmpty()) { decision = Decision.INCONCLUSIVE; confidence = Confidence.INSUFFICIENT; }
        else if (!evidence.conditions().isEmpty()) { decision = Decision.CONDITIONAL_PASS; confidence = Confidence.MODERATE; }
        else if (!warnings.isEmpty()) { decision = Decision.PASS_WITH_WARNINGS; confidence = Confidence.MODERATE; }
        else { decision = Decision.PASS; confidence = Confidence.HIGH; }
        return new Result(decision, confidence, List.copyOf(blockers), List.copyOf(warnings),
                List.copyOf(unknowns), decision == Decision.PASS || decision == Decision.PASS_WITH_WARNINGS,
                false, now, evidence.evidenceRefs());
    }

    private static boolean same(String left, String right) {
        return left != null && !left.isBlank() && left.equals(right);
    }
}
