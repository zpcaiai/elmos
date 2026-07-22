package io.elmos.commercial;

import io.elmos.commercial.CommercialModels.*;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public final class OnboardingAndProjectService {
    private static final Set<String> REQUIRED_DIMENSIONS = Set.of("IDENTITY", "SCM", "RUNNER", "DEPENDENCY",
            "BUILD", "TEST", "SECURITY", "MODEL", "GOVERNANCE", "SUPPORT", "PILOT");

    public OnboardingReadiness assessReadiness(String organizationId, String deploymentMode,
                                               List<ReadinessDimension> dimensions) {
        List<String> blockers = new ArrayList<>(dimensions.stream().flatMap(value -> value.blockingTaskIds().stream()).distinct().toList());
        Set<String> present = dimensions.stream().map(ReadinessDimension::name).collect(java.util.stream.Collectors.toSet());
        boolean missing = !present.containsAll(REQUIRED_DIMENSIONS);
        boolean duplicate = present.size() != dimensions.size();
        dimensions.stream().filter(value -> value.evidenceRefs().isEmpty())
                .forEach(value -> blockers.add("READINESS_EVIDENCE_MISSING:" + value.name()));
        if (duplicate) blockers.add("DUPLICATE_READINESS_DIMENSION");
        ReadinessStatus overall;
        if (duplicate || dimensions.stream().anyMatch(value -> value.status() == ReadinessStatus.BLOCKED)) overall = ReadinessStatus.BLOCKED;
        else if (missing || dimensions.stream().anyMatch(value -> value.status() == ReadinessStatus.UNKNOWN)
                || dimensions.stream().anyMatch(value -> value.evidenceRefs().isEmpty())) overall = ReadinessStatus.UNKNOWN;
        else if (dimensions.stream().anyMatch(value -> value.status() == ReadinessStatus.NOT_READY)) overall = ReadinessStatus.NOT_READY;
        else if (!blockers.isEmpty() || dimensions.stream().anyMatch(value -> value.status() == ReadinessStatus.READY_WITH_CONDITIONS)) {
            overall = ReadinessStatus.READY_WITH_CONDITIONS;
        } else overall = ReadinessStatus.READY;
        return new OnboardingReadiness(organizationId, deploymentMode, overall, dimensions, blockers,
                overall == ReadinessStatus.READY);
    }

    public ProjectStatusSnapshot projectStatus(String projectId, List<ProjectStep> steps,
                                               Instant p50, Instant p80, BigDecimal budgetUsed,
                                               BigDecimal budgetLimit, boolean overrideRequested,
                                               String overrideReason) {
        if (steps.isEmpty()) return new ProjectStatusSnapshot(projectId, ProjectHealth.UNKNOWN, BigDecimal.ZERO,
                List.of("NO_PROJECT_STEPS"), p50, p80, budgetUsed, budgetLimit, false, null);
        BigDecimal totalWeight = steps.stream().map(ProjectStep::weight).reduce(BigDecimal.ZERO, BigDecimal::add);
        if (totalWeight.signum() <= 0) throw new IllegalArgumentException("PROJECT_WEIGHT_MUST_BE_POSITIVE");
        BigDecimal completeWeight = steps.stream().filter(ProjectStep::completed).map(ProjectStep::weight)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal progress = completeWeight.divide(totalWeight, 4, RoundingMode.HALF_UP);
        List<String> blockers = new ArrayList<>();
        steps.stream().filter(step -> step.criticalGate() && !step.gatePassed())
                .forEach(step -> blockers.add("CRITICAL_GATE_FAILED:" + step.stepId()));
        steps.stream().filter(step -> step.blockerType() != null && !step.blockerType().isBlank())
                .forEach(step -> blockers.add("BLOCKER:" + step.blockerType() + ":" + step.stepId()));
        if (budgetLimit != null && budgetUsed != null && budgetUsed.compareTo(budgetLimit) > 0) blockers.add("BUDGET_EXCEEDED");
        ProjectHealth calculated = !blockers.isEmpty() ? ProjectHealth.RED
                : progress.compareTo(new BigDecimal("0.75")) >= 0 ? ProjectHealth.GREEN : ProjectHealth.AMBER;
        boolean overrideApplied = overrideRequested && overrideReason != null && !overrideReason.isBlank()
                && calculated != ProjectHealth.RED;
        return new ProjectStatusSnapshot(projectId, calculated, progress, blockers, p50, p80,
                budgetUsed, budgetLimit, overrideApplied, overrideApplied ? overrideReason : null);
    }

    public ChangeRequest scopeChange(String changeId, String projectId, String description,
                                     int repositoryDelta, BigDecimal creditPerRepository) {
        if (repositoryDelta == 0) throw new IllegalArgumentException("SCOPE_CHANGE_DELTA_REQUIRED");
        return new ChangeRequest(changeId, projectId, description, repositoryDelta,
                creditPerRepository.multiply(BigDecimal.valueOf(Math.abs(repositoryDelta))), false,
                List.of("RISK", "EFFORT", "COST", "MILESTONE", "ENTITLEMENT"));
    }
}
