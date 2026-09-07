package io.elmos.enterprise;

import io.elmos.enterprise.EnterpriseModels.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

public final class PrivateExecutionGovernance {

    public RunnerJobLease lease(RunnerNode runner, RunnerJob job, Instant now, Duration duration) {
        requireShortLease(duration);
        if (!runner.organizationId().equals(job.organizationId())) throw new SecurityException("CROSS_TENANT_JOB_DENIED");
        if (runner.status() != RunnerStatus.ACTIVE) throw new IllegalStateException("RUNNER_NOT_ACTIVE");
        if (!runner.capabilities().containsAll(job.requiredCapabilities())) throw new IllegalStateException("RUNNER_CAPABILITY_MISMATCH");
        if (runner.certificateExpiresAt() == null || !now.isBefore(runner.certificateExpiresAt())) {
            throw new SecurityException("RUNNER_CERTIFICATE_EXPIRED");
        }
        String identity = job.jobId() + ":" + job.attempt() + ":" + runner.runnerId() + ":" + job.inputManifestHash();
        return new RunnerJobLease("lease-" + digest(identity).substring(0, 24), job.jobId(), runner.runnerId(),
                job.organizationId(), job.attempt(), now, now.plus(duration), digest("token:" + identity + ":" + now));
    }

    public void acceptCompletion(RunnerJobLease lease, int currentAttempt, String runnerId, Instant now) {
        if (!lease.runnerId().equals(runnerId)) throw new SecurityException("RUNNER_IDENTITY_MISMATCH");
        if (lease.attempt() != currentAttempt) throw new IllegalStateException("STALE_JOB_ATTEMPT");
        if (!now.isBefore(lease.expiresAt())) throw new IllegalStateException("JOB_LEASE_EXPIRED");
    }

    public Set<String> allowedUploadArtifacts(SourceUploadPolicy policy) {
        return switch (policy) {
            case NO_SOURCE_UPLOAD -> Set.of("FINDING", "HASH", "REDACTED_EVIDENCE", "STATUS");
            case PATCH_ONLY -> Set.of("PATCH", "FINDING", "HASH", "REDACTED_EVIDENCE", "STATUS");
            case METADATA_ONLY -> Set.of("FINDING", "HASH", "METRIC", "REDACTED_EVIDENCE", "STATUS");
            case SELECTED_SNIPPETS -> Set.of("APPROVED_SNIPPET", "PATCH", "FINDING", "HASH", "REDACTED_EVIDENCE", "STATUS");
            case FULL_EVIDENCE -> Set.of("APPROVED_SOURCE", "APPROVED_SNIPPET", "PATCH", "FINDING", "HASH", "METRIC", "REDACTED_EVIDENCE", "STATUS");
        };
    }

    public void validateUpload(RunnerNode runner, String artifactType) {
        if (!allowedUploadArtifacts(runner.uploadPolicy()).contains(artifactType)) {
            throw new SecurityException("SOURCE_UPLOAD_POLICY_VIOLATION");
        }
    }

    public RunnerNode quarantine(RunnerNode runner, String reasonCode) {
        EnterpriseModels.require(reasonCode, "reasonCode");
        return new RunnerNode(runner.runnerId(), runner.organizationId(), runner.poolId(), RunnerStatus.QUARANTINED,
                runner.capabilities(), runner.capabilityHash(), runner.certificateThumbprint(),
                runner.certificateExpiresAt(), runner.uploadPolicy());
    }

    public SecretLease issueSecretLease(SecretReference reference, WorkloadIdentity workload,
                                        SecretPurpose requestedPurpose, boolean production,
                                        Instant now, Duration duration) {
        requireShortLease(duration);
        if (!reference.organizationId().equals(workload.organizationId())) throw new SecurityException("CROSS_TENANT_SECRET_DENIED");
        if (reference.purpose() != requestedPurpose) throw new SecurityException("SECRET_PURPOSE_MISMATCH");
        if (production && reference.developmentProvider()) throw new SecurityException("DEVELOPMENT_SECRET_PROVIDER_FORBIDDEN");
        EnterpriseModels.require(workload.runnerId(), "runnerId"); EnterpriseModels.require(workload.jobId(), "jobId");
        String leaseSeed = reference.referenceId() + ":" + workload.runnerId() + ":" + workload.jobId() + ":" + requestedPurpose + ":" + now;
        return new SecretLease("secret-lease-" + digest(leaseSeed).substring(0, 20), reference.referenceId(), workload,
                requestedPurpose, now, now.plus(duration), false, false);
    }

    public SecretLease revoke(SecretLease lease) {
        return new SecretLease(lease.leaseId(), lease.referenceId(), lease.workload(), lease.purpose(),
                lease.issuedAt(), lease.expiresAt(), lease.renewable(), true);
    }

    public ModelRoutingDecision routeModel(ModelPolicy policy, ModelRequest request,
                                           List<ModelEndpoint> endpoints, BigDecimal reservedBudget) {
        List<String> blocked = new ArrayList<>();
        if (!request.secretScanPassed()) blocked.add("SECRET_SCAN_FAILED");
        if (request.classification() == DataClassification.SECRET) blocked.add("SECRET_DATA_MODEL_PROHIBITED");
        if (!policy.allowedClassifications().contains(request.classification())) blocked.add("DATA_CLASSIFICATION_NOT_ALLOWED");
        if (request.snippetCharacters() > policy.maximumSnippetCharacters()) blocked.add("CONTEXT_SIZE_EXCEEDED");
        if (reservedBudget == null || reservedBudget.compareTo(request.maximumCost()) < 0) blocked.add("MODEL_BUDGET_NOT_RESERVED");
        if (!blocked.isEmpty()) return new ModelRoutingDecision(ModelDecisionStatus.BLOCKED, null, null, blocked,
                policy.policyVersion(), false);

        List<ModelEndpoint> candidates = endpoints.stream()
                .filter(endpoint -> endpoint.organizationId().equals(request.organizationId()))
                .filter(ModelEndpoint::approved).filter(ModelEndpoint::healthy)
                .filter(endpoint -> policy.allowedProviders().contains(endpoint.type()))
                .filter(endpoint -> policy.allowedRegions().contains(endpoint.region()))
                .filter(endpoint -> endpoint.profiles().contains(request.modelProfile()))
                .filter(endpoint -> mayUseEndpoint(policy, request.classification(), endpoint.type()))
                .sorted(Comparator.comparing(ModelEndpoint::providerId).thenComparing(ModelEndpoint::modelVersion))
                .toList();
        if (candidates.isEmpty()) {
            return new ModelRoutingDecision(ModelDecisionStatus.HUMAN_REQUIRED, null, null,
                    List.of("NO_POLICY_COMPLIANT_MODEL"), policy.policyVersion(), false);
        }
        ModelEndpoint selected = candidates.getFirst();
        return new ModelRoutingDecision(ModelDecisionStatus.ALLOW, selected.providerId(), selected.modelVersion(),
                List.of("HARD_FILTERS_PASSED"), policy.policyVersion(), policy.retainPrompt() || policy.retainResponse());
    }

    public ModelRoutingDecision failover(ModelPolicy policy, ModelRequest request,
                                         ModelRoutingDecision previous, List<ModelEndpoint> alternatives,
                                         BigDecimal reservedBudget) {
        ModelRoutingDecision candidate = routeModel(policy, request, alternatives, reservedBudget);
        if (candidate.status() != ModelDecisionStatus.ALLOW) return candidate;
        if (previous.providerId() != null && previous.providerId().equals(candidate.providerId())) {
            return new ModelRoutingDecision(ModelDecisionStatus.HUMAN_REQUIRED, null, null,
                    List.of("NO_DISTINCT_FAILOVER_PROVIDER"), policy.policyVersion(), false);
        }
        return candidate;
    }

    private static boolean mayUseEndpoint(ModelPolicy policy, DataClassification classification, ModelProviderType type) {
        boolean privateProvider = Set.of(ModelProviderType.CUSTOMER_PRIVATE_ENDPOINT, ModelProviderType.ON_PREMISES_MODEL,
                ModelProviderType.OPENHANDS_LOCAL, ModelProviderType.OFFLINE_MODEL).contains(type);
        if (classification == DataClassification.RESTRICTED_CODE && !privateProvider) return false;
        return policy.sourceCodeMayLeavePrivateNetwork() || privateProvider
                || classification == DataClassification.PUBLIC_CODE || classification == DataClassification.OPEN_SOURCE;
    }

    private static void requireShortLease(Duration duration) {
        if (duration == null || duration.isZero() || duration.isNegative() || duration.compareTo(Duration.ofMinutes(15)) > 0) {
            throw new IllegalArgumentException("lease duration must be positive and no longer than 15 minutes");
        }
    }

    private static String digest(String value) {
        try {
            byte[] bytes = java.security.MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return java.util.HexFormat.of().formatHex(bytes);
        } catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
}
