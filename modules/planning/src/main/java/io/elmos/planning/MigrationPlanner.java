package io.elmos.planning;

import io.elmos.health.HealthModels;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

public final class MigrationPlanner {
    private final CompatibilityMatrix matrix;
    public MigrationPlanner(CompatibilityMatrix matrix) { this.matrix = Objects.requireNonNull(matrix); }

    public PlanningModels.MigrationPlan plan(HealthModels.LegacyHealthReport health, PlanningModels.OrganizationPolicy policy) {
        Objects.requireNonNull(health); Objects.requireNonNull(policy);
        PlanningModels.TargetProfile target = selectTarget(health, policy);
        List<PlanningModels.CompatibilityDecision> compatibility = matrix.resolve(health, target);
        PlanningModels.ScoreBreakdown risk = riskScore(health);
        PlanningModels.ScoreBreakdown automation = automationScore(health);
        List<PlanningModels.MigrationStep> steps = steps(health, target, risk, automation, policy);
        validateDag(steps); List<PlanningModels.MigrationWave> waves = waves(steps, policy.maxParallelSteps());
        List<PlanningModels.ApprovalGate> gates = gates(health, compatibility, steps, policy);
        PlanningModels.EffortRange total = sumEffort(steps, policy.personDaysPerMonth(), health.status());
        List<String> blocking = new ArrayList<>();
        if (health.buildSystem() == HealthModels.BuildSystem.UNKNOWN) blocking.add("BUILD_SYSTEM_UNKNOWN");
        if (health.detectedJavaVersion() == null) blocking.add("JAVA_VERSION_UNKNOWN");
        if (health.vulnerabilityEvidence().status() != HealthModels.EvidenceStatus.PASS) blocking.add("VULNERABILITY_EVIDENCE_INCOMPLETE");
        if (health.evidenceDigests().isEmpty()) blocking.add("SOURCE_EVIDENCE_MISSING");
        PlanningModels.PlanStatus status = !blocking.isEmpty() ? PlanningModels.PlanStatus.BLOCKED
                : gates.stream().anyMatch(PlanningModels.ApprovalGate::blocking) ? PlanningModels.PlanStatus.NEEDS_APPROVAL : PlanningModels.PlanStatus.READY;
        String canonical = health.reportId() + "\0" + target.javaVersion() + "\0" + steps.stream().map(PlanningModels.MigrationStep::stepId).reduce("", (a,b) -> a + "\0" + b);
        return new PlanningModels.MigrationPlan("1.0", "plan-" + sha256(canonical.getBytes(StandardCharsets.UTF_8)).substring(0,24), health.reportId(),
                health.snapshotId(), target, compatibility, steps, waves, gates, risk, automation, total, status, blocking);
    }

    private static PlanningModels.TargetProfile selectTarget(HealthModels.LegacyHealthReport health, PlanningModels.OrganizationPolicy policy) {
        int target = health.targetRecommendation() != null && policy.allowedJavaTargets().contains(health.targetRecommendation().javaVersion())
                ? health.targetRecommendation().javaVersion() : policy.defaultJavaTarget();
        List<String> assumptions = new ArrayList<>();
        if (health.detectedJavaVersion() == null) assumptions.add("Source Java level must be confirmed with an approved baseline build");
        if (target == 25) assumptions.add("Java 25 requires explicit framework, plugin and runtime certification evidence");
        String bootLine = health.springBootVersion() == null ? null : major(health.springBootVersion()) < 3 ? "3.x-approved-by-organization" : "preserve-approved-3.x";
        return new PlanningModels.TargetProfile(target, bootLine, "jakarta", health.buildSystem() == HealthModels.BuildSystem.MAVEN ? "MAVEN_REACTOR" :
                health.buildSystem() == HealthModels.BuildSystem.GRADLE ? "GRADLE_MULTI_PROJECT" : "MIXED_OR_UNKNOWN",
                assumptions, assumptions.isEmpty() ? HealthModels.EvidenceStatus.PASS : HealthModels.EvidenceStatus.INCONCLUSIVE);
    }
    private static PlanningModels.ScoreBreakdown riskScore(HealthModels.LegacyHealthReport health) {
        Map<String,Integer> factors = new LinkedHashMap<>();
        factors.put("criticalVulnerabilities", (int) health.vulnerabilities().stream().filter(v -> v.severity() == HealthModels.Severity.CRITICAL).count() * 20);
        factors.put("highFindings", (int) health.findings().stream().filter(f -> f.severity() == HealthModels.Severity.HIGH).count() * 7);
        factors.put("publicApis", Math.min(15, health.publicApis().size()));
        factors.put("modules", Math.min(15, Math.max(0, health.modules().size() - 1) * 2));
        factors.put("testGap", health.testReadiness().status() == HealthModels.EvidenceStatus.PASS ? 0 : 15);
        factors.put("inconclusiveEvidence", health.status() == HealthModels.EvidenceStatus.INCONCLUSIVE ? 15 : 0);
        int score = Math.min(100, factors.values().stream().mapToInt(Integer::intValue).sum());
        return new PlanningModels.ScoreBreakdown(score, factors, List.of("Risk is evidence-weighted and capped at 100", "Unknown evidence increases rather than lowers risk"));
    }
    private static PlanningModels.ScoreBreakdown automationScore(HealthModels.LegacyHealthReport health) {
        Map<String,Integer> factors = new LinkedHashMap<>();
        factors.put("deterministicBuild", health.buildSystem() == HealthModels.BuildSystem.UNKNOWN ? -25 : 15);
        factors.put("tests", health.testReadiness().status() == HealthModels.EvidenceStatus.PASS ? 20 : -20);
        factors.put("publicApiReview", -Math.min(20, health.publicApis().size() * 2));
        factors.put("architectureRisk", -Math.min(25, (int) health.findings().stream().filter(f -> f.category().equals("ARCHITECTURE")).count() * 5));
        factors.put("rewriteEligible", health.findings().stream().anyMatch(f -> f.code().equals("LEGACY_JAVAX_API")) ? 20 : 5);
        factors.put("highRiskManualWork", -Math.min(30, (int) health.findings().stream().filter(f -> f.severity().ordinal() >= HealthModels.Severity.HIGH.ordinal()).count() * 5));
        factors.put("inconclusiveEvidence", health.status() == HealthModels.EvidenceStatus.INCONCLUSIVE ? -20 : 0);
        int score = Math.max(0, Math.min(100, 50 + factors.values().stream().mapToInt(Integer::intValue).sum()));
        return new PlanningModels.ScoreBreakdown(score, factors, List.of("Automation score estimates deterministic transformation potential", "It does not authorize unattended migration"));
    }
    private static List<PlanningModels.MigrationStep> steps(HealthModels.LegacyHealthReport health, PlanningModels.TargetProfile target,
            PlanningModels.ScoreBreakdown risk, PlanningModels.ScoreBreakdown automation, PlanningModels.OrganizationPolicy policy) {
        List<PlanningModels.MigrationStep> steps = new ArrayList<>();
        add(steps, "S01", PlanningModels.StepType.BASELINE_RESTORE, List.of(), "Reproduce the current build and test baseline", health, 20, true, policy, "baseline-build", "baseline-tests");
        add(steps, "S02", PlanningModels.StepType.JDK_UPGRADE, List.of("S01"), "Upgrade toolchain to Java " + target.javaVersion(), health, 70, false, policy, "jdk-version", "compile-result");
        add(steps, "S03", PlanningModels.StepType.BUILD_PLUGIN_UPGRADE, List.of("S02"), "Upgrade build plugins and remove incompatible flags", health, 65, false, policy, "effective-build", "plugin-compatibility");
        add(steps, "S04", PlanningModels.StepType.SPRING_BOOT_UPGRADE, List.of("S03"), "Move Spring Boot to the approved target line", health, 60, false, policy, "dependency-tree", "boot-startup");
        add(steps, "S05", PlanningModels.StepType.JAKARTA_MIGRATION, List.of("S04"), "Migrate Java EE namespaces and contracts to Jakarta", health, 80, false, policy, "compile-result", "namespace-scan");
        add(steps, "S06", PlanningModels.StepType.SECURITY_MIGRATION, List.of("S04"), "Migrate Spring Security configuration and authorization behavior", health, 45, true, policy, "security-tests", "authorization-review");
        add(steps, "S07", PlanningModels.StepType.HIBERNATE_MIGRATION, List.of("S05"), "Migrate persistence mappings and query behavior", health, 45, true, policy, "schema-diff", "transaction-tests");
        add(steps, "S08", PlanningModels.StepType.TEST_UPGRADE, List.of("S05", "S06", "S07"), "Upgrade tests and restore or improve baseline coverage", health, 55, false, policy, "unit-tests", "integration-tests");
        add(steps, "S09", PlanningModels.StepType.API_VALIDATION, List.of("S08"), "Validate public API and serialization compatibility", health, 35, true, policy, "api-inventory", "compatibility-report");
        return steps;
    }
    private static void add(List<PlanningModels.MigrationStep> steps, String id, PlanningModels.StepType type, List<String> depends,
            String objective, HealthModels.LegacyHealthReport health, int baseAutomation, boolean sensitive,
            PlanningModels.OrganizationPolicy policy, String... evidence) {
        int findings = (int) health.findings().stream().filter(f -> relevant(type, f)).count();
        HealthModels.Severity risk = sensitive && findings > 0 ? HealthModels.Severity.HIGH : findings > 2 ? HealthModels.Severity.HIGH : findings > 0 ? HealthModels.Severity.MEDIUM : HealthModels.Severity.LOW;
        int automation = Math.max(0, Math.min(100, baseAutomation - findings * 8 - (health.testReadiness().status() == HealthModels.EvidenceStatus.PASS ? 0 : 15)));
        int base = switch (type) { case BASELINE_RESTORE -> 3; case JDK_UPGRADE, BUILD_PLUGIN_UPGRADE -> 4; case SPRING_BOOT_UPGRADE -> 8;
            case JAKARTA_MIGRATION -> 5; case SECURITY_MIGRATION, HIBERNATE_MIGRATION -> 7; case TEST_UPGRADE -> 8; case API_VALIDATION -> 5; };
        int moduleFactor = Math.max(1, health.modules().size()); int likely = base + moduleFactor + findings * 2;
        PlanningModels.EffortRange effort = range(Math.max(1, likely / 2), likely, likely * 2, policy.personDaysPerMonth(), health.status(), List.of("Static evidence only", "One experienced modernization engineer"));
        steps.add(new PlanningModels.MigrationStep(id, type, depends, objective, risk, automation, effort, List.of(evidence), sensitive || risk.ordinal() > policy.autoApprovalRiskCeiling().ordinal()));
    }
    private static boolean relevant(PlanningModels.StepType type, HealthModels.Finding finding) { return switch (type) {
        case JAKARTA_MIGRATION -> finding.code().contains("JAVAX"); case HIBERNATE_MIGRATION -> Set.of("DATABASE","TRANSACTION").contains(finding.category());
        case SECURITY_MIGRATION -> finding.category().equals("SECURITY"); case TEST_UPGRADE -> finding.category().equals("TEST");
        case API_VALIDATION -> true; case BASELINE_RESTORE, JDK_UPGRADE, BUILD_PLUGIN_UPGRADE, SPRING_BOOT_UPGRADE -> Set.of("BUILD","COMPATIBILITY","DEPENDENCY").contains(finding.category());
    }; }
    private static List<PlanningModels.ApprovalGate> gates(HealthModels.LegacyHealthReport health, List<PlanningModels.CompatibilityDecision> compatibility,
            List<PlanningModels.MigrationStep> steps, PlanningModels.OrganizationPolicy policy) {
        List<PlanningModels.ApprovalGate> gates = new ArrayList<>();
        for (PlanningModels.MigrationStep step : steps) if (step.approvalRequired()) gates.add(new PlanningModels.ApprovalGate("gate-" + step.stepId(),
                switch (step.type()) { case SECURITY_MIGRATION -> PlanningModels.GateType.SECURITY_REVIEW; case HIBERNATE_MIGRATION -> PlanningModels.GateType.DATA_REVIEW;
                    case API_VALIDATION -> PlanningModels.GateType.API_REVIEW; default -> PlanningModels.GateType.HUMAN_APPROVAL; }, step.stepId(),
                "Step risk exceeds unattended policy or changes a sensitive contract", step.requiredEvidence(), true));
        if (compatibility.stream().anyMatch(c -> c.status() == HealthModels.EvidenceStatus.INCONCLUSIVE)) gates.add(new PlanningModels.ApprovalGate("gate-compatibility-evidence",
                PlanningModels.GateType.EVIDENCE_REQUIRED, "S02", "Compatibility evidence is incomplete", List.of("approved-compatibility-matrix", "baseline-build"), true));
        if (health.buildSystem() == HealthModels.BuildSystem.UNKNOWN || health.detectedJavaVersion() == null) gates.add(new PlanningModels.ApprovalGate("gate-build-evidence",
                PlanningModels.GateType.EVIDENCE_REQUIRED, "S01", "Build system or source Java evidence is incomplete", List.of("effective-build", "jdk-version", "baseline-build"), true));
        if (health.vulnerabilityEvidence().status() != HealthModels.EvidenceStatus.PASS) gates.add(new PlanningModels.ApprovalGate("gate-vulnerability-evidence",
                PlanningModels.GateType.EVIDENCE_REQUIRED, "S04", "Vulnerability evidence is incomplete", List.of("provider-provenance", "vulnerability-report"), true));
        if (health.evidenceDigests().isEmpty()) gates.add(new PlanningModels.ApprovalGate("gate-source-evidence",
                PlanningModels.GateType.EVIDENCE_REQUIRED, "S01", "Source evidence digests are missing", List.of("snapshot-manifest", "source-digests"), true));
        if (health.vulnerabilities().stream().anyMatch(v -> v.severity().ordinal() >= HealthModels.Severity.HIGH.ordinal())) gates.add(new PlanningModels.ApprovalGate("gate-vulnerability",
                PlanningModels.GateType.SECURITY_REVIEW, "S04", "High or critical vulnerability requires remediation disposition", List.of("vulnerability-report", "remediation-decision"), true));
        return gates;
    }
    private static List<PlanningModels.MigrationWave> waves(List<PlanningModels.MigrationStep> steps, int maxParallel) {
        Map<String,Integer> wave = new LinkedHashMap<>();
        for (PlanningModels.MigrationStep step : steps) wave.put(step.stepId(), step.dependsOn().stream().map(wave::get).filter(Objects::nonNull).max(Integer::compareTo).orElse(0) + 1);
        List<PlanningModels.MigrationWave> result = new ArrayList<>();
        for (int number = 1; number <= wave.values().stream().max(Integer::compareTo).orElse(0); number++) {
            List<String> ids = new ArrayList<>(); for (var entry : wave.entrySet()) if (entry.getValue() == number) ids.add(entry.getKey());
            for (int offset = 0; offset < ids.size(); offset += maxParallel) result.add(new PlanningModels.MigrationWave(result.size() + 1,
                    ids.subList(offset, Math.min(ids.size(), offset + maxParallel)), "All required evidence passes and blocking approvals are recorded"));
        }
        return result;
    }
    private static void validateDag(List<PlanningModels.MigrationStep> steps) {
        Set<String> seen = new HashSet<>();
        for (PlanningModels.MigrationStep step : steps) { if (!seen.containsAll(step.dependsOn()) || !seen.add(step.stepId())) throw new IllegalStateException("migration plan is not a topologically ordered DAG"); }
    }
    private static PlanningModels.EffortRange sumEffort(List<PlanningModels.MigrationStep> steps, int daysPerMonth, HealthModels.EvidenceStatus evidenceStatus) {
        int min = steps.stream().map(PlanningModels.MigrationStep::effort).mapToInt(PlanningModels.EffortRange::minimumPersonDays).sum();
        int likely = steps.stream().map(PlanningModels.MigrationStep::effort).mapToInt(PlanningModels.EffortRange::likelyPersonDays).sum();
        int max = steps.stream().map(PlanningModels.MigrationStep::effort).mapToInt(PlanningModels.EffortRange::maximumPersonDays).sum();
        return range(min, likely, max, daysPerMonth, evidenceStatus, List.of("Does not include organization queue time", "Re-estimate after baseline and dependency evidence"));
    }
    private static PlanningModels.EffortRange range(int min, int likely, int max, int daysPerMonth, HealthModels.EvidenceStatus status, List<String> assumptions) {
        return new PlanningModels.EffortRange(min, likely, max, round(min/(double)daysPerMonth), round(likely/(double)daysPerMonth), round(max/(double)daysPerMonth),
                status == HealthModels.EvidenceStatus.PASS ? "MEDIUM" : "LOW", assumptions);
    }
    private static double round(double value) { return Math.round(value * 10d) / 10d; }
    private static int major(String version) { try { return Integer.parseInt(version.split("[.-]",2)[0]); } catch (RuntimeException ignored) { return 0; } }
    private static String sha256(byte[] bytes) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)); } catch (Exception error) { throw new IllegalStateException(error); } }
}
