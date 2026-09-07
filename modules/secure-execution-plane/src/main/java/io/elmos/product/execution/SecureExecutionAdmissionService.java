package io.elmos.product.execution;

import java.util.ArrayList;
import java.util.List;
import static io.elmos.product.execution.SecureExecutionModels.*;

/** Readiness evaluator; the scheduler, provider and enforcement receipts remain distinct external components. */
public final class SecureExecutionAdmissionService {
    public AdmissionResult evaluate(AdmissionRequest request) {
        required(request, "request"); List<String> blockers = new ArrayList<>();
        require(request.capabilityAttested(), "RUNNER_CAPABILITY_ATTESTATION_REQUIRED", blockers);
        require(request.capabilityIndependentlyVerified(), "RUNNER_SELF_CLAIM_NOT_TRUSTED", blockers);
        require(request.fixedRunnerVersion(), "RUNNER_VERSION_NOT_FIXED", blockers);
        require(request.fixedImageDigest(), "RUNNER_IMAGE_DIGEST_NOT_FIXED", blockers);
        require(request.capacityReserved(), "CAPACITY_RESERVATION_REQUIRED", blockers);
        require(request.hardConstraintsSatisfied(), "HARD_PLACEMENT_CONSTRAINT_FAILED", blockers);
        require(request.assignmentLeaseActive(), "ASSIGNMENT_LEASE_INACTIVE", blockers);
        require(request.schedulerSeparatedFromProvider(), "SCHEDULER_PROVIDER_SEPARATION_REQUIRED", blockers);
        require(request.sourceReadOnly(), "SOURCE_MUST_BE_READ_ONLY", blockers);
        require(request.rootless(), "ROOTLESS_EXECUTION_REQUIRED", blockers);
        require(request.defaultDenyNetwork(), "DEFAULT_DENY_NETWORK_REQUIRED", blockers);
        require(request.metadataEndpointsBlocked(), "METADATA_PRIVATE_ENDPOINT_BLOCK_REQUIRED", blockers);
        require(request.processBoundSecrets(), "PROCESS_BOUND_SECRET_REQUIRED", blockers);
        if (request.secretPersisted()) blockers.add("SECRET_PERSISTENCE_FORBIDDEN");
        require(request.seccompCapabilitiesAndLsmEnforced(), "KERNEL_SECURITY_PROFILE_REQUIRED", blockers);
        require(request.resourceLimitsEnforced(), "RESOURCE_LIMIT_REQUIRED", blockers);
        require(request.repositoryCannotWeakenSandbox(), "REPOSITORY_SANDBOX_DOWNGRADE_FORBIDDEN", blockers);
        require(request.typedCommandsOnly(), "ARBITRARY_SHELL_FORBIDDEN", blockers);
        require(request.checkpointCompatible(), "CHECKPOINT_COMPATIBILITY_REQUIRED", blockers);
        require(request.durableQueueAndOutbox(), "DURABLE_QUEUE_OUTBOX_REQUIRED", blockers);
        require(request.redactedBeforePersistence(), "LOG_REDACTION_BEFORE_PERSISTENCE_REQUIRED", blockers);
        if (request.offlinePermitCreatesNewRights()) blockers.add("OFFLINE_PERMIT_CANNOT_CREATE_RIGHTS");
        require(request.siteEpochValid(), "SITE_EPOCH_INVALID", blockers);
        require(request.checksummedArtifactTransfer(), "CHECKSUMMED_RESUMABLE_TRANSFER_REQUIRED", blockers);
        require(request.idempotentCleanup(), "IDEMPOTENT_CLEANUP_REQUIRED", blockers);
        require(request.unknownResultsReconciled(), "UNKNOWN_RESULT_RECONCILIATION_REQUIRED", blockers);
        if (request.evidenceRefs().isEmpty()) blockers.add("IMMUTABLE_EVIDENCE_REQUIRED");
        List<String> result = blockers.stream().distinct().sorted().toList();
        return new AdmissionResult(result.isEmpty() ? Decision.READY_FOR_EXTERNAL_GATE : Decision.BLOCKED,
                result, List.of("TASK_CANNOT_SELECT_A_WEAKER_SANDBOX", "NETWORK_EGRESS_IS_DEFAULT_DENY",
                "OFFLINE_OPERATION_CANNOT_CREATE_NEW_AUTHORITY", "RESULTS_USE_EPOCH_RECEIPTS_AND_RECONCILIATION_NOT_EXACTLY_ONCE",
                "REAL_RUNNER_AND_SANDBOX_EXECUTION_REMAINS_AN_EXTERNAL_GATE"), false, false, false);
    }
    private static void require(boolean value, String blocker, List<String> blockers) { if (!value) blockers.add(blocker); }
}
