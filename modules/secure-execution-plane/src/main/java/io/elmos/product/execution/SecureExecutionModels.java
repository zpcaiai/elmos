package io.elmos.product.execution;

import java.time.Instant;
import java.util.List;
import java.util.Objects;

/** Product Batch 36 runner, sandbox and site-operations contracts. */
public final class SecureExecutionModels {
    private SecureExecutionModels() {}
    public enum IsolationProvider { ROOTLESS_OCI, GVISOR, KATA_CONTAINERS, FIRECRACKER }
    public enum Decision { BLOCKED, READY_FOR_EXTERNAL_GATE }

    public record AdmissionRequest(
            String organizationId, String taskId, String runnerId, long assignmentEpoch,
            String sourceSnapshotDigest, String policyBundleDigest, IsolationProvider isolationProvider,
            Instant evaluatedAt, boolean capabilityAttested, boolean capabilityIndependentlyVerified,
            boolean fixedRunnerVersion, boolean fixedImageDigest, boolean capacityReserved,
            boolean hardConstraintsSatisfied, boolean assignmentLeaseActive, boolean schedulerSeparatedFromProvider,
            boolean sourceReadOnly, boolean rootless, boolean defaultDenyNetwork, boolean metadataEndpointsBlocked,
            boolean processBoundSecrets, boolean secretPersisted, boolean seccompCapabilitiesAndLsmEnforced,
            boolean resourceLimitsEnforced, boolean repositoryCannotWeakenSandbox, boolean typedCommandsOnly,
            boolean checkpointCompatible, boolean durableQueueAndOutbox, boolean redactedBeforePersistence,
            boolean offlinePermitCreatesNewRights, boolean siteEpochValid, boolean checksummedArtifactTransfer,
            boolean idempotentCleanup, boolean unknownResultsReconciled, List<String> evidenceRefs) {
        public AdmissionRequest {
            text(organizationId, "organizationId"); text(taskId, "taskId"); text(runnerId, "runnerId");
            if (assignmentEpoch <= 0) throw new IllegalArgumentException("assignmentEpoch must be positive");
            digest(sourceSnapshotDigest, "sourceSnapshotDigest"); digest(policyBundleDigest, "policyBundleDigest");
            required(isolationProvider, "isolationProvider"); required(evaluatedAt, "evaluatedAt");
            evidenceRefs = value(evidenceRefs);
        }
    }

    public record AdmissionResult(Decision decision, List<String> blockers, List<String> restrictions,
                                  boolean externalOperationExecuted, boolean exactlyOnceClaimed, boolean certified) {
        public AdmissionResult {
            required(decision, "decision"); blockers = value(blockers); restrictions = nonempty(restrictions, "restrictions");
            if (externalOperationExecuted || exactlyOnceClaimed || certified)
                throw new IllegalArgumentException("Product B36 admission cannot execute, certify, or claim exactly-once");
            if (decision == Decision.READY_FOR_EXTERNAL_GATE && !blockers.isEmpty())
                throw new IllegalArgumentException("external-gate readiness requires no blockers");
        }
    }

    static void text(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required"); }
    static void digest(String value, String field) { text(value, field); if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be SHA-256"); }
    static <T> T required(T value, String field) { return Objects.requireNonNull(value, field + " is required"); }
    static <T> List<T> value(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <T> List<T> nonempty(List<T> values, String field) { if (values == null || values.isEmpty()) throw new IllegalArgumentException(field + " must not be empty"); return List.copyOf(values); }
}
