package io.elmos.platform;

import java.time.Instant;
import java.util.*;
import java.util.function.Supplier;

import static io.elmos.platform.EnterprisePlatformModels.*;

/** Fail-closed T-A through T-G evaluator over externally observed enterprise-platform evidence. */
public final class EnterprisePlatformService {
    private final EnterprisePlatformAuthorities authorities;

    public EnterprisePlatformService(EnterprisePlatformAuthorities authorities) {
        this.authorities = Objects.requireNonNull(authorities, "authorities");
    }

    public Outcome evaluate(Request request) {
        Objects.requireNonNull(request, "request");
        admit(request);
        List<String> blockers = new ArrayList<>();

        TenancyIdentityEvidence tenancy = observe("tenancy/identity", () -> authorities.tenancyIdentity().observe(request), blockers);
        AuthorizationAuditEvidence authorization = observe("authorization/audit", () -> authorities.authorizationAudit().observe(request), blockers);
        RunnerSecurityEvidence runner = observe("runner security", () -> authorities.runnerSecurity().observe(request), blockers);
        ModelCostEvidence modelCost = observe("model/cost", () -> authorities.modelCost().observe(request), blockers);
        DataGovernanceEvidence data = observe("data governance", () -> authorities.dataGovernance().observe(request), blockers);
        DeploymentEvidence deployment = observe("deployment", () -> authorities.deployment().observe(request), blockers);
        EnterpriseAcceptanceEvidence acceptance = observe("enterprise acceptance", () -> authorities.enterpriseAcceptance().observe(request), blockers);

        for (EvidenceEnvelope envelope : Arrays.asList(tenancy, authorization, runner, modelCost, data, deployment, acceptance))
            if (envelope != null) validateEnvelope(request, envelope, blockers);
        addCriticalBlockers(tenancy, authorization, runner, modelCost, data, deployment, acceptance, blockers);

        boolean ta = passesTa(request, tenancy);
        boolean tb = ta && passesTb(request, authorization);
        boolean tc = tb && passesTc(request, runner);
        boolean td = tc && passesTd(request, modelCost);
        boolean te = td && passesTe(request, data);
        boolean tf = te && passesTf(request, deployment);
        boolean tg = tf && passesTg(request, acceptance);
        Gate gate = tg ? Gate.T_G : tf ? Gate.T_F : te ? Gate.T_E : td ? Gate.T_D
                : tc ? Gate.T_C : tb ? Gate.T_B : ta ? Gate.T_A : Gate.BLOCKED;

        List<String> restrictions = restrictions(ta, tb, tc, td, te, tf, tg);
        boolean externalComplete = StreamEvidence.allValid(request, tenancy, authorization, runner, modelCost, data, deployment, acceptance);
        if (!ta) blockers.add("T-A tenant and identity evidence is not satisfied");
        blockers = blockers.stream().distinct().sorted().toList();
        RunStatus status = !blockers.isEmpty() ? RunStatus.BLOCKED : status(gate);
        List<ModeConformance> modeReports = modeConformance(request, deployment, gate, tg);
        boolean ready = tg && blockers.isEmpty() && externalComplete;
        Metrics metrics = metrics(tenancy, authorization, runner, modelCost, data, deployment, acceptance);
        List<String> evidenceRefs = evidenceRefs(request, tenancy, authorization, runner, modelCost, data, deployment, acceptance);
        ConformanceReport report = new ConformanceReport(12, request.assessmentRunId(), request.platform().platformVersion(),
                gate, status, modeReports, blockers, restrictions, metrics, externalComplete, ready,
                false, request.observedAt(), evidenceRefs);
        return new Outcome(request, tenancy, authorization, runner, modelCost, data, deployment, acceptance, report);
    }

    private static void admit(Request request) {
        PlatformArtifact platform = request.platform();
        if (!platform.immutable() || !platform.signed() || !platform.batch1Through11ControlPlanesVerified())
            throw new IllegalArgumentException("platform must be immutable, signed and bound to verified Batch 1-11 control planes");
        unique(request.tenants().stream().map(TenantProfile::tenantId).toList(), "tenant ids");
        unique(request.tenants().stream().map(TenantProfile::organizationId).toList(), "organization ownership");
        unique(request.tenants().stream().map(TenantProfile::encryptionKeyRef).toList(), "tenant encryption keys");
        unique(request.deployments().stream().map(profile -> profile.mode().name()).toList(), "deployment modes");
        unique(request.capabilities().stream().map(CapabilityBinding::capabilityId).toList(), "capability ids");
        Set<DeploymentMode> actual = new HashSet<>(request.deployments().stream().map(DeploymentProfile::mode).toList());
        if (!actual.equals(EnumSet.allOf(DeploymentMode.class)) || request.deployments().stream().anyMatch(profile -> !profile.required()))
            throw new IllegalArgumentException("all five Batch 12 deployment modes must be independently required and declared");
        if (request.tenants().stream().anyMatch(tenant -> !actual.contains(tenant.deploymentMode())))
            throw new IllegalArgumentException("every tenant must reference a declared deployment mode");
        if (request.capabilities().stream().anyMatch(capability -> !capability.available()))
            throw new IllegalArgumentException("all declared enterprise capability bindings must be available");
    }

    private static void unique(List<String> values, String label) {
        if (values.size() != new HashSet<>(values).size()) throw new IllegalArgumentException(label + " must be unique");
    }

    private static <T extends EvidenceEnvelope> T observe(String name, Supplier<T> call, List<String> blockers) {
        try {
            T result = call.get();
            if (result == null) blockers.add(name + " authority returned no evidence");
            return result;
        } catch (RuntimeException error) {
            blockers.add(name + " authority failed safely: " + error.getClass().getSimpleName());
            return null;
        }
    }

    private static void validateEnvelope(Request request, EvidenceEnvelope evidence, List<String> blockers) {
        if (!request.assessmentRunId().equals(evidence.assessmentRunId())) blockers.add("authority evidence run mismatch");
        if (!request.platform().platformVersion().equals(evidence.platformVersion())) blockers.add("authority evidence platform version mismatch");
        if (evidence.observedAt().isAfter(request.observedAt())) blockers.add("authority evidence observation is in the future");
        if (evidence.status() != EvidenceStatus.PASSED) blockers.add("authority evidence status is " + evidence.status());
    }

    private static boolean passesTa(Request request, TenancyIdentityEvidence value) {
        if (!validEnvelope(request, value)) return false;
        boolean profiles = request.tenants().stream().allMatch(tenant -> tenant.resourceOwnershipComplete()
                && tenant.dedicatedDataKey() && tenant.runnerBoundaryDeclared() && tenant.modelPolicyDeclared()
                && tenant.auditSinkConfigured() && tenant.legalHoldPolicyConfigured());
        boolean isolationMatches = request.tenants().stream().allMatch(tenant -> tenant.deploymentMode() != DeploymentMode.AIR_GAPPED
                || tenant.isolationLevel() == IsolationLevel.LEVEL_6_AIR_GAPPED);
        return profiles && isolationMatches
                && value.tenantOwnershipCoverage() >= request.policy().requiredTenantOwnershipCoverage()
                && value.crossTenantDataLeaks() == 0 && value.crossTenantArtifactContamination() == 0
                && value.crossTenantCacheContamination() == 0
                && value.tenantKeyIsolationCoverage() >= request.policy().requiredKeyIsolationCoverage()
                && value.noisyNeighborControlsPassed() && (value.oidcPassed() || value.samlPassed())
                && (!value.scimRequired() || (value.scimPassed() && value.scimIdempotent()))
                && value.sessionRevocationPassed()
                && value.deprovisionLatencySeconds() <= request.policy().maximumDeprovisionSeconds()
                && value.mfaForSensitiveRoles() && value.wrongTenantIdentityBindings() == 0
                && value.idpTenantBindingComplete();
    }

    private static boolean passesTb(Request request, AuthorizationAuditEvidence value) {
        return validEnvelope(request, value) && value.apiPermissionCoverage() >= request.policy().requiredPermissionCoverage()
                && value.policyCoverage() >= request.policy().requiredPolicyCoverage()
                && value.policyDecisionAuditCoverage() >= request.policy().requiredAuditCoverage()
                && value.highRiskApprovalCoverage() >= request.policy().requiredApprovalCoverage()
                && value.selfApprovalEvents() == 0 && value.tenantAdminPlatformPrivilegeEvents() == 0
                && value.separationOfDutiesPassed() && value.breakGlassDrillPassed()
                && value.unboundedBreakGlassEvents() == 0
                && value.breakGlassAuditCoverage() >= request.policy().requiredAuditCoverage()
                && value.criticalAuditCoverage() >= request.policy().requiredAuditCoverage()
                && value.auditTamperDetectionPassed() && value.auditOverwriteEvents() == 0;
    }

    private static boolean passesTc(Request request, RunnerSecurityEvidence value) {
        return validEnvelope(request, value) && value.workloadIdentityPassed() && value.attestationCoverage() == 1
                && value.runnerIdentityCopyEvents() == 0 && value.crossTenantJobLeaks() == 0
                && value.sandboxEscapeFindings() == 0 && value.unauthorizedEgressEvents() == 0
                && value.secretLeakEvents() == 0 && value.shortLivedCredentialsPassed()
                && value.sourceStayLocalVerified() && value.artifactTransferIntegrityPassed()
                && value.tenantRunnerIsolationPassed() && value.leaseRecoveryPassed()
                && value.duplicateNonIdempotentExecutions() == 0;
    }

    private static boolean passesTd(Request request, ModelCostEvidence value) {
        return validEnvelope(request, value) && value.modelGatewayBypassPaths() == 0 && value.modelDataPolicyViolations() == 0
                && value.promptSecretLeaks() == 0 && value.crossTenantPromptCacheEvents() == 0
                && value.modelProvenanceCoverage() >= request.policy().requiredModelProvenanceCoverage()
                && value.quotaBypassEvents() == 0 && value.duplicateMeterEvents() == 0
                && value.usageLedgerIntegrityPassed() && value.historicalLedgerMutationEvents() == 0
                && value.billingReconciliationDifference() <= request.policy().maximumBillingDifference()
                && value.duplicateCharges() == 0 && value.fairSchedulingPassed() && value.starvationEvents() == 0
                && value.budgetControlsPassed() && value.entitlementControlsPassed();
    }

    private static boolean passesTe(Request request, DataGovernanceEvidence value) {
        return validEnvelope(request, value) && value.classificationCoverage() >= request.policy().requiredClassificationCoverage()
                && value.residencyCompliancePassed()
                && value.retentionCoverage() >= request.policy().requiredRetentionCoverage()
                && value.legalHoldPassed() && value.legalHoldDeletionEvents() == 0
                && value.deletionCertificatePassed() && value.unexplainedResidualCopies() == 0
                && value.tenantKeyIsolationCoverage() >= request.policy().requiredKeyIsolationCoverage()
                && value.keyRotationPassed() && value.backupKeyRestorePassed() && value.cmkFailureFailsClosed()
                && value.artifactProvenanceCoverage() >= request.policy().requiredArtifactProvenanceCoverage()
                && value.supportAccessControlled();
    }

    private static boolean passesTf(Request request, DeploymentEvidence value) {
        if (!validEnvelope(request, value)) return false;
        Map<DeploymentMode, ModeResult> results = modeResults(value);
        return request.deployments().stream().allMatch(profile -> modePasses(profile, results.get(profile.mode())));
    }

    private static boolean passesTg(Request request, EnterpriseAcceptanceEvidence value) {
        return validEnvelope(request, value) && value.controlPlaneHaPassed() && value.backupRestorePassed()
                && value.queueRecoveryNoLoss() && value.auditAndLedgerRestorePassed()
                && value.runnerReconnectNoDuplicate() && value.observabilityPassed()
                && value.administrationConsolePassed() && value.apiCliSdkPassed() && value.gitCiIntegrationPassed()
                && value.engineeringAccepted() && value.securityAccepted() && value.operationsAccepted()
                && value.businessAccepted() && value.contractCapabilitiesAligned() && value.criticalOpenRisks() == 0
                && value.enterpriseEvidencePackComplete()
                && value.evidenceTraceability() >= request.policy().requiredEvidenceTraceability();
    }

    private static boolean modePasses(DeploymentProfile profile, ModeResult result) {
        if (result == null || result.status() != EvidenceStatus.PASSED || !profile.required()
                || !profile.contractDeclared() || !profile.responsibilityMatrixComplete() || !profile.dataFlowApproved()
                || !result.topologyValidated() || !result.responsibilityMatrixComplete()
                || !result.installationPassed() || result.hiddenSaasDependencies() != 0
                || !result.signedArtifactsPassed() || !result.dependencyClosurePassed()
                || !result.rollbackPassed() || !result.haAndBackupRestorePassed()) return false;
        if (profile.mode() == DeploymentMode.AIR_GAPPED) {
            return result.unexpectedNetworkRequests() == 0 && result.localModelExecutionPassed()
                    && result.modelLicensePassed() && result.offlineLicensePassed() && result.offlineUpdatePassed();
        }
        return true;
    }

    private static Map<DeploymentMode, ModeResult> modeResults(DeploymentEvidence value) {
        if (value == null) return Map.of();
        Map<DeploymentMode, ModeResult> result = new EnumMap<>(DeploymentMode.class);
        for (ModeResult mode : value.modes()) if (result.put(mode.mode(), mode) != null) return Map.of();
        return Map.copyOf(result);
    }

    private static void addCriticalBlockers(TenancyIdentityEvidence tenancy, AuthorizationAuditEvidence authorization,
                                            RunnerSecurityEvidence runner, ModelCostEvidence modelCost,
                                            DataGovernanceEvidence data, DeploymentEvidence deployment,
                                            EnterpriseAcceptanceEvidence acceptance, List<String> blockers) {
        if (tenancy != null) {
            if (tenancy.crossTenantDataLeaks() > 0) blockers.add("cross-tenant data leak detected");
            if (tenancy.crossTenantArtifactContamination() > 0 || tenancy.crossTenantCacheContamination() > 0)
                blockers.add("cross-tenant artifact or cache contamination detected");
            if (tenancy.wrongTenantIdentityBindings() > 0) blockers.add("external identity entered the wrong tenant");
        }
        if (authorization != null) {
            if (authorization.selfApprovalEvents() > 0) blockers.add("high-risk self approval detected");
            if (authorization.tenantAdminPlatformPrivilegeEvents() > 0) blockers.add("tenant administrator obtained platform privilege");
            if (authorization.unboundedBreakGlassEvents() > 0) blockers.add("unbounded break-glass access detected");
            if (authorization.auditOverwriteEvents() > 0) blockers.add("audit overwrite detected");
        }
        if (runner != null) {
            if (runner.runnerIdentityCopyEvents() > 0 || runner.crossTenantJobLeaks() > 0) blockers.add("runner identity or tenant job isolation failed");
            if (runner.sandboxEscapeFindings() > 0) blockers.add("sandbox escape finding is open");
            if (runner.unauthorizedEgressEvents() > 0) blockers.add("unauthorized Runner egress detected");
            if (runner.secretLeakEvents() > 0) blockers.add("secret leaked through Runner, log or Prompt");
            if (runner.duplicateNonIdempotentExecutions() > 0) blockers.add("non-idempotent Runner work executed more than once");
        }
        if (modelCost != null) {
            if (modelCost.modelGatewayBypassPaths() > 0) blockers.add("model gateway bypass path detected");
            if (modelCost.modelDataPolicyViolations() > 0 || modelCost.promptSecretLeaks() > 0)
                blockers.add("model data policy or Prompt secret violation detected");
            if (modelCost.crossTenantPromptCacheEvents() > 0) blockers.add("cross-tenant Prompt cache contamination detected");
            if (modelCost.quotaBypassEvents() > 0) blockers.add("quota bypass detected");
            if (modelCost.historicalLedgerMutationEvents() > 0) blockers.add("immutable usage ledger was modified");
            if (modelCost.duplicateCharges() > 0) blockers.add("duplicate customer charge detected");
        }
        if (data != null) {
            if (data.legalHoldDeletionEvents() > 0) blockers.add("data under Legal Hold was deleted");
            if (data.unexplainedResidualCopies() > 0) blockers.add("tenant deletion left unexplained data copies");
        }
        if (deployment != null) for (ModeResult mode : deployment.modes()) {
            if (mode.hiddenSaasDependencies() > 0) blockers.add(mode.mode() + " has hidden SaaS dependencies");
            if (mode.mode() == DeploymentMode.AIR_GAPPED && mode.unexpectedNetworkRequests() > 0)
                blockers.add("air-gapped installation attempted external network access");
            if (!mode.signedArtifactsPassed()) blockers.add(mode.mode() + " contains unsigned artifacts");
        }
        if (acceptance != null && acceptance.criticalOpenRisks() > 0) blockers.add("critical enterprise delivery risk remains open");
    }

    private static List<String> restrictions(boolean ta, boolean tb, boolean tc, boolean td,
                                             boolean te, boolean tf, boolean tg) {
        List<String> result = new ArrayList<>();
        if (!ta) result.add("T-A tenant and identity gate not passed");
        if (!tb) result.add("T-B authorization and audit gate not passed");
        if (!tc) result.add("T-C private Runner gate not passed");
        if (!td) result.add("T-D model and cost governance gate not passed");
        if (!te) result.add("T-E data governance gate not passed");
        if (!tf) result.add("T-F private and offline delivery gate not passed");
        if (!tg) result.add("T-G enterprise delivery gate not passed");
        return List.copyOf(result);
    }

    private static RunStatus status(Gate gate) {
        return switch (gate) {
            case BLOCKED -> RunStatus.INITIALIZED;
            case T_A -> RunStatus.TENANCY_IDENTITY_VALIDATED;
            case T_B -> RunStatus.AUTHORIZATION_AUDIT_VALIDATED;
            case T_C -> RunStatus.RUNNER_SECURITY_VALIDATED;
            case T_D -> RunStatus.MODEL_COST_GOVERNED;
            case T_E -> RunStatus.DATA_GOVERNED;
            case T_F -> RunStatus.DEPLOYMENT_MODES_VALIDATED;
            case T_G -> RunStatus.ENTERPRISE_DELIVERY_READY;
        };
    }

    private static List<ModeConformance> modeConformance(Request request, DeploymentEvidence evidence, Gate gate, boolean tg) {
        Map<DeploymentMode, ModeResult> results = modeResults(evidence);
        List<ModeConformance> reports = new ArrayList<>();
        for (DeploymentProfile profile : request.deployments()) {
            ModeResult result = results.get(profile.mode());
            boolean modePassed = modePasses(profile, result);
            List<String> blockers = new ArrayList<>();
            if (!modePassed) blockers.add("deployment mode has not passed its independent T-F evidence");
            Gate modeGate = gate.level() < Gate.T_E.level() ? gate : modePassed ? (tg ? Gate.T_G : Gate.T_F) : Gate.T_E;
            reports.add(new ModeConformance(profile.mode(), modeGate, tg && modePassed,
                    blockers, result == null ? List.of() : result.evidenceRefs()));
        }
        return reports.stream().sorted(Comparator.comparing(value -> value.mode().ordinal())).toList();
    }

    private static Metrics metrics(TenancyIdentityEvidence t, AuthorizationAuditEvidence a, RunnerSecurityEvidence r,
                                   ModelCostEvidence m, DataGovernanceEvidence d, DeploymentEvidence p,
                                   EnterpriseAcceptanceEvidence e) {
        int offlineRequests = p == null ? 0 : p.modes().stream().filter(v -> v.mode() == DeploymentMode.AIR_GAPPED)
                .mapToInt(ModeResult::unexpectedNetworkRequests).sum();
        return new Metrics(t == null ? 0 : t.tenantOwnershipCoverage(), t == null ? 0 : t.crossTenantDataLeaks(),
                a == null ? 0 : a.apiPermissionCoverage(), a == null ? 0 : a.policyCoverage(),
                r == null ? 0 : r.attestationCoverage(), r == null ? 0 : r.crossTenantJobLeaks() + r.sandboxEscapeFindings(),
                m == null ? 0 : m.modelGatewayBypassPaths(), m == null ? 0 : m.quotaBypassEvents(),
                m == null ? 0 : m.duplicateMeterEvents(), m == null ? 0 : m.billingReconciliationDifference(),
                a == null ? 0 : a.criticalAuditCoverage(), d == null ? 0 : d.classificationCoverage(),
                d == null ? 0 : d.retentionCoverage(), d == null ? 0 : d.legalHoldDeletionEvents(), offlineRequests,
                e == null ? 0 : e.criticalOpenRisks(), e == null ? 0 : e.evidenceTraceability());
    }

    private static List<String> evidenceRefs(Request request, EvidenceEnvelope... envelopes) {
        LinkedHashSet<String> refs = new LinkedHashSet<>(request.platform().evidenceRefs());
        request.tenants().forEach(value -> refs.addAll(value.evidenceRefs()));
        request.deployments().forEach(value -> refs.addAll(value.evidenceRefs()));
        request.capabilities().forEach(value -> refs.addAll(value.evidenceRefs()));
        for (EvidenceEnvelope value : envelopes) if (value != null) refs.addAll(value.evidenceRefs());
        return List.copyOf(refs);
    }

    private static boolean passed(EvidenceEnvelope value) { return value != null && value.status() == EvidenceStatus.PASSED; }

    private static boolean validEnvelope(Request request, EvidenceEnvelope value) {
        return passed(value) && request.assessmentRunId().equals(value.assessmentRunId())
                && request.platform().platformVersion().equals(value.platformVersion())
                && !value.observedAt().isAfter(request.observedAt());
    }

    private static final class StreamEvidence {
        private StreamEvidence() {}
        static boolean allValid(Request request, EvidenceEnvelope... values) {
            return Arrays.stream(values).allMatch(value -> validEnvelope(request, value));
        }
    }
}
