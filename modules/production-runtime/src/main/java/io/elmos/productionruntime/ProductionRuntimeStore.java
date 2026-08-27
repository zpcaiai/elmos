package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchIntent;
import io.elmos.productionruntime.ProductionRuntimeModels.JobRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ProjectRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ProgressSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.TenantAccount;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkItemRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.OutboxMessage;
import io.elmos.productionruntime.ProductionRuntimeModels.ReadyWorkItem;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.Optional;

/** Durable runtime-owned operations. Implementations must use PostgreSQL as the source of truth. */
public interface ProductionRuntimeStore {
    TenantAccount provisionTenant(UUID tenantId, UUID accountId, String tenantName, String currency);
    UUID createProject(ProjectRequest request);
    UUID createJob(JobRequest request);
    UUID createWorkItem(WorkItemRequest request);
    void addDependency(UUID tenantId, UUID workItemId, UUID dependsOnWorkItemId);
    void registerWorker(WorkerRegistration registration);
    DispatchIntent prepareReservation(UUID tenantId, UUID projectId, UUID jobId, UUID workItemId, UUID walletId, UUID workerId, java.math.BigDecimal estimatedCredits, java.time.Instant reservationExpiresAt, java.util.Map<String, Object> payload, String reservationIdempotencyKey, String dispatchIdempotencyKey);
    void markWaitingForCredit(UUID tenantId, UUID workItemId, String reason);
    DispatchIntent attachReservation(UUID tenantId, UUID dispatchIntentId, UUID reservationId);
    DispatchEnvelope createAttempt(UUID tenantId, UUID dispatchIntentId, UUID workerId, Duration leaseDuration, Map<String, Object> payload);
    void acknowledge(UUID tenantId, UUID attemptId, UUID workerId, long fencingToken);
    void heartbeat(UUID tenantId, UUID attemptId, UUID workerId, long fencingToken, Duration leaseDuration);
    void checkpoint(Checkpoint checkpoint);
    void complete(Completion completion);
    void applyFinalUsage(UUID tenantId, UUID workItemId, FinalUsage usage);
    List<ProductionRuntimeModels.SettlementRequest> pendingSettlementRequests(UUID tenantId, int limit);
    void markSettlementSettled(UUID tenantId, UUID workItemId);
    Optional<UUID> activeReservationForWorkItem(UUID tenantId, UUID workItemId);
    int resumeCreditWaiting(UUID tenantId, int limit);
    int expireLeases(Duration gracePeriod);
    int expireLeases(UUID tenantId, Duration gracePeriod);
    int abortDispatch(UUID tenantId, UUID dispatchIntentId, String reason);
    List<DispatchIntent> recoveryCandidates(int limit);
    List<ReadyWorkItem> selectFairReady(int limit);
    ProgressSnapshot rebuildProgress(UUID tenantId, UUID jobId);
    List<OutboxMessage> claimOutbox(int limit, Duration claimDuration);
    void markOutboxPublished(UUID claimToken, long eventId);
    void markOutboxFailed(UUID claimToken, long eventId, String error);
    List<String> invariantViolations(UUID tenantId);
}
