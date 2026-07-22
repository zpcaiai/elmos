package io.elmos.product.scmworkspace;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/** Fail-closed Product Batch 35 contracts. Provider DTOs never enter this model. */
public final class ScmWorkspaceModels {
    private ScmWorkspaceModels() {}

    public enum Provider {
        GITHUB_CLOUD, GITHUB_ENTERPRISE_SERVER, GITLAB_CLOUD, GITLAB_SELF_MANAGED,
        AZURE_DEVOPS, BITBUCKET_CLOUD, BITBUCKET_DATA_CENTER, GITEE
    }

    public enum Decision { BLOCKED, READY_FOR_EXTERNAL_GATE }

    public record RepositoryIdentity(Provider provider, String providerInstanceId, String nativeRepositoryId) {
        public RepositoryIdentity {
            required(provider, "provider"); text(providerInstanceId, "providerInstanceId");
            text(nativeRepositoryId, "nativeRepositoryId");
        }
        public String stableId() { return provider + ":" + providerInstanceId + ":" + nativeRepositoryId; }
    }

    public record CapabilityClaim(String capability, String providerVersion, String apiVersion,
                                  boolean discovered, boolean independentlyVerified, boolean supported) {
        public CapabilityClaim {
            text(capability, "capability"); text(providerVersion, "providerVersion"); text(apiVersion, "apiVersion");
        }
    }

    public record AdmissionRequest(
            String organizationId, String workspaceId, RepositoryIdentity repository,
            String sourceCommit, String workspaceManifestDigest, Instant evaluatedAt,
            List<CapabilityClaim> capabilities, boolean installationAuthorized,
            boolean webhookHmacVerified, boolean webhookReconciled, boolean shortLivedCredentialLease,
            boolean credentialPersisted, boolean customCaAndProxyVerified, boolean rateLimitBudgeted,
            boolean exactCommitResolved, boolean monorepoGraphComplete, boolean multiRepositoryLockComplete,
            boolean submodulesSeparatelyAuthorized, boolean lfsObjectsVerified,
            boolean partialCloneComplete, boolean sparseCheckoutComplete,
            boolean cacheTenantIsolated, boolean cleanupAndRecoveryVerified, List<String> evidenceRefs) {
        public AdmissionRequest {
            text(organizationId, "organizationId"); text(workspaceId, "workspaceId");
            required(repository, "repository"); commit(sourceCommit); digest(workspaceManifestDigest, "workspaceManifestDigest");
            required(evaluatedAt, "evaluatedAt"); capabilities = copy(capabilities); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record AdmissionResult(Decision decision, String repositoryStableId, List<String> blockers,
                                  List<String> restrictions, boolean externalOperationExecuted,
                                  boolean pullRequestMerged, boolean certified) {
        public AdmissionResult {
            required(decision, "decision"); text(repositoryStableId, "repositoryStableId");
            blockers = copy(blockers); restrictions = nonempty(restrictions, "restrictions");
            if (externalOperationExecuted || pullRequestMerged || certified)
                throw new IllegalArgumentException("Product B35 admission cannot mutate SCM or certify delivery");
            if (decision == Decision.READY_FOR_EXTERNAL_GATE && !blockers.isEmpty())
                throw new IllegalArgumentException("external-gate readiness requires no blockers");
        }
    }

    static void text(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void digest(String value, String field) {
        text(value, field); if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be SHA-256");
    }
    static void commit(String value) {
        text(value, "sourceCommit"); if (!value.matches("[a-f0-9]{40}|[a-f0-9]{64}"))
            throw new IllegalArgumentException("sourceCommit must be an immutable object id");
    }
    static <T> T required(T value, String field) { return Objects.requireNonNull(value, field + " is required"); }
    static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    static <T> List<T> nonempty(List<T> value, String field) {
        if (value == null || value.isEmpty() || value.stream().anyMatch(Objects::isNull))
            throw new IllegalArgumentException(field + " must not be empty");
        return List.copyOf(value);
    }
}
