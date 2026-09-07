package io.elmos.hardening;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.*;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;

import static io.elmos.hardening.ProductionHardeningModels.*;
import static org.junit.jupiter.api.Assertions.*;

class ProductionHardeningServiceTest {
    private static final String DIGEST = "a".repeat(64);
    private static final String OTHER_DIGEST = "b".repeat(64);
    private static final String ARTIFACT = "artifact-10";
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
    @TempDir Path temp;

    @Test void completeEvidenceReachesPfButNeverDeclaresProductionCutover() {
        Outcome outcome = evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", Evidence.good("orders")));
        ServiceGate gate = outcome.report().services().getFirst();
        assertEquals(Gate.P_F, gate.gate());
        assertTrue(gate.eligibleForProgressiveDelivery());
        assertFalse(gate.productionReady());
        assertFalse(gate.eligibleForCutover());
        assertEquals(RunStatus.READY_FOR_PROGRESSIVE_DELIVERY, outcome.report().status());
        assertFalse(outcome.report().productionReady());
    }

    @Test void p99FailureBlocksPerformanceGate() {
        Evidence evidence = Evidence.good("orders").withPerformance(performance("orders", true, false, 1, 40, ARTIFACT));
        assertEquals(Gate.BLOCKED, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void repositoryAverageCannotHideAServiceRegression() {
        Request request = request(temp.resolve("evidence"), List.of("healthy", "slow"));
        Evidence slow = Evidence.good("slow").withPerformance(performance("slow", true, false, 1, 40, ARTIFACT));
        Outcome outcome = evaluate(request, Map.of("healthy", Evidence.good("healthy"), "slow", slow));
        assertEquals(Gate.P_F, gate(outcome, "healthy").gate());
        assertEquals(Gate.BLOCKED, gate(outcome, "slow").gate());
        assertFalse(outcome.report().eligibleForProgressiveDelivery());
    }

    @Test void criticalVulnerabilityBlocksSecurityGate() {
        Evidence evidence = Evidence.good("orders").withSecurity(security("orders", 1, 0, ARTIFACT));
        assertEquals(Gate.P_A, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void tenantIsolationRegressionBlocksSecurityGate() {
        Evidence evidence = Evidence.good("orders").withSecurity(security("orders", 0, 1, ARTIFACT));
        assertEquals(Gate.P_A, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void requiredPenetrationFailureBlocksSecurityGate() {
        SecurityEvidence base = security("orders", 0, 0, ARTIFACT);
        SecurityEvidence failed = new SecurityEvidence(base.serviceId(), base.artifactId(), base.status(),
                base.criticalVulnerabilities(), base.exploitableHighVulnerabilities(), base.criticalSastFindings(),
                base.criticalDastFindings(), base.secretLeaks(), base.authenticationRegressions(),
                base.authorizationRegressions(), base.tenantIsolationRegressions(), base.weakCryptographyFindings(),
                base.criticalConfigurationFindings(), base.unknownOriginBinaries(), base.unapprovedSecurityWaivers(),
                base.criticalScenarioPassRate(), false, base.sbomComplete(), base.sbomMatchesArtifact(),
                base.fixedImageDigest(), base.nonRootLeastPrivilege(), false, false, base.authorityId(), base.evidenceRefs());
        Evidence evidence = Evidence.good("orders").withSecurity(failed);
        assertEquals(Gate.P_A, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void unsafeOrProductionConnectedScenarioIsRejectedBeforeAuthoritiesRun() {
        Request base = request(temp.resolve("evidence"), List.of("orders"));
        HardeningScenario unsafe = new HardeningScenario("unsafe", "orders", ARTIFACT, ScenarioKind.CHAOS,
                true, false, true, true, false, false, 30, List.of("chaos-log"));
        Request invalid = copy(base, concat(base.scenarios(), unsafe), base.riskProfiles(), base.openRisks());
        assertThrows(IllegalArgumentException.class, () -> evaluate(invalid, Map.of("orders", Evidence.good("orders"))));
    }

    @Test void requiredRestoreFailureBlocksReliabilityGate() {
        Evidence evidence = Evidence.good("orders").withReliability(reliability("orders", false, 0, false));
        assertEquals(Gate.P_B, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void unboundedRetryBlocksReliabilityGate() {
        Evidence evidence = Evidence.good("orders").withReliability(reliability("orders", true, 1, false));
        assertEquals(Gate.P_B, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void destructiveProductionChaosBlocksReliabilityGate() {
        Evidence evidence = Evidence.good("orders").withReliability(reliability("orders", true, 0, true));
        assertEquals(Gate.P_B, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void missingSliCoverageBlocksObservabilityGate() {
        Evidence evidence = Evidence.good("orders").withObservability(observability("orders", .8));
        assertEquals(Gate.P_C, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void unsignedArtifactBlocksProgressiveDelivery() {
        Evidence evidence = Evidence.good("orders").withRelease(release("orders", false, false));
        assertEquals(Gate.P_D, evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst().gate());
    }

    @Test void productionDeploymentClaimIsRejectedByReleaseGate() {
        Evidence evidence = Evidence.good("orders").withRelease(release("orders", true, true));
        ServiceGate gate = evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence))
                .report().services().getFirst();
        assertEquals(Gate.P_D, gate.gate());
        assertFalse(gate.productionReady());
    }

    @Test void mismatchedArtifactEvidenceFailsClosed() {
        Evidence evidence = Evidence.good("orders").withPerformance(performance("orders", true, true, 1, 40, "other-artifact"));
        Outcome outcome = evaluate(request(temp.resolve("evidence"), List.of("orders")), Map.of("orders", evidence));
        assertEquals(Gate.BLOCKED, outcome.report().services().getFirst().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("artifact mismatch")));
    }

    @Test void missingPeakScenarioIsAnAdmissionFailure() {
        Request base = request(temp.resolve("evidence"), List.of("orders"));
        List<HardeningScenario> withoutPeak = base.scenarios().stream().filter(value -> value.kind() != ScenarioKind.PEAK).toList();
        Request invalid = copy(base, withoutPeak, base.riskProfiles(), base.openRisks());
        assertThrows(IllegalArgumentException.class, () -> evaluate(invalid, Map.of("orders", Evidence.good("orders"))));
    }

    @Test void highRiskTierDowngradeIsAnAdmissionFailure() {
        Request base = request(temp.resolve("evidence"), List.of("orders"));
        RiskProfile downgraded = new RiskProfile("profile-orders", "orders", RiskTier.TIER_2, 20,
                false, false, false, false, false, false, false, true, "risk-owner", "approval");
        Request invalid = copy(base, base.scenarios(), List.of(downgraded), base.openRisks());
        assertThrows(IllegalArgumentException.class, () -> evaluate(invalid, Map.of("orders", Evidence.good("orders"))));
    }

    @Test void criticalOpenRiskBlocksRelease() {
        Request base = request(temp.resolve("evidence"), List.of("orders"));
        OpenRisk risk = new OpenRisk("risk-1", "orders", Severity.CRITICAL, true, false,
                NOW.plus(1, ChronoUnit.DAYS), "owner", "mitigate", "rollback", "");
        Request withRisk = copy(base, base.scenarios(), base.riskProfiles(), List.of(risk));
        assertEquals(Gate.P_D, evaluate(withRisk, Map.of("orders", Evidence.good("orders"))).report().services().getFirst().gate());
    }

    @Test void authorityFailureIsRecordedWithoutLeakingExceptionText() {
        Request request = request(temp.resolve("evidence"), List.of("orders"));
        Evidence evidence = Evidence.good("orders");
        ProductionHardeningAuthorities authorities = authorities(Map.of("orders", evidence));
        authorities = new ProductionHardeningAuthorities(authorities.environment(), authorities.performance(),
                ignored -> { throw new IllegalStateException("secret token"); }, authorities.reliability(),
                authorities.observability(), authorities.release(), authorities.cost());
        Outcome outcome = new ProductionHardeningService(authorities).evaluate(request);
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.equals("security authority failed safely: IllegalStateException")));
        assertTrue(outcome.report().blockers().stream().noneMatch(value -> value.contains("secret token")));
    }

    @Test void writerCreatesExactEvidenceTreeAndRefusesOverwrite() throws IOException {
        Path workspace = temp.resolve("evidence");
        Outcome outcome = evaluate(request(workspace, List.of("orders")), Map.of("orders", Evidence.good("orders")));
        Map<String, Path> files = new ProductionHardeningArtifactWriter().write(outcome);
        assertEquals(32, files.size());
        assertTrue(Files.isDirectory(workspace.resolve("reliability/disaster-recovery")));
        assertTrue(Files.isDirectory(workspace.resolve("release/approvals")));
        JsonNode report = new ObjectMapper().readTree(workspace.resolve("reports/batch-10-conformance-report.json").toFile());
        assertFalse(report.path("production_ready").asBoolean(true));
        assertFalse(report.path("eligible_for_cutover").asBoolean(true));
        JsonNode performanceReport = new ObjectMapper().readTree(workspace.resolve("reports/performance-report.json").toFile());
        assertTrue(performanceReport.path("domain_evidence").path("performance").has("orders"));
        assertTrue(Files.isRegularFile(workspace.resolve(
                "evidence/production-readiness-pack/production-readiness-evidence-pack.json")));
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(workspace.resolve("production-hardening/risk-profiles.jsonl.zst")))) {
            assertTrue(new String(input.readAllBytes()).contains("profile-orders"));
        }
        assertThrows(FileAlreadyExistsException.class, () -> new ProductionHardeningArtifactWriter().write(outcome));
    }

    @Test void writerRejectsSymbolicLinkWorkspace() throws IOException {
        Path real = temp.resolve("real"); Files.createDirectories(real);
        Path link = temp.resolve("link"); Files.createSymbolicLink(link, real);
        Outcome outcome = evaluate(request(link, List.of("orders")), Map.of("orders", Evidence.good("orders")));
        assertThrows(IOException.class, () -> new ProductionHardeningArtifactWriter().write(outcome));
    }

    private Outcome evaluate(Request request, Map<String, Evidence> evidence) {
        return new ProductionHardeningService(authorities(evidence)).evaluate(request);
    }

    private static ProductionHardeningAuthorities authorities(Map<String, Evidence> evidence) {
        return new ProductionHardeningAuthorities(
                ignored -> evidence.values().stream().map(Evidence::calibration).toList(),
                (ignored, calibrations) -> evidence.values().stream().map(Evidence::performance).toList(),
                ignored -> evidence.values().stream().map(Evidence::security).toList(),
                ignored -> evidence.values().stream().map(Evidence::reliability).toList(),
                ignored -> evidence.values().stream().map(Evidence::observability).toList(),
                ignored -> evidence.values().stream().map(Evidence::release).toList(),
                ignored -> evidence.values().stream().map(Evidence::cost).toList());
    }

    private Request request(Path workspace, List<String> services) {
        List<DeploymentUnit> units = services.stream().map(service -> new DeploymentUnit(service, service + "-module",
                true, true, true, true, true, false, 3, List.of("checkout"))).toList();
        List<RiskProfile> profiles = services.stream().map(service -> new RiskProfile("profile-" + service, service,
                RiskTier.TIER_4, 30, true, true, true, true, true, true, true,
                true, "risk-owner", "approval-" + service)).toList();
        List<WorkloadModel> workloads = services.stream().map(service -> new WorkloadModel("workload-" + service,
                service, WorkloadKind.OPEN, 100, 200, 300, 60, DIGEST, DIGEST, DIGEST,
                "production-baseline-" + service, 1, true, true, "v1", List.of("workload-evidence"))).toList();
        List<HardeningScenario> scenarios = new ArrayList<>();
        EnumSet<ScenarioKind> kinds = EnumSet.of(ScenarioKind.NORMAL, ScenarioKind.PEAK, ScenarioKind.STRESS,
                ScenarioKind.SOAK, ScenarioKind.SECURITY, ScenarioKind.CHAOS, ScenarioKind.CRASH,
                ScenarioKind.RESTORE, ScenarioKind.PITR, ScenarioKind.DISASTER_RECOVERY,
                ScenarioKind.OBSERVABILITY, ScenarioKind.CANARY, ScenarioKind.ROLLBACK, ScenarioKind.COST);
        for (String service : services) for (ScenarioKind kind : kinds)
            scenarios.add(new HardeningScenario("scenario-" + service + "-" + kind, service, ARTIFACT, kind,
                    true, true, false, kind == ScenarioKind.CHAOS, true, true, 300, List.of("evidence-" + kind)));
        ArtifactBinding artifact = new ArtifactBinding(ARTIFACT, DIGEST, "source-snapshot", "target-snapshot",
                OTHER_DIGEST, DIGEST, true, true, true, "sbom", "provenance", List.of("batch-9-report"));
        Policy policy = new Policy(.05, .95, 1, .95, 1, .95, .95, .90, .99, .99, 30, 1000);
        return new Request(workspace, temp.resolve("target-repository"), "hardening-run", "migration-1",
                "target-snapshot", ARTIFACT, true, artifact, units, profiles, workloads, scenarios,
                List.of(), policy, NOW);
    }

    private static Request copy(Request base, List<HardeningScenario> scenarios, List<RiskProfile> profiles, List<OpenRisk> risks) {
        return new Request(base.artifactWorkspace(), base.targetRepositoryPath(), base.hardeningRunId(), base.migrationId(),
                base.targetSnapshotId(), base.targetArtifactId(), base.batch9Eligible(), base.artifact(),
                base.deploymentUnits(), profiles, base.workloadModels(), scenarios, risks, base.policy(), base.observedAt());
    }

    private static <T> List<T> concat(List<T> values, T value) {
        List<T> result = new ArrayList<>(values); result.add(value); return result;
    }

    private static ServiceGate gate(Outcome outcome, String service) {
        return outcome.report().services().stream().filter(value -> value.serviceId().equals(service)).findFirst().orElseThrow();
    }

    private static PerformanceEvidence performance(String service, boolean p95, boolean p99, double rate,
                                                   double headroom, String artifact) {
        return new PerformanceEvidence(service, artifact, EvidenceStatus.PASSED, true, true, true, true,
                p95, p99, true, true, true, rate, headroom, 0, 0, false,
                false, false, "perf-lab", List.of("performance-evidence"));
    }

    private static SecurityEvidence security(String service, int critical, int tenantRegression, String artifact) {
        return new SecurityEvidence(service, artifact, EvidenceStatus.PASSED, critical, 0, 0, 0, 0, 0, 0,
                tenantRegression, 0, 0, 0, 0, 1, true, true, true, true, true,
                false, false, "security-lab", List.of("security-evidence"));
    }

    private static ReliabilityEvidence reliability(String service, boolean restore, int unboundedRetries,
                                                     boolean destructiveProductionChaos) {
        return new ReliabilityEvidence(service, ARTIFACT, EvidenceStatus.PASSED, 1, 1, 0,
                unboundedRetries, 0, 0, true, true, restore, true, true, true, true, true,
                false, destructiveProductionChaos, false, "reliability-lab", List.of("reliability-evidence"));
    }

    private static ObservabilityEvidence observability(String service, double sli) {
        return new ObservabilityEvidence(service, ARTIFACT, EvidenceStatus.PASSED, sli, 1, 1, 1,
                true, true, true, true, true, 0, 0, false, false,
                "observability-lab", List.of("observability-evidence"));
    }

    private static ReleaseEvidence release(String service, boolean signed, boolean productionDeployed) {
        return new ReleaseEvidence(service, ARTIFACT, EvidenceStatus.PASSED, true, signed, signed, true,
                true, true, true, true, true, true, true, true, 0, 0,
                true, productionDeployed, false, false, "release-lab", List.of("release-evidence"));
    }

    private record Evidence(ServiceCalibration calibration, PerformanceEvidence performance,
                            SecurityEvidence security, ReliabilityEvidence reliability,
                            ObservabilityEvidence observability, ReleaseEvidence release, CostEvidence cost) {
        static Evidence good(String service) {
            return new Evidence(new ServiceCalibration(service, ARTIFACT, DIGEST, true, .01, true, true,
                    false, true, true, false, false, List.of(), List.of("calibration-evidence")),
                    ProductionHardeningServiceTest.performance(service, true, true, 1, 40, ARTIFACT),
                    ProductionHardeningServiceTest.security(service, 0, 0, ARTIFACT),
                    ProductionHardeningServiceTest.reliability(service, true, 0, false),
                    ProductionHardeningServiceTest.observability(service, 1),
                    ProductionHardeningServiceTest.release(service, true, false),
                    new CostEvidence(service, ARTIFACT, EvidenceStatus.PASSED, BigDecimal.TEN,
                            BigDecimal.valueOf(20), BigDecimal.ONE, true, true, true, true,
                            "USD", "cost-lab", List.of("cost-evidence")));
        }
        Evidence withPerformance(PerformanceEvidence value) { return new Evidence(calibration, value, security, reliability, observability, release, cost); }
        Evidence withSecurity(SecurityEvidence value) { return new Evidence(calibration, performance, value, reliability, observability, release, cost); }
        Evidence withReliability(ReliabilityEvidence value) { return new Evidence(calibration, performance, security, value, observability, release, cost); }
        Evidence withObservability(ObservabilityEvidence value) { return new Evidence(calibration, performance, security, reliability, value, release, cost); }
        Evidence withRelease(ReleaseEvidence value) { return new Evidence(calibration, performance, security, reliability, observability, value, cost); }
    }
}
