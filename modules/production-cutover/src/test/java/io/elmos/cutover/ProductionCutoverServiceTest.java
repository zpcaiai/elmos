package io.elmos.cutover;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;

import static io.elmos.cutover.ProductionCutoverModels.*;
import static org.junit.jupiter.api.Assertions.*;

class ProductionCutoverServiceTest {
    private static final String DIGEST = "c".repeat(64);
    private static final String TARGET = "target-artifact";
    private static final String RUN = "cutover-run";
    private static final Instant NOW = Instant.parse("2026-07-21T02:00:00Z");
    @TempDir Path temp;

    @Test void completeProductionEvidenceReachesCgAndClosesMigration() {
        Outcome outcome = evaluate(request(Phase.P12_DECOMMISSIONED, true, "P_F"), Evidence.good(Phase.P12_DECOMMISSIONED));
        assertEquals(Gate.C_G, outcome.report().gate());
        assertEquals(RunStatus.COMPLETED, outcome.report().status());
        assertTrue(outcome.report().targetSystemOfRecord());
        assertTrue(outcome.report().legacySystemDecommissioned());
        assertTrue(outcome.report().migrationCompleted());
    }

    @Test void batch10AdmissionIsMandatory() {
        Request invalid = request(Phase.P0_PREPARED, false, "P_F");
        assertThrows(IllegalArgumentException.class, () -> evaluate(invalid, Evidence.good(Phase.P0_PREPARED)));
    }

    @Test void targetMustHavePeOrPfProgressiveEligibility() {
        Request invalid = request(Phase.P0_PREPARED, true, "P_D");
        assertThrows(IllegalArgumentException.class, () -> evaluate(invalid, Evidence.good(Phase.P0_PREPARED)));
    }

    @Test void declaredAndObservedPhaseMismatchFailsClosed() {
        Request request = request(Phase.P8_TARGET_WRITE_PRIMARY, true, "P_F");
        Evidence evidence = Evidence.good(Phase.P7_WRITE_CANARY);
        Outcome outcome = evaluate(request, evidence);
        assertEquals(RunStatus.BLOCKED, outcome.report().status());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("declared phase")));
    }

    @Test void authorityFailureDoesNotPersistSecretExceptionText() {
        Request request = request(Phase.P0_PREPARED, true, "P_F");
        Evidence evidence = Evidence.good(Phase.P0_PREPARED);
        ProductionCutoverAuthorities ports = authorities(evidence);
        ports = new ProductionCutoverAuthorities(ports.topologySchema(),
                ignored -> { throw new IllegalStateException("credential=secret"); }, ports.traffic(),
                ports.integrations(), ports.rollbackIncident(), ports.hypercareAcceptance(), ports.retirement());
        Outcome outcome = new ProductionCutoverService(ports).evaluate(request);
        assertTrue(outcome.report().blockers().contains("data migration authority failed safely: IllegalStateException"));
        assertTrue(outcome.report().blockers().stream().noneMatch(value -> value.contains("credential=secret")));
    }

    @Test void unknownCallerBlocksCa() {
        Evidence good = Evidence.good(Phase.P0_PREPARED);
        Evidence bad = good.withTopology(topology(1, false));
        assertEquals(Gate.BLOCKED, evaluate(request(Phase.P0_PREPARED, true, "P_F"), bad).report().gate());
    }

    @Test void prematureSchemaContractBlocksCa() {
        Evidence good = Evidence.good(Phase.P0_PREPARED);
        Evidence bad = good.withTopology(topology(0, true));
        assertEquals(Gate.BLOCKED, evaluate(request(Phase.P0_PREPARED, true, "P_F"), bad).report().gate());
    }

    @Test void incompleteAuthoritativeBackfillBlocksCb() {
        Evidence good = Evidence.good(Phase.P4_SHADOW_READ);
        Evidence bad = good.withData(data(0, false, "position-1", 0));
        assertEquals(Gate.C_A, evaluate(request(Phase.P4_SHADOW_READ, true, "P_F"), bad).report().gate());
    }

    @Test void cdcLagBeyondPolicyBlocksCb() {
        Evidence good = Evidence.good(Phase.P4_SHADOW_READ);
        Evidence bad = good.withData(data(31, true, "position-1", 0));
        assertEquals(Gate.C_A, evaluate(request(Phase.P4_SHADOW_READ, true, "P_F"), bad).report().gate());
    }

    @Test void criticalDualReadDifferenceBlocksCb() {
        Evidence good = Evidence.good(Phase.P4_SHADOW_READ);
        Evidence bad = good.withTraffic(traffic(Phase.P4_SHADOW_READ, 100, 100, 0, 1, 0, false, true));
        assertEquals(Gate.C_A, evaluate(request(Phase.P4_SHADOW_READ, true, "P_F"), bad).report().gate());
    }

    @Test void readPrimaryMustReachOneHundredPercentBeforeCc() {
        Evidence good = Evidence.good(Phase.P6_TARGET_READ_PRIMARY);
        Evidence bad = good.withTraffic(traffic(Phase.P6_TARGET_READ_PRIMARY, 95, 0, 1, 0, 0, false, true));
        assertEquals(Gate.C_B, evaluate(request(Phase.P6_TARGET_READ_PRIMARY, true, "P_F"), bad).report().gate());
    }

    @Test void dualPrimaryWriterBlocksCc() {
        Request base = request(Phase.P6_TARGET_READ_PRIMARY, true, "P_F");
        AggregateAuthority authority = new AggregateAuthority("Order", "tenant-a", base.currentPhase(),
                SystemRole.TARGET, SystemRole.TARGET, SystemRole.SOURCE, "tenant-id", 1,
                true, true, true, false, List.of("authority-evidence"));
        Request invalidState = copy(base, base.currentPhase(), List.of(authority));
        Evidence bad = Evidence.good(base.currentPhase()).withTraffic(
                traffic(base.currentPhase(), 100, 0, 1, 0, 1, false, true));
        assertEquals(Gate.C_B, evaluate(invalidState, bad).report().gate());
    }

    @Test void finalPositionMismatchBlocksCd() {
        Evidence good = Evidence.good(Phase.P7_WRITE_CANARY);
        Evidence bad = good.withData(data(0, true, "different-position", 0));
        assertEquals(Gate.C_C, evaluate(request(Phase.P7_WRITE_CANARY, true, "P_F"), bad).report().gate());
    }

    @Test void messageLossBlocksCd() {
        Evidence good = Evidence.good(Phase.P7_WRITE_CANARY);
        Evidence bad = good.withIntegration(integration(1, 0, 0));
        assertEquals(Gate.C_C, evaluate(request(Phase.P7_WRITE_CANARY, true, "P_F"), bad).report().gate());
    }

    @Test void sourceWritesBlockCe() {
        Evidence good = Evidence.good(Phase.P8_TARGET_WRITE_PRIMARY);
        Evidence bad = good.withTraffic(traffic(Phase.P8_TARGET_WRITE_PRIMARY, 100, 100, 1, 0, 0, false, true));
        assertEquals(Gate.C_D, evaluate(request(Phase.P8_TARGET_WRITE_PRIMARY, true, "P_F"), bad).report().gate());
    }

    @Test void unapprovedIrreversibilityFrontierBlocksCe() {
        Evidence good = Evidence.good(Phase.P8_TARGET_WRITE_PRIMARY);
        Evidence bad = good.withTraffic(traffic(Phase.P8_TARGET_WRITE_PRIMARY, 100, 100, 0, 0, 0, true, false));
        assertEquals(Gate.C_D, evaluate(request(Phase.P8_TARGET_WRITE_PRIMARY, true, "P_F"), bad).report().gate());
    }

    @Test void shortHypercareBlocksCf() {
        Evidence good = Evidence.good(Phase.P10_HYPERCARE);
        Evidence bad = good.withAcceptance(acceptance(3, ApprovalStatus.ACCEPTED));
        assertEquals(Gate.C_E, evaluate(request(Phase.P10_HYPERCARE, true, "P_F"), bad).report().gate());
    }

    @Test void unverifiedArchiveRestoreBlocksCf() {
        Evidence good = Evidence.good(Phase.P10_HYPERCARE);
        Evidence bad = good.withRetirement(retirement(false, true, true));
        assertEquals(Gate.C_E, evaluate(request(Phase.P10_HYPERCARE, true, "P_F"), bad).report().gate());
    }

    @Test void missingSecurityAcceptanceBlocksCg() {
        Evidence good = Evidence.good(Phase.P12_DECOMMISSIONED);
        Evidence bad = good.withAcceptance(acceptance(7, ApprovalStatus.PENDING));
        assertEquals(Gate.C_F, evaluate(request(Phase.P12_DECOMMISSIONED, true, "P_F"), bad).report().gate());
    }

    @Test void credentialsMustBeRevokedForCg() {
        Evidence good = Evidence.good(Phase.P12_DECOMMISSIONED);
        Evidence bad = good.withRetirement(retirement(true, false, true));
        Outcome outcome = evaluate(request(Phase.P12_DECOMMISSIONED, true, "P_F"), bad);
        assertEquals(Gate.C_F, outcome.report().gate());
        assertFalse(outcome.report().migrationCompleted());
    }

    @Test void decommissionMustBeExecutedByExternalAuthorityForCg() {
        Evidence good = Evidence.good(Phase.P12_DECOMMISSIONED);
        Evidence bad = good.withRetirement(retirement(true, true, false));
        assertEquals(Gate.C_F, evaluate(request(Phase.P12_DECOMMISSIONED, true, "P_F"), bad).report().gate());
    }

    @Test void wrongArtifactEvidenceFailsClosed() {
        Evidence good = Evidence.good(Phase.P0_PREPARED);
        TopologySchemaEvidence top = good.topology();
        Evidence bad = good.withTopology(new TopologySchemaEvidence(top.cutoverRunId(), "wrong", top.status(),
                top.topologyComplete(), top.unknownCallers(), top.ownerlessDependencies(),
                top.unknownDirectDatabaseConnections(), top.externalPartnersPending(), top.schemaExpandApplied(),
                top.oldAppReadsNewSchema(), top.oldAppWritesNewSchema(), top.newAppReadsOldData(),
                top.newAppWritesOldCompatibleData(), top.contractExecutedPrematurely(), top.authorityId(),
                top.productionObservedAt(), top.evidenceRefs()));
        Outcome outcome = evaluate(request(Phase.P0_PREPARED, true, "P_F"), bad);
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("artifact mismatch")));
    }

    @Test void stateMachineRejectsPhaseSkippingWithoutExecutingProduction() {
        Outcome outcome = evaluate(request(Phase.P4_SHADOW_READ, true, "P_F"), Evidence.good(Phase.P4_SHADOW_READ));
        var decision = new ProductionCutoverStateMachine().authorize(outcome, Phase.P7_WRITE_CANARY);
        assertFalse(decision.authorized()); assertFalse(decision.productionChangeExecuted());
        assertEquals(ProductionCutoverStateMachine.TransitionKind.BLOCKED, decision.kind());
    }

    @Test void stateMachineAuthorizesExternallyExecutedDecommissionAfterCfOnly() {
        Phase phase = Phase.P11_RETIREMENT_CANDIDATE;
        Evidence good = Evidence.good(phase).withRetirement(retirement(true, true, false));
        Outcome outcome = evaluate(request(phase, true, "P_F"), good);
        assertEquals(Gate.C_F, outcome.report().gate());
        var decision = new ProductionCutoverStateMachine().authorize(outcome, Phase.P12_DECOMMISSIONED);
        assertTrue(decision.authorized()); assertFalse(decision.productionChangeExecuted());
        assertEquals(Gate.C_F, decision.requiredGate());
    }

    @Test void rollbackFromDecommissionedPhaseIsForbidden() {
        Outcome outcome = evaluate(request(Phase.P12_DECOMMISSIONED, true, "P_F"), Evidence.good(Phase.P12_DECOMMISSIONED));
        var decision = new ProductionCutoverStateMachine().authorize(outcome, Phase.P10_HYPERCARE);
        assertFalse(decision.authorized()); assertFalse(decision.productionChangeExecuted());
    }

    @Test void writerCreatesAcceptancePackAndRefusesOverwrite() throws IOException {
        Path workspace = temp.resolve("evidence");
        Outcome outcome = evaluate(request(workspace, Phase.P12_DECOMMISSIONED, true, "P_F"), Evidence.good(Phase.P12_DECOMMISSIONED));
        Map<String, Path> files = new ProductionCutoverArtifactWriter().write(outcome);
        assertEquals(51, files.size());
        assertTrue(Files.isDirectory(workspace.resolve("retirement/decommission")));
        assertTrue(Files.isRegularFile(workspace.resolve("evidence/migration-acceptance-pack/executive-summary.md")));
        String manifest = Files.readString(workspace.resolve("cutover/cutover-run-manifest.yaml"));
        assertTrue(manifest.contains("batch: 11"));
        assertTrue(manifest.contains("batch10_eligible: true"));
        assertTrue(manifest.contains("production_change_executed: false"));
        JsonNode stateMachine = new ObjectMapper().readTree(workspace.resolve("cutover/state-machine.json").toFile());
        assertFalse(stateMachine.path("control_plane_executes_production_changes").asBoolean(true));
        JsonNode report = new ObjectMapper().readTree(workspace.resolve("reports/batch-11-conformance-report.json").toFile());
        assertTrue(report.path("conformance").path("migration_completed").asBoolean());
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(workspace.resolve("waves/wave-plans/waves.jsonl.zst")))) {
            assertTrue(new String(input.readAllBytes()).contains("wave-1"));
        }
        assertThrows(FileAlreadyExistsException.class, () -> new ProductionCutoverArtifactWriter().write(outcome));
    }

    @Test void writerRejectsSymbolicLinkWorkspace() throws IOException {
        Path real = temp.resolve("real"); Files.createDirectories(real);
        Path link = temp.resolve("link"); Files.createSymbolicLink(link, real);
        Outcome outcome = evaluate(request(link, Phase.P0_PREPARED, true, "P_F"), Evidence.good(Phase.P0_PREPARED));
        assertThrows(IOException.class, () -> new ProductionCutoverArtifactWriter().write(outcome));
    }

    private Outcome evaluate(Request request, Evidence evidence) {
        return new ProductionCutoverService(authorities(evidence)).evaluate(request);
    }

    private static ProductionCutoverAuthorities authorities(Evidence value) {
        return new ProductionCutoverAuthorities(ignored -> value.topology(), ignored -> value.data(), ignored -> value.traffic(),
                ignored -> value.integration(), ignored -> value.rollback(), ignored -> value.acceptance(), ignored -> value.retirement());
    }

    private Request request(Phase phase, boolean batch10, String gate) { return request(temp.resolve("evidence"), phase, batch10, gate); }

    private Request request(Path workspace, Phase phase, boolean batch10, String gate) {
        ArtifactBinding source = new ArtifactBinding(SystemRole.SOURCE, "source-artifact", DIGEST,
                "source-snapshot", true, "N_A", false, List.of("source-evidence"));
        ArtifactBinding target = new ArtifactBinding(SystemRole.TARGET, TARGET, DIGEST,
                "target-snapshot", true, gate, Set.of("P_E", "P_F").contains(gate), List.of("batch10-evidence"));
        MigrationWave wave = new MigrationWave("wave-1", 1, 2, true, true, "business-owner",
                List.of("tenant-id"), List.of("entry"), List.of("exit"), List.of("wave-evidence"));
        AggregateAuthority authority = new AggregateAuthority("Order", "tenant-a", phase, SystemRole.TARGET,
                SystemRole.TARGET, SystemRole.SOURCE, "tenant-id", 1, true, false, true, false,
                List.of("authority-evidence"));
        DataAsset asset = new DataAsset("orders", AssetCategory.AUTHORITATIVE, "data-owner",
                "source/orders", "target/orders", 1_000_000, 512_000_000, 250, "confidential",
                "backfill-plus-cdc", "7y", false, 1, false, false, List.of("asset-evidence"));
        List<Approval> approvals = Arrays.stream(ApprovalDimension.values()).map(dimension -> new Approval(dimension,
                ApprovalStatus.ACCEPTED, "approver-" + dimension, NOW.plus(30, ChronoUnit.DAYS), "", "approval-" + dimension)).toList();
        Policy policy = new Policy(1, 1, 1, 1, 30, .001, .001, 7, 1);
        return new Request(workspace, temp.resolve("source-repository"), temp.resolve("target-repository"), RUN,
                "migration-1", source, target, batch10, phase, List.of(wave), List.of(authority),
                List.of(asset), approvals, policy, NOW);
    }

    private static Request copy(Request base, Phase phase, List<AggregateAuthority> authorities) {
        return new Request(base.artifactWorkspace(), base.sourceRepositoryPath(), base.targetRepositoryPath(),
                base.cutoverRunId(), base.migrationId(), base.sourceArtifact(), base.targetArtifact(),
                base.batch10Eligible(), phase, base.waves(), authorities, base.dataAssets(), base.approvals(), base.policy(), base.observedAt());
    }

    private static TopologySchemaEvidence topology(int unknownCallers, boolean prematureContract) {
        return new TopologySchemaEvidence(RUN, TARGET, EvidenceStatus.PASSED, true, unknownCallers,
                0, 0, 0, true, true, true, true, true, prematureContract,
                "topology-authority", NOW.minusSeconds(1), List.of("topology-evidence"));
    }

    private static DataMigrationEvidence data(long lag, boolean backfillComplete, String targetPosition, int conflicts) {
        AssetResult result = new AssetResult("orders", true, true, backfillComplete, backfillComplete,
                true, conflicts, 0, 0, true, true, List.of("asset-result"));
        return new DataMigrationEvidence(RUN, TARGET, EvidenceStatus.PASSED, 1, 1, true, true, true,
                backfillComplete ? 1 : .5, backfillComplete ? 1 : .5, true, lag, true, 1, 1, 1,
                true, true, true, "position-1", targetPosition, conflicts == 0, conflicts, List.of(result),
                "data-authority", NOW.minusSeconds(1), List.of("data-evidence"));
    }

    private static TrafficAuthorityEvidence traffic(Phase phase, double reads, double writes, long sourceWrites,
                                                     int criticalReads, int dualPrimary, boolean frontier, boolean frontierApproved) {
        WaveResult wave = new WaveResult("wave-1", reads, writes, true, true, true,
                criticalReads, 0, dualPrimary, List.of("wave-result"));
        return new TrafficAuthorityEvidence(RUN, TARGET, EvidenceStatus.PASSED, phase, reads, writes,
                sourceWrites == 0 ? 0 : 1, sourceWrites, writes == 100, true, criticalReads == 0 ? 0 : .01,
                criticalReads, 0, true, true, true, dualPrimary, true, true, 0, 0, true, true,
                true, 0, true, true, frontier, frontierApproved, List.of(wave), "traffic-authority",
                NOW.minusSeconds(1), List.of("traffic-evidence"));
    }

    private static IntegrationEvidence integration(int messageLoss, int sourceConsumers, int sourceJobs) {
        return new IntegrationEvidence(RUN, TARGET, EvidenceStatus.PASSED, messageLoss, 0, 0,
                sourceConsumers, sourceJobs, true, true, true, true, true, 0, 0, 0,
                "integration-authority", NOW.minusSeconds(1), List.of("integration-evidence"));
    }

    private static RollbackIncidentEvidence rollback() {
        return new RollbackIncidentEvidence(RUN, TARGET, EvidenceStatus.PASSED, true, true, true, true,
                true, true, true, true, 0, true, false, "rollback-authority", NOW.minusSeconds(1),
                List.of("rollback-evidence"));
    }

    private static HypercareAcceptanceEvidence acceptance(int days, ApprovalStatus security) {
        return new HypercareAcceptanceEvidence(RUN, TARGET, EvidenceStatus.PASSED, days, 0, true, true,
                true, 0, ApprovalStatus.ACCEPTED, ApprovalStatus.ACCEPTED, security,
                ApprovalStatus.ACCEPTED, ApprovalStatus.ACCEPTED, true, true, true,
                "acceptance-authority", NOW.minusSeconds(1), List.of("acceptance-evidence"));
    }

    private static RetirementEvidence retirement(boolean archiveRestore, boolean credentials, boolean executed) {
        return new RetirementEvidence(RUN, TARGET, EvidenceStatus.PASSED, 0, 0, 0, 0, 0, 0, 0,
                true, true, archiveRestore, true, credentials, true, true, true, 0, executed,
                true, executed, true, 1, true, 0, "retirement-authority", NOW.minusSeconds(1),
                List.of("retirement-evidence"));
    }

    private record Evidence(TopologySchemaEvidence topology, DataMigrationEvidence data,
                            TrafficAuthorityEvidence traffic, IntegrationEvidence integration,
                            RollbackIncidentEvidence rollback, HypercareAcceptanceEvidence acceptance,
                            RetirementEvidence retirement) {
        static Evidence good(Phase phase) {
            double reads = switch (phase) {
                case P0_PREPARED, P1_SCHEMA_EXPANDED, P2_BACKFILL_RUNNING,
                        P3_INCREMENTAL_SYNC_HEALTHY, P4_SHADOW_READ -> 0;
                case P5_READ_CANARY -> 5;
                default -> 100;
            };
            double writes = switch (phase) {
                case P0_PREPARED, P1_SCHEMA_EXPANDED, P2_BACKFILL_RUNNING,
                        P3_INCREMENTAL_SYNC_HEALTHY, P4_SHADOW_READ, P5_READ_CANARY,
                        P6_TARGET_READ_PRIMARY -> 0;
                case P7_WRITE_CANARY -> 5;
                default -> 100;
            };
            long sourceWrites = phase.sequence() < Phase.P8_TARGET_WRITE_PRIMARY.sequence() ? 1 : 0;
            return new Evidence(ProductionCutoverServiceTest.topology(0, false),
                    ProductionCutoverServiceTest.data(0, true, "position-1", 0),
                    ProductionCutoverServiceTest.traffic(phase, reads, writes, sourceWrites, 0, 0, false, true),
                    ProductionCutoverServiceTest.integration(0, 0, 0),
                    ProductionCutoverServiceTest.rollback(),
                    ProductionCutoverServiceTest.acceptance(7, ApprovalStatus.ACCEPTED),
                    ProductionCutoverServiceTest.retirement(true, true, true));
        }
        Evidence withTopology(TopologySchemaEvidence value) { return new Evidence(value, data, traffic, integration, rollback, acceptance, retirement); }
        Evidence withData(DataMigrationEvidence value) { return new Evidence(topology, value, traffic, integration, rollback, acceptance, retirement); }
        Evidence withTraffic(TrafficAuthorityEvidence value) { return new Evidence(topology, data, value, integration, rollback, acceptance, retirement); }
        Evidence withIntegration(IntegrationEvidence value) { return new Evidence(topology, data, traffic, value, rollback, acceptance, retirement); }
        Evidence withAcceptance(HypercareAcceptanceEvidence value) { return new Evidence(topology, data, traffic, integration, rollback, value, retirement); }
        Evidence withRetirement(RetirementEvidence value) { return new Evidence(topology, data, traffic, integration, rollback, acceptance, value); }
    }
}
