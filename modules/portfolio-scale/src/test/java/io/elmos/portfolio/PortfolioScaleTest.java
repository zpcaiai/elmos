package io.elmos.portfolio;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static io.elmos.portfolio.PortfolioScaleModels.*;
import static org.junit.jupiter.api.Assertions.*;

class PortfolioScaleTest {
    @Test void inventoryRejectsDuplicateRepositoriesAndUnknownEdges() {
        RepositoryAsset a = repository("a", "tenant-a", RepositoryStatus.ACTIVE, "java", 1000);
        assertThrows(IllegalArgumentException.class, () -> snapshot(List.of(a, a), List.of()));
        Dependency unknown = new Dependency("e1", "a", "missing", "build", Criticality.P0, 1.0, List.of("pom.xml"));
        assertThrows(IllegalArgumentException.class, () -> snapshot(List.of(a), List.of(unknown)));
    }

    @Test void plannerCreatesStableDependencyOrderedUnitsAndExposesIncompleteScope() {
        RepositoryAsset provider = repository("provider", "tenant-a", RepositoryStatus.ACTIVE, "maven", 500);
        RepositoryAsset consumer = repository("consumer", "tenant-a", RepositoryStatus.ACTIVE, "maven", 1500);
        Dependency edge = new Dependency("e1", "consumer", "provider", "build", Criticality.P0, 1.0, List.of("pom.xml"));
        PortfolioSnapshot first = new PortfolioSnapshot("s1", "sha256:snapshot", 3, List.of(consumer, provider), List.of(), List.of(edge));
        PlanningResult plan = new PortfolioPlanner().plan(first);
        assertEquals(2d / 3d, plan.inventoryCoverage());
        assertTrue(plan.blockers().contains("INVENTORY_SCOPE_INCOMPLETE:1"));
        assertEquals("provider", plan.workUnits().getFirst().repositoryId());
        assertEquals(plan.workUnits().getFirst().id(), plan.workUnits().get(1).dependsOn().getFirst());
        assertEquals(plan.workUnits(), new PortfolioPlanner().plan(first).workUnits());
    }

    @Test void inaccessibleRepositoryStaysVisibleAndBlocksExecution() {
        PortfolioSnapshot inventory = new PortfolioSnapshot("s1", "sha256:snapshot", 2,
                List.of(repository("active", "tenant-a", RepositoryStatus.ACTIVE, "maven", 10)),
                List.of(new UnreachableAsset("secret/repo", "ACCESS_DENIED", "security-team")), List.of());
        PlanningResult result = new PortfolioPlanner().plan(inventory);
        assertFalse(result.executable());
        assertTrue(result.blockers().stream().anyMatch(value -> value.startsWith("REPOSITORY_UNREACHABLE:")));
    }

    @Test void schedulerEnforcesTenantRegionAttestationToolchainAndCapacity() {
        WorkUnit java = unit("java", "tenant-a", "maven", 1000, List.of());
        WorkUnit python = unit("python", "tenant-b", "pip", 2000, List.of());
        List<Runner> runners = List.of(
                new Runner("wrong-tenant", "tenant-b", "cn-east", true, Set.of("maven"), 5000),
                new Runner("unattested", "tenant-a", "cn-east", false, Set.of("maven"), 5000),
                new Runner("java-runner", "tenant-a", "cn-east", true, Set.of("maven"), 5000),
                new Runner("small-python", "tenant-b", "cn-east", true, Set.of("pip"), 1000));
        SchedulingResult result = new HardConstraintScheduler().scheduleWave(List.of(java, python), runners);
        assertEquals(List.of(new Assignment("java", "java-runner")), result.assignments());
        assertEquals(List.of("python"), result.unscheduledWorkUnitIds());
    }

    @Test void workflowRetriesWithinBoundAndDeduplicatesExternalEffects() {
        DurableWorkflowEngine engine = new DurableWorkflowEngine();
        TaskRequest request = new TaskRequest("task-1", "tenant-a", "wu-a", "idem-a", "sha256:input", 3, true);
        AtomicInteger activityRuns = new AtomicInteger();
        Set<String> appliedTokens = new java.util.HashSet<>();
        TaskOutcome first = engine.execute(request, (attempt, checkpoint) -> {
            activityRuns.incrementAndGet();
            return attempt < 2 ? ActivityResult.failure("state-" + attempt, "TRANSIENT")
                    : ActivityResult.success("state-2", "sha256:output");
        }, token -> assertTrue(appliedTokens.add(token)));
        assertEquals(TaskStatus.SUCCEEDED, first.status());
        assertEquals(2, first.attempts());
        assertEquals(1, appliedTokens.size());
        TaskOutcome replay = engine.execute(request, (attempt, checkpoint) -> fail("activity must not rerun"),
                token -> fail("external effect must not repeat"));
        assertTrue(replay.replayed());
        assertEquals(2, activityRuns.get());
        TaskRequest conflict = new TaskRequest("task-2", "tenant-a", "wu-a", "idem-a", "sha256:different", 1, false);
        assertThrows(IllegalStateException.class, () -> engine.execute(conflict,
                (attempt, checkpoint) -> ActivityResult.success("s", "o"), null));
    }

    @Test void workflowSnapshotRestoresCommitTokensAndOutcomes() {
        DurableWorkflowEngine first = new DurableWorkflowEngine();
        TaskRequest request = new TaskRequest("task-1", "tenant-a", "wu-a", "idem-a", "sha256:input", 1, true);
        first.execute(request, (attempt, checkpoint) -> ActivityResult.success("state", "output"), token -> {});
        DurableWorkflowEngine restored = DurableWorkflowEngine.restore(first.snapshot());
        TaskOutcome replay = restored.execute(request, (attempt, checkpoint) -> fail("must replay"), token -> fail("must not duplicate"));
        assertTrue(replay.replayed());
        assertTrue(replay.externalEffectApplied());
    }

    @Test void cacheRequiresCompleteManifestDigestAndTenantTrustIsolation() {
        TenantContentAddressedCache cache = new TenantContentAddressedCache();
        byte[] bytes = "artifact".getBytes(StandardCharsets.UTF_8);
        var manifest = new TenantContentAddressedCache.InputManifest("source", "deps", "toolchain", "profile", "policy", "env", "generator");
        var ref = cache.put("tenant-a", "trust-a", manifest, bytes, TenantContentAddressedCache.digest(bytes), true);
        assertArrayEquals(bytes, cache.get("tenant-a", "trust-a", ref).orElseThrow());
        assertTrue(cache.get("tenant-b", "trust-a", ref).isEmpty());
        assertTrue(cache.get("tenant-a", "trust-b", ref).isEmpty());
        assertThrows(IllegalArgumentException.class, () -> cache.put("tenant-a", "trust-a", manifest,
                bytes, "sha256:wrong", true));
        assertThrows(IllegalArgumentException.class, () -> cache.put("tenant-a", "trust-a", manifest,
                bytes, TenantContentAddressedCache.digest(bytes), false));
    }

    @Test void campaignIsDependencyAwareBudgetBoundedAndApprovalGated() {
        WorkUnit provider = unit("provider", "tenant-a", "maven", 1000, List.of());
        WorkUnit consumer = unit("consumer", "tenant-a", "maven", 2000, List.of("provider"));
        PortfolioCampaignCoordinator coordinator = new PortfolioCampaignCoordinator();
        Campaign blocked = new Campaign("c1", List.of(consumer, provider), 2, 2,
                Set.of("security", "portfolio-owner"), Set.of("portfolio-owner"));
        CampaignDecision decision = coordinator.plan(blocked);
        assertEquals(CampaignStatus.BLOCKED, decision.status());
        assertEquals(List.of(List.of("provider"), List.of("consumer")), decision.waves());
        assertTrue(decision.blockers().stream().anyMatch(value -> value.startsWith("MISSING_APPROVALS:")));
        assertTrue(decision.blockers().stream().anyMatch(value -> value.startsWith("BUDGET_EXCEEDED:")));
        Campaign ready = new Campaign("c2", List.of(consumer, provider), 2, 3,
                Set.of("security"), Set.of("security"));
        assertEquals(CampaignStatus.READY, coordinator.plan(ready).status());
    }

    @Test void workflowFailureIsBoundedAndCheckpointed() {
        DurableWorkflowEngine engine = new DurableWorkflowEngine();
        AtomicInteger runs = new AtomicInteger();
        TaskOutcome outcome = engine.execute(new TaskRequest("t", "tenant", "wu", "idem", "input", 3, false),
                (attempt, checkpoint) -> { runs.incrementAndGet(); return ActivityResult.failure("state-" + attempt, "DOWN"); }, null);
        assertEquals(TaskStatus.FAILED, outcome.status());
        assertEquals(3, runs.get());
        assertEquals(3, engine.snapshot().checkpoints().get("t").attempt());
    }

    private static RepositoryAsset repository(String id, String tenant, RepositoryStatus status, String toolchain, long loc) {
        return new RepositoryAsset(id, tenant, "team-" + id, Set.of("cn-east"), Set.of(toolchain), loc,
                status, Criticality.P1, List.of("inventory.json"));
    }

    private static PortfolioSnapshot snapshot(List<RepositoryAsset> repositories, List<Dependency> dependencies) {
        return new PortfolioSnapshot("s1", "sha256:snapshot", repositories.size(), repositories, List.of(), dependencies);
    }

    private static WorkUnit unit(String id, String tenant, String toolchain, long loc, List<String> dependencies) {
        return new WorkUnit(id, tenant, "team", "repo-" + id, Set.of("cn-east"), toolchain, loc,
                Criticality.P1, dependencies, "partition-" + id, new ArrayList<>());
    }
}
