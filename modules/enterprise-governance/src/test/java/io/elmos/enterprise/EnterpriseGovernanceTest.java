package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class EnterpriseGovernanceTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");

    @Test void tenantContextComesFromVerifiedMembershipNotRequestBody() {
        var service = new TenantIdentityAuthorization();
        var principal = new VerifiedPrincipal("alice", Map.of("org-a", Set.of("DEVELOPER")),
                AuthenticationAssurance.MFA, NOW.minusSeconds(60), false);
        var organization = organization("org-a");
        assertThrows(SecurityException.class, () -> service.deriveTenantContext(principal, organization, "org-b", "corr"));
        assertEquals("org-a", service.deriveTenantContext(principal, organization, "org-a", "corr").organizationId());
    }

    @Test void resourceCacheStorageAndSqlSettingsRemainTenantScoped() {
        var service = new TenantIdentityAuthorization();
        TenantContext tenant = tenant("org-a", "alice", Set.of("DEVELOPER"), AuthenticationAssurance.MFA);
        assertThrows(SecurityException.class, () -> service.verifyResourceBoundary(tenant, "org-b"));
        assertEquals("elmos:org-a:repository:repo-1", service.cacheKey(tenant, "REPOSITORY", "repo-1"));
        assertEquals("organizations/org-a/evidence/", service.objectStoragePrefix(tenant, "evidence"));
        assertTrue(service.transactionLocalSettings(tenant).getFirst().startsWith("SET LOCAL"));
    }

    @Test void oidcRejectsIssuerAudienceAndNonceProblemsAndUsesSubjectIdentity() {
        var service = new TenantIdentityAuthorization();
        IdentityAssertion valid = assertion(true, true, "sub-1", "old@example.com");
        FederatedIdentity first = service.validateFederatedIdentity(valid, Map.of("unknown", Set.of("AUDITOR")), NOW);
        FederatedIdentity renamed = service.validateFederatedIdentity(assertion(true, true, "sub-1", "new@example.com"),
                Map.of("unknown", Set.of("AUDITOR")), NOW);
        assertEquals(first.identityId(), renamed.identityId());
        assertEquals(Set.of("AUDITOR"), first.mappedRoles());
        assertThrows(SecurityException.class, () -> service.validateFederatedIdentity(valid, Map.of(), NOW));
        assertThrows(SecurityException.class, () -> service.validateFederatedIdentity(assertion(false, true, "sub", "x@y"), Map.of(), NOW));
        assertThrows(SecurityException.class, () -> service.validateFederatedIdentity(assertion(true, false, "sub", "x@y"), Map.of(), NOW));
    }

    @Test void authorizationDeniesByDefaultCrossTenantAndEnforcesSeparationOfDuties() {
        var service = new TenantIdentityAuthorization();
        TenantContext developer = tenant("org-a", "alice", Set.of("DEVELOPER"), AuthenticationAssurance.MFA);
        AuthorizationDecision denied = service.authorize(request(developer, "org-a", "migration:execute", "LOW", null), NOW);
        assertEquals(AuthorizationResult.DENY, denied.decision());
        TenantContext admin = tenant("org-a", "alice", Set.of("MIGRATION_ADMIN"), AuthenticationAssurance.MFA);
        assertEquals(AuthorizationResult.DENY, service.authorize(request(admin, "org-b", "migration:execute", "LOW", null), NOW).decision());
        TenantContext reviewer = tenant("org-a", "alice", Set.of("REVIEWER"), AuthenticationAssurance.MFA);
        assertEquals(AuthorizationResult.REQUIRE_APPROVAL,
                service.authorize(request(reviewer, "org-a", "migration:review", "CRITICAL", "alice"), NOW).decision());
    }

    @Test void highRiskOperationRequiresStepUp() {
        var service = new TenantIdentityAuthorization();
        TenantContext weak = tenant("org-a", "bob", Set.of("MIGRATION_ADMIN"), AuthenticationAssurance.PASSWORD);
        assertEquals(AuthorizationResult.REQUIRE_STEP_UP,
                service.authorize(request(weak, "org-a", "migration:execute", "HIGH", null), NOW).decision());
    }

    @Test void privateRunnerLeaseChecksTenantCapabilityCertificateAndAttempt() {
        var service = new PrivateExecutionGovernance();
        RunnerNode runner = runner("org-a", RunnerStatus.ACTIVE, Set.of("JAVA_8", "MAVEN"), SourceUploadPolicy.NO_SOURCE_UPLOAD);
        RunnerJob job = new RunnerJob("job-1", "org-a", Set.of("JAVA_8"), "a".repeat(64), "idem", 1);
        RunnerJobLease lease = service.lease(runner, job, NOW, Duration.ofMinutes(5));
        assertDoesNotThrow(() -> service.acceptCompletion(lease, 1, "runner-1", NOW.plusSeconds(20)));
        assertThrows(IllegalStateException.class, () -> service.acceptCompletion(lease, 2, "runner-1", NOW.plusSeconds(20)));
        assertThrows(SecurityException.class, () -> service.lease(runner, new RunnerJob("job-2", "org-b", Set.of(), "b".repeat(64), "i2", 1), NOW, Duration.ofMinutes(5)));
        assertThrows(IllegalArgumentException.class, () -> service.lease(runner, job, NOW, Duration.ZERO));
        assertThrows(IllegalArgumentException.class, () -> service.lease(runner, job, NOW, Duration.ofHours(1)));
    }

    @Test void noSourceUploadRejectsPatchAndQuarantineStopsLeasing() {
        var service = new PrivateExecutionGovernance();
        RunnerNode runner = runner("org-a", RunnerStatus.ACTIVE, Set.of("JAVA_8"), SourceUploadPolicy.NO_SOURCE_UPLOAD);
        assertThrows(SecurityException.class, () -> service.validateUpload(runner, "PATCH"));
        RunnerNode quarantined = service.quarantine(runner, "CAPABILITY_TAMPERED");
        assertThrows(IllegalStateException.class, () -> service.lease(quarantined,
                new RunnerJob("job", "org-a", Set.of(), "c".repeat(64), "i", 1), NOW, Duration.ofMinutes(1)));
    }

    @Test void secretLeaseIsPurposeTenantAndWorkloadBound() {
        var service = new PrivateExecutionGovernance();
        SecretReference reference = new SecretReference("ref", "org-a", SecretPurpose.MAVEN_READ, "VAULT", "maven/read", false);
        WorkloadIdentity workload = new WorkloadIdentity("org-a", "runner", "job", "step");
        SecretLease lease = service.issueSecretLease(reference, workload, SecretPurpose.MAVEN_READ, true, NOW, Duration.ofMinutes(2));
        assertFalse(lease.revoked());
        assertTrue(service.revoke(lease).revoked());
        assertThrows(SecurityException.class, () -> service.issueSecretLease(reference, workload, SecretPurpose.ARTIFACT_WRITE, true, NOW, Duration.ofMinutes(1)));
        SecretReference development = new SecretReference("dev", "org-a", SecretPurpose.MAVEN_READ, "DEV", "x", true);
        assertThrows(SecurityException.class, () -> service.issueSecretLease(development, workload, SecretPurpose.MAVEN_READ, true, NOW, Duration.ofMinutes(1)));
        assertThrows(IllegalArgumentException.class, () -> service.issueSecretLease(reference, workload,
                SecretPurpose.MAVEN_READ, true, NOW, Duration.ofSeconds(-1)));
    }

    @Test void restrictedCodeCannotFailOverToPublicProvider() {
        var service = new PrivateExecutionGovernance();
        ModelPolicy policy = new ModelPolicy("p1", Set.of(ModelProviderType.ELMOS_MANAGED, ModelProviderType.ON_PREMISES_MODEL),
                Set.of("cn-private", "us"), Set.of(DataClassification.RESTRICTED_CODE), false, 2000, false, false);
        ModelRequest request = new ModelRequest("inv", "org-a", "JAVA_REPAIR_STANDARD", DataClassification.RESTRICTED_CODE,
                100, true, BigDecimal.TEN, "a".repeat(64), "b".repeat(64));
        ModelEndpoint publicEndpoint = endpoint("public", ModelProviderType.ELMOS_MANAGED, "us");
        assertEquals(ModelDecisionStatus.HUMAN_REQUIRED, service.routeModel(policy, request, List.of(publicEndpoint), BigDecimal.TEN).status());
        ModelEndpoint privateEndpoint = endpoint("private", ModelProviderType.ON_PREMISES_MODEL, "cn-private");
        assertEquals("private", service.routeModel(policy, request, List.of(publicEndpoint, privateEndpoint), BigDecimal.TEN).providerId());
    }

    @Test void secretScanAndBudgetBlockModelBeforeRouting() {
        var service = new PrivateExecutionGovernance();
        ModelPolicy policy = new ModelPolicy("p1", Set.of(ModelProviderType.ON_PREMISES_MODEL), Set.of("cn"),
                Set.of(DataClassification.INTERNAL_CODE), false, 100, false, false);
        ModelRequest request = new ModelRequest("inv", "org-a", "JAVA_REPAIR_STANDARD", DataClassification.INTERNAL_CODE,
                90, false, BigDecimal.TEN, "a".repeat(64), "b".repeat(64));
        ModelRoutingDecision result = service.routeModel(policy, request,
                List.of(endpoint("private", ModelProviderType.ON_PREMISES_MODEL, "cn")), BigDecimal.ONE);
        assertEquals(ModelDecisionStatus.BLOCKED, result.status());
        assertTrue(result.reasonCodes().containsAll(List.of("SECRET_SCAN_FAILED", "MODEL_BUDGET_NOT_RESERVED")));
    }

    @Test void concurrentCreditReservationCannotCreateNegativeBalance() throws Exception {
        var ledger = new UsageAndAuditGovernance();
        ledger.openCreditAccount("org-a", new BigDecimal("100"));
        try (var executor = Executors.newFixedThreadPool(2)) {
            Callable<UsageReservation> first = () -> ledger.reserve("org-a", new BigDecimal("80"), "a", NOW.plusSeconds(60));
            Callable<UsageReservation> second = () -> ledger.reserve("org-a", new BigDecimal("80"), "b", NOW.plusSeconds(60));
            var results = executor.invokeAll(List.of(first, second)).stream().map(future -> {
                try { return future.get(); } catch (Exception error) { throw new RuntimeException(error); }
            }).toList();
            assertEquals(1, results.stream().filter(value -> value.status() == ReservationStatus.RESERVED).count());
            assertEquals(new BigDecimal("20"), ledger.available("org-a"));
        }
    }

    @Test void usageEventsAreIdempotentAndRequireCostSnapshot() {
        var ledger = new UsageAndAuditGovernance();
        UsageEvent event = new UsageEvent("u1", "org-a", "AGENT_OUTPUT_TOKEN", BigDecimal.TEN, "TOKEN", NOW, "inv", "idem", "cost-v1");
        assertTrue(ledger.recordUsage(event));
        assertFalse(ledger.recordUsage(event));
        assertTrue(ledger.recordUsage(new UsageEvent("u-org-b", "org-b", "AGENT_OUTPUT_TOKEN", BigDecimal.ONE,
                "TOKEN", NOW, "inv-b", "idem", "cost-v1")));
        assertThrows(IllegalArgumentException.class, () -> ledger.recordUsage(new UsageEvent("u2", "org-a", "X", BigDecimal.ONE, "U", NOW, "x", "i2", null)));
    }

    @Test void reservationIdempotencyAndSettlementAreTenantScoped() {
        var ledger = new UsageAndAuditGovernance();
        ledger.openCreditAccount("org-a", BigDecimal.TEN);
        ledger.openCreditAccount("org-b", BigDecimal.TEN);
        UsageReservation orgA = ledger.reserve("org-a", BigDecimal.ONE, "same-key", NOW.plusSeconds(60));
        UsageReservation orgB = ledger.reserve("org-b", BigDecimal.ONE, "same-key", NOW.plusSeconds(60));
        assertEquals("org-a", orgA.organizationId());
        assertEquals("org-b", orgB.organizationId());
        ledger.reserve("org-a", BigDecimal.ONE, "org-a-only", NOW.plusSeconds(60));
        assertThrows(IllegalStateException.class,
                () -> ledger.settle("org-b", "org-a-only", BigDecimal.ZERO, NOW, "cost-v1"));
        assertThrows(IllegalStateException.class,
                () -> ledger.release("org-b", "org-a-only"));
    }

    @Test void auditChainDetectsTamperingAndRejectsSecrets() {
        var governance = new UsageAndAuditGovernance();
        AuditDraft draft = audit("a1", Map.of("reason", "approved"));
        AuditEvent event = governance.appendAudit(List.of(), draft, true, true);
        assertTrue(governance.verifyAudit(List.of(event)).valid());
        AuditEvent tampered = new AuditEvent(new AuditDraft("a1", "org-a", "USER", "alice", "migration.delete",
                "RUN", "r1", "ALLOWED", "p1", null, null, "corr", NOW, Map.of()), event.previousHash(), event.eventHash());
        assertFalse(governance.verifyAudit(List.of(tampered)).valid());
        assertThrows(SecurityException.class, () -> governance.appendAudit(List.of(), audit("a2", Map.of("password", "value")), true, true));
        assertThrows(IllegalStateException.class, () -> governance.appendAudit(List.of(), draft, false, true));
    }

    @Test void legalHoldBlocksDeletionAndRestoreReplaysTombstone() {
        var governance = new DataAndDeploymentGovernance();
        LegalHold hold = new LegalHold("h1", "org-a", Set.of("EVIDENCE"), NOW.minusSeconds(1), null, false);
        assertEquals(DeletionStatus.BLOCKED_BY_LEGAL_HOLD,
                governance.planDeletion("org-a", Set.of("EVIDENCE"), List.of(hold), true, false, NOW).status());
        assertEquals(Set.of("keep"), governance.reconcileRestore(Set.of("keep", "deleted"), Set.of("deleted")));
    }

    @Test void dataResidencyIsChosenBeforeStorage() {
        var governance = new DataAndDeploymentGovernance();
        TenantContext tenant = tenant("org-a", "alice", Set.of("DEVELOPER"), AuthenticationAssurance.MFA);
        assertThrows(SecurityException.class, () -> governance.registerData("d1", tenant, "SOURCE_SNAPSHOT", "eu",
                Set.of("cn", "eu"), "organizations/org-a/snapshots/x", DataClassification.CONFIDENTIAL_CODE, "r1", "k1", NOW));
    }

    @Test void airGapBundleAndLicenseFailClosedButHistoryRemainsReadable() {
        var governance = new DataAndDeploymentGovernance();
        ReleaseBundle bundle = new ReleaseBundle("b1", "1.0", Map.of("image", "a".repeat(64)), true, true, true, false);
        assertEquals(CapabilityStatus.AVAILABLE, governance.verifyBundle(bundle, DeploymentMode.AIR_GAPPED,
                true, true, true, true, true).status());
        OfflineLicense license = new OfflineLicense("install", "ENTERPRISE", Set.of("migration.execute"), 5,
                NOW.minusSeconds(3600), NOW.minusSeconds(120), 0, true);
        DeploymentDecision expired = governance.evaluateOfflineLicense(license, "install", NOW, true);
        assertEquals(CapabilityStatus.BLOCKED, expired.status());
        assertTrue(expired.historicalEvidenceReadable());
        assertTrue(governance.noAgentModeCapabilities(false).get("openRewrite") == CapabilityStatus.AVAILABLE);
    }

    private static Organization organization(String id) {
        return new Organization(id, id, OrganizationStatus.ACTIVE, IsolationClass.T2_DEDICATED_DATA_PLANE, "cn", "key-" + id);
    }
    private static TenantContext tenant(String org, String actor, Set<String> roles, AuthenticationAssurance assurance) {
        return new TenantContext(org, actor, roles, assurance, "cn", "corr");
    }
    private static IdentityAssertion assertion(boolean issuer, boolean nonce, String subject, String email) {
        return new IdentityAssertion(AuthenticationProtocol.OIDC, "conn", issuer ? "https://idp" : "https://bad",
                "https://idp", "elmos", "elmos", subject, email, "n", nonce, true,
                NOW.plusSeconds(60), true, Set.of("unknown"));
    }
    private static AuthorizationRequest request(TenantContext tenant, String resourceOrg, String action, String risk, String author) {
        return new AuthorizationRequest(tenant, resourceOrg, "MIGRATION_RUN", "run", action, Map.of("risk", risk), author, Set.of(), "p1");
    }
    private static RunnerNode runner(String org, RunnerStatus status, Set<String> capabilities, SourceUploadPolicy upload) {
        return new RunnerNode("runner-1", org, "pool", status, capabilities, "a".repeat(64), "thumb", NOW.plusSeconds(600), upload);
    }
    private static ModelEndpoint endpoint(String id, ModelProviderType type, String region) {
        return new ModelEndpoint(id, type, "org-a", region, "v1", true, true, Set.of("JAVA_REPAIR_STANDARD"));
    }
    private static AuditDraft audit(String id, Map<String,String> metadata) {
        return new AuditDraft(id, "org-a", "USER", "alice", "migration.execute", "RUN", "r1", "ALLOWED",
                "p1", null, null, "corr", NOW, metadata);
    }
}
