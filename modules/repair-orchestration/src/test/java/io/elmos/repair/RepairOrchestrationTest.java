package io.elmos.repair;

import io.elmos.repair.RepairModels.*;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class RepairOrchestrationTest {
    private static final String HASH_A = "a".repeat(64);
    private static final String HASH_B = "b".repeat(64);
    private static final String HASH_C = "c".repeat(64);

    @Test
    void failuresAreRedactedNormalizedAndClusteredWithoutVolatileLineNumbers() {
        FailureNormalizer normalizer = new FailureNormalizer();
        Failure first = normalizer.normalize(new RawFailure("build-1", Stage.COMPILE, "orders", 1,
                "/Users/alice/repo/A.java:42: cannot find symbol Widget token=super-secret", Map.of()));
        Failure second = normalizer.normalize(new RawFailure("build-2", Stage.COMPILE, "orders", 1,
                "/home/runner/repo/A.java:99: cannot find symbol Widget token=another", Map.of()));
        assertEquals(ErrorCategory.MISSING_SYMBOL, first.category());
        assertFalse(first.normalizedMessage().contains("super-secret"));
        assertEquals(first.fingerprint(), second.fingerprint());
        assertEquals(1, normalizer.cluster(List.of(first, second)).size());
        assertEquals(2, normalizer.cluster(List.of(first, second)).getFirst().memberFailureIds().size());
    }

    @Test
    void contextPackExcludesSecretsPrioritizesEvidenceAndMarksRepositoryTextUntrusted() {
        RepairTask task = task(Risk.MEDIUM, 3);
        List<ContextItem> items = List.of(
                new ContextItem("failure", "evidence://failure", HASH_A, 100, 100, false, false),
                new ContextItem("source", "repo://src/A.java", HASH_B, 100, 90, false, true),
                new ContextItem("credential", "secret://token", HASH_C, 10, 1000, true, false),
                new ContextItem("noise", "repo://large.log", HASH_C, 1000, 1, false, true));
        ContextPack pack = new RepairTaskBuilder().pack(task, items, 250);
        assertEquals(List.of("evidence://failure", "repo://src/A.java"), pack.items().stream().map(ContextItem::reference).toList());
        assertTrue(pack.truncated());
        assertTrue(pack.repositoryContentUntrusted());
    }

    @Test
    void routerAppliesResidencyPrivacyToolsRiskContextAndBudgetAsHardFilters() {
        RepairTask task = task(Risk.MEDIUM, 3);
        ProviderProfile ineligible = provider("codex", ProviderType.CODEX, Set.of("US"), false, Set.of("edit"), 1);
        ProviderProfile eligible = provider("claude", ProviderType.CLAUDE, Set.of("CN"), true, Set.of("edit", "search"), 2);
        RoutingDecision decision = new AgentRouter().route(new RoutingRequest(task, true, "CN", Set.of("edit"),
                1024, 5_000, 10_000), List.of(ineligible, eligible));
        assertEquals(RoutingOutcome.ROUTED, decision.outcome());
        assertEquals("claude", decision.providerId());

        RoutingDecision blocked = new AgentRouter().route(new RoutingRequest(task, true, "CN", Set.of("edit"),
                1024, 20_000, 10_000), List.of(eligible));
        assertEquals(RoutingOutcome.BUDGET_BLOCKED, blocked.outcome());
        assertEquals(RoutingOutcome.HUMAN_REQUIRED, new AgentRouter().route(new RoutingRequest(task(Risk.CRITICAL, 1), true,
                "CN", Set.of(), 1, 1, 1), List.of(eligible)).outcome());
    }

    @Test
    void budgetMustBeReservedAndUnknownUsageIsChargedConservatively() {
        BudgetController controller = new BudgetController();
        RepairBudget budget = new RepairBudget("budget-1", 10_000, 5_000, 2_000, 300);
        BudgetReservation reserved = controller.reserve(budget, "task-1", 5_000, 1_000, 500);
        assertEquals(BudgetStatus.RESERVED, reserved.status());
        BudgetReservation settled = controller.settle(reserved, budget, new Usage(0, 0, 0, 20, false));
        assertEquals(BudgetStatus.UNKNOWN_USAGE_CHARGED, settled.status());
        assertEquals(5_000, settled.reservedCostMicros());
        assertEquals(BudgetStatus.REJECTED, controller.reserve(budget, "task-2", 20_000, 1, 1).status());
    }

    @Test
    void providerPlansAreNonInteractiveNetworkDeniedAndNeverMountDockerSocket() {
        List<ProviderCommandPlan> plans = List.of(ProviderPolicies.codex("/task.json"),
                ProviderPolicies.claude("/task.json"), ProviderPolicies.openHands("/task.json"));
        assertTrue(plans.stream().noneMatch(ProviderCommandPlan::networkEnabled));
        assertTrue(plans.stream().noneMatch(ProviderCommandPlan::dockerSocketMounted));
        assertTrue(ProviderPolicies.codex("/task.json").argv().contains("workspace-write"));
        assertTrue(ProviderPolicies.claude("/task.json").deniedCapabilities().contains("secret-read"));
        assertTrue(ProviderPolicies.openHands("/task.json").deniedCapabilities().contains("host-docker-socket"));
    }

    @Test
    void patchCannotEscapeScopeMutateScmOrSelfValidate() {
        RepairTask task = task(Risk.HIGH, 3);
        AgentPatch patch = new AgentPatch(task.taskId(), 1, "codex", HASH_A, HASH_B,
                List.of("src/A.java", "secrets/key.txt"), 20, List.of("git push origin HEAD"),
                true, true, true, "artifact://patch/1");
        PatchReview review = new RepairPolicyEngine().review(task, patch);
        assertFalse(review.allowed());
        assertTrue(review.manualReviewRequired());
        assertTrue(review.findings().containsAll(Set.of("PATCH_OUTSIDE_ALLOWED_SCOPE", "PATCH_DENIED_PATH_CHANGED",
                "SCM_MUTATION_REQUESTED", "COMMAND_NOT_ALLOWLISTED", "TEST_CHANGE_FORBIDDEN",
                "BUILD_CONFIGURATION_CHANGE_FORBIDDEN", "FILE_DELETION_REQUIRES_REVIEW")));
        assertTrue(review.independentValidations().contains("fresh-workspace-build"));
    }

    @Test
    void repairLoopStopsOnSuccessBudgetAndOscillationAndSwitchesOnNoProgress() {
        RepairPolicyEngine engine = new RepairPolicyEngine();
        RepairTask task = task(Risk.MEDIUM, 4);
        VerificationResult success = new VerificationResult(true, true, true, null, 100, List.of("evidence://validation/1"));
        assertEquals(LoopAction.STOP_SUCCESS, engine.next(task, List.of(), success, 1, List.of("codex")).action());
        VerificationResult unevidenced = new VerificationResult(true, true, true, null, 100, List.of());
        assertNotEquals(LoopAction.STOP_SUCCESS, engine.next(task, List.of(), unevidenced, 1, List.of("codex")).action());
        assertEquals(LoopAction.STOP_BUDGET, engine.next(task, List.of(), null, 0, List.of("codex")).action());

        List<AttemptSnapshot> oscillation = List.of(
                attempt(1, "codex", "f1", "f2", HASH_A, 10),
                attempt(2, "codex", "f2", "f3", HASH_B, 20),
                attempt(3, "claude", "f3", "f2", HASH_A, 15));
        assertEquals(LoopAction.STOP_OSCILLATION, engine.next(task, oscillation, null, 100, List.of("codex", "claude")).action());

        List<AttemptSnapshot> stalled = List.of(
                attempt(1, "codex", "f1", "f2", HASH_A, 20),
                attempt(2, "codex", "f2", "f2", HASH_B, 20));
        LoopDecision switched = engine.next(task, stalled, null, 100, List.of("codex", "claude"));
        assertEquals(LoopAction.SWITCH_PROVIDER, switched.action());
        assertEquals("claude", switched.nextProviderId());
    }

    @Test
    void escalationPackageContainsAuditableAttemptsAndRequiredHumanDecisions() {
        RepairTask task = task(Risk.HIGH, 2);
        EscalationPackage value = new RepairPolicyEngine().escalate(task, "MAXIMUM_ATTEMPTS_REACHED",
                List.of(attempt(1, "codex", "f1", "f2", HASH_A, 10), attempt(2, "claude", "f2", "f3", HASH_B, 20)),
                List.of("artifact://patch/1"), List.of("evidence://validation/1"), 9000);
        assertEquals(List.of("codex", "claude"), value.attemptedProviders());
        assertEquals(3, value.requiredHumanDecisions().size());
    }

    private static RepairTask task(Risk risk, int attempts) {
        FailureCluster cluster = new FailureCluster("cluster-1", HASH_A, "failure-1", List.of("failure-1"),
                ErrorCategory.MISSING_SYMBOL, Stage.COMPILE, "orders");
        RepairScope scope = new RepairScope(Set.of("src/"), Set.of("secrets/"), Set.of("mvn", "./mvnw"),
                5, 100, false, false);
        return new RepairTaskBuilder().build(cluster, scope, risk, attempts, Instant.parse("2026-07-21T00:00:00Z"));
    }

    private static ProviderProfile provider(String id, ProviderType type, Set<String> residences, boolean privateRepos,
                                            Set<String> tools, int priority) {
        return new ProviderProfile(id, type, true, residences, privateRepos, tools, Set.of(Risk.LOW, Risk.MEDIUM),
                10_000, 10_000, priority);
    }

    private static AttemptSnapshot attempt(int number, String provider, String before, String after, String tree, int score) {
        return new AttemptSnapshot(number, provider, before, after, tree, score, List.of("src/A.java"));
    }
}
