package io.elmos.application;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Control-plane authority for Batch 15. It evaluates evidence and never connects to a database. */
public final class DatabaseDataCutoverGovernance {
    public enum Stage {
        DISCOVERY, DUAL_RUNNING, READ_CUTOVER, WRITE_CUTOVER,
        STABILITY_HOLD, SOURCE_READ_ONLY, ARCHIVING, DECOMMISSIONED
    }
    public enum Decision { ADVANCE, HOLD, HUMAN_REVIEW, BLOCKED }

    public record Evidence(
            String organizationId,
            Stage currentStage,
            Stage requestedStage,
            boolean schemaPassed,
            boolean procedurePassed,
            boolean queryResultPassed,
            boolean queryPerformancePassed,
            boolean snapshotCdcFrontierPassed,
            boolean reconciliationPassed,
            boolean dataQualityPassed,
            boolean biMetricPassed,
            boolean biSecurityPassed,
            boolean governancePassed,
            boolean writerInventoryComplete,
            boolean rollbackValidated,
            boolean sourceWriteControlled,
            List<String> evidenceRefs,
            String approvedBy) {
        public Evidence {
            require(organizationId, "organizationId");
            Objects.requireNonNull(currentStage, "currentStage");
            Objects.requireNonNull(requestedStage, "requestedStage");
            evidenceRefs = List.copyOf(Objects.requireNonNull(evidenceRefs, "evidenceRefs"));
        }
    }

    public record Result(Decision decision, boolean automatic, List<String> blockers,
                         List<String> evidenceRefs, Map<String, String> checks) {}

    public Result evaluate(Evidence evidence) {
        if (evidence.requestedStage().ordinal() != evidence.currentStage().ordinal() + 1) {
            return result(Decision.BLOCKED, false, List.of("DATABASE_MIGRATION_STAGE_SKIP"), evidence, Map.of());
        }
        if (evidence.evidenceRefs().isEmpty()) {
            return result(Decision.HOLD, false, List.of("DATABASE_DATA_EVIDENCE_MISSING"), evidence, Map.of());
        }
        var blockers = new java.util.ArrayList<String>();
        var checks = new LinkedHashMap<String, String>();
        gate(checks, blockers, "SCHEMA", evidence.schemaPassed());
        gate(checks, blockers, "PROCEDURE", evidence.procedurePassed());
        gate(checks, blockers, "QUERY_RESULT", evidence.queryResultPassed());
        gate(checks, blockers, "QUERY_PERFORMANCE", evidence.queryPerformancePassed());
        gate(checks, blockers, "SNAPSHOT_CDC_FRONTIER", evidence.snapshotCdcFrontierPassed());
        gate(checks, blockers, "DATA_RECONCILIATION", evidence.reconciliationPassed());
        gate(checks, blockers, "DATA_QUALITY", evidence.dataQualityPassed());
        gate(checks, blockers, "BI_METRIC", evidence.biMetricPassed());
        gate(checks, blockers, "BI_SECURITY", evidence.biSecurityPassed());
        gate(checks, blockers, "GOVERNANCE", evidence.governancePassed());
        gate(checks, blockers, "WRITER_INVENTORY", evidence.writerInventoryComplete());
        gate(checks, blockers, "ROLLBACK", evidence.rollbackValidated());
        gate(checks, blockers, "SOURCE_WRITE_CONTROL", evidence.sourceWriteControlled());
        if (!blockers.isEmpty()) return result(Decision.HOLD, false, blockers, evidence, checks);

        if (requiresNamedApproval(evidence.requestedStage())
                && (evidence.approvedBy() == null || evidence.approvedBy().isBlank())) {
            return result(Decision.HUMAN_REVIEW, false,
                    List.of("NAMED_DATABASE_AUTHORITY_APPROVAL_REQUIRED"), evidence, checks);
        }
        return result(Decision.ADVANCE, evidence.requestedStage().ordinal() < Stage.READ_CUTOVER.ordinal(),
                List.of(), evidence, checks);
    }

    private boolean requiresNamedApproval(Stage stage) {
        return stage == Stage.READ_CUTOVER || stage == Stage.WRITE_CUTOVER
                || stage == Stage.SOURCE_READ_ONLY || stage == Stage.ARCHIVING
                || stage == Stage.DECOMMISSIONED;
    }

    private void gate(Map<String, String> checks, List<String> blockers, String gate, boolean passed) {
        checks.put(gate, passed ? "PASS" : "FAIL");
        if (!passed) blockers.add(gate + "_FAILED");
    }

    private Result result(Decision decision, boolean automatic, List<String> blockers,
                          Evidence evidence, Map<String, String> checks) {
        return new Result(decision, automatic, List.copyOf(blockers), evidence.evidenceRefs(), Map.copyOf(checks));
    }

    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
