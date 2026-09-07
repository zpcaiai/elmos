package io.elmos.repair;

import io.elmos.repair.RepairLoopModels.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class RepairLoopServiceTest {
    private static final String A = "a".repeat(64), B = "b".repeat(64), C = "c".repeat(64);
    private static final String ENV = "e".repeat(64);
    @TempDir Path temporary;

    @Test void cleanBuildStaticTestsAndTwoReproducibilityRunsReachRD() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        AtomicInteger calls = new AtomicInteger();
        RepairLoopService service = service(execution -> {
            calls.incrementAndGet();
            return passing(execution.targetSnapshotId(), execution.scope() == ValidationScope.FULL,
                    execution.cleanEnvironment());
        }, context -> null, context -> null, transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.CONVERGED_SUCCESS, result.stopDecision().outcome());
        assertEquals(2, calls.get());
        assertTrue(result.conformance().eligibleForBatch9());
        assertEquals("R-E", result.conformance().modules().getFirst().gate());
        assertEquals(2, result.conformance().metrics().reproducibilityRunsPassed());
        assertTrue(result.matrix().getFirst().commands().stream().anyMatch(value -> value.phase() == Phase.FULL_REGRESSION));
    }

    @Test void sourceExistingDiagnosticIsReportedButNotCountedAsMigrationRegression() throws Exception {
        RawDiagnostic raw = symbolDiagnostic(42, "token=source-secret");
        String fingerprint = new RepairDiagnosticProtocol().normalize("repair-run-8", raw).fingerprint();
        Request request = request(true, baseline(Set.of(fingerprint)), policy(true, 2));
        RepairLoopService service = service(execution -> withDiagnostics(passing(execution.targetSnapshotId(), true, true), List.of(raw)),
                context -> null, context -> null, transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.CONVERGED_SUCCESS, result.stopDecision().outcome());
        assertEquals(Attribution.SOURCE_EXISTING, result.attributions().getFirst().attribution());
        assertTrue(result.diagnostics().getFirst().message().contains("[REDACTED]"));
        assertTrue(result.conformance().eligibleForBatch9());
    }

    @Test void zeroTestDiscoveryCannotBecomeGreen() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(false, 2));
        ExecutionResult zero = new ExecutionResult(Status.PASSED, "snapshot-1", true, true, 1, 1, 1,
                0, 0, true, 0, List.of(), 0, 0, 0, 0, 1,
                true, true, false, false, "sandbox@sha256:test", ENV, List.of(), List.of("evidence://zero"),
                Map.of("orders", moduleExecution(1, true, 0, true)));
        RepairLoopService service = service(execution -> zero, context -> null, context -> null, transaction());

        RunResult result = service.run(request);

        assertNotEquals(StopOutcome.CONVERGED_SUCCESS, result.stopDecision().outcome());
        assertFalse(result.conformance().eligibleForBatch9());
        assertTrue(result.diagnostics().stream().anyMatch(value -> "ZERO_TEST_DISCOVERY".equals(value.nativeCode())));
        assertTrue(result.conformance().blockingErrors().contains("required-test-discovery-not-proven"));
    }

    @Test void deterministicPatchMustBeAtomicLocallyValidatedAndFullyRegressed() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        Deque<ExecutionResult> results = new ArrayDeque<>();
        results.add(failing("snapshot-1", symbolDiagnostic(10, "cannot find symbol Widget")));
        results.add(passing("snapshot-2", false, false));
        results.add(passing("snapshot-2", true, true));
        results.add(passing("snapshot-2", true, true));
        RepairLoopService service = service(execution -> results.removeFirst(),
                context -> patch(context, false, false, false, false, B), context -> null, transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.CONVERGED_SUCCESS, result.stopDecision().outcome());
        assertEquals("snapshot-2", result.stopDecision().stableSnapshotId());
        assertEquals(PatchOutcome.EFFECTIVE, result.patches().getFirst().outcome());
        assertEquals("AVAILABLE", result.patches().getFirst().rollbackStatus());
        assertEquals(1, result.stopDecision().patchAttempts());
        assertTrue(result.conformance().eligibleForBatch9());
        assertTrue(results.isEmpty());
    }

    @Test void assertionWeakeningAndUnreviewedHighRiskAgentPatchFailClosed() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        RawDiagnostic raw = new RawDiagnostic(Phase.UNIT_TEST, "junit", "ASSERT", "test-assertion", "error",
                "AssertionError expected 42", "orders", "src/test/OrdersTest.java", 20, 2,
                null, null, "targetdecl:test", "source-test:orders", "evidence://assertion");
        ExecutionResult failing = failing("snapshot-1", raw);
        RepairLoopService service = service(execution -> failing, context -> null,
                context -> patch(context, true, true, false, true, B), transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.STOPPED_BY_RISK, result.stopDecision().outcome());
        assertEquals(PatchState.REJECTED, result.patches().getFirst().application().state());
        assertTrue(result.patches().getFirst().policyFindings().stream().anyMatch(value -> value.startsWith("ASSERTION_WEAKENED")));
        assertTrue(result.patches().getFirst().policyFindings().contains("HIGH_RISK_AGENT_PATCH_UNREVIEWED"));
        assertFalse(result.conformance().eligibleForBatch9());
    }

    @Test void independentInspectionBlocksUndeclaredPublicApiDrift() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        RawDiagnostic raw = new RawDiagnostic(Phase.UNIT_TEST, "junit", "ASSERT", "test-assertion", "error",
                "AssertionError expected 42", "orders", "src/test/OrdersTest.java", 20, 2,
                null, null, "targetdecl:test", "source-test:orders", "evidence://assertion");
        ExecutionResult failing = failing("snapshot-1", raw);
        AgentRepairAuthority agent = context -> patch(context, true, false, false, false, B);
        PatchInspectionAuthority inspection = (patch, plan) -> new PatchInspection(patch.patchId(),
                true, true, true, patch.modifications().stream().map(Modification::file).toList(),
                true, false, false, false, false, 0, 0, List.of(),
                List.of("evidence://inspection/public-api"), List.of());
        AtomicInteger applications = new AtomicInteger();
        TransactionalPatchAuthority transaction = new TransactionalPatchAuthority() {
            @Override public PatchApplication apply(Patch patch, RepairPlan plan) {
                applications.incrementAndGet();
                return new PatchApplication(patch.patchId(), PatchState.APPLIED, "snapshot-2", true, true,
                        List.of("evidence://apply"), List.of());
            }
            @Override public PatchApplication rollback(Patch patch, String stableSnapshotId) {
                throw new AssertionError("rejected patch must not be rolled back");
            }
        };
        RepairLoopService service = new RepairLoopService(execution -> failing, context -> null,
                agent, inspection, transaction);

        RunResult result = service.run(request);

        assertEquals(StopOutcome.STOPPED_BY_RISK, result.stopDecision().outcome());
        assertEquals(0, applications.get());
        assertTrue(result.patches().getFirst().policyFindings().contains("INSPECTION_PUBLIC_API_CHANGED"));
        assertEquals(List.of("evidence://inspection/public-api"), result.patches().getFirst().inspection().evidenceRefs());
    }

    @Test void environmentFailureNeverEntersCodeRepairAgent() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        RawDiagnostic raw = new RawDiagnostic(Phase.RESTORE, "sandbox", "SANDBOX_UNAVAILABLE", "environment", "blocking",
                "sandbox unavailable", "orders", null, null, null, null, null, null, null, "evidence://sandbox");
        ExecutionResult failed = failing("snapshot-1", raw);
        AtomicInteger repairCalls = new AtomicInteger();
        RepairLoopService service = service(execution -> failed,
                context -> { repairCalls.incrementAndGet(); return null; },
                context -> { repairCalls.incrementAndGet(); return null; }, transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.BLOCKED_BY_ENVIRONMENT, result.stopDecision().outcome());
        assertEquals(0, repairCalls.get());
        assertTrue(result.plans().stream().allMatch(value -> value.strategy() == RepairStrategy.ENVIRONMENT));
    }

    @Test void repeatedNeutralRepairStateStopsAsOscillationAndKeepsStableSnapshot() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(false, 2));
        RawDiagnostic raw = symbolDiagnostic(10, "cannot find symbol Widget");
        Deque<ExecutionResult> results = new ArrayDeque<>();
        results.add(failing("snapshot-1", raw));
        results.add(passing("snapshot-2", false, false));
        results.add(failing("snapshot-2", raw));
        results.add(passing("snapshot-2", false, false));
        results.add(failing("snapshot-2", raw));
        AtomicInteger attempt = new AtomicInteger();
        RepairLoopService service = service(execution -> results.removeFirst(), context -> {
            int number = attempt.incrementAndGet();
            Patch base = patch(context, false, false, false, false, number == 1 ? B : C);
            return new Patch("patch:neutral:" + number, base.clusterId(), base.planId(), base.baseSnapshotId(),
                    base.modifications(), false, false, false, null, 0, 0,
                    base.expectedDiagnosticsRemoved(), base.patchArtifactRef());
        }, context -> null, transaction());

        RunResult result = service.run(request);

        assertEquals(StopOutcome.STOPPED_BY_OSCILLATION, result.stopDecision().outcome());
        assertEquals("snapshot-1", result.stopDecision().stableSnapshotId());
        assertEquals(2, result.stopDecision().patchAttempts());
        assertTrue(result.patches().stream().allMatch(value -> value.outcome() == PatchOutcome.NEUTRAL));
        assertTrue(result.patches().stream().allMatch(value -> "ROLLED_BACK".equals(value.rollbackStatus())));
    }

    @Test void missingBatch7AdmissionStopsBeforeAnyExecution() throws Exception {
        Request request = request(false, baseline(Set.of()), policy(true, 2));
        AtomicInteger calls = new AtomicInteger();
        RepairLoopService service = service(execution -> { calls.incrementAndGet(); return passing("snapshot-1", true, true); },
                context -> null, context -> null, transaction());

        RunResult result = service.run(request);

        assertEquals(0, calls.get());
        assertEquals(Status.NOT_RUN, result.finalExecution().status());
        assertTrue(result.stopDecision().blockers().contains("batch-7-f-d-admission-missing"));
    }

    @Test void diagnosticsAreStableAcrossLineAndHostChangesAndPreserveNativeCode() {
        RepairDiagnosticProtocol protocol = new RepairDiagnosticProtocol();
        Diagnostic first = protocol.normalize("run", new RawDiagnostic(Phase.COMPILE, "javac", "JAVAC_SYMBOL", null, null,
                "/Users/alice/repo/A.java:42 cannot find symbol Widget token=alpha", "orders", "/Users/alice/repo/A.java",
                42, 1, "Widget", null, "targetdecl:widget", null, "log://1"));
        Diagnostic second = protocol.normalize("run", new RawDiagnostic(Phase.COMPILE, "javac", "JAVAC_SYMBOL", null, null,
                "/home/runner/repo/A.java:99 cannot find symbol Widget token=beta", "orders", "/home/runner/repo/A.java",
                99, 1, "Widget", null, "targetdecl:widget", null, "log://2"));

        assertEquals(first.fingerprint(), second.fingerprint());
        assertEquals("JAVAC_SYMBOL", first.nativeCode());
        assertFalse(first.message().contains("alpha"));
        assertFalse(first.message().contains("/Users/alice"));
    }

    @Test void convergencePolicyRequiresTwoCleanRuns() {
        assertThrows(IllegalArgumentException.class, () -> policy(true, 1));
    }

    @Test void repositoryAverageCannotHideAFailingModule() throws Exception {
        Request base = request(true, baseline(Set.of()), policy(true, 2));
        Request request = new Request(base.artifactWorkspace(), base.repairRunId(), base.migrationId(),
                base.sourceSnapshotId(), base.targetSnapshotId(), base.targetRepositoryPath(), true,
                base.sourceBaseline(), List.of(
                base.modules().getFirst(),
                new ModuleTarget("payments", Language.JAVA, "21", "spring-boot-3.5.3",
                        "maven", "3.9.11", List.of("linux-x64"), true, 0)),
                List.of(), base.policy(), base.observedAt());
        ExecutionResult passing = passing("snapshot-1", true, true);
        ExecutionResult mixed = new ExecutionResult(Status.FAILED, "snapshot-1", true, true,
                0.99, 0.99, 0.99, 0, 0, true, 2, passing.tests(),
                0, 0, 0, 0, 1, true, true, false, false,
                "sandbox@sha256:test", ENV, List.of(), List.of("evidence://mixed"), Map.of(
                "orders", moduleExecution("orders", 1, true, 2, true),
                "payments", moduleExecution("payments", 0.5, true, 0, true)));

        ConformanceReport report = new RepairLoopPolicy().conformance(request, mixed,
                List.of(), List.of(), List.of(), 2, List.of());

        assertEquals("R-E", report.modules().stream().filter(value -> value.targetModuleId().equals("orders"))
                .findFirst().orElseThrow().gate());
        assertEquals("BLOCKED", report.modules().stream().filter(value -> value.targetModuleId().equals("payments"))
                .findFirst().orElseThrow().gate());
        assertFalse(report.eligibleForBatch9());
    }

    @Test void artifactWriterProducesCompressedEvidenceAndRejectsSymlinkParent() throws Exception {
        Request request = request(true, baseline(Set.of()), policy(true, 2));
        RunResult result = service(execution -> passing(execution.targetSnapshotId(), true, true),
                context -> null, context -> null, transaction()).run(request);
        Path artifacts = temporary.resolve("artifacts-out");
        Map<String,Path> written = new RepairArtifactWriter().write(artifacts, result);

        assertTrue(Files.size(written.get("repair/diagnostics.jsonl.zst")) > 0);
        assertTrue(Files.isRegularFile(written.get("repair/repair-run-manifest.yaml")));
        assertTrue(Files.isRegularFile(written.get("reports/batch-8-conformance-report.json")));
        assertEquals(0, Files.list(request.targetRepositoryPath()).count());

        Path outside = temporary.resolve("outside");
        Files.createDirectories(outside);
        Files.move(artifacts.resolve("reports"), artifacts.resolve("reports-owned"));
        Files.createSymbolicLink(artifacts.resolve("reports"), outside);
        assertThrows(SecurityException.class, () -> new RepairArtifactWriter().write(artifacts, result));
        assertEquals(0, Files.list(outside).count());
    }

    private Request request(boolean batch7, SourceBaseline baseline, Policy policy) throws Exception {
        Path target = temporary.resolve("target-repository");
        Files.createDirectories(target);
        return new Request(temporary.resolve("migration-workspace"), "repair-run-8", "migration-8",
                "source-snapshot-1", "snapshot-1", target, batch7, baseline,
                List.of(new ModuleTarget("orders", Language.JAVA, "21", "spring-boot-3.5.3",
                        "maven", "3.9.11", List.of("linux-x64"), false, 2)), List.of(), policy,
                Instant.parse("2026-07-21T10:00:00Z"));
    }

    private SourceBaseline baseline(Set<String> fingerprints) {
        return new SourceBaseline(true, fingerprints, Map.of("source-test:orders", TestStatus.PASSED),
                List.of("evidence://source-baseline"));
    }

    private Policy policy(boolean agent, int reproducibilityRuns) {
        return new Policy(true, agent, Set.of("approved:package"), false,
                6, 6, 3, 20_000, 100_000, 600,
                5, 300, reproducibilityRuns);
    }

    private RepairLoopService service(ExecutionAuthority execution, DeterministicRepairAuthority deterministic,
                                      AgentRepairAuthority agent, TransactionalPatchAuthority transaction) {
        PatchInspectionAuthority inspection = (patch, plan) -> new PatchInspection(patch.patchId(),
                true, true, true, patch.modifications().stream().map(Modification::file).toList(),
                false, false, false, false, false, 0, 0, List.of(),
                List.of("evidence://patch/inspection"), List.of());
        return new RepairLoopService(execution, deterministic, agent, inspection, transaction);
    }

    private TransactionalPatchAuthority transaction() {
        return new TransactionalPatchAuthority() {
            @Override public PatchApplication apply(Patch patch, RepairPlan plan) {
                return new PatchApplication(patch.patchId(), PatchState.APPLIED, "snapshot-2", true, true,
                        List.of("evidence://patch/apply"), List.of());
            }
            @Override public PatchApplication rollback(Patch patch, String stableSnapshotId) {
                return new PatchApplication(patch.patchId(), PatchState.ROLLED_BACK, stableSnapshotId, true, true,
                        List.of("evidence://patch/rollback"), List.of());
            }
        };
    }

    private Patch patch(RepairContext context, boolean agent, boolean highRisk,
                        boolean approved, boolean weakensAssertion, String afterHash) {
        String file = context.plan().allowedFiles().getFirst();
        String declaration = context.plan().allowedDeclarations().isEmpty()
                ? null : context.plan().allowedDeclarations().getFirst();
        Modification modification = new Modification(file, declaration, "replace-generated-region",
                A, afterHash, 8, false, false, false, false,
                false, weakensAssertion, 0, 0, List.of());
        return new Patch("patch:" + context.plan().planId(), context.cluster().clusterId(), context.plan().planId(),
                context.targetSnapshotId(), List.of(modification), agent, highRisk, approved,
                approved ? "review://approved" : null, agent ? 100 : 0, agent ? 1000 : 0,
                context.cluster().diagnosticIds(), "artifact://patch");
    }

    private ExecutionResult passing(String snapshot, boolean full, boolean clean) {
        List<TestResult> tests = List.of(
                new TestResult("test:unit", "orders", "source-test:orders", Phase.UNIT_TEST,
                        TestStatus.PASSED, null, true, null, List.of("evidence://test/unit")),
                new TestResult("test:contract", "orders", "source-test:contract", Phase.CONTRACT_TEST,
                        TestStatus.PASSED, null, true, null, List.of("evidence://test/contract")));
        return new ExecutionResult(Status.PASSED, snapshot, true, true, 1, 1, 1,
                0, 0, true, 2, tests, 0, 0, 0, 0, 1,
                full, clean, false, false, "sandbox@sha256:test", ENV,
                List.of(), List.of("evidence://execution/" + (full ? "full" : "local")),
                Map.of("orders", moduleExecution(1, true, 2, full)));
    }

    private ExecutionResult failing(String snapshot, RawDiagnostic diagnostic) {
        List<TestResult> tests = List.of(
                new TestResult("test:unit", "orders", "source-test:orders", Phase.UNIT_TEST,
                        TestStatus.FAILED, A, true, "assertion", List.of("evidence://test/failure")),
                new TestResult("test:contract", "orders", "source-test:contract", Phase.CONTRACT_TEST,
                        TestStatus.PASSED, null, true, null, List.of("evidence://test/contract")));
        return new ExecutionResult(Status.FAILED, snapshot, true, true, 0.5, 0.5, 0.5,
                0, 0, true, 2, tests, 0, 0, 0, 0, 1,
                true, true, false, false, "sandbox@sha256:test", ENV,
                List.of(diagnostic), List.of("evidence://execution/failure"),
                Map.of("orders", moduleExecution(0.5, true, 2, true)));
    }

    private ExecutionResult withDiagnostics(ExecutionResult base, List<RawDiagnostic> diagnostics) {
        return new ExecutionResult(base.status(), base.targetSnapshotId(), base.dependencyRestorePassed(),
                base.buildModelLoaded(), base.compileRate(), base.symbolResolutionRate(), base.typeValidationRate(),
                base.blockingStaticDiagnostics(), base.criticalStaticDiagnostics(), base.testDiscoveryPassed(),
                base.discoveredTests(), base.tests(), base.publicApiRegressions(), base.securityRegressions(),
                base.transactionRegressions(), base.serializationRegressions(), base.sourceTargetTraceCoverage(),
                base.fullRegressionExecuted(), base.cleanEnvironment(), base.productionResourceAccessed(),
                base.secretMaterialObserved(), base.sandboxRef(), base.environmentHash(), diagnostics, base.evidenceRefs(),
                base.moduleExecutions());
    }

    private ModuleExecution moduleExecution(double compileRate, boolean discovery, int discovered, boolean full) {
        return moduleExecution("orders", compileRate, discovery, discovered, full);
    }

    private ModuleExecution moduleExecution(String moduleId, double compileRate,
                                            boolean discovery, int discovered, boolean full) {
        return new ModuleExecution(moduleId, true, true, compileRate, compileRate, compileRate,
                0, 0, discovery, discovered, 0, 0, 0, 0, full,
                List.of("evidence://module/" + moduleId));
    }

    private RawDiagnostic symbolDiagnostic(int line, String suffix) {
        return new RawDiagnostic(Phase.COMPILE, "javac", "JAVAC_SYMBOL", "symbol", "error",
                "src/Orders.java:" + line + " cannot find symbol Widget " + suffix,
                "orders", "src/Orders.java", line, 4, "Widget", null,
                "targetdecl:orders", null, "evidence://javac");
    }
}
