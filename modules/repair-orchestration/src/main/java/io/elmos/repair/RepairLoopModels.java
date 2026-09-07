package io.elmos.repair;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Batch 8 build, diagnostic, test and bounded-repair contracts. */
public final class RepairLoopModels {
    private RepairLoopModels() {}

    public enum Language { JAVA, PYTHON, CSHARP, TYPESCRIPT, JAVASCRIPT }
    public enum Phase { RESTORE, BUILD_MODEL, COMPILE, STATIC_ANALYSIS, TEST_DISCOVERY,
        UNIT_TEST, CONTRACT_TEST, INTEGRATION_TEST, STARTUP_TEST, FULL_REGRESSION }
    public enum Status { PASSED, FAILED, BLOCKED, NOT_RUN, INCONCLUSIVE }
    public enum DiagnosticCategory { ENVIRONMENT, DEPENDENCY, BUILD_CONFIGURATION, SYNTAX, SYMBOL,
        TYPE, GENERIC, NULLABILITY, API_MAPPING, FRAMEWORK, STATIC_ANALYSIS, TEST_DISCOVERY,
        TEST_COMPILATION, TEST_FIXTURE, TEST_ASSERTION, RUNTIME, DATABASE, MESSAGING,
        SECURITY, PERFORMANCE, FLAKY, SOURCE_BASELINE, UNKNOWN }
    public enum Severity { INFO, WARNING, ERROR, BLOCKING, CRITICAL }
    public enum Attribution { SOURCE_EXISTING, MIGRATION_INTRODUCED, TARGET_ENVIRONMENT,
        DEPENDENCY_INFRASTRUCTURE, TEST_MIGRATION, TEST_FLAKY, UNKNOWN, MIXED }
    public enum TestStatus { PASSED, FAILED, FLAKY, SKIPPED_WITH_REASON, SOURCE_EXISTING_FAILURE,
        MANUAL_REQUIRED, UNMAPPED }
    public enum RepairStrategy { ENVIRONMENT, DETERMINISTIC_RECIPE, AGENT_PATCH, HUMAN }
    public enum PatchState { PREPARED, APPLIED, REJECTED, ROLLED_BACK, CONFLICTED }
    public enum PatchOutcome { EFFECTIVE, PARTIALLY_EFFECTIVE, NEUTRAL, REGRESSIVE, UNSAFE, INCONCLUSIVE }
    public enum ValidationScope { AFFECTED, FULL }
    public enum StopOutcome { CONVERGED_SUCCESS, CONVERGED_WITH_WARNINGS, PARTIALLY_CONVERGED,
        BLOCKED_BY_SEMANTIC_GAP, BLOCKED_BY_ENVIRONMENT, STOPPED_BY_BUDGET,
        STOPPED_BY_OSCILLATION, STOPPED_BY_NO_PROGRESS, STOPPED_BY_RISK,
        HUMAN_REVIEW_REQUIRED, FAILED_SAFELY }

    public record Request(Path artifactWorkspace, String repairRunId, String migrationId,
                          String sourceSnapshotId, String targetSnapshotId, Path targetRepositoryPath,
                          boolean batch7Eligible, SourceBaseline sourceBaseline,
                          List<ModuleTarget> modules, List<SemanticObligation> obligations,
                          Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(targetRepositoryPath, "targetRepositoryPath");
            text(repairRunId, "repairRunId"); text(migrationId, "migrationId");
            text(sourceSnapshotId, "sourceSnapshotId"); text(targetSnapshotId, "targetSnapshotId");
            required(sourceBaseline, "sourceBaseline"); required(policy, "policy"); required(observedAt, "observedAt");
            modules = copy(modules); obligations = copy(obligations);
            if (modules.isEmpty()) throw new IllegalArgumentException("modules are required");
            if (artifactWorkspace.toAbsolutePath().normalize().equals(targetRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("artifact workspace must be outside target repository");
        }
    }

    public record SourceBaseline(boolean comparable, Set<String> diagnosticFingerprints,
                                 Map<String,TestStatus> sourceTests, List<String> evidenceRefs) {
        public SourceBaseline {
            diagnosticFingerprints = set(diagnosticFingerprints); sourceTests = map(sourceTests);
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ModuleTarget(String moduleId, Language language, String runtimeVersion,
                               String targetFramework, String buildSystem, String buildToolVersion,
                               List<String> deploymentPlatforms, boolean highRisk,
                               int expectedRequiredTests) {
        public ModuleTarget {
            text(moduleId, "moduleId"); required(language, "language"); text(runtimeVersion, "runtimeVersion");
            text(buildSystem, "buildSystem"); text(buildToolVersion, "buildToolVersion");
            deploymentPlatforms = copy(deploymentPlatforms);
            if (deploymentPlatforms.isEmpty()) throw new IllegalArgumentException("deployment platform is required");
            if (expectedRequiredTests < 0) throw new IllegalArgumentException("expectedRequiredTests cannot be negative");
        }
    }

    public record SemanticObligation(String obligationId, boolean blocking, String strategy, String owner) {
        public SemanticObligation { text(obligationId, "obligationId"); }
        public boolean hasStrategy() { return strategy != null && !strategy.isBlank(); }
    }

    public record Policy(boolean deterministicFixFirst, boolean agentFixEnabled,
                         Set<String> approvedPackages, boolean warningsBlocking,
                         int maximumRounds, int maximumPatchAttempts, int maximumAgentCalls,
                         long maximumAgentTokens, long maximumCostMicros, int maximumWallSeconds,
                         int maximumFilesPerPatch, int maximumLinesPerPatch,
                         int requiredReproducibilityRuns) {
        public Policy {
            approvedPackages = set(approvedPackages);
            if (maximumRounds < 1 || maximumPatchAttempts < 1 || maximumAgentCalls < 0
                    || maximumAgentTokens < 0 || maximumCostMicros < 0 || maximumWallSeconds < 1
                    || maximumFilesPerPatch < 1 || maximumLinesPerPatch < 1
                    || requiredReproducibilityRuns < 2)
                throw new IllegalArgumentException("repair policy limits are invalid");
        }
    }

    public record MatrixEntry(String matrixId, String moduleId, Language language,
                              String runtimeVersion, String platform, String configuration,
                              List<Phase> phases, List<CommandRecord> commands, String reductionReason) {
        public MatrixEntry {
            text(matrixId, "matrixId"); text(moduleId, "moduleId"); phases = copy(phases);
            commands = copy(commands); text(reductionReason, "reductionReason");
        }
    }

    public record CommandRecord(String commandId, Phase phase, String workingDirectory,
                                String executable, List<String> arguments, Map<String,String> environment,
                                int timeoutSeconds, List<String> expectedReports, String toolVersion) {
        public CommandRecord {
            text(commandId, "commandId"); required(phase, "phase"); text(workingDirectory, "workingDirectory");
            text(executable, "executable"); arguments = copy(arguments); environment = map(environment);
            expectedReports = copy(expectedReports); text(toolVersion, "toolVersion");
            if (timeoutSeconds < 1) throw new IllegalArgumentException("command timeout must be positive");
        }
    }

    public record ExecutionRequest(String repairRunId, String targetSnapshotId,
                                   ValidationScope scope, List<MatrixEntry> matrix,
                                   List<String> affectedModules, boolean cleanEnvironment) {
        public ExecutionRequest {
            text(repairRunId, "repairRunId"); text(targetSnapshotId, "targetSnapshotId");
            required(scope, "scope"); matrix = copy(matrix); affectedModules = copy(affectedModules);
        }
    }

    public record RawDiagnostic(Phase phase, String tool, String nativeCode, String categoryHint,
                                String severityHint, String message, String moduleId, String file,
                                Integer line, Integer column, String symbol, String dependency,
                                String targetDeclarationId, String sourceTestId, String rawOutputRef) {
        public RawDiagnostic {
            required(phase, "phase"); text(tool, "tool"); text(message, "message");
            text(moduleId, "moduleId"); text(rawOutputRef, "rawOutputRef");
        }
    }

    public record Diagnostic(String diagnosticId, String repairRunId, Phase phase, String tool,
                             String nativeCode, DiagnosticCategory category, Severity severity,
                             String message, String moduleId, String file, Integer line, Integer column,
                             String normalizedSymbol, String dependency, String targetDeclarationId,
                             String sourceTestId, String rawOutputRef, String fingerprint, double confidence) {
        public Diagnostic {
            text(diagnosticId, "diagnosticId"); text(repairRunId, "repairRunId");
            required(phase, "phase"); required(category, "category"); required(severity, "severity");
            text(message, "message"); text(moduleId, "moduleId"); text(rawOutputRef, "rawOutputRef");
            digest(fingerprint, "fingerprint"); rate(confidence, "confidence");
        }
    }

    public record TestResult(String testId, String moduleId, String sourceTestId, Phase layer, TestStatus status,
                             String failureFingerprint, boolean required, String reason,
                             List<String> evidenceRefs) {
        public TestResult {
            text(testId, "testId"); text(moduleId, "moduleId");
            RepairLoopModels.required(layer, "layer"); RepairLoopModels.required(status, "status");
            evidenceRefs = copy(evidenceRefs);
            if (status == TestStatus.SKIPPED_WITH_REASON && (reason == null || reason.isBlank()))
                throw new IllegalArgumentException("skipped test requires a reason");
        }
    }

    public record ModuleExecution(String moduleId, boolean dependencyRestorePassed,
                                  boolean buildModelLoaded, double compileRate,
                                  double symbolResolutionRate, double typeValidationRate,
                                  int blockingStaticDiagnostics, int criticalStaticDiagnostics,
                                  boolean testDiscoveryPassed, int discoveredTests,
                                  int publicApiRegressions, int securityRegressions,
                                  int transactionRegressions, int serializationRegressions,
                                  boolean fullRegressionExecuted, List<String> evidenceRefs) {
        public ModuleExecution {
            text(moduleId, "moduleId"); rate(compileRate, "compileRate");
            rate(symbolResolutionRate, "symbolResolutionRate"); rate(typeValidationRate, "typeValidationRate");
            if (blockingStaticDiagnostics < 0 || criticalStaticDiagnostics < 0 || discoveredTests < 0
                    || publicApiRegressions < 0 || securityRegressions < 0
                    || transactionRegressions < 0 || serializationRegressions < 0)
                throw new IllegalArgumentException("module execution counts cannot be negative");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ExecutionResult(Status status, String targetSnapshotId, boolean dependencyRestorePassed,
                                  boolean buildModelLoaded, double compileRate, double symbolResolutionRate,
                                  double typeValidationRate, int blockingStaticDiagnostics,
                                  int criticalStaticDiagnostics, boolean testDiscoveryPassed,
                                  int discoveredTests, List<TestResult> tests,
                                  int publicApiRegressions, int securityRegressions,
                                  int transactionRegressions, int serializationRegressions,
                                  double sourceTargetTraceCoverage, boolean fullRegressionExecuted,
                                  boolean cleanEnvironment, boolean productionResourceAccessed,
                                  boolean secretMaterialObserved, String sandboxRef,
                                  String environmentHash, List<RawDiagnostic> diagnostics,
                                  List<String> evidenceRefs, Map<String,ModuleExecution> moduleExecutions) {
        public ExecutionResult {
            required(status, "status"); text(targetSnapshotId, "targetSnapshotId");
            rate(compileRate, "compileRate"); rate(symbolResolutionRate, "symbolResolutionRate");
            rate(typeValidationRate, "typeValidationRate"); rate(sourceTargetTraceCoverage, "sourceTargetTraceCoverage");
            if (blockingStaticDiagnostics < 0 || criticalStaticDiagnostics < 0 || discoveredTests < 0
                    || publicApiRegressions < 0 || securityRegressions < 0 || transactionRegressions < 0
                    || serializationRegressions < 0) throw new IllegalArgumentException("execution counts cannot be negative");
            tests = copy(tests); diagnostics = copy(diagnostics); evidenceRefs = copy(evidenceRefs);
            moduleExecutions = map(moduleExecutions);
            if (moduleExecutions.entrySet().stream().anyMatch(entry -> !entry.getKey().equals(entry.getValue().moduleId())))
                throw new IllegalArgumentException("module execution key must match moduleId");
            digest(environmentHash, "environmentHash");
        }
    }

    public record DiagnosticCluster(String clusterId, DiagnosticCategory primaryCategory,
                                    List<String> diagnosticIds, List<String> suspectedRootEntities,
                                    List<String> affectedModules, List<String> causalChain,
                                    double confidence, String estimatedFixScope, String priority,
                                    Severity maximumSeverity) {
        public DiagnosticCluster {
            text(clusterId, "clusterId"); required(primaryCategory, "primaryCategory");
            diagnosticIds = copy(diagnosticIds); suspectedRootEntities = copy(suspectedRootEntities);
            affectedModules = copy(affectedModules); causalChain = copy(causalChain);
            rate(confidence, "confidence"); text(estimatedFixScope, "estimatedFixScope");
            text(priority, "priority"); required(maximumSeverity, "maximumSeverity");
        }
    }

    public record AttributionRecord(String clusterId, Attribution attribution,
                                    List<String> evidence, double confidence) {
        public AttributionRecord {
            text(clusterId, "clusterId"); required(attribution, "attribution");
            evidence = copy(evidence); rate(confidence, "confidence");
        }
    }

    public record RepairPlan(String planId, String clusterId, RepairStrategy strategy, String ruleId,
                             List<String> allowedFiles, List<String> allowedDeclarations,
                             List<String> invariants, List<String> localValidations,
                             List<String> regressionValidations, String rollbackSnapshotId,
                             boolean humanReviewRequired) {
        public RepairPlan {
            text(planId, "planId"); text(clusterId, "clusterId"); required(strategy, "strategy");
            allowedFiles = copy(allowedFiles); allowedDeclarations = copy(allowedDeclarations);
            invariants = copy(invariants); localValidations = copy(localValidations);
            regressionValidations = copy(regressionValidations); text(rollbackSnapshotId, "rollbackSnapshotId");
        }
    }

    public record RepairContext(RepairPlan plan, DiagnosticCluster cluster,
                                List<Diagnostic> diagnostics, String targetSnapshotId,
                                Path targetRepositoryPath) {
        public RepairContext { diagnostics = copy(diagnostics); }
    }

    public record Modification(String file, String targetDeclarationId, String operation,
                               String beforeHash, String afterHash, int linesChanged,
                               boolean touchesManualRegion, boolean publicApiChanged,
                               boolean securityBehaviorChanged, boolean transactionBehaviorChanged,
                               boolean deletesTest, boolean weakensAssertion,
                               int suppressDelta, int dynamicOrAnyDelta,
                               List<String> dependenciesAdded) {
        public Modification {
            text(file, "file"); text(operation, "operation"); digest(beforeHash, "beforeHash");
            digest(afterHash, "afterHash"); dependenciesAdded = copy(dependenciesAdded);
            if (linesChanged < 0 || suppressDelta < 0 || dynamicOrAnyDelta < 0)
                throw new IllegalArgumentException("modification counters cannot be negative");
        }
    }

    public record Patch(String patchId, String clusterId, String planId, String baseSnapshotId,
                        List<Modification> modifications, boolean agentGenerated,
                        boolean highRisk, boolean humanReviewApproved, String reviewEvidenceRef,
                        long agentTokens, long costMicros, List<String> expectedDiagnosticsRemoved,
                        String patchArtifactRef) {
        public Patch {
            text(patchId, "patchId"); text(clusterId, "clusterId"); text(planId, "planId");
            text(baseSnapshotId, "baseSnapshotId"); modifications = copy(modifications);
            expectedDiagnosticsRemoved = copy(expectedDiagnosticsRemoved); text(patchArtifactRef, "patchArtifactRef");
            if (modifications.isEmpty()) throw new IllegalArgumentException("patch must contain modifications");
            if (agentTokens < 0 || costMicros < 0) throw new IllegalArgumentException("patch usage cannot be negative");
        }
    }

    public record PatchApplication(String patchId, PatchState state, String targetSnapshotId,
                                   boolean atomic, boolean rollbackAvailable,
                                   List<String> evidenceRefs, List<String> diagnostics) {
        public PatchApplication {
            text(patchId, "patchId"); required(state, "state"); evidenceRefs = copy(evidenceRefs);
            diagnostics = copy(diagnostics);
        }
    }

    public record PatchInspection(String patchId, boolean parsed, boolean scopeVerified,
                                  boolean generatedManualBoundaryVerified,
                                  List<String> actualChangedFiles, boolean publicApiChanged,
                                  boolean securityBehaviorChanged, boolean transactionBehaviorChanged,
                                  boolean testsDeleted, boolean assertionsWeakened,
                                  int suppressDelta, int dynamicOrAnyDelta,
                                  List<String> dependenciesAdded, List<String> evidenceRefs,
                                  List<String> findings) {
        public PatchInspection {
            text(patchId, "patchId"); actualChangedFiles = copy(actualChangedFiles);
            dependenciesAdded = copy(dependenciesAdded); evidenceRefs = copy(evidenceRefs); findings = copy(findings);
            if (suppressDelta < 0 || dynamicOrAnyDelta < 0)
                throw new IllegalArgumentException("inspection counters cannot be negative");
        }
    }

    public record PatchAudit(Patch patch, PatchInspection inspection, PatchApplication application, PatchOutcome outcome,
                             List<String> validationEvidenceRefs, String rollbackStatus,
                             List<String> policyFindings) {
        public PatchAudit {
            required(outcome, "outcome"); validationEvidenceRefs = copy(validationEvidenceRefs);
            policyFindings = copy(policyFindings);
        }
    }

    public record ProgressSnapshot(int round, String targetSnapshotId, int blockingErrors,
                                   int migrationRegressions, int passedRequiredTests,
                                   int failedRequiredTests, String diagnosticSetHash,
                                   PatchOutcome patchOutcome, List<String> evidenceRefs) {
        public ProgressSnapshot { digest(diagnosticSetHash, "diagnosticSetHash"); evidenceRefs = copy(evidenceRefs); }
    }

    public record StopDecision(StopOutcome outcome, String reason, String stableSnapshotId,
                               int rounds, int patchAttempts, int agentCalls,
                               long agentTokens, long costMicros, List<String> blockers,
                               List<String> evidenceRefs) {
        public StopDecision {
            required(outcome, "outcome"); text(reason, "reason"); text(stableSnapshotId, "stableSnapshotId");
            blockers = copy(blockers); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ModuleGate(String targetModuleId, String gate, Status status,
                             boolean eligibleForBehavioralEquivalence,
                             boolean eligibleForProductionValidation,
                             List<String> restrictions, List<String> evidenceRefs) {
        public ModuleGate {
            text(targetModuleId, "targetModuleId"); text(gate, "gate"); required(status, "status");
            restrictions = copy(restrictions); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record Metrics(double dependencyRestoreRate, double projectLoadRate, double compileRate,
                          double diagnosticClassificationRate, double clusterCoverageRate,
                          double attributionRate, double testDiscoveryRate,
                          double requiredTestExecutionRate, double unitPassRate,
                          double contractPassRate, double integrationPassRate,
                          double flakyRate, double deterministicFixRate,
                          double verifiedAgentFixRate, double unresolvedClusterRate,
                          double patchRollbackRate, double patchRollbackAvailabilityRate,
                          double sourceTargetTraceCoverage, int reproducibilityRunsPassed) {}

    public record ConformanceReport(int batch, Status status, String repairRunId,
                                    List<ModuleGate> modules, Metrics metrics,
                                    List<String> blockingErrors, List<String> openObligations,
                                    boolean eligibleForBatch9) {
        public ConformanceReport {
            if (batch != 8) throw new IllegalArgumentException("conformance batch must be 8");
            modules = copy(modules); blockingErrors = copy(blockingErrors); openObligations = copy(openObligations);
        }
    }

    public record RunManifest(String repairRunId, String migrationId, String sourceSnapshotId,
                              String targetSnapshotBefore, String targetSnapshotAfter,
                              String environmentHash, List<String> matrixIds,
                              List<String> commandIds, List<String> diagnosticIds,
                              List<String> clusterIds, List<String> patchIds,
                              String configurationHash, Instant createdAt) {
        public RunManifest {
            matrixIds = copy(matrixIds); commandIds = copy(commandIds); diagnosticIds = copy(diagnosticIds);
            clusterIds = copy(clusterIds); patchIds = copy(patchIds); digest(configurationHash, "configurationHash");
            digest(environmentHash, "environmentHash");
        }
    }

    public record RunResult(RunManifest manifest, List<MatrixEntry> matrix,
                            List<Diagnostic> diagnostics, List<DiagnosticCluster> clusters,
                            List<AttributionRecord> attributions, List<RepairPlan> plans,
                            List<PatchAudit> patches, List<ProgressSnapshot> progress,
                            StopDecision stopDecision, ExecutionResult finalExecution,
                            ConformanceReport conformance) {
        public RunResult {
            matrix = copy(matrix); diagnostics = copy(diagnostics); clusters = copy(clusters);
            attributions = copy(attributions); plans = copy(plans); patches = copy(patches); progress = copy(progress);
        }
    }

    @FunctionalInterface public interface ExecutionAuthority { ExecutionResult execute(ExecutionRequest request); }
    @FunctionalInterface public interface DeterministicRepairAuthority { Patch propose(RepairContext context); }
    @FunctionalInterface public interface AgentRepairAuthority { Patch propose(RepairContext context); }
    @FunctionalInterface public interface PatchInspectionAuthority { PatchInspection inspect(Patch patch, RepairPlan plan); }
    public interface TransactionalPatchAuthority {
        PatchApplication apply(Patch patch, RepairPlan plan);
        PatchApplication rollback(Patch patch, String stableSnapshotId);
    }

    private static void text(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    private static void required(Object value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " is required");
    }
    private static void digest(String value, String field) {
        if (value == null || !value.matches("[0-9a-f]{64}"))
            throw new IllegalArgumentException(field + " must be a raw sha256 digest");
    }
    private static void rate(double value, String field) {
        if (Double.isNaN(value) || value < 0 || value > 1) throw new IllegalArgumentException(field + " must be in [0,1]");
    }
    private static <T> List<T> copy(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
    private static <T> Set<T> set(Set<T> values) { return values == null ? Set.of() : Set.copyOf(values); }
    private static <K,V> Map<K,V> map(Map<K,V> values) { return values == null ? Map.of() : Map.copyOf(values); }
}
