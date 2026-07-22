package io.elmos.repair;

import io.elmos.repair.RepairLoopModels.*;

import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Batch 8 control plane. It never executes a host command or edits a target repository itself;
 * those capabilities must arrive through isolated, auditable authorities.
 */
public final class RepairLoopService {
    private final ExecutionAuthority execution;
    private final DeterministicRepairAuthority deterministicRepair;
    private final AgentRepairAuthority agentRepair;
    private final PatchInspectionAuthority patchInspection;
    private final TransactionalPatchAuthority patches;
    private final RepairExecutionPlanner planner;
    private final RepairDiagnosticProtocol diagnostics;
    private final RepairLoopPolicy policy;

    public RepairLoopService(ExecutionAuthority execution,
                             DeterministicRepairAuthority deterministicRepair,
                             AgentRepairAuthority agentRepair,
                             PatchInspectionAuthority patchInspection,
                             TransactionalPatchAuthority patches) {
        this(execution, deterministicRepair, agentRepair, patchInspection, patches,
                new RepairExecutionPlanner(), new RepairDiagnosticProtocol(), new RepairLoopPolicy());
    }

    RepairLoopService(ExecutionAuthority execution, DeterministicRepairAuthority deterministicRepair,
                      AgentRepairAuthority agentRepair, PatchInspectionAuthority patchInspection,
                      TransactionalPatchAuthority patches,
                      RepairExecutionPlanner planner, RepairDiagnosticProtocol diagnostics,
                      RepairLoopPolicy policy) {
        this.execution = Objects.requireNonNull(execution);
        this.deterministicRepair = Objects.requireNonNull(deterministicRepair);
        this.agentRepair = Objects.requireNonNull(agentRepair);
        this.patchInspection = Objects.requireNonNull(patchInspection);
        this.patches = Objects.requireNonNull(patches);
        this.planner = Objects.requireNonNull(planner);
        this.diagnostics = Objects.requireNonNull(diagnostics);
        this.policy = Objects.requireNonNull(policy);
    }

    public RunResult run(Request request) {
        List<MatrixEntry> matrix = planner.plan(request);
        List<String> preflight = preflight(request);
        if (!preflight.isEmpty()) return blockedBeforeExecution(request, matrix, preflight);

        List<RepairPlan> plans = new ArrayList<>();
        List<PatchAudit> audits = new ArrayList<>();
        List<ProgressSnapshot> progress = new ArrayList<>();
        Map<String,Diagnostic> allDiagnostics = new TreeMap<>();
        Map<String,DiagnosticCluster> allClusters = new TreeMap<>();
        Map<String,AttributionRecord> allAttributions = new TreeMap<>();
        Set<String> attemptedPatchIds = new HashSet<>();
        Set<String> attemptedPatchContents = new HashSet<>();

        String stableSnapshot = request.targetSnapshotId();
        ExecutionResult current = execute(request, matrix, stableSnapshot, ValidationScope.FULL,
                request.modules().stream().map(ModuleTarget::moduleId).toList(), true);
        CurrentAnalysis analysis = analyze(request, current);
        remember(analysis, allDiagnostics, allClusters, allAttributions);
        progress.add(progress(0, current, analysis, null));

        int rounds = 0, patchAttempts = 0, agentCalls = 0;
        long agentTokens = 0, costMicros = 0;
        int reproducibilityRuns = current.cleanEnvironment() && current.fullRegressionExecuted() ? 1 : 0;
        StopDecision stop = riskStop(request, current, stableSnapshot, rounds, patchAttempts,
                agentCalls, agentTokens, costMicros);

        while (stop == null && !greenCandidate(request, current, analysis, audits)) {
            if (rounds >= request.policy().maximumRounds()
                    || patchAttempts >= request.policy().maximumPatchAttempts()) {
                stop = stop(StopOutcome.STOPPED_BY_BUDGET, "repair-round-or-patch-budget-exhausted",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of("bounded-repair-budget-exhausted"), current.evidenceRefs());
                break;
            }
            if (noProgress(progress)) {
                stop = stop(StopOutcome.STOPPED_BY_NO_PROGRESS, "three-round-no-progress-window",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of("blocking-errors-and-required-tests-did-not-improve"), progressEvidence(progress));
                break;
            }
            if (oscillating(progress)) {
                stop = stop(StopOutcome.STOPPED_BY_OSCILLATION, "stable-snapshot-or-diagnostic-set-oscillation",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of("repair-oscillation-detected"), progressEvidence(progress));
                break;
            }

            DiagnosticCluster cluster = selectCluster(analysis);
            if (cluster == null) {
                List<String> blockers = remainingNonDiagnosticBlockers(request, current);
                StopOutcome outcome = blockers.stream().anyMatch(value -> value.contains("environment"))
                        ? StopOutcome.BLOCKED_BY_ENVIRONMENT : StopOutcome.BLOCKED_BY_SEMANTIC_GAP;
                stop = stop(outcome, "no-safely-repairable-root-cause-cluster", stableSnapshot,
                        rounds, patchAttempts, agentCalls, agentTokens, costMicros, blockers, current.evidenceRefs());
                break;
            }
            List<Diagnostic> members = members(cluster, analysis.diagnostics());
            RepairPlan plan = policy.plan(request, cluster, members, stableSnapshot, null);
            plans.add(plan);
            if (plan.strategy() == RepairStrategy.ENVIRONMENT) {
                stop = stop(StopOutcome.BLOCKED_BY_ENVIRONMENT, "environment-failure-is-not-a-code-repair-task",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of(cluster.clusterId()), diagnosticEvidence(members));
                break;
            }
            if (plan.strategy() == RepairStrategy.HUMAN) {
                stop = stop(StopOutcome.HUMAN_REVIEW_REQUIRED, "critical-or-unknown-cluster-requires-human",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of(cluster.clusterId()), diagnosticEvidence(members));
                break;
            }

            RepairContext context = new RepairContext(plan, cluster, members, stableSnapshot,
                    request.targetRepositoryPath());
            Patch patch = propose(plan, context);
            if (patch == null && plan.strategy() == RepairStrategy.DETERMINISTIC_RECIPE
                    && request.policy().agentFixEnabled()) {
                if (agentCalls >= request.policy().maximumAgentCalls()) {
                    stop = stop(StopOutcome.STOPPED_BY_BUDGET, "agent-call-budget-exhausted",
                            stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                            List.of(cluster.clusterId()), diagnosticEvidence(members));
                    break;
                }
                plan = policy.plan(request, cluster, members, stableSnapshot, RepairStrategy.AGENT_PATCH);
                plans.add(plan);
                context = new RepairContext(plan, cluster, members, stableSnapshot, request.targetRepositoryPath());
                patch = propose(plan, context);
            }
            if (patch == null) {
                stop = stop(StopOutcome.HUMAN_REVIEW_REQUIRED, "no-authority-produced-a-safe-structured-patch",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        List.of(cluster.clusterId()), diagnosticEvidence(members));
                break;
            }

            patchAttempts++;
            if (patch.agentGenerated()) agentCalls++;
            agentTokens += patch.agentTokens(); costMicros += patch.costMicros();
            PatchInspection inspection = inspect(patch, plan);
            List<String> findings = new ArrayList<>(policy.reviewPatch(request, plan, patch, stableSnapshot, inspection));
            if (!attemptedPatchIds.add(patch.patchId())) findings.add("REPEATED_PATCH_ID");
            if (!attemptedPatchContents.add(RepairLoopIds.hash(patch.modifications()))) findings.add("REPEATED_PATCH_CONTENT");
            if (agentCalls > request.policy().maximumAgentCalls()) findings.add("AGENT_CALL_BUDGET_EXCEEDED");
            if (agentTokens > request.policy().maximumAgentTokens()) findings.add("AGENT_TOKEN_BUDGET_EXCEEDED");
            if (costMicros > request.policy().maximumCostMicros()) findings.add("AGENT_COST_BUDGET_EXCEEDED");
            if (!findings.isEmpty()) {
                PatchApplication rejected = new PatchApplication(patch.patchId(), PatchState.REJECTED,
                        stableSnapshot, true, true, List.of(), findings);
                audits.add(new PatchAudit(patch, inspection, rejected, PatchOutcome.UNSAFE, inspection.evidenceRefs(),
                        "NOT_APPLIED", findings));
                stop = stop(findings.stream().anyMatch(value -> value.contains("BUDGET"))
                                ? StopOutcome.STOPPED_BY_BUDGET : StopOutcome.STOPPED_BY_RISK,
                        "patch-policy-rejected", stableSnapshot, rounds, patchAttempts, agentCalls,
                        agentTokens, costMicros, findings, diagnosticEvidence(members));
                break;
            }

            PatchApplication application = patches.apply(patch, plan);
            List<String> applicationFindings = validateApplication(application, patch, stableSnapshot);
            if (!applicationFindings.isEmpty()) {
                audits.add(new PatchAudit(patch, inspection, application, PatchOutcome.UNSAFE, application.evidenceRefs(),
                        "ROLLBACK_NOT_PROVEN", applicationFindings));
                stop = stop(StopOutcome.FAILED_SAFELY, "transactional-patch-application-not-proven",
                        stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                        applicationFindings, application.evidenceRefs());
                break;
            }

            List<String> affectedModules = cluster.affectedModules();
            ExecutionResult local = execute(request, matrix, application.targetSnapshotId(),
                    ValidationScope.AFFECTED, affectedModules, false);
            CurrentAnalysis localAnalysis = analyze(request, local);
            remember(localAnalysis, allDiagnostics, allClusters, allAttributions);
            PatchOutcome outcome;
            List<String> validationEvidence = new ArrayList<>(inspection.evidenceRefs());
            validationEvidence.addAll(local.evidenceRefs());
            if (!localPasses(local, affectedModules)) {
                outcome = local.productionResourceAccessed() || local.secretMaterialObserved()
                        ? PatchOutcome.UNSAFE : PatchOutcome.REGRESSIVE;
                PatchApplication rollback = patches.rollback(patch, stableSnapshot);
                List<String> rollbackFindings = validateRollback(rollback, patch, stableSnapshot);
                audits.add(new PatchAudit(patch, inspection, application, outcome, validationEvidence,
                        rollbackFindings.isEmpty() ? "ROLLED_BACK" : "ROLLBACK_FAILED", rollbackFindings));
                if (!rollbackFindings.isEmpty() || outcome == PatchOutcome.UNSAFE) {
                    stop = stop(StopOutcome.STOPPED_BY_RISK, "local-validation-failed-or-unsafe",
                            stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                            rollbackFindings.isEmpty() ? List.of("unsafe-local-validation") : rollbackFindings,
                            validationEvidence);
                    break;
                }
                rounds++;
                progress.add(progress(rounds, current, analysis, outcome));
                continue;
            }

            ExecutionResult full = execute(request, matrix, application.targetSnapshotId(),
                    ValidationScope.FULL, request.modules().stream().map(ModuleTarget::moduleId).toList(), true);
            CurrentAnalysis fullAnalysis = analyze(request, full);
            remember(fullAnalysis, allDiagnostics, allClusters, allAttributions);
            validationEvidence.addAll(full.evidenceRefs());
            outcome = policy.effectiveness(current, full, migrationCount(analysis), migrationCount(fullAnalysis));
            if (outcome == PatchOutcome.UNSAFE || outcome == PatchOutcome.REGRESSIVE
                    || outcome == PatchOutcome.NEUTRAL || outcome == PatchOutcome.INCONCLUSIVE) {
                PatchApplication rollback = patches.rollback(patch, stableSnapshot);
                List<String> rollbackFindings = validateRollback(rollback, patch, stableSnapshot);
                audits.add(new PatchAudit(patch, inspection, application, outcome, validationEvidence,
                        rollbackFindings.isEmpty() ? "ROLLED_BACK" : "ROLLBACK_FAILED", rollbackFindings));
                if (!rollbackFindings.isEmpty() || outcome == PatchOutcome.UNSAFE) {
                    stop = stop(StopOutcome.STOPPED_BY_RISK, "regressive-or-unsafe-patch",
                            stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                            rollbackFindings.isEmpty() ? List.of(outcome.name()) : rollbackFindings,
                            validationEvidence);
                    break;
                }
            } else {
                stableSnapshot = application.targetSnapshotId();
                current = full; analysis = fullAnalysis;
                reproducibilityRuns = current.cleanEnvironment() && current.fullRegressionExecuted() ? 1 : 0;
                audits.add(new PatchAudit(patch, inspection, application, outcome, validationEvidence,
                        "AVAILABLE", List.of()));
            }
            rounds++;
            progress.add(progress(rounds, current, analysis, outcome));
            StopDecision risk = riskStop(request, current, stableSnapshot, rounds, patchAttempts,
                    agentCalls, agentTokens, costMicros);
            if (risk != null) stop = risk;
        }

        if (stop == null && greenCandidate(request, current, analysis, audits)) {
            String signature = executionSignature(request, current);
            while (reproducibilityRuns < request.policy().requiredReproducibilityRuns()) {
                ExecutionResult repeated = execute(request, matrix, stableSnapshot, ValidationScope.FULL,
                        request.modules().stream().map(ModuleTarget::moduleId).toList(), true);
                CurrentAnalysis repeatedAnalysis = analyze(request, repeated);
                remember(repeatedAnalysis, allDiagnostics, allClusters, allAttributions);
                if (!greenCandidate(request, repeated, repeatedAnalysis, audits)
                        || !signature.equals(executionSignature(request, repeated))) {
                    current = repeated; analysis = repeatedAnalysis;
                    stop = stop(StopOutcome.STOPPED_BY_NO_PROGRESS,
                            "clean-environment-reproducibility-mismatch", stableSnapshot, rounds,
                            patchAttempts, agentCalls, agentTokens, costMicros,
                            List.of("repeated-clean-run-did-not-match"), repeated.evidenceRefs());
                    break;
                }
                current = repeated; analysis = repeatedAnalysis; reproducibilityRuns++;
            }
            if (stop == null) stop = stop(StopOutcome.CONVERGED_SUCCESS,
                    "all-build-static-test-and-reproducibility-gates-passed", stableSnapshot,
                    rounds, patchAttempts, agentCalls, agentTokens, costMicros, List.of(), current.evidenceRefs());
        }
        if (stop == null) stop = stop(StopOutcome.FAILED_SAFELY, "repair-loop-ended-without-convergence",
                stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                List.of("unclassified-terminal-state"), current.evidenceRefs());

        List<String> conformanceBlockers = stop.outcome() == StopOutcome.CONVERGED_SUCCESS
                ? List.of() : stop.blockers();
        ConformanceReport conformance = policy.conformance(request, current, analysis.diagnostics(),
                analysis.attributions(), audits, reproducibilityRuns, conformanceBlockers);
        RunManifest manifest = manifest(request, matrix, stableSnapshot, current,
                allDiagnostics.values(), allClusters.values(), audits);
        return new RunResult(manifest, matrix, List.copyOf(allDiagnostics.values()),
                List.copyOf(allClusters.values()), List.copyOf(allAttributions.values()),
                plans, audits, progress, stop, current, conformance);
    }

    private Patch propose(RepairPlan plan, RepairContext context) {
        return plan.strategy() == RepairStrategy.DETERMINISTIC_RECIPE
                ? deterministicRepair.propose(context) : agentRepair.propose(context);
    }

    private PatchInspection inspect(Patch patch, RepairPlan plan) {
        try {
            PatchInspection value = patchInspection.inspect(patch, plan);
            if (value != null) return value;
        } catch (RuntimeException ignored) {
            // Convert an unavailable or failed independent inspection into a fail-closed record.
        }
        return new PatchInspection(patch.patchId(), false, false, false, List.of(),
                false, false, false, false, false, 0, 0,
                List.of(), List.of(), List.of("PATCH_INSPECTION_AUTHORITY_FAILED"));
    }

    private ExecutionResult execute(Request request, List<MatrixEntry> matrix, String snapshot,
                                    ValidationScope scope, List<String> affectedModules, boolean clean) {
        ExecutionResult value;
        try {
            value = execution.execute(new ExecutionRequest(request.repairRunId(), snapshot, scope,
                    matrix, affectedModules, clean));
        } catch (RuntimeException failure) {
            RawDiagnostic diagnostic = new RawDiagnostic(Phase.BUILD_MODEL, "execution-authority", "EXECUTION_NOT_RUN",
                    "environment", "blocking", "execution authority failed before evidence was produced: "
                    + failure.getClass().getSimpleName(), affectedModules.getFirst(), null, null, null,
                    null, null, null, null, "authority://exception");
            return new ExecutionResult(Status.NOT_RUN, snapshot, false, false, 0, 0, 0,
                    0, 0, false, 0, List.of(), 0, 0, 0, 0, 0,
                    scope == ValidationScope.FULL, clean, false, false, null,
                    RepairLoopIds.hash(List.of("not-run", snapshot)), List.of(diagnostic), List.of(), Map.of());
        }
        if (!snapshot.equals(value.targetSnapshotId())) {
            List<RawDiagnostic> raw = new ArrayList<>(value.diagnostics());
            raw.add(new RawDiagnostic(Phase.BUILD_MODEL, "repair-loop", "SNAPSHOT_MISMATCH",
                    "environment", "critical", "execution result was not bound to the requested target snapshot",
                    affectedModules.getFirst(), null, null, null, null, null, null, null,
                    "repair-loop://snapshot-binding"));
            value = copyExecution(value, Status.BLOCKED, snapshot, raw);
        }
        List<ModuleTarget> undiscovered = new ArrayList<>();
        for (ModuleTarget module : request.modules()) {
            if (!affectedModules.contains(module.moduleId()) || module.expectedRequiredTests() == 0) continue;
            ModuleExecution moduleExecution = value.moduleExecutions().get(module.moduleId());
            if (moduleExecution == null || !moduleExecution.testDiscoveryPassed()
                    || moduleExecution.discoveredTests() == 0) undiscovered.add(module);
        }
        if (!undiscovered.isEmpty()) {
            List<RawDiagnostic> raw = new ArrayList<>(value.diagnostics());
            for (ModuleTarget module : undiscovered) raw.add(new RawDiagnostic(Phase.TEST_DISCOVERY,
                    "repair-loop", "ZERO_TEST_DISCOVERY", "test-discovery", "blocking",
                    "required test discovery produced zero usable tests", module.moduleId(),
                    null, null, null, null, null, null, null, "repair-loop://test-discovery"));
            value = copyExecution(value, Status.BLOCKED, value.targetSnapshotId(), raw);
        }
        return value;
    }

    private ExecutionResult copyExecution(ExecutionResult value, Status status, String snapshot,
                                          List<RawDiagnostic> raw) {
        return new ExecutionResult(status, snapshot, value.dependencyRestorePassed(), value.buildModelLoaded(),
                value.compileRate(), value.symbolResolutionRate(), value.typeValidationRate(),
                value.blockingStaticDiagnostics(), value.criticalStaticDiagnostics(), value.testDiscoveryPassed(),
                value.discoveredTests(), value.tests(), value.publicApiRegressions(), value.securityRegressions(),
                value.transactionRegressions(), value.serializationRegressions(), value.sourceTargetTraceCoverage(),
                value.fullRegressionExecuted(), value.cleanEnvironment(), value.productionResourceAccessed(),
                value.secretMaterialObserved(), value.sandboxRef(), value.environmentHash(), raw, value.evidenceRefs(),
                value.moduleExecutions());
    }

    private CurrentAnalysis analyze(Request request, ExecutionResult result) {
        List<Diagnostic> normalized = diagnostics.normalize(request.repairRunId(), result.diagnostics());
        List<DiagnosticCluster> clusters = diagnostics.cluster(normalized);
        List<AttributionRecord> attributions = diagnostics.attribute(clusters, normalized, request.sourceBaseline());
        return new CurrentAnalysis(normalized, clusters, attributions);
    }

    private List<String> preflight(Request request) {
        List<String> blockers = new ArrayList<>();
        if (!request.batch7Eligible()) blockers.add("batch-7-f-d-admission-missing");
        if (!request.sourceBaseline().comparable()) blockers.add("source-target-baseline-not-comparable");
        if (request.sourceBaseline().evidenceRefs().isEmpty()) blockers.add("source-baseline-evidence-missing");
        if (!Files.isDirectory(request.targetRepositoryPath(), LinkOption.NOFOLLOW_LINKS)) blockers.add("target-repository-not-a-directory");
        if (Files.isSymbolicLink(request.targetRepositoryPath())) blockers.add("target-repository-symlink-rejected");
        Set<String> moduleIds = new HashSet<>();
        if (request.modules().stream().anyMatch(value -> !moduleIds.add(value.moduleId()))) blockers.add("duplicate-target-module-id");
        request.obligations().stream().filter(value -> value.blocking() && !value.hasStrategy())
                .map(value -> "blocking-obligation-without-strategy:" + value.obligationId()).forEach(blockers::add);
        return List.copyOf(blockers);
    }

    private RunResult blockedBeforeExecution(Request request, List<MatrixEntry> matrix, List<String> blockers) {
        ExecutionResult notRun = new ExecutionResult(Status.NOT_RUN, request.targetSnapshotId(), false, false,
                0, 0, 0, 0, 0, false, 0, List.of(), 0, 0, 0, 0, 0,
                false, false, false, false, null, RepairLoopIds.hash("not-run"), List.of(), List.of(), Map.of());
        StopDecision stop = stop(blockers.stream().anyMatch(value -> value.contains("baseline"))
                        ? StopOutcome.BLOCKED_BY_SEMANTIC_GAP : StopOutcome.FAILED_SAFELY,
                "batch-8-preflight-blocked", request.targetSnapshotId(), 0, 0, 0, 0, 0,
                blockers, List.of());
        ConformanceReport conformance = policy.conformance(request, notRun, List.of(), List.of(), List.of(), 0, blockers);
        RunManifest manifest = manifest(request, matrix, request.targetSnapshotId(), notRun,
                List.of(), List.of(), List.of());
        return new RunResult(manifest, matrix, List.of(), List.of(), List.of(), List.of(),
                List.of(), List.of(), stop, notRun, conformance);
    }

    private boolean greenCandidate(Request request, ExecutionResult current, CurrentAnalysis analysis,
                                   List<PatchAudit> audits) {
        if (current.status() != Status.PASSED || !current.dependencyRestorePassed() || !current.buildModelLoaded()
                || current.compileRate() != 1.0 || current.blockingStaticDiagnostics() != 0
                || current.criticalStaticDiagnostics() != 0 || !current.fullRegressionExecuted()
                || current.publicApiRegressions() != 0 || current.securityRegressions() != 0
                || current.transactionRegressions() != 0 || current.serializationRegressions() != 0
                || current.productionResourceAccessed() || current.secretMaterialObserved()
                || current.sandboxRef() == null || current.sandboxRef().isBlank() || current.evidenceRefs().isEmpty()) return false;
        int expected = request.modules().stream().mapToInt(ModuleTarget::expectedRequiredTests).sum();
        if (expected > 0 && (!current.testDiscoveryPassed() || current.discoveredTests() == 0)) return false;
        for (ModuleTarget module : request.modules()) {
            ModuleExecution evidence = current.moduleExecutions().get(module.moduleId());
            if (evidence == null || !evidence.dependencyRestorePassed() || !evidence.buildModelLoaded()
                    || evidence.compileRate() != 1.0 || evidence.symbolResolutionRate() < 0.98
                    || evidence.typeValidationRate() < 0.97 || evidence.blockingStaticDiagnostics() != 0
                    || evidence.criticalStaticDiagnostics() != 0 || evidence.publicApiRegressions() != 0
                    || evidence.securityRegressions() != 0 || evidence.transactionRegressions() != 0
                    || evidence.serializationRegressions() != 0 || !evidence.fullRegressionExecuted()
                    || evidence.evidenceRefs().isEmpty()) return false;
            if (module.expectedRequiredTests() > 0
                    && (!evidence.testDiscoveryPassed() || evidence.discoveredTests() == 0)) return false;
        }
        if (RepairLoopPolicy.failedRequired(current) > 0) return false;
        if (request.obligations().stream().anyMatch(SemanticObligation::blocking)) return false;
        if (analysis.attributions().stream().anyMatch(value -> value.attribution() == Attribution.UNKNOWN)) return false;
        if (migrationCount(analysis) > 0) return false;
        return audits.stream().noneMatch(value -> value.patch().agentGenerated() && value.patch().highRisk()
                && !value.patch().humanReviewApproved());
    }

    private StopDecision riskStop(Request request, ExecutionResult current, String stableSnapshot,
                                  int rounds, int patchAttempts, int agentCalls,
                                  long agentTokens, long costMicros) {
        List<String> blockers = new ArrayList<>();
        if (current.productionResourceAccessed()) blockers.add("production-resource-accessed");
        if (current.secretMaterialObserved()) blockers.add("secret-material-observed");
        if (current.publicApiRegressions() > 0) blockers.add("public-api-regression");
        if (current.securityRegressions() > 0) blockers.add("security-regression");
        if (current.transactionRegressions() > 0) blockers.add("transaction-regression");
        if (current.criticalStaticDiagnostics() > 0) blockers.add("critical-static-diagnostics-present");
        if (!blockers.isEmpty()) return stop(StopOutcome.STOPPED_BY_RISK, "risk-stop-condition",
                stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                blockers, current.evidenceRefs());
        if (agentCalls > request.policy().maximumAgentCalls() || agentTokens > request.policy().maximumAgentTokens()
                || costMicros > request.policy().maximumCostMicros())
            return stop(StopOutcome.STOPPED_BY_BUDGET, "agent-resource-budget-exhausted",
                    stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                    List.of("agent-budget-exceeded"), current.evidenceRefs());
        if (current.status() == Status.NOT_RUN || current.status() == Status.INCONCLUSIVE
                || current.sandboxRef() == null || current.sandboxRef().isBlank())
            return stop(StopOutcome.BLOCKED_BY_ENVIRONMENT, "execution-authority-or-sandbox-evidence-missing",
                    stableSnapshot, rounds, patchAttempts, agentCalls, agentTokens, costMicros,
                    List.of("environment-execution-not-proven"), current.evidenceRefs());
        return null;
    }

    private List<String> validateApplication(PatchApplication application, Patch patch, String stableSnapshot) {
        List<String> findings = new ArrayList<>();
        if (!application.patchId().equals(patch.patchId())) findings.add("PATCH_APPLICATION_ID_MISMATCH");
        if (application.state() != PatchState.APPLIED) findings.add("PATCH_NOT_APPLIED");
        if (!application.atomic()) findings.add("PATCH_APPLICATION_NOT_ATOMIC");
        if (!application.rollbackAvailable()) findings.add("PATCH_ROLLBACK_UNAVAILABLE");
        if (application.targetSnapshotId() == null || application.targetSnapshotId().isBlank()
                || application.targetSnapshotId().equals(stableSnapshot)) findings.add("NEW_TARGET_SNAPSHOT_NOT_PRODUCED");
        if (application.evidenceRefs().isEmpty()) findings.add("PATCH_APPLICATION_EVIDENCE_MISSING");
        return findings;
    }

    private List<String> validateRollback(PatchApplication rollback, Patch patch, String stableSnapshot) {
        List<String> findings = new ArrayList<>();
        if (!rollback.patchId().equals(patch.patchId())) findings.add("ROLLBACK_PATCH_ID_MISMATCH");
        if (rollback.state() != PatchState.ROLLED_BACK) findings.add("PATCH_ROLLBACK_NOT_COMPLETED");
        if (!stableSnapshot.equals(rollback.targetSnapshotId())) findings.add("ROLLBACK_SNAPSHOT_MISMATCH");
        if (rollback.evidenceRefs().isEmpty()) findings.add("ROLLBACK_EVIDENCE_MISSING");
        return findings;
    }

    private boolean localPasses(ExecutionResult value, List<String> affectedModules) {
        boolean modulesPassed = affectedModules.stream().allMatch(moduleId -> {
            ModuleExecution module = value.moduleExecutions().get(moduleId);
            return module != null && module.compileRate() == 1.0 && module.blockingStaticDiagnostics() == 0
                    && module.criticalStaticDiagnostics() == 0 && !module.evidenceRefs().isEmpty();
        });
        return modulesPassed && value.status() == Status.PASSED && value.compileRate() == 1.0
                && value.criticalStaticDiagnostics() == 0 && RepairLoopPolicy.failedRequired(value) == 0
                && !value.productionResourceAccessed() && !value.secretMaterialObserved()
                && !value.evidenceRefs().isEmpty();
    }

    private DiagnosticCluster selectCluster(CurrentAnalysis analysis) {
        Map<String,Attribution> attributions = analysis.attributions().stream()
                .collect(Collectors.toMap(AttributionRecord::clusterId, AttributionRecord::attribution));
        return analysis.clusters().stream()
                .filter(value -> attributions.get(value.clusterId()) != Attribution.SOURCE_EXISTING)
                .sorted(Comparator.comparingInt((DiagnosticCluster value) -> value.maximumSeverity().ordinal()).reversed()
                        .thenComparing(DiagnosticCluster::priority).thenComparing(DiagnosticCluster::clusterId))
                .findFirst().orElse(null);
    }

    private int migrationCount(CurrentAnalysis analysis) {
        Map<String,Attribution> attributions = analysis.attributions().stream()
                .collect(Collectors.toMap(AttributionRecord::clusterId, AttributionRecord::attribution));
        return (int) analysis.clusters().stream().filter(value -> value.maximumSeverity().ordinal() >= Severity.ERROR.ordinal())
                .filter(value -> !Set.of(Attribution.SOURCE_EXISTING, Attribution.TARGET_ENVIRONMENT,
                        Attribution.DEPENDENCY_INFRASTRUCTURE).contains(attributions.get(value.clusterId()))).count();
    }

    private ProgressSnapshot progress(int round, ExecutionResult execution, CurrentAnalysis analysis,
                                      PatchOutcome outcome) {
        int passed = (int) execution.tests().stream().filter(value -> value.required()
                && value.status() == TestStatus.PASSED).count();
        return new ProgressSnapshot(round, execution.targetSnapshotId(),
                (int) analysis.diagnostics().stream().filter(value -> value.severity().ordinal() >= Severity.BLOCKING.ordinal()).count(),
                migrationCount(analysis), passed, RepairLoopPolicy.failedRequired(execution),
                RepairLoopIds.hash(analysis.diagnostics().stream().map(Diagnostic::fingerprint).sorted().toList()),
                outcome, execution.evidenceRefs());
    }

    private boolean noProgress(List<ProgressSnapshot> progress) {
        if (progress.size() < 4) return false;
        List<ProgressSnapshot> window = progress.subList(progress.size() - 4, progress.size());
        int firstBlocking = window.getFirst().blockingErrors();
        int firstPassed = window.getFirst().passedRequiredTests();
        return window.stream().skip(1).allMatch(value -> value.blockingErrors() >= firstBlocking
                && value.passedRequiredTests() <= firstPassed);
    }

    private boolean oscillating(List<ProgressSnapshot> progress) {
        Map<String,Integer> snapshots = new HashMap<>(), diagnostics = new HashMap<>();
        for (int index = 0; index < progress.size(); index++) {
            ProgressSnapshot value = progress.get(index);
            Integer snapshotSeen = snapshots.putIfAbsent(value.targetSnapshotId(), index);
            Integer diagnosticSeen = diagnostics.putIfAbsent(value.diagnosticSetHash(), index);
            if ((snapshotSeen != null && index - snapshotSeen > 1)
                    || (diagnosticSeen != null && index - diagnosticSeen > 1)) return true;
        }
        return false;
    }

    private String executionSignature(Request request, ExecutionResult value) {
        CurrentAnalysis analysis = analyze(request, value);
        return RepairLoopIds.hash(List.of(value.status(), value.dependencyRestorePassed(), value.buildModelLoaded(),
                value.compileRate(), value.symbolResolutionRate(), value.typeValidationRate(),
                value.blockingStaticDiagnostics(), value.criticalStaticDiagnostics(), value.discoveredTests(),
                value.tests().stream().map(test -> Arrays.asList(test.testId(), test.status(), test.failureFingerprint())).sorted(
                        Comparator.comparing(Object::toString)).toList(),
                analysis.diagnostics().stream().map(Diagnostic::fingerprint).sorted().toList(),
                value.publicApiRegressions(), value.securityRegressions(), value.transactionRegressions(),
                value.serializationRegressions(), value.sourceTargetTraceCoverage(), value.environmentHash(),
                value.moduleExecutions()));
    }

    private RunManifest manifest(Request request, List<MatrixEntry> matrix, String stableSnapshot,
                                 ExecutionResult finalExecution, Collection<Diagnostic> diagnostics,
                                 Collection<DiagnosticCluster> clusters, List<PatchAudit> audits) {
        List<String> commands = matrix.stream().flatMap(value -> value.commands().stream())
                .map(CommandRecord::commandId).distinct().sorted().toList();
        String environmentHash = finalExecution.environmentHash() == null || finalExecution.environmentHash().isBlank()
                ? RepairLoopIds.hash("unknown-environment") : finalExecution.environmentHash();
        return new RunManifest(request.repairRunId(), request.migrationId(), request.sourceSnapshotId(),
                request.targetSnapshotId(), stableSnapshot, environmentHash,
                matrix.stream().map(MatrixEntry::matrixId).sorted().toList(), commands,
                diagnostics.stream().map(Diagnostic::diagnosticId).sorted().toList(),
                clusters.stream().map(DiagnosticCluster::clusterId).sorted().toList(),
                audits.stream().map(value -> value.patch().patchId()).sorted().toList(),
                RepairLoopIds.hash(List.of(request.policy(), request.modules(), request.obligations())), request.observedAt());
    }

    private List<String> remainingNonDiagnosticBlockers(Request request, ExecutionResult current) {
        List<String> values = new ArrayList<>();
        request.obligations().stream().filter(SemanticObligation::blocking)
                .map(value -> "open-obligation:" + value.obligationId()).forEach(values::add);
        if (!current.dependencyRestorePassed()) values.add("dependency-restore-blocked");
        if (!current.buildModelLoaded()) values.add("build-model-blocked");
        if (!current.testDiscoveryPassed()) values.add("test-discovery-blocked");
        if (values.isEmpty()) values.add("no-repairable-cluster-with-unmet-gates");
        return List.copyOf(values);
    }

    private StopDecision stop(StopOutcome outcome, String reason, String stableSnapshot,
                              int rounds, int patchAttempts, int agentCalls,
                              long agentTokens, long costMicros, List<String> blockers,
                              List<String> evidence) {
        return new StopDecision(outcome, reason, stableSnapshot, rounds, patchAttempts, agentCalls,
                agentTokens, costMicros, blockers, evidence);
    }

    private void remember(CurrentAnalysis analysis, Map<String,Diagnostic> diagnostics,
                          Map<String,DiagnosticCluster> clusters,
                          Map<String,AttributionRecord> attributions) {
        analysis.diagnostics().forEach(value -> diagnostics.put(value.diagnosticId(), value));
        analysis.clusters().forEach(value -> clusters.put(value.clusterId(), value));
        analysis.attributions().forEach(value -> attributions.put(value.clusterId(), value));
    }

    private static List<Diagnostic> members(DiagnosticCluster cluster, List<Diagnostic> diagnostics) {
        Set<String> ids = Set.copyOf(cluster.diagnosticIds());
        return diagnostics.stream().filter(value -> ids.contains(value.diagnosticId())).toList();
    }
    private static List<String> diagnosticEvidence(List<Diagnostic> values) {
        return values.stream().map(Diagnostic::rawOutputRef).distinct().sorted().toList();
    }
    private static List<String> progressEvidence(List<ProgressSnapshot> values) {
        return values.stream().flatMap(value -> value.evidenceRefs().stream()).distinct().sorted().toList();
    }

    private record CurrentAnalysis(List<Diagnostic> diagnostics, List<DiagnosticCluster> clusters,
                                   List<AttributionRecord> attributions) {}
}
