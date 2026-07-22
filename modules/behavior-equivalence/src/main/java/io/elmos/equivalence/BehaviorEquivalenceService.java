package io.elmos.equivalence;

import io.elmos.equivalence.BehaviorEquivalenceModels.*;
import io.elmos.equivalence.BehaviorEquivalencePorts.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.function.Predicate;
import java.util.stream.Collectors;

/** Fail-closed Batch 9 orchestration; this class never executes customer code or production traffic. */
public final class BehaviorEquivalenceService {
    private static final Set<ObservationType> STATE_EFFECTS = Set.of(
            ObservationType.DATABASE_STATE, ObservationType.DATABASE_WRITE_TRACE,
            ObservationType.MESSAGE_EVENT, ObservationType.FILE_OUTPUT,
            ObservationType.OBJECT_STORAGE_OUTPUT, ObservationType.CACHE_STATE,
            ObservationType.AUDIT, ObservationType.EXTERNAL_CALL);
    private static final Set<ObservationType> FILE_EFFECTS = Set.of(
            ObservationType.FILE_OUTPUT, ObservationType.OBJECT_STORAGE_OUTPUT);
    private final DualRuntimeAuthority runtimes;
    private final DifferentialExecutionAuthority executions;
    private final EquivalenceOracleAuthority oracles;
    private final Batch8RepairFeedbackAuthority repairFeedback;

    public BehaviorEquivalenceService(DualRuntimeAuthority runtimes,
                                      DifferentialExecutionAuthority executions,
                                      EquivalenceOracleAuthority oracles,
                                      Batch8RepairFeedbackAuthority repairFeedback) {
        this.runtimes = Objects.requireNonNull(runtimes);
        this.executions = Objects.requireNonNull(executions);
        this.oracles = Objects.requireNonNull(oracles);
        this.repairFeedback = Objects.requireNonNull(repairFeedback);
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        List<String> admission = admissionBlockers(request);
        if (!admission.isEmpty()) return blockedOutcome(request, null, List.of(), List.of(), admission, RunStatus.BLOCKED);

        EnvironmentAlignment alignment;
        try {
            alignment = Objects.requireNonNull(runtimes.prepare(request), "environment alignment");
        } catch (RuntimeException failure) {
            return blockedOutcome(request, null, List.of(), List.of(),
                    List.of("dual-runtime-prepare-failed:" + failure.getClass().getSimpleName()), RunStatus.NOT_COMPARABLE);
        }

        List<CleanRun> cleanRuns = new ArrayList<>();
        List<Comparison> comparisons = new ArrayList<>();
        List<String> executionBlockers = new ArrayList<>();
        if (!alignment.comparable()) {
            executionBlockers.add("source-target-environment-not-comparable");
            alignment.differences().stream().map(value -> "alignment:" + value).forEach(executionBlockers::add);
            try { runtimes.cleanup(request, alignment); }
            catch (RuntimeException failure) { executionBlockers.add("dual-runtime-cleanup-failed:" + failure.getClass().getSimpleName()); }
            return blockedOutcome(request, alignment, cleanRuns, comparisons, executionBlockers, RunStatus.NOT_COMPARABLE);
        }
        try {
            for (int index = 1; index <= request.policy().requiredCleanRuns(); index++) {
                CleanRun run;
                try {
                    run = Objects.requireNonNull(executions.execute(request, alignment, index), "clean run");
                } catch (RuntimeException failure) {
                    executionBlockers.add("differential-execution-failed:run-" + index + ":" + failure.getClass().getSimpleName());
                    break;
                }
                cleanRuns.add(run);
                compareRun(request, run, comparisons, executionBlockers);
            }
        } finally {
            try { runtimes.cleanup(request, alignment); }
            catch (RuntimeException failure) { executionBlockers.add("dual-runtime-cleanup-failed:" + failure.getClass().getSimpleName()); }
        }

        comparisons = markFlaky(comparisons);
        List<RepairFeedback> feedback = buildRepairFeedback(request, comparisons);
        for (RepairFeedback value : feedback) {
            try { repairFeedback.submit(request, value); }
            catch (RuntimeException failure) {
                executionBlockers.add("batch8-repair-feedback-failed:" + value.clusterId() + ":" + failure.getClass().getSimpleName());
            }
        }
        return conformance(request, alignment, cleanRuns, comparisons, feedback, executionBlockers);
    }

    private List<String> admissionBlockers(Request request) {
        List<String> blockers = new ArrayList<>();
        if (!request.batch8Eligible()) blockers.add("batch-8-r-d-admission-missing");
        if (request.scenarios().size() > request.policy().maximumScenarios()) blockers.add("scenario-budget-exceeded");
        if (request.sourceRuntime().productionAccessAllowed() || request.targetRuntime().productionAccessAllowed())
            blockers.add("production-access-declared");
        if (request.sourceRuntime().evidenceRefs().isEmpty() || request.targetRuntime().evidenceRefs().isEmpty())
            blockers.add("runtime-evidence-missing");
        Set<String> sourceResources = new HashSet<>(request.sourceRuntime().mutableResources().values());
        sourceResources.retainAll(new HashSet<>(request.targetRuntime().mutableResources().values()));
        sourceResources.stream().sorted().map(value -> "shared-mutable-resource:" + value).forEach(blockers::add);

        Set<String> moduleIds = ids(request.modules(), ModuleScope::moduleId, "module", blockers);
        Set<String> scenarioIds = ids(request.scenarios(), Scenario::scenarioId, "scenario", blockers);
        ids(request.observationPoints(), ObservationPoint::pointId, "observation-point", blockers);
        ids(request.normalizationRules(), CanonicalizationRule::ruleId, "normalization-rule", blockers);
        ids(request.tolerances(), Tolerance::toleranceId, "tolerance", blockers);
        ids(request.approvedChanges(), ApprovedChange::changeId, "approved-change", blockers);
        ids(request.goldenMasters(), GoldenMaster::goldenId, "golden", blockers);

        Map<String,Set<ObservationType>> pointsByModule = request.observationPoints().stream()
                .filter(ObservationPoint::required)
                .collect(Collectors.groupingBy(ObservationPoint::moduleId,
                        Collectors.mapping(ObservationPoint::type, Collectors.toSet())));
        Map<String,GoldenMaster> goldenByScenario = request.goldenMasters().stream()
                .collect(Collectors.toMap(GoldenMaster::scenarioId, value -> value, (left, right) -> left));
        for (Scenario scenario : request.scenarios()) {
            if (!moduleIds.contains(scenario.moduleId())) blockers.add("scenario-module-unknown:" + scenario.scenarioId());
            Set<ObservationType> registered = pointsByModule.getOrDefault(scenario.moduleId(), Set.of());
            scenario.expectedObservations().stream().filter(type -> !registered.contains(type))
                    .map(type -> "critical-observation-point-missing:" + scenario.scenarioId() + ":" + type)
                    .forEach(blockers::add);
            if (scenario.critical()) {
                GoldenMaster golden = goldenByScenario.get(scenario.scenarioId());
                if (golden == null || !golden.trusted()) blockers.add("trusted-golden-missing:" + scenario.scenarioId());
                else {
                    if (!golden.sourceSnapshotId().equals(request.sourceSnapshotId())) blockers.add("golden-source-snapshot-mismatch:" + scenario.scenarioId());
                    if (!golden.initialStateHash().equals(scenario.initialStateHash())) blockers.add("golden-initial-state-mismatch:" + scenario.scenarioId());
                }
            }
        }
        for (SemanticObligation obligation : request.obligations()) {
            if (!moduleIds.contains(obligation.moduleId())) blockers.add("obligation-module-unknown:" + obligation.obligationId());
            if (obligation.blocking() && !obligation.resolved()) {
                if (obligation.scenarioIds().isEmpty()) blockers.add("blocking-obligation-without-scenario:" + obligation.obligationId());
                obligation.scenarioIds().stream().filter(id -> !scenarioIds.contains(id))
                        .map(id -> "obligation-scenario-unknown:" + obligation.obligationId() + ":" + id).forEach(blockers::add);
            }
        }
        for (CanonicalizationRule rule : request.normalizationRules()) {
            String lower = (rule.fieldPath() + " " + rule.transformation()).toLowerCase(Locale.ROOT);
            if (!rule.semanticImpactNone()) blockers.add("normalization-semantic-impact-not-none:" + rule.ruleId());
            if (containsAny(lower, "amount", "decimal", "permission", "authorization", "tenant", "http.status",
                    "error.code", "row.count", "message.count", "transaction", "audit-event"))
                blockers.add("normalization-protected-field:" + rule.ruleId());
            if (containsAny(lower, "ignore-all", "drop-field", "remove-record", "sort-all-collections"))
                blockers.add("normalization-rule-too-broad:" + rule.ruleId());
        }
        Map<String,Scenario> scenarioById = request.scenarios().stream().collect(Collectors.toMap(Scenario::scenarioId, value -> value));
        for (Tolerance tolerance : request.tolerances()) {
            Scenario scenario = scenarioById.get(tolerance.scenarioId());
            if (scenario == null) blockers.add("tolerance-scenario-unknown:" + tolerance.toleranceId());
            else if (scenario.highRisk()) blockers.add("tolerance-forbidden-high-risk-scenario:" + tolerance.toleranceId());
            if (!tolerance.expiresAt().isAfter(request.observedAt())) blockers.add("tolerance-expired:" + tolerance.toleranceId());
            String lower = tolerance.fieldPath().toLowerCase(Locale.ROOT);
            if (containsAny(lower, "amount", "decimal", "permission", "tenant", "status", "row-count", "message-count", "transaction", "audit"))
                blockers.add("tolerance-protected-field:" + tolerance.toleranceId());
        }
        for (GoldenMaster golden : request.goldenMasters()) {
            if (!scenarioIds.contains(golden.scenarioId())) blockers.add("golden-scenario-unknown:" + golden.goldenId());
            if (!golden.sourceSnapshotId().equals(request.sourceSnapshotId())) blockers.add("golden-source-snapshot-mismatch:" + golden.scenarioId());
        }
        return blockers.stream().distinct().sorted().toList();
    }

    private void compareRun(Request request, CleanRun run, List<Comparison> comparisons, List<String> blockers) {
        if (run.runIndex() < 1 || run.runIndex() > request.policy().requiredCleanRuns())
            blockers.add("clean-run-index-invalid:" + run.runIndex());
        Map<String,List<ScenarioExecution>> executionsByScenario = run.scenarios().stream()
                .collect(Collectors.groupingBy(ScenarioExecution::scenarioId));
        for (Scenario scenario : request.scenarios()) {
            List<ScenarioExecution> matching = executionsByScenario.getOrDefault(scenario.scenarioId(), List.of());
            if (matching.size() != 1) {
                blockers.add("scenario-execution-cardinality:" + scenario.scenarioId() + ":" + matching.size());
                scenario.expectedObservations().forEach(type -> comparisons.add(missing(scenario, type, run.runIndex(), "scenario-execution-missing")));
                continue;
            }
            ScenarioExecution execution = matching.getFirst();
            if (!execution.cleanEnvironment()) blockers.add("scenario-not-clean:" + scenario.scenarioId());
            if (execution.productionSideEffect()) blockers.add("production-side-effect:" + scenario.scenarioId());
            if (execution.secretLeak()) blockers.add("secret-material-observed:" + scenario.scenarioId());
            if (execution.crossContamination()) blockers.add("source-target-cross-contamination:" + scenario.scenarioId());
            execution.collectorFailures().stream().map(value -> "collector-failure:" + scenario.scenarioId() + ":" + value).forEach(blockers::add);
            Map<ObservationType,List<Observation>> source = execution.sourceObservations().stream()
                    .collect(Collectors.groupingBy(Observation::observationType));
            Map<ObservationType,List<Observation>> target = execution.targetObservations().stream()
                    .collect(Collectors.groupingBy(Observation::observationType));
            for (ObservationType type : scenario.expectedObservations()) {
                List<Observation> sourceValues = source.getOrDefault(type, List.of());
                List<Observation> targetValues = target.getOrDefault(type, List.of());
                if (sourceValues.size() != 1 || targetValues.size() != 1) {
                    blockers.add("observation-cardinality:" + scenario.scenarioId() + ":" + type);
                    comparisons.add(missing(scenario, type, run.runIndex(), "observation-pair-missing"));
                    continue;
                }
                Observation sourceValue = sourceValues.getFirst();
                Observation targetValue = targetValues.getFirst();
                if (!validObservation(sourceValue, scenario, SystemRole.SOURCE, type)
                        || !validObservation(targetValue, scenario, SystemRole.TARGET, type)
                        || sourceValue.collectorStatus() != CollectorStatus.COMPLETE
                        || targetValue.collectorStatus() != CollectorStatus.COMPLETE) {
                    blockers.add("observation-invalid-or-incomplete:" + scenario.scenarioId() + ":" + type);
                    comparisons.add(missing(scenario, type, run.runIndex(), "collector-incomplete"));
                    continue;
                }
                try {
                    Comparison supplied = Objects.requireNonNull(oracles.compare(
                            new ComparisonRequest(request, scenario, sourceValue, targetValue, run.runIndex())), "comparison");
                    comparisons.add(validateComparison(request, scenario, sourceValue, targetValue, supplied));
                } catch (RuntimeException failure) {
                    blockers.add("oracle-execution-failed:" + scenario.scenarioId() + ":" + type);
                    comparisons.add(missing(scenario, type, run.runIndex(), "oracle-execution-failed"));
                }
            }
        }
    }

    private Comparison validateComparison(Request request, Scenario scenario, Observation source,
                                          Observation target, Comparison value) {
        if (!value.scenarioId().equals(scenario.scenarioId()) || !value.moduleId().equals(scenario.moduleId())
                || value.observationType() != source.observationType()
                || !value.sourceObservationId().equals(source.observationId())
                || !value.targetObservationId().equals(target.observationId()))
            return unsafe(value, scenario, source, target, "oracle-scope-mismatch", ComparisonStatus.UNKNOWN);

        Map<String,OracleResult> oracleById = value.oracleResults().stream()
                .collect(Collectors.toMap(OracleResult::oracleId, result -> result, (left, right) -> left));
        boolean failedRequired = scenario.requiredOracleIds().stream()
                .map(oracleById::get).anyMatch(result -> result != null && result.status() == OracleStatus.FAILED);
        boolean missingRequired = scenario.requiredOracleIds().stream()
                .map(oracleById::get).anyMatch(result -> result == null
                        || result.status() == OracleStatus.UNKNOWN || result.status() == OracleStatus.NOT_RUN
                        || result.evidenceRefs().isEmpty());
        if (failedRequired) return unsafe(value, scenario, source, target, "required-oracle-failed", ComparisonStatus.REGRESSION);
        if (missingRequired) return unsafe(value, scenario, source, target, "required-oracle-not-passed", ComparisonStatus.UNKNOWN);
        if (value.evidenceId() == null || value.evidenceId().isBlank())
            return unsafe(value, scenario, source, target, "comparison-evidence-missing", ComparisonStatus.UNKNOWN);
        if (value.decisionOrigin() == DecisionOrigin.AGENT && value.acceptable())
            return unsafe(value, scenario, source, target, "agent-cannot-adjudicate-equivalence", ComparisonStatus.UNKNOWN);
        if (value.status() == ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION
                && request.normalizationRules().stream().noneMatch(rule -> rule.observationType() == value.observationType()
                && rule.semanticImpactNone()))
            return unsafe(value, scenario, source, target, "normalization-rule-missing", ComparisonStatus.UNKNOWN);
        if (value.status() == ComparisonStatus.WITHIN_TOLERANCE) {
            Tolerance tolerance = request.tolerances().stream().filter(candidate -> candidate.toleranceId().equals(value.toleranceId()))
                    .filter(candidate -> candidate.scenarioId().equals(scenario.scenarioId()))
                    .filter(candidate -> candidate.observationType() == value.observationType()).findFirst().orElse(null);
            if (tolerance == null || !tolerance.expiresAt().isAfter(request.observedAt()) || scenario.highRisk())
                return unsafe(value, scenario, source, target, "invalid-tolerance", ComparisonStatus.REGRESSION);
        }
        if (value.status() == ComparisonStatus.APPROVED_CHANGE) {
            ApprovedChange change = request.approvedChanges().stream()
                    .filter(candidate -> candidate.changeId().equals(value.approvedChangeId()))
                    .filter(candidate -> candidate.scenarioId().equals(scenario.scenarioId()))
                    .filter(candidate -> candidate.observationType() == value.observationType()).findFirst().orElse(null);
            if (change == null || (scenario.highRisk() && !change.highRiskApproved()))
                return unsafe(value, scenario, source, target, "approved-change-evidence-invalid", ComparisonStatus.UNKNOWN);
        }
        return value;
    }

    private static boolean validObservation(Observation value, Scenario scenario, SystemRole role, ObservationType type) {
        return value.scenarioId().equals(scenario.scenarioId()) && value.moduleId().equals(scenario.moduleId())
                && value.systemRole() == role && value.observationType() == type
                && value.sensitiveDataRedacted() && !value.evidenceRefs().isEmpty();
    }

    private static Comparison unsafe(Comparison value, Scenario scenario, Observation source,
                                     Observation target, String reason, ComparisonStatus status) {
        return new Comparison(value.comparisonId(), scenario.scenarioId(), scenario.moduleId(),
                source.observationId(), target.observationId(), source.observationType(),
                value.rawDifferenceRef(), value.canonicalDifferenceRef(), value.oracleResults(), status,
                status == ComparisonStatus.REGRESSION ? Severity.CRITICAL : Severity.HIGH,
                value.rootCause(), scenario.obligationIds(), "invalid:" + reason,
                value.toleranceId(), value.approvedChangeId(), DecisionOrigin.DETERMINISTIC_ORACLE,
                value.flaky(), false);
    }

    private static Comparison missing(Scenario scenario, ObservationType type, int run, String reason) {
        return new Comparison(id("comparison", scenario.scenarioId(), type, run, reason), scenario.scenarioId(),
                scenario.moduleId(), "missing:source", "missing:target", type,
                "missing:" + reason, "missing:" + reason,
                scenario.requiredOracleIds().stream().sorted().map(oracle ->
                        new OracleResult(oracle, OracleStatus.NOT_RUN, true, reason, List.of())).toList(),
                ComparisonStatus.NOT_COMPARABLE, scenario.critical() ? Severity.CRITICAL : Severity.HIGH,
                RootCause.COLLECTOR, scenario.obligationIds(), "missing:" + reason,
                null, null, DecisionOrigin.DETERMINISTIC_ORACLE, false, false);
    }

    private static List<Comparison> markFlaky(List<Comparison> values) {
        Map<String,Set<String>> fingerprints = new HashMap<>();
        for (Comparison value : values) {
            String key = value.scenarioId() + "|" + value.observationType();
            String fingerprint = value.status() + "|" + value.canonicalDifferenceRef() + "|"
                    + value.oracleResults().stream().map(result -> result.oracleId() + ":" + result.status()).sorted().toList();
            fingerprints.computeIfAbsent(key, ignored -> new HashSet<>()).add(fingerprint);
        }
        return values.stream().map(value -> {
            String key = value.scenarioId() + "|" + value.observationType();
            if (fingerprints.getOrDefault(key, Set.of()).size() <= 1) return value;
            return new Comparison(value.comparisonId(), value.scenarioId(), value.moduleId(),
                    value.sourceObservationId(), value.targetObservationId(), value.observationType(),
                    value.rawDifferenceRef(), value.canonicalDifferenceRef(), value.oracleResults(), value.status(),
                    value.severity(), value.rootCause(), value.obligationIds(), value.evidenceId(),
                    value.toleranceId(), value.approvedChangeId(), value.decisionOrigin(), true,
                    value.sourceTargetTraceLinked());
        }).toList();
    }

    private List<RepairFeedback> buildRepairFeedback(Request request, List<Comparison> comparisons) {
        Map<String,List<Comparison>> groups = comparisons.stream()
                .filter(value -> value.status() == ComparisonStatus.REGRESSION)
                .collect(Collectors.groupingBy(value -> value.moduleId() + "|" + value.rootCause()));
        return groups.values().stream().map(group -> {
            Comparison first = group.getFirst();
            List<String> comparisonIds = group.stream().map(Comparison::comparisonId).distinct().sorted().toList();
            List<String> evidence = group.stream().map(Comparison::evidenceId).distinct().sorted().toList();
            return new RepairFeedback(id("behavior-regression", first.moduleId(), first.rootCause(), comparisonIds),
                    first.moduleId(), first.rootCause(), comparisonIds, evidence, first.rootCause() != RootCause.SOURCE_BUG);
        }).toList();
    }

    private Outcome conformance(Request request, EnvironmentAlignment alignment, List<CleanRun> runs,
                                List<Comparison> comparisons, List<RepairFeedback> feedback,
                                List<String> executionBlockers) {
        List<String> open = request.obligations().stream().filter(value -> value.blocking() && !value.resolved())
                .map(SemanticObligation::obligationId).sorted().toList();
        List<ModuleGate> gates = request.modules().stream()
                .map(module -> moduleGate(request, module, alignment, runs, comparisons, open)).toList();
        List<String> collectedBlockers = new ArrayList<>(executionBlockers);
        gates.forEach(gate -> gate.blockers().stream().map(value -> gate.moduleId() + ":" + value).forEach(collectedBlockers::add));
        List<String> blockers = collectedBlockers.stream().distinct().sorted().toList();
        boolean eligible = blockers.isEmpty() && gates.stream().allMatch(ModuleGate::eligibleForProductionHardening);
        boolean approved = comparisons.stream().anyMatch(value -> value.status() == ComparisonStatus.APPROVED_CHANGE);
        RunStatus status = eligible ? (approved ? RunStatus.EQUIVALENT_WITH_APPROVED_DIFFERENCES : RunStatus.EQUIVALENT)
                : comparisons.stream().anyMatch(value -> value.status() == ComparisonStatus.REGRESSION)
                ? RunStatus.REGRESSION_DETECTED : RunStatus.PARTIALLY_EQUIVALENT;
        ConformanceReport report = new ConformanceReport(9, request.equivalenceRunId(), status, gates,
                blockers, open, eligible, false, request.observedAt());
        return new Outcome(request, alignment, runs, comparisons, feedback, report);
    }

    private ModuleGate moduleGate(Request request, ModuleScope module, EnvironmentAlignment alignment,
                                  List<CleanRun> runs, List<Comparison> allComparisons, List<String> open) {
        List<Scenario> scenarios = request.scenarios().stream().filter(value -> value.moduleId().equals(module.moduleId())).toList();
        List<Comparison> comparisons = allComparisons.stream().filter(value -> value.moduleId().equals(module.moduleId())).toList();
        Metrics metrics = metrics(module, scenarios, comparisons, runs);
        List<String> blockers = new ArrayList<>();
        boolean ea = alignment != null && alignment.comparable();
        if (!ea) blockers.add("E-A-comparability-not-proven");

        List<Scenario> http = scenarios.stream().filter(value -> value.expectedObservations().contains(ObservationType.HTTP_RESPONSE)).toList();
        long criticalHttp = http.stream().filter(Scenario::critical).count();
        double criticalHttpCoverage = module.criticalEndpointCount() == 0 ? 1.0
                : Math.min(1.0, (double) criticalHttp / module.criticalEndpointCount());
        double httpPass = ratio(http.stream().filter(value -> scenarioPass(value, comparisons)).count(), http.size(), true);
        boolean securityPassed = scenarios.stream().filter(Scenario::securitySensitive)
                .allMatch(value -> scenarioStrictPass(value, comparisons));
        boolean errorContractsPassed = comparisons.stream().filter(value -> value.observationType() == ObservationType.EXCEPTION)
                .noneMatch(value -> !value.acceptable());
        boolean eb = ea && criticalHttpCoverage == 1.0
                && (module.publicEndpointCount() == 0 || metrics.publicEndpointCoverage() >= 0.99)
                && httpPass >= request.policy().publicEndpointEquivalenceThreshold()
                && securityPassed && errorContractsPassed;
        if (!eb) blockers.add("E-B-public-contract-equivalence-not-proven");

        List<Scenario> criticalDatabase = scenarios.stream().filter(Scenario::critical)
                .filter(value -> value.expectedObservations().contains(ObservationType.DATABASE_STATE)).toList();
        double criticalDatabaseRate = ratio(criticalDatabase.stream()
                .filter(value -> scenarioPassForType(value, comparisons, ObservationType.DATABASE_STATE)).count(), criticalDatabase.size(), true);
        boolean atomicity = noRegression(comparisons, ObservationType.DATABASE_WRITE_TRACE);
        boolean messages = noRegression(comparisons, ObservationType.MESSAGE_EVENT);
        boolean files = comparisons.stream().filter(value -> FILE_EFFECTS.contains(value.observationType()))
                .noneMatch(value -> !value.acceptable());
        boolean audit = noRegression(comparisons, ObservationType.AUDIT);
        boolean ec = eb && criticalDatabaseRate == 1.0 && atomicity && messages && files && audit;
        if (!ec) blockers.add("E-C-state-and-side-effect-equivalence-not-proven");

        long unknownCritical = comparisons.stream().filter(value -> scenario(value.scenarioId(), scenarios).critical())
                .filter(value -> Set.of(ComparisonStatus.UNKNOWN, ComparisonStatus.NOT_COMPARABLE).contains(value.status())).count();
        boolean highRiskStrict = scenarios.stream().filter(Scenario::highRisk)
                .allMatch(value -> scenarioStrictPass(value, comparisons));
        boolean stable = runs.size() >= request.policy().requiredCleanRuns()
                && runs.stream().allMatch(run -> run.scenarios().stream()
                .filter(value -> scenarios.stream().anyMatch(scenario -> scenario.scenarioId().equals(value.scenarioId())))
                .allMatch(value -> value.cleanEnvironment() && !value.productionSideEffect()
                        && !value.secretLeak() && !value.crossContamination() && value.collectorFailures().isEmpty()));
        boolean ed = ec && metrics.criticalScenarioEquivalence() == 1.0
                && metrics.requiredScenarioEquivalence() >= request.policy().requiredScenarioEquivalenceThreshold()
                && open.stream().noneMatch(id -> request.obligations().stream()
                .anyMatch(value -> value.moduleId().equals(module.moduleId()) && value.obligationId().equals(id)))
                && unknownCritical == 0 && highRiskStrict && stable && metrics.flakyDifferenceRate() == 0.0;
        if (!ed) blockers.add("E-D-production-hardening-admission-not-proven");

        boolean hasProperty = scenarios.stream().anyMatch(value -> value.category() == ScenarioCategory.PROPERTY);
        boolean hasMetamorphic = scenarios.stream().anyMatch(value -> value.category() == ScenarioCategory.METAMORPHIC);
        boolean ee = ed && hasProperty && hasMetamorphic
                && metrics.requiredScenarioEquivalence() >= request.policy().highConfidenceThreshold()
                && metrics.propertyDifferentialPassRate() >= request.policy().propertyPassThreshold()
                && metrics.metamorphicRelationPassRate() >= request.policy().metamorphicPassThreshold()
                && metrics.flakyDifferenceRate() <= request.policy().maximumFlakyDifferenceRate()
                && metrics.observationCoverage() >= request.policy().observationCoverageThreshold()
                && metrics.sourceTargetTraceCoverage() >= request.policy().traceCoverageThreshold();
        Gate gate = ee ? Gate.E_E : ed ? Gate.E_D : ec ? Gate.E_C : eb ? Gate.E_B : ea ? Gate.E_A : Gate.BLOCKED;
        List<String> restrictions = new ArrayList<>();
        if (!hasProperty) restrictions.add("property-differential-corpus-pending");
        if (!hasMetamorphic) restrictions.add("metamorphic-corpus-pending");
        if (comparisons.stream().anyMatch(value -> value.status() == ComparisonStatus.APPROVED_CHANGE))
            restrictions.add("approved-behavior-changes-present");
        return new ModuleGate(module.moduleId(), gate, ed, false,
                ed ? List.of() : blockers.stream().distinct().toList(), restrictions, metrics);
    }

    private Metrics metrics(ModuleScope module, List<Scenario> scenarios, List<Comparison> comparisons, List<CleanRun> runs) {
        Set<String> comparedScenarios = comparisons.stream().filter(value -> value.status() != ComparisonStatus.NOT_COMPARABLE)
                .map(Comparison::scenarioId).collect(Collectors.toSet());
        List<Scenario> critical = scenarios.stream().filter(Scenario::critical).toList();
        List<Scenario> required = scenarios.stream().filter(Scenario::required).toList();
        List<Scenario> http = scenarios.stream().filter(value -> value.expectedObservations().contains(ObservationType.HTTP_RESPONSE)).toList();
        List<Scenario> database = scenarios.stream().filter(value -> value.expectedObservations().contains(ObservationType.DATABASE_STATE)).toList();
        List<Scenario> transaction = scenarios.stream().filter(Scenario::transactionSensitive).toList();
        long expected = scenarios.stream().mapToLong(value -> value.expectedObservations().size()).sum();
        long observed = comparisons.stream().filter(value -> value.status() != ComparisonStatus.NOT_COMPARABLE).count();
        List<Scenario> property = scenarios.stream().filter(value -> value.category() == ScenarioCategory.PROPERTY).toList();
        List<Scenario> metamorphic = scenarios.stream().filter(value -> value.category() == ScenarioCategory.METAMORPHIC).toList();
        return new Metrics(
                ratio(critical.stream().filter(value -> comparedScenarios.contains(value.scenarioId())).count(), critical.size(), true),
                ratio(http.stream().filter(value -> comparedScenarios.contains(value.scenarioId())).count(), module.publicEndpointCount(), true),
                ratio(database.stream().filter(value -> comparedScenarios.contains(value.scenarioId())).count(), database.size(), true),
                ratio(transaction.stream().filter(value -> scenarioPass(value, comparisons)).count(), transaction.size(), true),
                ratio(observed, expected, true),
                ratio(critical.stream().filter(value -> scenarioPass(value, comparisons)).count(), critical.size(), true),
                ratio(required.stream().filter(value -> scenarioPass(value, comparisons)).count(), required.size(), true),
                ratio(property.stream().filter(value -> scenarioPass(value, comparisons)).count(), property.size(), false),
                ratio(metamorphic.stream().filter(value -> scenarioPass(value, comparisons)).count(), metamorphic.size(), false),
                ratio(comparisons.stream().filter(Comparison::flaky).count(), comparisons.size(), true),
                ratio(comparisons.stream().filter(Comparison::sourceTargetTraceLinked).count(), comparisons.size(), true),
                comparisons.stream().filter(value -> value.status() == ComparisonStatus.APPROVED_CHANGE).count(),
                comparisons.stream().filter(value -> value.status() == ComparisonStatus.REGRESSION).count(),
                comparisons.stream().filter(value -> value.status() == ComparisonStatus.UNKNOWN
                        || value.status() == ComparisonStatus.NOT_COMPARABLE).count(),
                runs.size());
    }

    private static boolean scenarioPass(Scenario scenario, List<Comparison> comparisons) {
        return scenario.expectedObservations().stream().allMatch(type -> scenarioPassForType(scenario, comparisons, type))
                && (!scenario.highRisk() || scenarioStrictPass(scenario, comparisons));
    }
    private static boolean scenarioStrictPass(Scenario scenario, List<Comparison> comparisons) {
        return scenario.expectedObservations().stream().allMatch(type -> comparisons.stream()
                .filter(value -> value.scenarioId().equals(scenario.scenarioId()) && value.observationType() == type)
                .findFirst().map(Comparison::strictEquivalent).orElse(false));
    }
    private static boolean scenarioPassForType(Scenario scenario, List<Comparison> comparisons, ObservationType type) {
        return comparisons.stream().filter(value -> value.scenarioId().equals(scenario.scenarioId())
                && value.observationType() == type).findFirst().map(Comparison::acceptable).orElse(false);
    }
    private static boolean noRegression(List<Comparison> comparisons, ObservationType type) {
        return comparisons.stream().filter(value -> value.observationType() == type).noneMatch(value -> !value.acceptable());
    }
    private static Scenario scenario(String id, List<Scenario> scenarios) {
        return scenarios.stream().filter(value -> value.scenarioId().equals(id)).findFirst()
                .orElseThrow(() -> new IllegalStateException("comparison references unknown scenario"));
    }

    private Outcome blockedOutcome(Request request, EnvironmentAlignment alignment, List<CleanRun> runs,
                                   List<Comparison> comparisons, List<String> blockers, RunStatus status) {
        List<ModuleGate> gates = request.modules().stream().map(module -> new ModuleGate(module.moduleId(), Gate.BLOCKED,
                false, false, blockers, List.of(), emptyMetrics())).toList();
        List<String> open = request.obligations().stream().filter(value -> value.blocking() && !value.resolved())
                .map(SemanticObligation::obligationId).sorted().toList();
        ConformanceReport report = new ConformanceReport(9, request.equivalenceRunId(), status, gates,
                blockers.stream().distinct().sorted().toList(), open, false, false, request.observedAt());
        return new Outcome(request, alignment, runs, comparisons, List.of(), report);
    }

    private static Metrics emptyMetrics() {
        return new Metrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
    }
    private static double ratio(long numerator, long denominator, boolean emptyPasses) {
        return denominator == 0 ? (emptyPasses ? 1.0 : 0.0) : Math.min(1.0, (double) numerator / denominator);
    }
    private static <T> Set<String> ids(List<T> values, java.util.function.Function<T,String> id,
                                       String kind, List<String> blockers) {
        Set<String> result = new HashSet<>();
        for (T value : values) if (!result.add(id.apply(value))) blockers.add("duplicate-" + kind + "-id:" + id.apply(value));
        return result;
    }
    private static boolean containsAny(String value, String... needles) {
        return Arrays.stream(needles).anyMatch(value::contains);
    }
    private static String id(Object... values) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            for (Object value : values) digest.update(String.valueOf(value).getBytes(StandardCharsets.UTF_8));
            return "b9:" + HexFormat.of().formatHex(digest.digest()).substring(0, 32);
        } catch (Exception impossible) { throw new IllegalStateException(impossible); }
    }
}
