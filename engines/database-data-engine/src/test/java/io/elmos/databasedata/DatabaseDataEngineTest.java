package io.elmos.databasedata;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static io.elmos.databasedata.DatabaseDataModels.*;
import static org.junit.jupiter.api.Assertions.*;

class DatabaseDataEngineTest {
    @Test void declaresThreeTracksAndSeparateUnconfiguredRunners() {
        var engine = new DatabaseDataEngineService();
        var capabilities = engine.capabilities();
        assertEquals("ELMOS_DATABASE_DATA", capabilities.engineName());
        assertEquals(List.of("OLTP_DATABASE", "ANALYTICS_PLATFORM", "BI_SEMANTIC"),
                capabilities.solutionFormats());
        assertEquals(6, capabilities.runnerProfiles().size());
        assertEquals("RUNNER_REQUIRED_FAIL_CLOSED",
                capabilities.sandboxRequirements().get("customerCodeExecution"));
    }

    @Test void discoveryAndExecutionFailClosedWithoutFabricatedEvidence() {
        var engine = new DatabaseDataEngineService();
        var request = request("scan-1", "ORACLE");
        var scan = engine.scan(request);
        assertEquals(EngineApi.JobStatus.FAILED, scan.status());
        assertEquals(EngineApi.ErrorCode.DATABASE_RUNNER_REQUIRED, scan.error().errorCode());
        assertTrue(scan.evidenceRefs().isEmpty());
        assertEquals(false, scan.result().get("customerCodeExecuted"));

        var step = new EngineApi.ExecuteStepRequest("org-1", "run-1", 1,
                new EngineApi.StepDefinition("cdc-1", EngineApi.ExecutorType.DATABASE_CDC,
                        java.util.Map.of()), "workspace-1", "commit-1",
                new EngineApi.ExecutionBudget(60, 60, 1024, 0), java.util.Map.of(),
                "corr-1", "execute-1");
        var result = engine.executeStep(step);
        assertEquals(EngineApi.ErrorCode.DATABASE_CDC_PERMISSION_REQUIRED, result.error().errorCode());
        assertTrue(result.evidenceRefs().isEmpty());
    }

    @Test void idempotencyIsTenantScopedAndChangedInputIsRejected() {
        var engine = new DatabaseDataEngineService();
        var first = engine.scan(request("same", "ORACLE"));
        assertSame(first, engine.scan(request("same", "ORACLE")));
        assertThrows(EngineApi.IdempotencyConflictException.class, () -> engine.scan(request("same", "MYSQL")));
        assertThrows(EngineApi.JobNotFoundException.class, () -> engine.job("org-2", first.jobId()));
        assertThrows(EngineApi.JobConflictException.class, () -> engine.cancel("org-1", first.jobId()));
        assertSame(first, engine.job("org-1", first.jobId()));
    }

    @Test void discoveryPermissionsAreReadOnlyAndWritesRequireApproval() {
        var registry = new VendorRunnerRegistry();
        for (var profile : registry.all().values()) {
            assertEquals(RunnerStatus.NOT_CONFIGURED, profile.status());
            assertTrue(profile.productionApprovalRequired());
            assertEquals(Set.of("METADATA_READ", "CATALOG_READ", "PLAN_READ", "PERFORMANCE_VIEW_READ"),
                    profile.discoveryPermissions());
            assertTrue(profile.productionCapabilities().contains("WRITER_CUTOVER"));
        }
    }

    @Test void plannerProducesIndependentOltpAnalyticsAndBiCandidates() {
        var estate = new EstateProfile("estate-1", DatabaseVendor.ORACLE, Set.of("spatial"),
                true, true, false, true, List.of("evidence://estate"));
        var candidates = new DatabaseTargetPlanner().candidates(estate);
        assertTrue(candidates.stream().anyMatch(value -> value.track() == ModernizationTrack.OLTP_DATABASE));
        assertTrue(candidates.stream().anyMatch(value -> value.track() == ModernizationTrack.ANALYTICS_PLATFORM));
        assertTrue(candidates.stream().anyMatch(value -> value.track() == ModernizationTrack.BI_SEMANTIC));
        assertTrue(candidates.stream().anyMatch(value -> value.strategy() == Strategy.IN_PLACE_UPGRADE));
        assertTrue(candidates.stream().anyMatch(value -> value.strategy() == Strategy.HETEROGENEOUS_REPLATFORM));
    }

    @Test void cutoverAggregatesDataPerformanceBiGovernanceWriterAndRollbackGates() {
        var evidence = passingEvidence(null);
        var withoutApproval = new DatabaseCutoverAdjudicator().evaluate(evidence);
        assertEquals(CutoverStatus.CUTOVER_READY_WITH_CONDITIONS, withoutApproval.status());
        assertFalse(withoutApproval.automatic());

        var approved = new DatabaseCutoverAdjudicator().evaluate(passingEvidence("dba-owner"));
        assertEquals(CutoverStatus.CUTOVER_READY, approved.status());
        var blocked = new DatabaseCutoverAdjudicator().evaluate(new CutoverEvidence(
                true, true, true, true, true, true, true, false, true, true, false,
                true, false, true, true, true, "dba-owner", List.of("ev")));
        assertEquals(CutoverStatus.CUTOVER_BLOCKED, blocked.status());
        assertTrue(blocked.blockers().contains("QUERY_PERFORMANCE_FAILED"));
        assertTrue(blocked.blockers().contains("BI_SECURITY_FAILED"));
        assertTrue(blocked.blockers().contains("WRITER_INVENTORY_FAILED"));
    }

    @Test void lifecycleCannotSkipReadAndWriteCutoverStates() {
        var lifecycle = new DatabaseMigrationLifecycle();
        assertEquals(MigrationState.WORKLOAD_BASELINING,
                lifecycle.advance(MigrationState.DISCOVERY, MigrationState.WORKLOAD_BASELINING));
        assertThrows(IllegalStateException.class,
                () -> lifecycle.advance(MigrationState.RECONCILING, MigrationState.WRITE_CUTOVER));
    }

    @Test void canonicalConversionPipelineCannotBeStringReplacement() {
        assertEquals(List.of("VENDOR_PARSER", "VENDOR_AST", "CANONICAL_IR", "TARGET_AST", "TARGET_SQL"),
                new DatabaseModernizationPolicy().canonicalIrStages());
    }

    private EngineApi.JobRequest request(String key, String profile) {
        return new EngineApi.JobRequest("org-1", "snapshot-1", "workspace-1",
                profile, "corr-1", key);
    }

    private CutoverEvidence passingEvidence(String approvedBy) {
        return new CutoverEvidence(true, true, true, true, true, true, true, true,
                true, true, true, true, true, true, true, true, approvedBy, List.of("ev-1"));
    }
}
