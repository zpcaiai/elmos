package io.elmos.product.scmworkspace;

import java.util.ArrayList;
import java.util.List;

import static io.elmos.product.scmworkspace.ScmWorkspaceModels.*;

/** Evaluates readiness only. Real provider calls and PR/MR mutations remain outside this service. */
public final class ScmWorkspaceAdmissionService {
    public AdmissionResult evaluate(AdmissionRequest request) {
        required(request, "request");
        List<String> blockers = new ArrayList<>();
        if (request.capabilities().isEmpty()) blockers.add("CAPABILITY_DISCOVERY_NOT_RUN");
        request.capabilities().forEach(claim -> {
            String prefix = "CAPABILITY_" + claim.capability().toUpperCase().replace('-', '_') + ":";
            if (!claim.discovered()) blockers.add(prefix + "UNKNOWN");
            if (!claim.independentlyVerified()) blockers.add(prefix + "UNVERIFIED");
            if (!claim.supported()) blockers.add(prefix + "UNSUPPORTED");
        });
        require(request.installationAuthorized(), "INSTALLATION_AUTHORIZATION_REQUIRED", blockers);
        require(request.webhookHmacVerified(), "WEBHOOK_HMAC_REQUIRED", blockers);
        require(request.webhookReconciled(), "WEBHOOK_POLL_RECONCILIATION_REQUIRED", blockers);
        require(request.shortLivedCredentialLease(), "SHORT_LIVED_CREDENTIAL_LEASE_REQUIRED", blockers);
        if (request.credentialPersisted()) blockers.add("CREDENTIAL_PERSISTENCE_FORBIDDEN");
        require(request.customCaAndProxyVerified(), "NETWORK_CA_PROXY_VERIFICATION_REQUIRED", blockers);
        require(request.rateLimitBudgeted(), "RATE_LIMIT_BUDGET_REQUIRED", blockers);
        require(request.exactCommitResolved(), "EXACT_COMMIT_REQUIRED", blockers);
        require(request.monorepoGraphComplete(), "MONOREPO_GRAPH_INCOMPLETE", blockers);
        require(request.multiRepositoryLockComplete(), "MULTI_REPOSITORY_LOCK_INCOMPLETE", blockers);
        require(request.submodulesSeparatelyAuthorized(), "SUBMODULE_AUTHORIZATION_REQUIRED", blockers);
        require(request.lfsObjectsVerified(), "LFS_OBJECT_VERIFICATION_REQUIRED", blockers);
        require(request.partialCloneComplete(), "PARTIAL_CLONE_NOT_HYDRATED", blockers);
        require(request.sparseCheckoutComplete(), "SPARSE_SCOPE_NOT_COMPLETE", blockers);
        require(request.cacheTenantIsolated(), "OBJECT_CACHE_TENANT_ISOLATION_REQUIRED", blockers);
        require(request.cleanupAndRecoveryVerified(), "CLEANUP_RECOVERY_NOT_VERIFIED", blockers);
        if (request.evidenceRefs().isEmpty()) blockers.add("IMMUTABLE_EVIDENCE_REQUIRED");
        List<String> finalBlockers = blockers.stream().distinct().sorted().toList();
        Decision decision = finalBlockers.isEmpty() ? Decision.READY_FOR_EXTERNAL_GATE : Decision.BLOCKED;
        return new AdmissionResult(decision, request.repository().stableId(), finalBlockers, List.of(
                "SPARSE_CHECKOUT_IS_NOT_A_SECURITY_BOUNDARY",
                "PARTIAL_CLONE_IS_INCOMPLETE_UNTIL_HYDRATED",
                "SUBMODULES_REQUIRE_SEPARATE_AUTHORIZATION",
                "TOKENS_SECRETS_AND_PRIVATE_KEYS_MUST_NOT_BE_PERSISTED",
                "PR_MR_CREATION_REQUIRES_RENEWED_AUTHORIZATION_AND_HUMAN_DELIVERY_GATE"), false, false, false);
    }

    private static void require(boolean value, String blocker, List<String> blockers) {
        if (!value) blockers.add(blocker);
    }
}
