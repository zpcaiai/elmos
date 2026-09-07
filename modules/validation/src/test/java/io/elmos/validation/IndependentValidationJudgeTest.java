package io.elmos.validation;

import io.elmos.validation.ValidationModels.*;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class IndependentValidationJudgeTest {
    private final IndependentValidationJudge judge = new IndependentValidationJudge();

    @Test
    void existingBuildAndTestFailureIsPreservedWithoutBecomingMigrationRegression() {
        DomainResult build = judge.compareBuild(build(Status.FAIL), build(Status.FAIL));
        assertEquals(Status.PASS, build.status());
        assertTrue(build.findings().stream().anyMatch(value -> value.code().startsWith("BASELINE_FAILURE_PRESERVED")));
        TestCase before = test(TestStatus.FAILED, "same");
        TestCase after = test(TestStatus.FAILED, "same");
        assertEquals(Status.PASS, judge.compareTests(List.of(before), List.of(after), List.of("evidence://tests")).status());
    }

    @Test
    void missingOrSilentlySkippedTestIsNeverPass() {
        TestCase original = test(TestStatus.PASSED, null);
        assertEquals(Status.FAIL, judge.compareTests(List.of(original), List.of()).status());
        assertTrue(judge.compareTests(List.of(original), List.of(test(TestStatus.SKIPPED, null))).findings().stream()
                .anyMatch(value -> value.code().startsWith("TEST_SILENTLY_SKIPPED")));
    }

    @Test
    void baselineAndMigratedWorkspacesAndContainersMustBeIndependentPinnedAndNonReusable() {
        Environment baseline = environment("baseline", "workspace-baseline", false, "sha256:" + "d".repeat(64));
        Environment migrated = environment("migrated", "workspace-migrated", false, "sha256:" + "d".repeat(64));
        assertEquals(Status.PASS, judge.compareEnvironments(baseline, migrated).status());
        Environment reused = environment("migrated", "workspace-baseline", true, "postgres:latest");
        DomainResult result = judge.compareEnvironments(baseline, reused);
        assertEquals(Status.FAIL, result.status());
        assertTrue(result.findings().stream().map(Finding::code).anyMatch("TESTCONTAINERS_REUSE_FORBIDDEN"::equals));
        assertTrue(result.findings().stream().map(Finding::code).anyMatch("TESTCONTAINERS_IMAGE_NOT_PINNED"::equals));
    }

    @Test
    void httpRequiredRequestFieldAdditionIsBreaking() {
        HttpContract baseline = new HttpContract(Map.of("POST /orders", new HttpOperation(Set.of("sku"), Set.of("id"), Set.of("oauth2"))));
        HttpContract migrated = new HttpContract(Map.of("POST /orders", new HttpOperation(Set.of("sku", "tenant"), Set.of("id"), Set.of("oauth2"))));
        assertCritical(judge.compareHttp(baseline, migrated), "HTTP_REQUEST_REQUIRED_FIELD_ADDED");
    }

    @Test
    void javaBinaryRemovalIsCritical() {
        assertCritical(judge.compareJava(new JavaApi(Set.of("A#m()V"), Set.of("A.m()")),
                new JavaApi(Set.of(), Set.of("A.m()"))), "JAVA_BINARY_API_REMOVED");
    }

    @Test
    void jsonDateFormatChangeIsCritical() {
        SerializationContract before = serialization(Map.of("createdAt", "date-time"));
        SerializationContract after = serialization(Map.of("createdAt", "yyyy/MM/dd"));
        assertCritical(judge.compareSerialization(before, after, Domain.SERIALIZATION), "SERIALIZATION_FORMAT_CHANGED");
    }

    @Test
    void databaseNullableTighteningIsCriticalAndRenameIsNotGuessed() {
        DatabaseSchema before = new DatabaseSchema(Map.of("orders.note", new Column("varchar", true, null)), Set.of(), Set.of());
        DatabaseSchema after = new DatabaseSchema(Map.of("orders.memo", new Column("varchar", false, null)), Set.of(), Set.of());
        DomainResult result = judge.compareDatabase(before, after);
        assertEquals(Status.FAIL, result.status());
        assertTrue(result.findings().stream().map(Finding::code).anyMatch("DATABASE_RENAME_REQUIRES_CONFIRMATION"::equals));
        assertTrue(result.findings().stream().anyMatch(value -> value.code().startsWith("DATABASE_COLUMN_REMOVED")));
    }

    @Test
    void transactionRollbackBecomingCommitIsCriticalAndTestManagedTransactionIsInsufficient() {
        TransactionObservation before = transaction(false, true, false);
        TransactionObservation after = transaction(true, false, true);
        DomainResult result = judge.compareTransactions(List.of(before), List.of(after));
        assertCritical(result, "TRANSACTION_ROLLBACK_CHANGED_TO_COMMIT");
        assertTrue(result.findings().stream().map(Finding::code).anyMatch(code -> code.startsWith("TRANSACTION_TEST_MANAGED_EVIDENCE_INSUFFICIENT")));
    }

    @Test
    void performanceNoiseWarnsButSevereStableP99RegressionFails() {
        PerformanceSample stable = performance(List.of(100d, 100d, 100d, 100d, 100d, 100d, 100d));
        PerformanceSample mild = performance(List.of(102d, 103d, 104d, 103d, 102d, 104d, 103d));
        assertEquals(Status.PASS_WITH_WARNINGS, judge.comparePerformance(stable, mild, .02, .20, .20,
                List.of("evidence://performance")).status());
        PerformanceSample severe = performance(List.of(150d, 151d, 149d, 150d, 150d, 151d, 149d));
        assertCritical(judge.comparePerformance(stable, severe, .05, .20, .20), "PERFORMANCE_LATENCY_REGRESSION");
    }

    @Test
    void aggregateFailsClosedOnMissingDomainAndCriticalFinding() {
        Environment baseline = environment("baseline", "workspace-baseline", false, "sha256:" + "d".repeat(64));
        Environment migrated = environment("migrated", "workspace-migrated", false, "sha256:" + "d".repeat(64));
        ValidationPolicy policy = new ValidationPolicy("quality-v1", EnumSet.of(Domain.ENVIRONMENT, Domain.BUILD, Domain.TEST),
                Set.of(), Set.of(), .8);
        ValidationDecision missing = judge.aggregate(policy, baseline, migrated,
                List.of(judge.compareEnvironments(baseline, migrated), judge.compareBuild(build(Status.PASS), build(Status.PASS))),
                Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(Status.FAIL, missing.status());
        assertTrue(missing.blockingReasons().contains("VALIDATION_EVIDENCE_MISSING:TEST"));

        DomainResult critical = judge.compareTests(List.of(test(TestStatus.PASSED, null)), List.of(test(TestStatus.FAILED, "new")));
        ValidationDecision failed = judge.aggregate(policy, baseline, migrated,
                List.of(judge.compareEnvironments(baseline, migrated), judge.compareBuild(build(Status.PASS), build(Status.PASS)), critical),
                Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(Status.FAIL, failed.status());
    }

    @Test
    void successfulComparisonWithoutEvidenceIsInconclusiveAndCannotBeAggregated() {
        TestCase test = test(TestStatus.PASSED, null);
        DomainResult unbound = judge.compareTests(List.of(test), List.of(test));
        assertEquals(Status.INCONCLUSIVE, unbound.status());
        assertEquals(0, unbound.confidence());

        Environment baseline = environment("baseline", "workspace-baseline", false, "sha256:" + "d".repeat(64));
        Environment migrated = environment("migrated", "workspace-migrated", false, "sha256:" + "d".repeat(64));
        ValidationPolicy policy = new ValidationPolicy("quality-v1", EnumSet.of(Domain.TEST), Set.of(), Set.of(), .8);
        ValidationDecision decision = judge.aggregate(policy, baseline, migrated, List.of(unbound),
                Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(Status.FAIL, decision.status());
        assertTrue(decision.blockingReasons().contains("VALIDATION_EVIDENCE_MISSING:TEST"));
    }

    @Test
    void requiredDomainFailureAndDuplicateDomainCannotBeHiddenByAggregation() {
        Environment baseline = environment("baseline", "workspace-baseline", false, "sha256:" + "d".repeat(64));
        Environment migrated = new Environment("migrated", "workspace-migrated", "snapshot-migrated", "deadbeef",
                "sha256:" + "a".repeat(64), "gradle-9", Map.of("postgres", "sha256:" + "d".repeat(64)),
                false, "deny-v1", "sha256:" + "b".repeat(64));
        DomainResult failedEnvironment = judge.compareEnvironments(baseline, migrated);
        assertEquals(Status.FAIL, failedEnvironment.status());
        ValidationPolicy policy = new ValidationPolicy("quality-v1", EnumSet.of(Domain.ENVIRONMENT), Set.of(), Set.of(), .8);
        ValidationDecision decision = judge.aggregate(policy, baseline, migrated, List.of(failedEnvironment),
                Instant.parse("2026-07-21T00:00:00Z"));
        assertEquals(Status.FAIL, decision.status());
        assertTrue(decision.blockingReasons().contains("VALIDATION_DOMAIN_FAILED:ENVIRONMENT"));
        assertThrows(IllegalArgumentException.class, () -> judge.aggregate(policy, baseline, migrated,
                List.of(failedEnvironment, failedEnvironment), Instant.parse("2026-07-21T00:00:00Z")));
    }

    private static Environment environment(String id, String workspace, boolean reuse, String image) {
        return new Environment(id, workspace, "snapshot-" + id, "deadbeef", "sha256:" + "a".repeat(64), "maven-3.9.11",
                Map.of("postgres", image), reuse, "deny-v1", "sha256:" + "b".repeat(64));
    }
    private static BuildSnapshot build(Status status) {
        return new BuildSnapshot("env", Map.of("compile", status), Set.of(), Set.of(), "c".repeat(64), true, List.of("evidence://build"));
    }
    private static TestCase test(TestStatus status, String fingerprint) {
        return new TestCase("junit", "OrderTest", "createsOrder", "", status, fingerprint, 10, false);
    }
    private static SerializationContract serialization(Map<String,String> formats) {
        return new SerializationContract(Set.of("createdAt"), formats, Set.of("OPEN"), Map.of());
    }
    private static TransactionObservation transaction(boolean committed, boolean rolledBack, boolean managed) {
        return new TransactionObservation("checkout", committed, rolledBack, "REQUIRED", "READ_COMMITTED", 1, false, managed, "d".repeat(64));
    }
    private static PerformanceSample performance(List<Double> values) {
        return new PerformanceSample("orders", values, 10, 1, 1024, "perf-env");
    }
    private static void assertCritical(DomainResult result, String prefix) {
        assertEquals(Status.FAIL, result.status());
        assertTrue(result.findings().stream().anyMatch(value -> value.code().startsWith(prefix) && value.severity() == Severity.CRITICAL));
    }
}
