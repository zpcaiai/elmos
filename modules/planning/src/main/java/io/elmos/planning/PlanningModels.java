package io.elmos.planning;

import io.elmos.health.HealthModels;

import java.util.List;
import java.util.Map;
import java.util.Set;

public final class PlanningModels {
    private PlanningModels() {}
    public enum PlanStatus { READY, NEEDS_APPROVAL, BLOCKED }
    public enum StepType { BASELINE_RESTORE, JDK_UPGRADE, BUILD_PLUGIN_UPGRADE, SPRING_BOOT_UPGRADE,
        JAKARTA_MIGRATION, SECURITY_MIGRATION, HIBERNATE_MIGRATION, TEST_UPGRADE, API_VALIDATION }
    public enum GateType { HUMAN_APPROVAL, SECURITY_REVIEW, ARCHITECTURE_REVIEW, DATA_REVIEW, API_REVIEW, EVIDENCE_REQUIRED }

    public record OrganizationPolicy(Set<Integer> allowedJavaTargets, int defaultJavaTarget,
                                     HealthModels.Severity autoApprovalRiskCeiling,
                                     int maxParallelSteps, int personDaysPerMonth) {
        public OrganizationPolicy {
            allowedJavaTargets = Set.copyOf(allowedJavaTargets);
            if (!allowedJavaTargets.contains(defaultJavaTarget) || maxParallelSteps < 1 || maxParallelSteps > 16
                    || personDaysPerMonth < 15 || personDaysPerMonth > 24) throw new IllegalArgumentException("invalid organization planning policy");
        }
        public static OrganizationPolicy defaults() { return new OrganizationPolicy(Set.of(17, 21, 25), 21, HealthModels.Severity.MEDIUM, 3, 20); }
    }

    public record TargetProfile(int javaVersion, String springBootLine, String jakartaNamespace,
                                String buildToolStrategy, List<String> assumptions,
                                HealthModels.EvidenceStatus status) {
        public TargetProfile { assumptions = List.copyOf(assumptions); }
    }
    public record CompatibilityDecision(String component, String sourceVersion, String targetVersion,
                                        boolean compatible, boolean migrationRequired, String rationale,
                                        HealthModels.EvidenceStatus status, String matrixVersion) {}
    public record EffortRange(int minimumPersonDays, int likelyPersonDays, int maximumPersonDays,
                              double minimumPersonMonths, double likelyPersonMonths, double maximumPersonMonths,
                              String confidence, List<String> assumptions) {
        public EffortRange { assumptions = List.copyOf(assumptions); }
    }
    public record MigrationStep(String stepId, StepType type, List<String> dependsOn, String objective,
                                HealthModels.Severity risk, int automationScore, EffortRange effort,
                                List<String> requiredEvidence, boolean approvalRequired) {
        public MigrationStep { dependsOn = List.copyOf(dependsOn); requiredEvidence = List.copyOf(requiredEvidence); }
    }
    public record MigrationWave(int number, List<String> stepIds, String exitCriterion) {
        public MigrationWave { stepIds = List.copyOf(stepIds); }
    }
    public record ApprovalGate(String gateId, GateType type, String beforeStepId, String reason,
                               List<String> requiredEvidence, boolean blocking) {
        public ApprovalGate { requiredEvidence = List.copyOf(requiredEvidence); }
    }
    public record ScoreBreakdown(int score, Map<String,Integer> factors, List<String> rationale) {
        public ScoreBreakdown { factors = Map.copyOf(factors); rationale = List.copyOf(rationale); }
    }
    public record MigrationPlan(String schemaVersion, String planId, String healthReportId, String snapshotId, TargetProfile target,
                                List<CompatibilityDecision> compatibility, List<MigrationStep> steps,
                                List<MigrationWave> waves, List<ApprovalGate> approvalGates,
                                ScoreBreakdown migrationRisk, ScoreBreakdown automation,
                                EffortRange totalEffort, PlanStatus status, List<String> blockingReasons) {
        public MigrationPlan {
            if (!"1.0".equals(schemaVersion)) throw new IllegalArgumentException("unsupported migration plan schema version");
            compatibility = List.copyOf(compatibility); steps = List.copyOf(steps); waves = List.copyOf(waves);
            approvalGates = List.copyOf(approvalGates); blockingReasons = List.copyOf(blockingReasons);
        }
    }
}
