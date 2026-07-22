package io.elmos.platform;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.luben.zstd.ZstdInputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;

import static io.elmos.platform.EnterprisePlatformModels.*;
import static org.junit.jupiter.api.Assertions.*;

class EnterprisePlatformServiceTest {
    private static final String DIGEST = "d".repeat(64);
    private static final String RUN = "enterprise-assessment-1";
    private static final String VERSION = "enterprise-platform-v1";
    private static final Instant NOW = Instant.parse("2026-07-21T04:00:00Z");
    @TempDir Path temp;

    @Test void completeExternalEvidenceReachesTgForAllModes() {
        Outcome outcome = evaluate(request(), Evidence.good());
        assertEquals(Gate.T_G, outcome.report().gate());
        assertEquals(RunStatus.ENTERPRISE_DELIVERY_READY, outcome.report().status());
        assertTrue(outcome.report().externalEvidenceComplete());
        assertTrue(outcome.report().enterpriseDeliveryReady());
        assertFalse(outcome.report().productionOperationExecuted());
        assertEquals(5, outcome.report().modes().size());
        assertTrue(outcome.report().modes().stream().allMatch(ModeConformance::deliveryReady));
    }

    @Test void platformAdmissionRequiresImmutableSignedBatchOneThroughElevenBinding() {
        PlatformArtifact invalid = new PlatformArtifact(VERSION, DIGEST, true, false,
                "sbom", "provenance", true, List.of("platform-evidence"));
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(request(), invalid, request().deployments(), request().tenants()), Evidence.good()));
    }

    @Test void allFiveDeploymentModesAreMandatory() {
        Request base = request();
        List<DeploymentProfile> missing = base.deployments().stream().filter(value -> value.mode() != DeploymentMode.AIR_GAPPED).toList();
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, base.platform(), missing, base.tenants()), Evidence.good()));
    }

    @Test void tenantKeysCannotBeShared() {
        Request base = request();
        TenantProfile first = base.tenants().get(0);
        TenantProfile second = base.tenants().get(1);
        second = new TenantProfile(second.tenantId(), second.organizationId(), second.isolationLevel(), second.deploymentMode(),
                second.dataRegion(), first.encryptionKeyRef(), second.retentionPolicyId(), true, true, true, true, true, true,
                second.evidenceRefs());
        TenantProfile finalSecond = second;
        assertThrows(IllegalArgumentException.class, () -> evaluate(copy(base, base.platform(), base.deployments(), List.of(first, finalSecond)), Evidence.good()));
    }

    @Test void authorityFailureIsSanitizedAndFailsClosed() {
        Evidence good = Evidence.good();
        EnterprisePlatformAuthorities ports = authorities(good);
        ports = new EnterprisePlatformAuthorities(ignored -> { throw new IllegalStateException("token=secret"); },
                ports.authorizationAudit(), ports.runnerSecurity(), ports.modelCost(), ports.dataGovernance(),
                ports.deployment(), ports.enterpriseAcceptance());
        Outcome outcome = new EnterprisePlatformService(ports).evaluate(request());
        assertEquals(Gate.BLOCKED, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("tenancy/identity authority failed safely: IllegalStateException"));
        assertTrue(outcome.report().blockers().stream().noneMatch(value -> value.contains("token=secret")));
    }

    @Test void mismatchedPlatformEvidenceCannotAdvanceGate() {
        Evidence good = Evidence.good();
        TenancyIdentityEvidence wrong = tenancy("another-version", 0, true, true);
        Outcome outcome = evaluate(request(), good.withTenancy(wrong));
        assertEquals(Gate.BLOCKED, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("authority evidence platform version mismatch"));
    }

    @Test void crossTenantDataLeakBlocksTa() {
        Outcome outcome = evaluate(request(), Evidence.good().withTenancy(tenancy(VERSION, 1, true, true)));
        assertEquals(Gate.BLOCKED, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("cross-tenant data leak detected"));
    }

    @Test void oidcOrSamlMustActuallyPass() {
        Outcome outcome = evaluate(request(), Evidence.good().withTenancy(tenancy(VERSION, 0, false, false)));
        assertEquals(Gate.BLOCKED, outcome.report().gate());
    }

    @Test void selfApprovalBlocksAuthorizationGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withAuthorization(authorization(1, 0)));
        assertEquals(Gate.T_A, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("high-risk self approval detected"));
    }

    @Test void auditOverwriteBlocksAuthorizationGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withAuthorization(authorization(0, 1)));
        assertEquals(Gate.T_A, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("audit overwrite detected"));
    }

    @Test void crossTenantRunnerJobBlocksRunnerGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withRunner(runner(1, 0, 0, 0)));
        assertEquals(Gate.T_B, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("tenant job isolation")));
    }

    @Test void sandboxEscapeBlocksRunnerGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withRunner(runner(0, 1, 0, 0)));
        assertEquals(Gate.T_B, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("sandbox escape finding is open"));
    }

    @Test void unauthorizedEgressBlocksRunnerGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withRunner(runner(0, 0, 1, 0)));
        assertEquals(Gate.T_B, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("unauthorized Runner egress detected"));
    }

    @Test void secretLeakBlocksRunnerGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withRunner(runner(0, 0, 0, 1)));
        assertEquals(Gate.T_B, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("secret leaked")));
    }

    @Test void modelGatewayBypassBlocksModelGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(1, 0, 0, 0, 0, 0)));
        assertEquals(Gate.T_C, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("model gateway bypass path detected"));
    }

    @Test void modelDataPolicyViolationBlocksModelGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(0, 1, 0, 0, 0, 0)));
        assertEquals(Gate.T_C, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("model data policy")));
    }

    @Test void quotaBypassBlocksModelCostGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(0, 0, 1, 0, 0, 0)));
        assertEquals(Gate.T_C, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("quota bypass detected"));
    }

    @Test void usageLedgerMutationBlocksModelCostGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(0, 0, 0, 1, 0, 0)));
        assertEquals(Gate.T_C, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("usage ledger")));
    }

    @Test void duplicateChargeBlocksModelCostGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(0, 0, 0, 0, 1, 0)));
        assertEquals(Gate.T_C, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("duplicate customer charge detected"));
    }

    @Test void billingDifferenceCannotBeAveragedAway() {
        Outcome outcome = evaluate(request(), Evidence.good().withModel(model(0, 0, 0, 0, 0, .01)));
        assertEquals(Gate.T_C, outcome.report().gate());
    }

    @Test void legalHoldDeletionBlocksDataGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withData(data(1, 0, true)));
        assertEquals(Gate.T_D, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("data under Legal Hold was deleted"));
    }

    @Test void residualTenantCopyBlocksDataGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withData(data(0, 1, true)));
        assertEquals(Gate.T_D, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("unexplained data copies")));
    }

    @Test void keyRotationMustBeExternallyVerified() {
        Outcome outcome = evaluate(request(), Evidence.good().withData(data(0, 0, false)));
        assertEquals(Gate.T_D, outcome.report().gate());
    }

    @Test void airGapNetworkRequestBlocksDeploymentGateWithoutCompensatingOtherModes() {
        DeploymentEvidence failed = deployment(DeploymentMode.AIR_GAPPED, 1, false, false);
        Outcome outcome = evaluate(request(), Evidence.good().withDeployment(failed));
        assertEquals(Gate.T_E, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("air-gapped installation attempted external network access"));
        ModeConformance airGap = outcome.report().modes().stream().filter(value -> value.mode() == DeploymentMode.AIR_GAPPED).findFirst().orElseThrow();
        ModeConformance shared = outcome.report().modes().stream().filter(value -> value.mode() == DeploymentMode.SAAS_SHARED).findFirst().orElseThrow();
        assertEquals(Gate.T_E, airGap.gate());
        assertEquals(Gate.T_F, shared.gate());
    }

    @Test void unsignedOfflineArtifactBlocksDeploymentGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withDeployment(deployment(DeploymentMode.AIR_GAPPED, 0, true, false)));
        assertEquals(Gate.T_E, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("unsigned artifacts")));
    }

    @Test void hiddenSelfHostedSaasDependencyBlocksDeploymentGate() {
        Outcome outcome = evaluate(request(), Evidence.good().withDeployment(deployment(DeploymentMode.SELF_HOSTED, 0, false, true)));
        assertEquals(Gate.T_E, outcome.report().gate());
        assertTrue(outcome.report().blockers().stream().anyMatch(value -> value.contains("hidden SaaS")));
    }

    @Test void tGRequiresHaAndAllFourAcceptanceDimensions() {
        Outcome outcome = evaluate(request(), Evidence.good().withAcceptance(acceptance(false, 0)));
        assertEquals(Gate.T_F, outcome.report().gate());
        assertFalse(outcome.report().enterpriseDeliveryReady());
    }

    @Test void criticalRiskPreventsCommercialReadiness() {
        Outcome outcome = evaluate(request(), Evidence.good().withAcceptance(acceptance(true, 1)));
        assertEquals(Gate.T_F, outcome.report().gate());
        assertTrue(outcome.report().blockers().contains("critical enterprise delivery risk remains open"));
    }

    @Test void writerCreatesExactReportsAndRefusesOverwrite() throws IOException {
        Path workspace = temp.resolve("enterprise-evidence");
        Outcome outcome = evaluate(request(workspace), Evidence.good());
        Map<String, Path> files = new EnterprisePlatformArtifactWriter().write(outcome);
        assertEquals(26, files.size());
        Path root = workspace.resolve("enterprise-platform");
        Set<String> expectedTopLevel = Set.of("control-plane", "execution-plane", "model-plane",
                "artifact-plane", "trust-plane", "integrations", "deployments", "offline",
                "observability", "tests", "reports");
        try (var directories = Files.list(root)) {
            assertEquals(expectedTopLevel, directories.filter(Files::isDirectory)
                    .map(path -> path.getFileName().toString()).collect(java.util.stream.Collectors.toSet()));
        }
        try (var directories = Files.walk(root)) {
            assertEquals(77, directories.filter(Files::isDirectory).count());
        }
        Set<String> expectedReports = Set.of("tenant-isolation-report.json", "identity-security-report.json",
                "authorization-report.json", "private-runner-report.json", "model-governance-report.json",
                "quota-metering-report.json", "billing-reconciliation-report.json", "audit-integrity-report.json",
                "data-governance-report.json", "self-hosted-report.json", "air-gapped-report.json",
                "batch-12-conformance-report.json");
        try (var reports = Files.list(root.resolve("reports"))) {
            assertEquals(expectedReports, reports.filter(Files::isRegularFile)
                    .map(path -> path.getFileName().toString()).collect(java.util.stream.Collectors.toSet()));
        }
        assertTrue(Files.isDirectory(workspace.resolve("enterprise-platform/offline/vulnerability-feeds")));
        assertTrue(Files.isDirectory(workspace.resolve("enterprise-platform/tests/offline")));
        assertTrue(Files.isRegularFile(root.resolve("control-plane/batch-12-gate-results.json")));
        String manifest = Files.readString(workspace.resolve("enterprise-platform/control-plane/platform-manifest.yaml"));
        assertTrue(manifest.contains("batch: 12"));
        assertTrue(manifest.contains("production_operation_executed: false"));
        JsonNode report = new ObjectMapper().readTree(workspace.resolve(
                "enterprise-platform/reports/batch-12-conformance-report.json").toFile());
        assertTrue(report.path("conformance").path("enterprise_delivery_ready").asBoolean());
        try (ZstdInputStream input = new ZstdInputStream(Files.newInputStream(workspace.resolve(
                "enterprise-platform/control-plane/tenant/tenant-profiles.jsonl.zst")))) {
            assertTrue(new String(input.readAllBytes()).contains("tenant-a"));
        }
        assertThrows(FileAlreadyExistsException.class, () -> new EnterprisePlatformArtifactWriter().write(outcome));
    }

    @Test void writerRejectsSymbolicLinkWorkspace() throws IOException {
        Path real = temp.resolve("real"); Files.createDirectories(real);
        Path link = temp.resolve("link"); Files.createSymbolicLink(link, real);
        Outcome outcome = evaluate(request(link), Evidence.good());
        assertThrows(IOException.class, () -> new EnterprisePlatformArtifactWriter().write(outcome));
    }

    @Test void writerRejectsSymbolicLinkAncestorThatResolvesIntoRepository() throws IOException {
        Path real = temp.resolve("platform-repository-real"); Files.createDirectories(real);
        Path link = temp.resolve("linked-parent"); Files.createSymbolicLink(link, real);
        Request base = request(link.resolve("evidence"));
        Request attack = new Request(base.artifactWorkspace(), real, base.assessmentRunId(), base.platform(),
                base.tenants(), base.deployments(), base.capabilities(), base.policy(), base.observedAt());
        Outcome outcome = evaluate(attack, Evidence.good());
        assertThrows(IllegalArgumentException.class, () -> new EnterprisePlatformArtifactWriter().write(outcome));
        assertFalse(Files.exists(real.resolve("evidence")));
    }

    private Outcome evaluate(Request request, Evidence evidence) {
        return new EnterprisePlatformService(authorities(evidence)).evaluate(request);
    }

    private static EnterprisePlatformAuthorities authorities(Evidence value) {
        return new EnterprisePlatformAuthorities(ignored -> value.tenancy(), ignored -> value.authorization(),
                ignored -> value.runner(), ignored -> value.model(), ignored -> value.data(),
                ignored -> value.deployment(), ignored -> value.acceptance());
    }

    private Request request() { return request(temp.resolve("enterprise-evidence")); }

    private Request request(Path workspace) {
        PlatformArtifact platform = new PlatformArtifact(VERSION, DIGEST, true, true,
                "sbom://enterprise-v1", "provenance://enterprise-v1", true, List.of("platform-evidence"));
        List<TenantProfile> tenants = List.of(
                new TenantProfile("tenant-a", "org-a", IsolationLevel.LEVEL_3_NAMESPACE_RUNNER,
                        DeploymentMode.SAAS_SHARED, "cn-east", "key-a", "retention-a",
                        true, true, true, true, true, true, List.of("tenant-a-evidence")),
                new TenantProfile("tenant-b", "org-b", IsolationLevel.LEVEL_6_AIR_GAPPED,
                        DeploymentMode.AIR_GAPPED, "customer-local", "key-b", "retention-b",
                        true, true, true, true, true, true, List.of("tenant-b-evidence")));
        List<DeploymentProfile> deployments = Arrays.stream(DeploymentMode.values()).map(mode ->
                new DeploymentProfile("profile-" + mode.name().toLowerCase(Locale.ROOT), mode, true,
                        true, true, true, List.of("profile-" + mode))).toList();
        List<CapabilityBinding> capabilities = List.of("identity", "authorization", "private-runner",
                        "model-gateway", "metering-billing", "audit", "data-governance", "offline-delivery")
                .stream().map(name -> new CapabilityBinding("capability-" + name, name, "v1", true,
                        true, List.of("capability-evidence-" + name))).toList();
        Policy policy = new Policy(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 300, 0, 1);
        return new Request(workspace, temp.resolve("platform-repository"), RUN, platform,
                tenants, deployments, capabilities, policy, NOW);
    }

    private static Request copy(Request base, PlatformArtifact platform, List<DeploymentProfile> deployments,
                                List<TenantProfile> tenants) {
        return new Request(base.artifactWorkspace(), base.platformRepositoryPath(), base.assessmentRunId(),
                platform, tenants, deployments, base.capabilities(), base.policy(), base.observedAt());
    }

    private static TenancyIdentityEvidence tenancy(String version, int leaks, boolean oidc, boolean saml) {
        return new TenancyIdentityEvidence(RUN, version, EvidenceStatus.PASSED, 1, leaks, 0, 0, 1,
                true, oidc, saml, true, true, true, true, 1, true, 0, true,
                "tenant-authority", NOW, List.of("tenant-identity-evidence"));
    }

    private static AuthorizationAuditEvidence authorization(int selfApproval, int auditOverwrite) {
        return new AuthorizationAuditEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, 1, 1, 1,
                selfApproval, 0, true, true, 0, 1, 1, true, auditOverwrite,
                "authorization-authority", NOW, List.of("authorization-evidence"));
    }

    private static RunnerSecurityEvidence runner(int crossTenantJob, int sandbox, int egress, int secret) {
        return new RunnerSecurityEvidence(RUN, VERSION, EvidenceStatus.PASSED, true, 1, 0,
                crossTenantJob, sandbox, egress, secret, true, true, true, true, true, 0,
                "runner-authority", NOW, List.of("runner-evidence"));
    }

    private static ModelCostEvidence model(int bypass, int policyViolation, int quotaBypass,
                                           int ledgerMutation, int duplicateCharges, double billingDifference) {
        return new ModelCostEvidence(RUN, VERSION, EvidenceStatus.PASSED, bypass, policyViolation,
                0, 0, 1, quotaBypass, 0, true, ledgerMutation, billingDifference, duplicateCharges,
                true, 0, true, true, "model-cost-authority", NOW, List.of("model-cost-evidence"));
    }

    private static DataGovernanceEvidence data(int legalHoldDeletion, int residualCopies, boolean keyRotation) {
        return new DataGovernanceEvidence(RUN, VERSION, EvidenceStatus.PASSED, 1, true, 1,
                true, legalHoldDeletion, true, residualCopies, 1, keyRotation, true, true, 1, true,
                "data-authority", NOW, List.of("data-evidence"));
    }

    private static DeploymentEvidence deployment(DeploymentMode changed, int airRequests,
                                                  boolean unsigned, boolean hiddenDependency) {
        List<ModeResult> modes = Arrays.stream(DeploymentMode.values()).map(mode -> new ModeResult(mode,
                EvidenceStatus.PASSED, true, true, true, mode == changed && hiddenDependency ? 1 : 0,
                mode == DeploymentMode.AIR_GAPPED ? airRequests : 0,
                !(mode == changed && unsigned), true, true, true, true, true, true, true,
                List.of("deployment-evidence-" + mode))).toList();
        return new DeploymentEvidence(RUN, VERSION, EvidenceStatus.PASSED, modes,
                "deployment-authority", NOW, List.of("deployment-evidence"));
    }

    private static EnterpriseAcceptanceEvidence acceptance(boolean ha, int risks) {
        return new EnterpriseAcceptanceEvidence(RUN, VERSION, EvidenceStatus.PASSED, ha, true,
                true, true, true, true, true, true, true, true, true, true, true, true,
                risks, true, 1, "acceptance-authority", NOW, List.of("acceptance-evidence"));
    }

    private record Evidence(TenancyIdentityEvidence tenancy, AuthorizationAuditEvidence authorization,
                            RunnerSecurityEvidence runner, ModelCostEvidence model,
                            DataGovernanceEvidence data, DeploymentEvidence deployment,
                            EnterpriseAcceptanceEvidence acceptance) {
        static Evidence good() {
            return new Evidence(EnterprisePlatformServiceTest.tenancy(VERSION, 0, true, true),
                    EnterprisePlatformServiceTest.authorization(0, 0), EnterprisePlatformServiceTest.runner(0, 0, 0, 0),
                    EnterprisePlatformServiceTest.model(0, 0, 0, 0, 0, 0), EnterprisePlatformServiceTest.data(0, 0, true),
                    EnterprisePlatformServiceTest.deployment(null, 0, false, false), EnterprisePlatformServiceTest.acceptance(true, 0));
        }
        Evidence withTenancy(TenancyIdentityEvidence value) { return new Evidence(value, authorization, runner, model, data, deployment, acceptance); }
        Evidence withAuthorization(AuthorizationAuditEvidence value) { return new Evidence(tenancy, value, runner, model, data, deployment, acceptance); }
        Evidence withRunner(RunnerSecurityEvidence value) { return new Evidence(tenancy, authorization, value, model, data, deployment, acceptance); }
        Evidence withModel(ModelCostEvidence value) { return new Evidence(tenancy, authorization, runner, value, data, deployment, acceptance); }
        Evidence withData(DataGovernanceEvidence value) { return new Evidence(tenancy, authorization, runner, model, value, deployment, acceptance); }
        Evidence withDeployment(DeploymentEvidence value) { return new Evidence(tenancy, authorization, runner, model, data, value, acceptance); }
        Evidence withAcceptance(EnterpriseAcceptanceEvidence value) { return new Evidence(tenancy, authorization, runner, model, data, deployment, value); }
    }
}
