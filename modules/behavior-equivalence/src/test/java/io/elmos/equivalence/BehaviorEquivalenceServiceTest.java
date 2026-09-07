package io.elmos.equivalence;

import com.github.luben.zstd.ZstdInputStream;
import io.elmos.equivalence.BehaviorEquivalenceModels.*;
import io.elmos.equivalence.BehaviorEquivalencePorts.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class BehaviorEquivalenceServiceTest {
    private static final String A = "a".repeat(64);
    private static final String B = "b".repeat(64);
    private static final String C = "c".repeat(64);
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
    @TempDir Path temporary;

    @Test
    void equivalentCleanRunsReachHighConfidenceGateWithoutAuthorizingCutover() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, feedback) -> {}).evaluate(request);

        assertEquals(RunStatus.EQUIVALENT, outcome.report().status());
        assertEquals(Gate.E_E, outcome.report().modules().getFirst().gate());
        assertTrue(outcome.report().eligibleForProductionHardening());
        assertFalse(outcome.report().eligibleForCutover());
        assertEquals(2, outcome.report().modules().getFirst().metrics().stableCleanRuns());
    }

    @Test
    void identicalHttpCannotHideDatabaseRegressionAndFeedsBatch8() {
        List<RepairFeedback> feedback = new ArrayList<>();
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> input.source().observationType() == ObservationType.DATABASE_STATE
                ? comparison(input, ComparisonStatus.REGRESSION, RootCause.TRANSACTION, "database-row-duplicated", DecisionOrigin.DETERMINISTIC_ORACLE)
                : equivalent(input);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle, (ignored, value) -> feedback.add(value)).evaluate(request);

        assertEquals(RunStatus.REGRESSION_DETECTED, outcome.report().status());
        assertTrue(outcome.report().modules().getFirst().gate().ordinal() < Gate.E_C.ordinal());
        assertFalse(outcome.report().eligibleForProductionHardening());
        assertEquals(1, feedback.size());
        assertEquals(RootCause.TRANSACTION, feedback.getFirst().rootCause());
    }

    @Test
    void missingCriticalObservationIsNotComparableRatherThanEquivalent() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        DifferentialExecutionAuthority execution = (ignored, alignment, index) -> {
            CleanRun run = cleanRun(ignored, alignment, index);
            List<ScenarioExecution> changed = run.scenarios().stream().map(value -> {
                if (!value.scenarioId().equals("critical-http")) return value;
                return new ScenarioExecution(value.scenarioId(), value.sourceObservations(),
                        value.targetObservations().stream().filter(observation -> observation.observationType() != ObservationType.DATABASE_STATE).toList(),
                        true, false, false, false, List.of(), value.evidenceRefs());
            }).toList();
            return new CleanRun(index, changed, run.evidenceRefs());
        };
        Outcome outcome = service(perfectAlignment(), execution, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertTrue(outcome.comparisons().stream().anyMatch(value -> value.status() == ComparisonStatus.NOT_COMPARABLE));
        assertFalse(outcome.report().eligibleForProductionHardening());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("observation-cardinality")));
    }

    @Test
    void agentCannotAdjudicateAnAcceptableDifference() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> comparison(input, ComparisonStatus.EQUIVALENT,
                RootCause.UNKNOWN, "agent-says-same", DecisionOrigin.AGENT);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle, (ignored, value) -> {}).evaluate(request);

        assertTrue(outcome.comparisons().stream().allMatch(value -> value.status() == ComparisonStatus.UNKNOWN));
        assertFalse(outcome.report().eligibleForProductionHardening());
    }

    @Test
    void moneyToleranceIsRejectedBeforeAnyRuntimeStarts() {
        AtomicInteger prepares = new AtomicInteger();
        Scenario money = new Scenario("money", "orders", ScenarioCategory.HTTP, Criticality.CRITICAL,
                true, false, true, false, Set.of(ObservationType.HTTP_RESPONSE), Set.of("oracle"),
                List.of(), "contract", C, "recording", "clock", 7L, "trace");
        Tolerance tolerance = new Tolerance("tol", "money", ObservationType.HTTP_RESPONSE,
                "body.amount", "absolute", new BigDecimal("0.01"), BigDecimal.ZERO, "rounding",
                NOW.plus(1, ChronoUnit.DAYS), "business-owner", "approval:tol", true);
        Request request = request(defaultModules(), List.of(money), List.of(), List.of(tolerance), List.of(),
                List.of(golden(money)), uniqueRuntimes());
        DualRuntimeAuthority runtime = new DualRuntimeAuthority() {
            @Override public EnvironmentAlignment prepare(Request ignored) { prepares.incrementAndGet(); return perfectAlignment(); }
        };
        Outcome outcome = new BehaviorEquivalenceService(runtime, this::cleanRun, this::equivalent,
                (ignored, value) -> {}).evaluate(request);

        assertEquals(0, prepares.get());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("tolerance-forbidden-high-risk")));
    }

    @Test
    void sharedMutableResourceBlocksDualRuntimeProvisioning() {
        AtomicInteger prepares = new AtomicInteger();
        RuntimeProfile source = runtime(SystemRole.SOURCE, "source-snapshot", Map.of("database", "database:shared"));
        RuntimeProfile target = runtime(SystemRole.TARGET, "target-snapshot", Map.of("database", "database:shared"));
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), List.of(source, target));
        DualRuntimeAuthority runtime = new DualRuntimeAuthority() {
            @Override public EnvironmentAlignment prepare(Request ignored) { prepares.incrementAndGet(); return perfectAlignment(); }
        };
        Outcome outcome = new BehaviorEquivalenceService(runtime, this::cleanRun, this::equivalent,
                (ignored, value) -> {}).evaluate(request);

        assertEquals(0, prepares.get());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.startsWith("shared-mutable-resource")));
    }

    @Test
    void retryVariabilityIsFlakyAndNeverStablePass() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> comparison(input, ComparisonStatus.EQUIVALENT,
                RootCause.UNKNOWN, "run-" + input.cleanRunIndex(), DecisionOrigin.DETERMINISTIC_ORACLE);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle, (ignored, value) -> {}).evaluate(request);

        assertTrue(outcome.comparisons().stream().allMatch(Comparison::flaky));
        assertFalse(outcome.report().eligibleForProductionHardening());
    }

    @Test
    void shadowProductionEffectBlocksEligibilityEvenWhenOutputsMatch() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        DifferentialExecutionAuthority execution = (ignored, alignment, index) -> {
            CleanRun run = cleanRun(ignored, alignment, index);
            ScenarioExecution first = run.scenarios().getFirst();
            List<ScenarioExecution> changed = new ArrayList<>(run.scenarios());
            changed.set(0, new ScenarioExecution(first.scenarioId(), first.sourceObservations(), first.targetObservations(),
                    true, true, false, false, List.of(), first.evidenceRefs()));
            return new CleanRun(index, changed, run.evidenceRefs());
        };
        Outcome outcome = service(perfectAlignment(), execution, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertFalse(outcome.report().eligibleForProductionHardening());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.startsWith("production-side-effect")));
    }

    @Test
    void repositoryAverageCannotHideOneFailedCriticalModule() {
        List<ModuleScope> modules = List.of(defaultModules().getFirst(), new ModuleScope("billing", 1, 1, true, List.of("billing")));
        Scenario billing = new Scenario("billing-critical", "billing", ScenarioCategory.HTTP, Criticality.CRITICAL,
                true, false, true, true, Set.of(ObservationType.HTTP_RESPONSE, ObservationType.DATABASE_STATE,
                ObservationType.DATABASE_WRITE_TRACE), Set.of("oracle"), List.of(), "contract", C,
                "recording", "clock", 8L, "trace");
        List<Scenario> scenarios = new ArrayList<>(defaultScenarios()); scenarios.add(billing);
        List<GoldenMaster> golden = new ArrayList<>(defaultGolden()); golden.add(golden(billing));
        Request request = request(modules, scenarios, List.of(), List.of(), List.of(), golden, uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> input.scenario().moduleId().equals("billing")
                ? comparison(input, ComparisonStatus.REGRESSION, RootCause.NUMERIC_SEMANTICS,
                "money-mismatch", DecisionOrigin.DETERMINISTIC_ORACLE) : equivalent(input);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle, (ignored, value) -> {}).evaluate(request);

        assertEquals(2, outcome.report().modules().size());
        assertTrue(outcome.report().modules().stream().filter(value -> value.moduleId().equals("orders"))
                .allMatch(ModuleGate::eligibleForProductionHardening));
        assertTrue(outcome.report().modules().stream().filter(value -> value.moduleId().equals("billing"))
                .noneMatch(ModuleGate::eligibleForProductionHardening));
        assertFalse(outcome.report().eligibleForProductionHardening());
    }

    @Test
    void unreviewedGoldenBlocksCriticalScenarioBeforeExecution() {
        GoldenMaster candidate = new GoldenMaster("golden:critical-http", "critical-http", "source-snapshot",
                A, B, C, "raw", "canonical", "normalization-v1", GoldenStatus.CANDIDATE, null, null);
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(),
                List.of(candidate), uniqueRuntimes());
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertTrue(outcome.report().blockers().contains("trusted-golden-missing:critical-http"));
        assertTrue(outcome.cleanRuns().isEmpty());
    }

    @Test
    void blockingObligationWithoutResolutionPreventsED() {
        SemanticObligation obligation = new SemanticObligation("obligation:atomicity", "orders", true,
                false, List.of("critical-http"), "domain-owner");
        Request request = request(defaultModules(), defaultScenarios(), List.of(obligation), List.of(), List.of(),
                defaultGolden(), uniqueRuntimes());
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertEquals(Gate.E_C, outcome.report().modules().getFirst().gate());
        assertFalse(outcome.report().eligibleForProductionHardening());
        assertEquals(List.of("obligation:atomicity"), outcome.report().openBlockingObligations());
    }

    @Test
    void declaredEndpointInventoryCannotBeHiddenByOnePassingScenario() {
        List<ModuleScope> modules = List.of(new ModuleScope("orders", 2, 1, true, List.of("order-management")));
        Request request = request(modules, defaultScenarios(), List.of(), List.of(), List.of(),
                defaultGolden(), uniqueRuntimes());
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertEquals(0.5, outcome.report().modules().getFirst().metrics().publicEndpointCoverage());
        assertEquals(Gate.E_A, outcome.report().modules().getFirst().gate());
        assertFalse(outcome.report().eligibleForProductionHardening());
    }

    @Test
    void reviewedOrdinaryApprovedChangeRemainsSeparateFromEquivalence() {
        Scenario ordinary = new Scenario("ordinary-http", "orders", ScenarioCategory.HTTP, Criticality.HIGH,
                true, false, false, false, Set.of(ObservationType.HTTP_RESPONSE), Set.of("oracle"),
                List.of(), "contract", C, "recording", "clock", 10L, "trace");
        List<Scenario> scenarios = new ArrayList<>(defaultScenarios()); scenarios.add(ordinary);
        ApprovedChange change = new ApprovedChange("change:error-format", ordinary.scenarioId(),
                ObservationType.HTTP_RESPONSE, "versioned client error envelope", "v2 compatibility window",
                "product-owner", "approval:change", false);
        List<ModuleScope> modules = List.of(new ModuleScope("orders", 2, 1, true, List.of("order-management")));
        Request request = request(modules, scenarios, List.of(), List.of(), List.of(change), defaultGolden(), uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> input.scenario().scenarioId().equals(ordinary.scenarioId())
                ? approved(input, change) : equivalent(input);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle, (ignored, value) -> {}).evaluate(request);

        assertEquals(RunStatus.EQUIVALENT_WITH_APPROVED_DIFFERENCES, outcome.report().status());
        assertTrue(outcome.report().eligibleForProductionHardening());
        assertTrue(outcome.comparisons().stream().anyMatch(value -> value.status() == ComparisonStatus.APPROVED_CHANGE));
        assertTrue(outcome.report().modules().getFirst().restrictions().contains("approved-behavior-changes-present"));
    }

    @Test
    void failedBatch8FeedbackSubmissionIsVisibleAndNonPassing() {
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(), defaultGolden(), uniqueRuntimes());
        EquivalenceOracleAuthority oracle = input -> input.source().observationType() == ObservationType.DATABASE_STATE
                ? comparison(input, ComparisonStatus.REGRESSION, RootCause.ORM, "row-mismatch", DecisionOrigin.DETERMINISTIC_ORACLE)
                : equivalent(input);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, oracle,
                (ignored, value) -> { throw new IllegalStateException("feedback unavailable"); }).evaluate(request);

        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.startsWith("batch8-repair-feedback-failed")));
        assertFalse(outcome.report().eligibleForProductionHardening());
    }

    @Test
    void artifactWriterCreatesCompressedEvidenceTreeAndRefusesOverwrite() throws IOException {
        Path workspace = temporary.resolve("migration-workspace");
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(),
                defaultGolden(), uniqueRuntimes(), workspace);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, value) -> {}).evaluate(request);
        BehaviorEquivalenceArtifactWriter writer = new BehaviorEquivalenceArtifactWriter();

        Map<String,Path> written = writer.write(outcome);
        assertEquals(27, written.size());
        assertTrue(Files.exists(workspace.resolve("equivalence/comparisons.jsonl.zst")));
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(
                workspace.resolve("equivalence/comparisons.jsonl.zst")))) {
            String content = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(content.contains("critical-http"));
        }
        assertThrows(FileAlreadyExistsException.class, () -> writer.write(outcome));
    }

    @Test
    void artifactWriterRejectsSymlinkedEvidenceDirectory() throws IOException {
        Path workspace = temporary.resolve("workspace");
        Files.createDirectories(workspace);
        Path redirected = temporary.resolve("redirected"); Files.createDirectories(redirected);
        Files.createSymbolicLink(workspace.resolve("equivalence"), redirected);
        Request request = request(defaultModules(), defaultScenarios(), List.of(), List.of(), List.of(),
                defaultGolden(), uniqueRuntimes(), workspace);
        Outcome outcome = service(perfectAlignment(), this::cleanRun, this::equivalent, (ignored, value) -> {}).evaluate(request);

        assertThrows(IOException.class, () -> new BehaviorEquivalenceArtifactWriter().write(outcome));
    }

    private BehaviorEquivalenceService service(EnvironmentAlignment alignment,
                                               DifferentialExecutionAuthority execution,
                                               EquivalenceOracleAuthority oracle,
                                               Batch8RepairFeedbackAuthority feedback) {
        DualRuntimeAuthority runtime = new DualRuntimeAuthority() {
            @Override public EnvironmentAlignment prepare(Request ignored) { return alignment; }
        };
        return new BehaviorEquivalenceService(runtime, execution, oracle, feedback);
    }

    private CleanRun cleanRun(Request request, EnvironmentAlignment ignored, int index) {
        List<ScenarioExecution> executions = request.scenarios().stream().map(scenario -> {
            List<Observation> source = scenario.expectedObservations().stream().map(type -> observation(scenario, type, SystemRole.SOURCE, index)).toList();
            List<Observation> target = scenario.expectedObservations().stream().map(type -> observation(scenario, type, SystemRole.TARGET, index)).toList();
            return new ScenarioExecution(scenario.scenarioId(), source, target, true, false, false,
                    false, List.of(), List.of("evidence:scenario:" + scenario.scenarioId()));
        }).toList();
        return new CleanRun(index, executions, List.of("evidence:clean-run:" + index));
    }

    private Observation observation(Scenario scenario, ObservationType type, SystemRole role, int run) {
        String id = role.name().toLowerCase(Locale.ROOT) + ":" + scenario.scenarioId() + ":" + type + ":" + run;
        return new Observation(id, scenario.scenarioId(), scenario.moduleId(), role, type,
                "raw:" + id, A, "canonical:" + id, B, Map.of("logical", "same"),
                CollectorStatus.COMPLETE, true, List.of("evidence:" + id));
    }

    private Comparison equivalent(ComparisonRequest input) {
        return comparison(input, ComparisonStatus.EQUIVALENT, RootCause.UNKNOWN,
                "no-difference", DecisionOrigin.DETERMINISTIC_ORACLE);
    }

    private Comparison approved(ComparisonRequest input, ApprovedChange change) {
        List<OracleResult> results = input.scenario().requiredOracleIds().stream()
                .map(id -> new OracleResult(id, OracleStatus.PASSED, true, "approved-versioned-change",
                        List.of("evidence:oracle:" + id))).toList();
        return new Comparison("comparison:" + input.source().observationId(), input.scenario().scenarioId(),
                input.scenario().moduleId(), input.source().observationId(), input.target().observationId(),
                input.source().observationType(), "raw-diff:approved", "approved-diff", results,
                ComparisonStatus.APPROVED_CHANGE, Severity.LOW, RootCause.SERIALIZATION,
                input.scenario().obligationIds(), "evidence:approved:" + input.source().observationId(),
                null, change.changeId(), DecisionOrigin.HUMAN_REVIEW, false, true);
    }

    private Comparison comparison(ComparisonRequest input, ComparisonStatus status, RootCause cause,
                                  String canonicalDiff, DecisionOrigin origin) {
        List<OracleResult> results = input.scenario().requiredOracleIds().stream()
                .map(id -> new OracleResult(id, status == ComparisonStatus.REGRESSION ? OracleStatus.FAILED : OracleStatus.PASSED,
                        true, canonicalDiff, List.of("evidence:oracle:" + id))).toList();
        return new Comparison("comparison:" + input.source().observationId(), input.scenario().scenarioId(),
                input.scenario().moduleId(), input.source().observationId(), input.target().observationId(),
                input.source().observationType(), "raw-diff:" + canonicalDiff, canonicalDiff, results,
                status, status == ComparisonStatus.REGRESSION ? Severity.CRITICAL : Severity.INFO,
                cause, input.scenario().obligationIds(), "evidence:comparison:" + input.source().observationId(),
                null, null, origin, false, true);
    }

    private Request request(List<ModuleScope> modules, List<Scenario> scenarios,
                            List<SemanticObligation> obligations, List<Tolerance> tolerances,
                            List<ApprovedChange> changes, List<GoldenMaster> golden,
                            List<RuntimeProfile> runtimes) {
        return request(modules, scenarios, obligations, tolerances, changes, golden, runtimes,
                temporary.resolve("artifacts"));
    }

    private Request request(List<ModuleScope> modules, List<Scenario> scenarios,
                            List<SemanticObligation> obligations, List<Tolerance> tolerances,
                            List<ApprovedChange> changes, List<GoldenMaster> golden,
                            List<RuntimeProfile> runtimes, Path workspace) {
        Set<String> moduleTypes = new HashSet<>();
        List<ObservationPoint> points = new ArrayList<>();
        for (Scenario scenario : scenarios) for (ObservationType type : scenario.expectedObservations()) {
            String key = scenario.moduleId() + ":" + type;
            if (moduleTypes.add(key)) points.add(new ObservationPoint("point:" + key, scenario.moduleId(), type,
                    true, "confidential", "collector:" + type));
        }
        Policy policy = new Policy(2, 0.99, 0.98, 0.995, 0.99, 0.99,
                0.005, 0.995, 0.995, 1000, 60);
        return new Request(workspace, temporary.resolve("source-repo"), temporary.resolve("target-repo"),
                "equivalence-run:test", "migration:test", "source-snapshot", "target-snapshot", true,
                runtimes.get(0), runtimes.get(1), modules, scenarios, points, obligations,
                List.of(), tolerances, changes, golden, policy, NOW);
    }

    private List<ModuleScope> defaultModules() {
        return List.of(new ModuleScope("orders", 1, 1, true, List.of("order-management")));
    }

    private List<Scenario> defaultScenarios() {
        Scenario critical = new Scenario("critical-http", "orders", ScenarioCategory.HTTP, Criticality.CRITICAL,
                true, true, false, true, Set.of(ObservationType.HTTP_RESPONSE, ObservationType.DATABASE_STATE,
                ObservationType.DATABASE_WRITE_TRACE, ObservationType.MESSAGE_EVENT, ObservationType.AUDIT),
                Set.of("oracle"), List.of(), "contract", C, "recording", "clock", 7L, "trace");
        Scenario property = new Scenario("property", "orders", ScenarioCategory.PROPERTY, Criticality.HIGH,
                true, false, false, false, Set.of(ObservationType.RETURN_VALUE), Set.of("oracle"),
                List.of(), "generator", C, "recording", "clock", 8L, "trace");
        Scenario metamorphic = new Scenario("metamorphic", "orders", ScenarioCategory.METAMORPHIC, Criticality.HIGH,
                true, false, false, false, Set.of(ObservationType.RETURN_VALUE), Set.of("oracle"),
                List.of(), "domain-relation", C, "recording", "clock", 9L, "trace");
        return List.of(critical, property, metamorphic);
    }

    private List<GoldenMaster> defaultGolden() { return List.of(golden(defaultScenarios().getFirst())); }
    private GoldenMaster golden(Scenario scenario) {
        return new GoldenMaster("golden:" + scenario.scenarioId(), scenario.scenarioId(), "source-snapshot",
                A, B, scenario.initialStateHash(), "raw", "canonical", "normalization-v1",
                GoldenStatus.APPROVED, "reviewer", "approval:golden");
    }

    private List<RuntimeProfile> uniqueRuntimes() {
        return List.of(runtime(SystemRole.SOURCE, "source-snapshot", Map.of("database", "database:source", "broker", "broker:source")),
                runtime(SystemRole.TARGET, "target-snapshot", Map.of("database", "database:target", "broker", "broker:target")));
    }
    private RuntimeProfile runtime(SystemRole role, String snapshot, Map<String,String> resources) {
        return new RuntimeProfile(role, snapshot, "runtime-1", "environment:" + role, resources,
                false, List.of("evidence:runtime:" + role));
    }
    private EnvironmentAlignment perfectAlignment() {
        return new EnvironmentAlignment(true, true, true, true, true, true, true, true, true,
                true, true, true, true, true, false, false, List.of(), List.of("evidence:alignment"));
    }
}
