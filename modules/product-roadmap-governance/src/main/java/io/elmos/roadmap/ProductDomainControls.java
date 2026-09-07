package io.elmos.roadmap;

import java.math.BigDecimal;
import java.util.*;

/** Domain-specific, read-only controls for Product Batches 27-30. */
public final class ProductDomainControls {
    public enum ControlDecision { BLOCKED, READY_FOR_HUMAN_REVIEW }

    public record ControlResult(int batch, ControlDecision decision, List<String> reasonCodes,
                                boolean humanApprovalGranted, boolean externalOperationExecuted) {
        public ControlResult {
            if (batch < 27 || batch > 30) throw new IllegalArgumentException("domain control batch must be 27-30");
            Objects.requireNonNull(decision, "decision"); reasonCodes = List.copyOf(reasonCodes);
            if (humanApprovalGranted || externalOperationExecuted)
                throw new IllegalArgumentException("domain controls cannot approve or execute external actions");
            if (decision == ControlDecision.READY_FOR_HUMAN_REVIEW && !reasonCodes.isEmpty())
                throw new IllegalArgumentException("human review readiness cannot contain blockers");
        }
    }

    public record TbmEvidence(BigDecimal sourceCostTotal, BigDecimal normalizedCostTotal,
                              BigDecimal allocatedCostTotal, double allocationDriverCoverage,
                              double unallocatedCostRatio, int duplicateCostRecords,
                              boolean currencyAndPeriodVersioned, boolean benefitBaselinePredatesChange,
                              boolean benefitDoubleCountFree, boolean capitalizationPolicyBound,
                              boolean chargebackPolicyBound, List<String> evidenceRefs) {
        public TbmEvidence {
            nonnegative(sourceCostTotal, "sourceCostTotal"); nonnegative(normalizedCostTotal, "normalizedCostTotal");
            nonnegative(allocatedCostTotal, "allocatedCostTotal"); rate(allocationDriverCoverage, "allocationDriverCoverage");
            rate(unallocatedCostRatio, "unallocatedCostRatio");
            if (duplicateCostRecords < 0) throw new IllegalArgumentException("duplicateCostRecords must be non-negative");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record WorkforceEvidence(double consentCoverage, double skillEvidenceCoverage,
                                    int capacityOverAllocations, boolean personalRankingProduced,
                                    boolean opaqueAttritionPredictionUsed, boolean automatedEmploymentDecision,
                                    boolean invasiveIndividualTelemetryCollected, boolean appealAvailable,
                                    boolean humanAccountabilityAssigned, List<String> evidenceRefs) {
        public WorkforceEvidence {
            rate(consentCoverage, "consentCoverage"); rate(skillEvidenceCoverage, "skillEvidenceCoverage");
            if (capacityOverAllocations < 0) throw new IllegalArgumentException("capacityOverAllocations must be non-negative");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record TransformationEvidence(double strategyAlignmentCoverage, double dependencyCoverage,
                                         double stakeholderImpactCoverage, double readinessCoverage,
                                         boolean changeSaturationWithinCapacity, boolean adoptionUsesBehaviorEvidence,
                                         boolean benefitBaselinePredatesChange, boolean benefitDoubleCountFree,
                                         boolean cutoverRollbackPrepared, boolean successAutoDeclared,
                                         List<String> evidenceRefs) {
        public TransformationEvidence {
            rate(strategyAlignmentCoverage, "strategyAlignmentCoverage"); rate(dependencyCoverage, "dependencyCoverage");
            rate(stakeholderImpactCoverage, "stakeholderImpactCoverage"); rate(readinessCoverage, "readinessCoverage");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ControlTowerEvidence(double identityResolutionCoverage, double provenanceCoverage,
                                       boolean temporalConflictsResolved, boolean planBounded,
                                       boolean policyDecisionAllows, boolean idempotencyPassed,
                                       boolean compensationAndRecoveryPassed, boolean killSwitchVerified,
                                       boolean separationOfDutiesPassed, boolean crossTenantLeakDetected,
                                       boolean autonomousProductionExecutionRequested,
                                       List<String> evidenceRefs) {
        public ControlTowerEvidence {
            rate(identityResolutionCoverage, "identityResolutionCoverage"); rate(provenanceCoverage, "provenanceCoverage");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public ControlResult evaluateTbm(TbmEvidence value) {
        Objects.requireNonNull(value, "value"); List<String> reasons = new ArrayList<>();
        if (value.sourceCostTotal().compareTo(value.normalizedCostTotal()) != 0) reasons.add("FINANCIAL_SOURCE_RECONCILIATION_FAILED");
        if (value.normalizedCostTotal().compareTo(value.allocatedCostTotal()) != 0) reasons.add("ALLOCATION_TOTAL_RECONCILIATION_FAILED");
        if (value.allocationDriverCoverage() < 1) reasons.add("ALLOCATION_DRIVER_COVERAGE_INCOMPLETE");
        if (value.unallocatedCostRatio() > 0) reasons.add("UNALLOCATED_COST_REMAINS");
        if (value.duplicateCostRecords() > 0) reasons.add("DUPLICATE_COST_RECORDS");
        if (!value.currencyAndPeriodVersioned()) reasons.add("CURRENCY_OR_PERIOD_NOT_VERSIONED");
        if (!value.benefitBaselinePredatesChange()) reasons.add("BENEFIT_BASELINE_CREATED_TOO_LATE");
        if (!value.benefitDoubleCountFree()) reasons.add("BENEFIT_DOUBLE_COUNT_RISK");
        if (!value.capitalizationPolicyBound()) reasons.add("CAPITALIZATION_POLICY_NOT_BOUND");
        if (!value.chargebackPolicyBound()) reasons.add("CHARGEBACK_POLICY_NOT_BOUND");
        evidence(value.evidenceRefs(), reasons); return result(27, reasons);
    }

    public ControlResult evaluateWorkforce(WorkforceEvidence value) {
        Objects.requireNonNull(value, "value"); List<String> reasons = new ArrayList<>();
        if (value.consentCoverage() < 1) reasons.add("SKILL_EVIDENCE_CONSENT_INCOMPLETE");
        if (value.skillEvidenceCoverage() < 1) reasons.add("SKILL_EVIDENCE_COVERAGE_INCOMPLETE");
        if (value.capacityOverAllocations() > 0) reasons.add("PERSON_CAPACITY_DOUBLE_COUNTED");
        if (value.personalRankingProduced()) reasons.add("PERSONAL_RANKING_FORBIDDEN");
        if (value.opaqueAttritionPredictionUsed()) reasons.add("OPAQUE_ATTRITION_PREDICTION_FORBIDDEN");
        if (value.automatedEmploymentDecision()) reasons.add("AUTOMATED_EMPLOYMENT_DECISION_FORBIDDEN");
        if (value.invasiveIndividualTelemetryCollected()) reasons.add("INVASIVE_INDIVIDUAL_TELEMETRY_FORBIDDEN");
        if (!value.appealAvailable()) reasons.add("APPEAL_PATH_REQUIRED");
        if (!value.humanAccountabilityAssigned()) reasons.add("HUMAN_ACCOUNTABILITY_REQUIRED");
        evidence(value.evidenceRefs(), reasons); return result(28, reasons);
    }

    public ControlResult evaluateTransformation(TransformationEvidence value) {
        Objects.requireNonNull(value, "value"); List<String> reasons = new ArrayList<>();
        if (value.strategyAlignmentCoverage() < 1) reasons.add("STRATEGY_ALIGNMENT_INCOMPLETE");
        if (value.dependencyCoverage() < 1) reasons.add("DEPENDENCY_COVERAGE_INCOMPLETE");
        if (value.stakeholderImpactCoverage() < 1) reasons.add("CHANGE_IMPACT_COVERAGE_INCOMPLETE");
        if (value.readinessCoverage() < 1) reasons.add("BUSINESS_READINESS_INCOMPLETE");
        if (!value.changeSaturationWithinCapacity()) reasons.add("CHANGE_SATURATION_EXCEEDS_CAPACITY");
        if (!value.adoptionUsesBehaviorEvidence()) reasons.add("ADOPTION_IS_SELF_REPORTED_ONLY");
        if (!value.benefitBaselinePredatesChange()) reasons.add("BENEFIT_BASELINE_CREATED_TOO_LATE");
        if (!value.benefitDoubleCountFree()) reasons.add("BENEFIT_DOUBLE_COUNT_RISK");
        if (!value.cutoverRollbackPrepared()) reasons.add("CUTOVER_ROLLBACK_NOT_PREPARED");
        if (value.successAutoDeclared()) reasons.add("AUTOMATIC_TRANSFORMATION_SUCCESS_FORBIDDEN");
        evidence(value.evidenceRefs(), reasons); return result(29, reasons);
    }

    public ControlResult evaluateControlTower(ControlTowerEvidence value) {
        Objects.requireNonNull(value, "value"); List<String> reasons = new ArrayList<>();
        if (value.identityResolutionCoverage() < 1) reasons.add("IDENTITY_RESOLUTION_INCOMPLETE");
        if (value.provenanceCoverage() < 1) reasons.add("PROVENANCE_INCOMPLETE");
        if (!value.temporalConflictsResolved()) reasons.add("TEMPORAL_TRUTH_CONFLICT_OPEN");
        if (!value.planBounded()) reasons.add("AUTONOMOUS_PLAN_UNBOUNDED");
        if (!value.policyDecisionAllows()) reasons.add("POLICY_DENIED");
        if (!value.idempotencyPassed()) reasons.add("IDEMPOTENCY_NOT_VERIFIED");
        if (!value.compensationAndRecoveryPassed()) reasons.add("COMPENSATION_OR_RECOVERY_NOT_VERIFIED");
        if (!value.killSwitchVerified()) reasons.add("KILL_SWITCH_NOT_VERIFIED");
        if (!value.separationOfDutiesPassed()) reasons.add("SEPARATION_OF_DUTIES_FAILED");
        if (value.crossTenantLeakDetected()) reasons.add("CROSS_TENANT_LEAK_DETECTED");
        if (value.autonomousProductionExecutionRequested()) reasons.add("AUTONOMOUS_PRODUCTION_EXECUTION_FORBIDDEN");
        evidence(value.evidenceRefs(), reasons); return result(30, reasons);
    }

    private static ControlResult result(int batch, List<String> reasons) {
        List<String> finalReasons = reasons.stream().distinct().sorted().toList();
        return new ControlResult(batch, finalReasons.isEmpty() ? ControlDecision.READY_FOR_HUMAN_REVIEW : ControlDecision.BLOCKED,
                finalReasons, false, false);
    }
    private static void evidence(List<String> refs, List<String> reasons) { if (refs.isEmpty()) reasons.add("EVIDENCE_REQUIRED"); }
    private static void rate(double value, String field) {
        if (!Double.isFinite(value) || value < 0 || value > 1) throw new IllegalArgumentException(field + " must be between zero and one");
    }
    private static void nonnegative(BigDecimal value, String field) {
        if (value == null || value.signum() < 0) throw new IllegalArgumentException(field + " must be non-negative");
    }
    private static List<String> copy(List<String> value) { return value == null ? List.of() : List.copyOf(value); }
}
