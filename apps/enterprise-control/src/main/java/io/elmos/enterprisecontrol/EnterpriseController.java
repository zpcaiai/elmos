package io.elmos.enterprisecontrol;

import io.elmos.enterprise.*;
import io.elmos.enterprise.EnterpriseModels.*;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

@RestController
@RequestMapping("/enterprise/v1")
public final class EnterpriseController {
    private final TenantIdentityAuthorization identity = new TenantIdentityAuthorization();
    private final PrivateExecutionGovernance execution = new PrivateExecutionGovernance();
    private final UsageAndAuditGovernance usageAudit = new UsageAndAuditGovernance();
    private final DataAndDeploymentGovernance dataDeployment = new DataAndDeploymentGovernance();

    public record TenantRequest(VerifiedPrincipal principal, Organization organization,
                                String requestedOrganizationId, String correlationId) {}
    public record LeaseRequest(RunnerNode runner, RunnerJob job, Instant now, long durationSeconds) {}
    public record SecretLeaseRequest(SecretReference reference, WorkloadIdentity workload,
                                     SecretPurpose purpose, boolean production, Instant now, long durationSeconds) {}
    public record ModelRouteRequest(ModelPolicy policy, ModelRequest request,
                                    List<ModelEndpoint> endpoints, BigDecimal reservedBudget) {}
    public record ReserveRequest(String organizationId, BigDecimal amount, String idempotencyKey, Instant expiresAt) {}
    public record AuditAppendRequest(List<AuditEvent> chain, AuditDraft event,
                                     boolean auditWriterAvailable, boolean highRisk) {}
    public record DeletionRequest(String organizationId, Set<String> dataTypes, List<LegalHold> legalHolds,
                                  boolean independentOrganizationKey, boolean backupSelectiveDeletionSupported,
                                  Instant now) {}
    public record BundleRequest(ReleaseBundle bundle, DeploymentMode mode, boolean localRegistryReady,
                                boolean localRecipeRegistryReady, boolean localVulnerabilityDbReady,
                                boolean localIdentityReady, boolean localSecretProviderReady) {}
    public record LicenseRequest(OfflineLicense license, String installationId, Instant now, boolean startNewWork) {}

    @PostMapping("/tenant-context") TenantContext tenant(@RequestBody TenantRequest request) {
        return identity.deriveTenantContext(request.principal(), request.organization(), request.requestedOrganizationId(), request.correlationId());
    }
    @PostMapping("/authorization/decisions") AuthorizationDecision authorize(@RequestBody AuthorizationRequest request) {
        return identity.authorize(request, Instant.now());
    }
    @PostMapping("/runner/job-leases") RunnerJobLease lease(@RequestBody LeaseRequest request) {
        return execution.lease(request.runner(), request.job(), request.now(), Duration.ofSeconds(request.durationSeconds()));
    }
    @PostMapping("/secret/leases") SecretLease secretLease(@RequestBody SecretLeaseRequest request) {
        return execution.issueSecretLease(request.reference(), request.workload(), request.purpose(), request.production(),
                request.now(), Duration.ofSeconds(request.durationSeconds()));
    }
    @PostMapping("/models/route") ModelRoutingDecision modelRoute(@RequestBody ModelRouteRequest request) {
        return execution.routeModel(request.policy(), request.request(), request.endpoints(), request.reservedBudget());
    }
    @PostMapping("/usage/accounts/{organizationId}") void openAccount(@PathVariable String organizationId,
                                                                      @RequestBody Map<String, BigDecimal> body) {
        usageAudit.openCreditAccount(organizationId, body.get("available"));
    }
    @PostMapping("/usage/reservations") UsageReservation reserve(@RequestBody ReserveRequest request) {
        return usageAudit.reserve(request.organizationId(), request.amount(), request.idempotencyKey(), request.expiresAt());
    }
    @PostMapping("/audit/events") AuditEvent audit(@RequestBody AuditAppendRequest request) {
        return usageAudit.appendAudit(request.chain(), request.event(), request.auditWriterAvailable(), request.highRisk());
    }
    @PostMapping("/audit/verify") AuditVerification verify(@RequestBody List<AuditEvent> chain) { return usageAudit.verifyAudit(chain); }
    @PostMapping("/deletions/plan") DeletionDecision deletion(@RequestBody DeletionRequest request) {
        return dataDeployment.planDeletion(request.organizationId(), request.dataTypes(), request.legalHolds(),
                request.independentOrganizationKey(), request.backupSelectiveDeletionSupported(), request.now());
    }
    @PostMapping("/deployments/bundles/verify") DeploymentDecision bundle(@RequestBody BundleRequest request) {
        return dataDeployment.verifyBundle(request.bundle(), request.mode(), request.localRegistryReady(),
                request.localRecipeRegistryReady(), request.localVulnerabilityDbReady(), request.localIdentityReady(),
                request.localSecretProviderReady());
    }
    @PostMapping("/deployments/licenses/evaluate") DeploymentDecision license(@RequestBody LicenseRequest request) {
        return dataDeployment.evaluateOfflineLicense(request.license(), request.installationId(), request.now(), request.startNewWork());
    }
    @GetMapping("/capabilities") Map<String,Object> capabilities() {
        return Map.of("schemaVersion", "1.0", "tenantPolicy", "AVAILABLE", "authorizationPolicy", "AVAILABLE",
                "oidcAdapter", "NOT_CONFIGURED", "samlAdapter", "NOT_CONFIGURED", "privateRunnerChannel", "NOT_CONFIGURED",
                "externalSecretProvider", "NOT_CONFIGURED", "externalModelProvider", "NOT_CONFIGURED",
                "airGapBundleVerification", "AVAILABLE", "reason", "External integrations require tenant-scoped configuration and evidence.");
    }
    @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class, SecurityException.class})
    @ResponseStatus(HttpStatus.BAD_REQUEST) Map<String,Object> bad(RuntimeException error) {
        return Map.of("errorCode", "ENTERPRISE_POLICY_REJECTED", "message", "The enterprise request was rejected by its policy contract.", "retryable", false);
    }
}
