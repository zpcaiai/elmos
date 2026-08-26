package io.elmos.workflow;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Durable execution job contract shared by the control plane and the runner fleet.
 *
 * <p>Placement follows the existing module boundaries: the port lives in
 * {@code modules/workflow} next to the other workflow aggregates, and the only
 * implementation is {@code io.elmos.persistence.JdbcExecutionJobStore}. No new
 * Maven module is introduced, so the reactor and the ArchUnit boundary tests are
 * unchanged.</p>
 *
 * <p>Every method that a tenant can reach takes an explicit {@code organizationId}
 * and binds it to {@code app.organization_id} inside the same transaction, exactly
 * like {@code JdbcSelfServiceBillingStore}. Runner-facing methods are authorised by
 * the lease credential instead, because a runner is not a tenant.</p>
 */
public interface ExecutionJobPort {

    enum BusinessLine {
        GENERATION, TRANSLATION, SPRING_UPGRADE, REPOSITORY_WORKSPACE, MODERNIZATION_PROOF
    }

    enum Status { QUEUED, CLAIMED, RUNNING, SUCCEEDED, PARTIAL, FAILED, CANCELLED, LOST }

    enum ResultStatus { NOT_RUN, PASSED, PARTIAL, FAILED, BLOCKED }

    /** Stable, machine-readable failures. Raw provider text never crosses this boundary. */
    final class ExecutionStateException extends RuntimeException {
        private final String code;

        public ExecutionStateException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    record EnqueueCommand(
            String jobId,
            String organizationId,
            String actorId,
            BusinessLine businessLine,
            String jobKind,
            String idempotencyKey,
            String requestDigest,
            Map<String, Object> requestPayload,
            String requiredCapability,
            String runnerImage,
            short priority,
            int budgetWallSeconds,
            short maxAttempts
    ) {}

    record JobView(
            String jobId,
            String organizationId,
            String actorId,
            BusinessLine businessLine,
            String jobKind,
            Status status,
            String stage,
            short progress,
            ResultStatus resultStatus,
            String failureCode,
            short attempt,
            short maxAttempts,
            Instant createdAt,
            Instant startedAt,
            Instant finishedAt,
            boolean cancelRequested,
            long stateVersion
    ) {}

    /**
     * Minimal authoritative result for reconciling an enqueue whose acknowledgement was lost.
     * The request digest is kept separate from {@link JobView} so existing management callers do
     * not accidentally expose the canonical dispatch subject in list responses.
     */
    record IdempotencyLookup(
            String jobId,
            String requestDigest,
            Status status
    ) {
        public IdempotencyLookup {
            if (jobId == null || jobId.isBlank()
                    || requestDigest == null || !requestDigest.matches("[0-9a-f]{64}")
                    || status == null) {
                throw new IllegalArgumentException("invalid execution idempotency lookup");
            }
        }
    }

    record LeaseGrant(
            String jobId,
            String organizationId,
            String leaseId,
            /** Returned exactly once. Only its SHA-256 is persisted. */
            String leaseToken,
            Instant leaseExpiresAt,
            BusinessLine businessLine,
            String jobKind,
            String runnerImage,
            int budgetWallSeconds,
            int budgetCpuMillis,
            int budgetMemoryMib,
            short attempt,
            Map<String, Object> checkpointCursor,
            Map<String, Object> requestPayload
    ) {}

    record HeartbeatCommand(
            String leaseId,
            String runnerNodeId,
            String leaseToken,
            String stage,
            Short progress,
            Map<String, Object> checkpoint,
            int leaseSeconds
    ) {}

    record HeartbeatResult(boolean cancelRequested, Instant leaseExpiresAt) {}

    record CompletionCommand(
            String leaseId,
            String runnerNodeId,
            String leaseToken,
            Status status,
            ResultStatus resultStatus,
            String failureCode
    ) {}

    // ---- tenant facing -----------------------------------------------------

    /**
     * Idempotent by {@code (organizationId, idempotencyKey)}. A replay with the same
     * request digest returns the original job id; a replay with a different digest
     * raises {@code ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT} rather than overwriting.
     */
    String enqueue(EnqueueCommand command);

    Optional<JobView> find(String organizationId, String jobId);

    /**
     * Authoritative tenant-scoped lookup used after an uncertain enqueue acknowledgement.
     * Implementations must return the persisted request digest so a reconciler can distinguish
     * the original side effect from a material-drifted retry.
     */
    default Optional<IdempotencyLookup> findByIdempotencyKey(
            String organizationId,
            String idempotencyKey
    ) {
        throw new ExecutionStateException("ELMOS_EXECUTION_IDEMPOTENCY_LOOKUP_UNAVAILABLE");
    }

    List<JobView> list(String organizationId, BusinessLine businessLine, int limit, int offset);

    /**
     * Records the intent to cancel. The runner observes it on its next heartbeat and
     * terminates its own container; the control plane never kills a workload directly.
     */
    Status requestCancel(String organizationId, String jobId, String actorId);

    // ---- runner facing -----------------------------------------------------

    /**
     * Leases up to {@code limit} jobs to an attested, heartbeating runner.
     * Per-tenant concurrency comes from the CNY plan catalog, so a plan change moves
     * the limit without a second source of truth.
     */
    List<LeaseGrant> claim(String runnerNodeId, List<String> capabilities, int limit, int leaseSeconds);

    HeartbeatResult heartbeat(HeartbeatCommand command);

    boolean complete(CompletionCommand command);

    /** Requeues or fails jobs whose runner stopped heartbeating. Idempotent. */
    int reapExpiredLeases();
}
