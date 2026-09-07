package io.elmos.repair;

import io.elmos.repair.RepairLoopModels.*;

import java.nio.file.Path;
import java.util.*;

/** Fail-closed planning, patch review, effectiveness and Batch 8 gate policy. */
public final class RepairLoopPolicy {
    private static final Set<DiagnosticCategory> DETERMINISTIC = Set.of(
            DiagnosticCategory.DEPENDENCY, DiagnosticCategory.BUILD_CONFIGURATION,
            DiagnosticCategory.SYNTAX, DiagnosticCategory.SYMBOL, DiagnosticCategory.TYPE,
            DiagnosticCategory.GENERIC, DiagnosticCategory.NULLABILITY,
            DiagnosticCategory.TEST_COMPILATION, DiagnosticCategory.TEST_FIXTURE,
            DiagnosticCategory.TEST_DISCOVERY);

    public RepairPlan plan(Request request, DiagnosticCluster cluster, List<Diagnostic> members,
                           String stableSnapshotId, RepairStrategy override) {
        RepairStrategy strategy = override == null ? strategy(request, cluster) : override;
        List<String> files = members.stream().map(Diagnostic::file).filter(Objects::nonNull)
                .filter(value -> !value.contains("<WORKSPACE_PATH>"))
                .filter(RepairLoopPolicy::safeRelative).distinct().sorted().toList();
        List<String> declarations = members.stream().map(Diagnostic::targetDeclarationId)
                .filter(Objects::nonNull).distinct().sorted().toList();
        List<String> invariants = new ArrayList<>(List.of("public-api-locked", "effects-locked",
                "security-locked", "transactions-locked", "tests-and-assertions-locked",
                "approved-dependencies-only", "generated-manual-boundary-locked"));
        if (cluster.maximumSeverity().ordinal() >= Severity.BLOCKING.ordinal()) invariants.add("blocking-diagnostics-must-decrease");
        boolean review = cluster.maximumSeverity() == Severity.CRITICAL
                || cluster.primaryCategory() == DiagnosticCategory.SECURITY
                || strategy == RepairStrategy.HUMAN;
        String ruleId = strategy == RepairStrategy.DETERMINISTIC_RECIPE
                ? "repair." + cluster.primaryCategory().name().toLowerCase(Locale.ROOT).replace('_', '-') + "@1" : null;
        String id = RepairLoopIds.id("repair-plan", cluster.clusterId(), strategy, files, declarations, stableSnapshotId);
        return new RepairPlan(id, cluster.clusterId(), strategy, ruleId, files, declarations,
                invariants, List.of("parse-modified-files", "compile-affected-module", "run-affected-tests"),
                List.of("run-dependent-modules", "run-contract-tests", "run-full-regression"),
                stableSnapshotId, review);
    }

    public List<String> reviewPatch(Request request, RepairPlan plan, Patch patch, String currentSnapshotId,
                                    PatchInspection inspection) {
        List<String> findings = new ArrayList<>();
        if (!patch.clusterId().equals(plan.clusterId())) findings.add("PATCH_CLUSTER_MISMATCH");
        if (!patch.planId().equals(plan.planId())) findings.add("PATCH_PLAN_MISMATCH");
        if (!patch.baseSnapshotId().equals(currentSnapshotId)) findings.add("PATCH_BASE_SNAPSHOT_MISMATCH");
        if (patch.modifications().size() > request.policy().maximumFilesPerPatch()) findings.add("PATCH_FILE_LIMIT_EXCEEDED");
        int lines = patch.modifications().stream().mapToInt(Modification::linesChanged).sum();
        if (lines > request.policy().maximumLinesPerPatch()) findings.add("PATCH_LINE_LIMIT_EXCEEDED");
        Set<String> files = new HashSet<>();
        for (Modification modification : patch.modifications()) {
            if (!safeRelative(modification.file())) findings.add("PATCH_PATH_UNSAFE:" + modification.file());
            if (!files.add(modification.file())) findings.add("PATCH_DUPLICATE_FILE:" + modification.file());
            if (!plan.allowedFiles().contains(modification.file())) findings.add("PATCH_OUTSIDE_PLANNED_FILES:" + modification.file());
            if (modification.targetDeclarationId() != null && !plan.allowedDeclarations().contains(modification.targetDeclarationId()))
                findings.add("PATCH_OUTSIDE_PLANNED_DECLARATIONS:" + modification.targetDeclarationId());
            if (modification.beforeHash().equals(modification.afterHash())) findings.add("PATCH_NO_CONTENT_CHANGE:" + modification.file());
            if (modification.touchesManualRegion()) findings.add("MANUAL_REGION_MODIFIED:" + modification.file());
            if (modification.publicApiChanged()) findings.add("PUBLIC_API_CHANGED:" + modification.file());
            if (modification.deletesTest()) findings.add("TEST_DELETED:" + modification.file());
            if (modification.weakensAssertion()) findings.add("ASSERTION_WEAKENED:" + modification.file());
            if (modification.suppressDelta() > 0) findings.add("SUPPRESS_ADDED:" + modification.file());
            if (modification.dynamicOrAnyDelta() > 0) findings.add("DYNAMIC_OR_ANY_ADDED:" + modification.file());
            List<String> unapproved = modification.dependenciesAdded().stream()
                    .filter(value -> !request.policy().approvedPackages().contains(value)).toList();
            if (!unapproved.isEmpty()) findings.add("UNAPPROVED_DEPENDENCIES:" + String.join(",", unapproved));
            if ((modification.securityBehaviorChanged() || modification.transactionBehaviorChanged())
                    && (!patch.humanReviewApproved() || patch.reviewEvidenceRef() == null || patch.reviewEvidenceRef().isBlank()))
                findings.add("HIGH_RISK_BEHAVIOR_CHANGE_UNREVIEWED:" + modification.file());
        }
        if (patch.agentGenerated() && patch.highRisk()
                && (!patch.humanReviewApproved() || patch.reviewEvidenceRef() == null || patch.reviewEvidenceRef().isBlank()))
            findings.add("HIGH_RISK_AGENT_PATCH_UNREVIEWED");
        if (patch.agentGenerated() && plan.strategy() != RepairStrategy.AGENT_PATCH) findings.add("AGENT_PATCH_NOT_PLANNED");
        if (!patch.agentGenerated() && plan.strategy() == RepairStrategy.AGENT_PATCH) findings.add("AGENT_PATCH_PROVENANCE_MISSING");
        if (patch.agentTokens() > request.policy().maximumAgentTokens()) findings.add("AGENT_TOKEN_BUDGET_EXCEEDED");
        if (patch.costMicros() > request.policy().maximumCostMicros()) findings.add("AGENT_COST_BUDGET_EXCEEDED");
        if (!inspection.patchId().equals(patch.patchId())) findings.add("PATCH_INSPECTION_ID_MISMATCH");
        if (!inspection.parsed()) findings.add("PATCH_PARSE_NOT_PROVEN");
        if (!inspection.scopeVerified()) findings.add("PATCH_SCOPE_INSPECTION_NOT_PROVEN");
        if (!inspection.generatedManualBoundaryVerified()) findings.add("GENERATED_MANUAL_BOUNDARY_NOT_PROVEN");
        Set<String> declaredFiles = patch.modifications().stream().map(Modification::file).collect(java.util.stream.Collectors.toSet());
        if (!declaredFiles.equals(Set.copyOf(inspection.actualChangedFiles()))) findings.add("PATCH_ACTUAL_FILES_MISMATCH");
        if (inspection.publicApiChanged()) findings.add("INSPECTION_PUBLIC_API_CHANGED");
        if (inspection.testsDeleted()) findings.add("INSPECTION_TEST_DELETED");
        if (inspection.assertionsWeakened()) findings.add("INSPECTION_ASSERTION_WEAKENED");
        if (inspection.suppressDelta() > 0) findings.add("INSPECTION_SUPPRESS_ADDED");
        if (inspection.dynamicOrAnyDelta() > 0) findings.add("INSPECTION_DYNAMIC_OR_ANY_ADDED");
        List<String> inspectedUnapproved = inspection.dependenciesAdded().stream()
                .filter(value -> !request.policy().approvedPackages().contains(value)).toList();
        if (!inspectedUnapproved.isEmpty()) findings.add("INSPECTION_UNAPPROVED_DEPENDENCIES:" + String.join(",", inspectedUnapproved));
        if ((inspection.securityBehaviorChanged() || inspection.transactionBehaviorChanged())
                && (!patch.humanReviewApproved() || patch.reviewEvidenceRef() == null || patch.reviewEvidenceRef().isBlank()))
            findings.add("INSPECTION_HIGH_RISK_CHANGE_UNREVIEWED");
        if (inspection.evidenceRefs().isEmpty()) findings.add("PATCH_INSPECTION_EVIDENCE_MISSING");
        inspection.findings().stream().map(value -> "INSPECTION:" + value).forEach(findings::add);
        return List.copyOf(findings);
    }

    public PatchOutcome effectiveness(ExecutionResult before, ExecutionResult after,
                                      int beforeMigrationDiagnostics, int afterMigrationDiagnostics) {
        if (after.productionResourceAccessed() || after.secretMaterialObserved()
                || after.publicApiRegressions() > before.publicApiRegressions()
                || after.securityRegressions() > before.securityRegressions()
                || after.transactionRegressions() > before.transactionRegressions()
                || after.serializationRegressions() > before.serializationRegressions()
                || after.criticalStaticDiagnostics() > before.criticalStaticDiagnostics()) return PatchOutcome.UNSAFE;
        int beforeFailed = failedRequired(before), afterFailed = failedRequired(after);
        if (afterMigrationDiagnostics > beforeMigrationDiagnostics || afterFailed > beforeFailed
                || after.compileRate() < before.compileRate()) return PatchOutcome.REGRESSIVE;
        boolean diagnosticImproved = afterMigrationDiagnostics < beforeMigrationDiagnostics;
        boolean testImproved = afterFailed < beforeFailed;
        boolean compileImproved = after.compileRate() > before.compileRate();
        if (diagnosticImproved && (testImproved || compileImproved || afterFailed == 0)) return PatchOutcome.EFFECTIVE;
        if (diagnosticImproved || testImproved || compileImproved) return PatchOutcome.PARTIALLY_EFFECTIVE;
        if (after.status() == Status.INCONCLUSIVE || after.status() == Status.NOT_RUN) return PatchOutcome.INCONCLUSIVE;
        return PatchOutcome.NEUTRAL;
    }

    public ConformanceReport conformance(Request request, ExecutionResult execution,
                                         List<Diagnostic> diagnostics, List<AttributionRecord> attributions,
                                         List<PatchAudit> patches, int reproducibilityRuns, List<String> extraBlockers) {
        Map<String,Attribution> attributionByCluster = new HashMap<>();
        attributions.forEach(value -> attributionByCluster.put(value.clusterId(), value.attribution()));
        List<String> blockers = new ArrayList<>(extraBlockers);
        if (!execution.dependencyRestorePassed()) blockers.add("dependency-restore-not-proven");
        if (!execution.buildModelLoaded()) blockers.add("build-model-load-not-proven");
        if (execution.compileRate() < 1.0) blockers.add("full-compile-not-passed");
        if (execution.blockingStaticDiagnostics() > 0) blockers.add("blocking-static-diagnostics-present");
        if (execution.criticalStaticDiagnostics() > 0) blockers.add("critical-static-diagnostics-present");
        int expected = request.modules().stream().mapToInt(ModuleTarget::expectedRequiredTests).sum();
        if (expected > 0 && (!execution.testDiscoveryPassed() || execution.discoveredTests() == 0))
            blockers.add("required-test-discovery-not-proven");
        if (execution.tests().stream().anyMatch(test -> test.required()
                && Set.of(TestStatus.FAILED, TestStatus.FLAKY, TestStatus.MANUAL_REQUIRED, TestStatus.UNMAPPED).contains(test.status())))
            blockers.add("required-tests-not-stably-passed");
        if (!execution.fullRegressionExecuted()) blockers.add("full-regression-not-executed");
        if (execution.publicApiRegressions() > 0) blockers.add("public-api-regression");
        if (execution.securityRegressions() > 0) blockers.add("security-regression");
        if (execution.transactionRegressions() > 0) blockers.add("transaction-regression");
        if (execution.serializationRegressions() > 0) blockers.add("serialization-regression");
        if (execution.productionResourceAccessed()) blockers.add("production-resource-accessed");
        if (execution.secretMaterialObserved()) blockers.add("secret-material-observed");
        if (execution.sandboxRef() == null || execution.sandboxRef().isBlank()) blockers.add("sandbox-evidence-missing");
        if (execution.evidenceRefs().isEmpty()) blockers.add("execution-evidence-missing");
        request.modules().stream().filter(module -> !execution.moduleExecutions().containsKey(module.moduleId()))
                .map(module -> "module-execution-evidence-missing:" + module.moduleId()).forEach(blockers::add);
        request.modules().stream().filter(module -> module.expectedRequiredTests() > 0)
                .filter(module -> {
                    ModuleExecution value = execution.moduleExecutions().get(module.moduleId());
                    return value == null || !value.testDiscoveryPassed() || value.discoveredTests() == 0;
                }).map(module -> "module-test-discovery-not-proven:" + module.moduleId()).forEach(blockers::add);
        if (reproducibilityRuns < request.policy().requiredReproducibilityRuns()) blockers.add("reproducibility-runs-insufficient");
        if (patches.stream().anyMatch(value -> value.patch().agentGenerated() && value.patch().highRisk()
                && !value.patch().humanReviewApproved())) blockers.add("unreviewed-high-risk-agent-patch");
        List<String> open = request.obligations().stream().filter(SemanticObligation::blocking)
                .map(SemanticObligation::obligationId).toList();
        if (!open.isEmpty()) blockers.add("open-blocking-obligations");
        long unknown = attributions.stream().filter(value -> value.attribution() == Attribution.UNKNOWN).count();
        if (unknown > 0) blockers.add("unclassified-or-unknown-failures");
        blockers = blockers.stream().distinct().sorted().toList();

        Metrics metrics = metrics(request, execution, diagnostics, attributions, patches, reproducibilityRuns);
        List<ModuleGate> modules = request.modules().stream().map(module -> moduleGate(module, request,
                execution, diagnostics, patches, reproducibilityRuns, metrics)).toList();
        boolean eligible = blockers.isEmpty() && modules.stream().allMatch(ModuleGate::eligibleForBehavioralEquivalence);
        return new ConformanceReport(8, eligible ? Status.PASSED : Status.BLOCKED, request.repairRunId(),
                modules, metrics, blockers, open, eligible);
    }

    private RepairStrategy strategy(Request request, DiagnosticCluster cluster) {
        if (cluster.primaryCategory() == DiagnosticCategory.ENVIRONMENT) return RepairStrategy.ENVIRONMENT;
        if (cluster.primaryCategory() == DiagnosticCategory.UNKNOWN || cluster.maximumSeverity() == Severity.CRITICAL)
            return RepairStrategy.HUMAN;
        if (request.policy().deterministicFixFirst() && DETERMINISTIC.contains(cluster.primaryCategory()))
            return RepairStrategy.DETERMINISTIC_RECIPE;
        return request.policy().agentFixEnabled() ? RepairStrategy.AGENT_PATCH : RepairStrategy.HUMAN;
    }

    private ModuleGate moduleGate(ModuleTarget module, Request request, ExecutionResult execution,
                                  List<Diagnostic> diagnostics, List<PatchAudit> patches, int reproducibilityRuns,
                                  Metrics metrics) {
        List<Diagnostic> moduleDiagnostics = diagnostics.stream().filter(value -> value.moduleId().equals(module.moduleId())).toList();
        List<TestResult> moduleTests = execution.tests().stream().filter(value -> value.moduleId().equals(module.moduleId())).toList();
        ModuleExecution evidence = execution.moduleExecutions().get(module.moduleId());
        if (evidence == null) return new ModuleGate(module.moduleId(), "BLOCKED", Status.BLOCKED,
                false, false, List.of("module-execution-evidence-missing"), List.of());
        boolean ra = evidence.dependencyRestorePassed() && evidence.buildModelLoaded() && evidence.compileRate() >= 0.95
                && moduleDiagnostics.stream().noneMatch(value -> value.category() == DiagnosticCategory.BUILD_CONFIGURATION
                && value.severity().ordinal() >= Severity.BLOCKING.ordinal());
        boolean rb = ra && evidence.symbolResolutionRate() >= 0.98 && evidence.typeValidationRate() >= 0.97
                && evidence.criticalStaticDiagnostics() == 0 && evidence.publicApiRegressions() == 0;
        boolean rc = rb && (module.expectedRequiredTests() == 0 || evidence.testDiscoveryPassed())
                && requiredExecutionRate(moduleTests, module.expectedRequiredTests()) >= 0.95
                && passRate(moduleTests, Phase.UNIT_TEST) >= 0.95
                && passRate(moduleTests, Phase.CONTRACT_TEST) >= 1.0
                && moduleTests.stream().noneMatch(value -> value.status() == TestStatus.UNMAPPED);
        boolean rd = rc && evidence.compileRate() == 1.0 && evidence.blockingStaticDiagnostics() == 0
                && evidence.securityRegressions() == 0 && evidence.transactionRegressions() == 0
                && evidence.serializationRegressions() == 0 && evidence.fullRegressionExecuted()
                && reproducibilityRuns >= request.policy().requiredReproducibilityRuns()
                && request.obligations().stream().noneMatch(SemanticObligation::blocking)
                && patches.stream().noneMatch(value -> value.patch().highRisk() && value.patch().agentGenerated()
                && !value.patch().humanReviewApproved());
        boolean re = rd && metrics.unitPassRate() >= 0.99 && metrics.contractPassRate() >= 0.99
                && metrics.integrationPassRate() >= 0.97 && metrics.flakyRate() <= 0.01
                && metrics.deterministicFixRate() + metrics.verifiedAgentFixRate() >= 0.95
                && metrics.unresolvedClusterRate() <= 0.01
                && metrics.sourceTargetTraceCoverage() >= 0.995;
        String gate = re ? "R-E" : rd ? "R-D" : rc ? "R-C" : rb ? "R-B" : ra ? "R-A" : "BLOCKED";
        List<String> restrictions = new ArrayList<>();
        if (!evidence.fullRegressionExecuted()) restrictions.add("full-regression-pending");
        if (moduleTests.stream().anyMatch(value -> value.status() == TestStatus.FLAKY)) restrictions.add("flaky-tests-present");
        if (request.obligations().stream().anyMatch(SemanticObligation::blocking)) restrictions.add("open-blocking-obligations");
        return new ModuleGate(module.moduleId(), gate, rd ? Status.PASSED : Status.BLOCKED, rd,
                false, restrictions, evidence.evidenceRefs());
    }

    private Metrics metrics(Request request, ExecutionResult execution, List<Diagnostic> diagnostics,
                            List<AttributionRecord> attributions, List<PatchAudit> patches, int reproducibilityRuns) {
        int expected = request.modules().stream().mapToInt(ModuleTarget::expectedRequiredTests).sum();
        long classified = diagnostics.stream().filter(value -> value.category() != DiagnosticCategory.UNKNOWN).count();
        long attributed = attributions.stream().filter(value -> value.attribution() != Attribution.UNKNOWN).count();
        long required = execution.tests().stream().filter(TestResult::required)
                .filter(value -> value.status() != TestStatus.SOURCE_EXISTING_FAILURE).count();
        long stablePassed = execution.tests().stream().filter(value -> value.required()
                && value.status() == TestStatus.PASSED).count();
        long flaky = execution.tests().stream().filter(value -> value.status() == TestStatus.FLAKY).count();
        long rolledBack = patches.stream().filter(value -> "ROLLED_BACK".equals(value.rollbackStatus())).count();
        long rollbackAvailable = patches.stream().filter(value -> value.application().rollbackAvailable()).count();
        List<PatchAudit> successful = patches.stream().filter(value -> Set.of(PatchOutcome.EFFECTIVE,
                PatchOutcome.PARTIALLY_EFFECTIVE).contains(value.outcome())).toList();
        long deterministic = successful.stream().filter(value -> !value.patch().agentGenerated()).count();
        long agent = successful.stream().filter(value -> value.patch().agentGenerated()).count();
        long unresolved = attributions.stream().filter(value -> Set.of(Attribution.MIGRATION_INTRODUCED,
                Attribution.TEST_MIGRATION, Attribution.MIXED, Attribution.UNKNOWN).contains(value.attribution())).count();
        return new Metrics(execution.dependencyRestorePassed() ? 1 : 0, execution.buildModelLoaded() ? 1 : 0,
                execution.compileRate(), ratio(classified, diagnostics.size()), diagnostics.isEmpty() ? 1 : 1,
                ratio(attributed, attributions.size()), expected == 0 ? 1 : execution.testDiscoveryPassed() ? 1 : 0,
                expected == 0 ? 1 : Math.min(1, ratio(required, expected)), ratio(stablePassed, required),
                passRate(execution.tests(), Phase.CONTRACT_TEST), passRate(execution.tests(), Phase.INTEGRATION_TEST),
                execution.tests().isEmpty() ? 0 : ratio(flaky, execution.tests().size()),
                successful.isEmpty() ? 1 : ratio(deterministic, successful.size()),
                successful.isEmpty() ? 0 : ratio(agent, successful.size()),
                attributions.isEmpty() ? 0 : ratio(unresolved, attributions.size()),
                patches.isEmpty() ? 0 : ratio(rolledBack, patches.size()),
                patches.isEmpty() ? 1 : ratio(rollbackAvailable, patches.size()),
                execution.sourceTargetTraceCoverage(), reproducibilityRuns);
    }

    static int failedRequired(ExecutionResult value) {
        return (int) value.tests().stream().filter(test -> test.required() && test.status() != TestStatus.PASSED
                && test.status() != TestStatus.SOURCE_EXISTING_FAILURE).count();
    }
    static double passRate(List<TestResult> tests, Phase layer) {
        List<TestResult> selected = tests.stream().filter(value -> value.layer() == layer && value.required())
                .filter(value -> value.status() != TestStatus.SOURCE_EXISTING_FAILURE).toList();
        if (selected.isEmpty()) return 1;
        return ratio(selected.stream().filter(value -> value.status() == TestStatus.PASSED).count(), selected.size());
    }
    private static double requiredExecutionRate(List<TestResult> tests, int expected) {
        if (expected == 0) return 1;
        long executed = tests.stream().filter(TestResult::required)
                .filter(value -> value.status() != TestStatus.UNMAPPED).count();
        return Math.min(1, ratio(executed, expected));
    }
    private static double ratio(long numerator, long denominator) { return denominator == 0 ? 1 : (double) numerator / denominator; }
    private static boolean safeRelative(String value) {
        try {
            Path path = Path.of(value).normalize();
            return !path.isAbsolute() && !path.startsWith("..") && !value.isBlank();
        } catch (RuntimeException invalid) { return false; }
    }
}
