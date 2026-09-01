package io.elmos.productionruntime;

import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchIntent;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Cross-context coordinator for the durable dispatch saga.
 *
 * <p>It intentionally does not pretend to have a distributed transaction:
 * PostgreSQL commits the intent, Billing owns the reservation, and recovery
 * makes each externally visible step converge through stable keys.</p>
 */
public final class ProductionRuntimeCoordinator {
    private final ProductionRuntimeStore runtime;
    private final ProductionBillingPort billing;

    public ProductionRuntimeCoordinator(ProductionRuntimeStore runtime, ProductionBillingPort billing) {
        this.runtime = Objects.requireNonNull(runtime, "runtime");
        this.billing = Objects.requireNonNull(billing, "billing");
    }

    public DispatchOutcome dispatch(DispatchRequest request, WorkerGateway gateway) {
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(gateway, "gateway");
        DispatchIntent intent = runtime.prepareReservation(request.tenantId(), request.projectId(), request.jobId(), request.workItemId(), request.walletId(), request.workerId(), request.estimatedCredits(), request.reservationExpiresAt(), request.payload(), request.reservationIdempotencyKey(), request.dispatchIdempotencyKey());
        if (intent.state() == ProductionRuntimeModels.DispatchState.COMPLETED) return new DispatchOutcome(intent, null, DispatchStatus.ALREADY_COMPLETED);
        ReservationResult reservation;
        if (intent.reservationId() != null) {
            reservation = new ReservationResult(intent.reservationId(), ProductionRuntimeModels.ReservationStatus.ACTIVE, request.estimatedCredits(), BigDecimal.ZERO);
        } else {
            try {
                reservation = billing.reserve(new ProductionRuntimeModels.ReserveRequest(request.tenantId(), request.walletId(), request.projectId(), request.jobId(), request.workItemId(), request.reservationIdempotencyKey(), request.estimatedCredits(), request.reservationExpiresAt()));
            } catch (ProductionRuntimeException ex) {
                if (!"CREDIT_EXHAUSTED".equals(ex.code())) throw ex;
                runtime.markWaitingForCredit(request.tenantId(), request.workItemId(), ex.code());
                return new DispatchOutcome(intent, null, DispatchStatus.WAITING_FOR_CREDIT);
            }
            runtime.attachReservation(request.tenantId(), intent.id(), reservation.reservationId());
        }
        DispatchEnvelope envelope = runtime.createAttempt(request.tenantId(), intent.id(), request.workerId(), request.leaseDuration(), request.payload());
        WorkerGatewayResult result = gateway.dispatch(envelope);
        if (result == WorkerGatewayResult.ACKED) {
            runtime.acknowledge(request.tenantId(), envelope.attemptId(), envelope.workerId(), envelope.fencingToken());
            return new DispatchOutcome(runtime.prepareReservation(request.tenantId(), request.projectId(), request.jobId(), request.workItemId(), request.walletId(), request.workerId(), request.estimatedCredits(), request.reservationExpiresAt(), request.payload(), request.reservationIdempotencyKey(), request.dispatchIdempotencyKey()), envelope, DispatchStatus.ACKED);
        }
        if (result == WorkerGatewayResult.REJECTED) {
            runtime.abortDispatch(request.tenantId(), intent.id(), "WORKER_REJECTED");
            billing.release(request.tenantId(), reservation.reservationId(), "WORKER_REJECTED");
            return new DispatchOutcome(intent, envelope, DispatchStatus.RELEASED_AFTER_REJECTION);
        }
        // UNKNOWN is deliberately non-success. The intent, lease, and reserve
        // stay durable so reconciliation can query the worker before retrying.
        return new DispatchOutcome(intent, envelope, DispatchStatus.PROVIDER_OR_WORKER_OUTCOME_UNKNOWN);
    }

    public void complete(Completion completion, FinalUsage usage, String failureReason) {
        runtime.complete(completion);
        settleOrRelease(completion, usage, failureReason);
    }

    /**
     * Production worker success boundary.  The durable runtime validates and
     * records the output receipt before the work item can become SUCCEEDED.
     */
    public void completeVerified(
            Completion completion,
            OutputVerificationReceipt receipt,
            FinalUsage usage,
            String failureReason
    ) {
        runtime.completeVerified(completion, receipt);
        settleOrRelease(completion, usage, failureReason);
    }

    private void settleOrRelease(
            Completion completion,
            FinalUsage usage,
            String failureReason
    ) {
        if (completion.status() == ProductionRuntimeModels.AttemptStatus.SUCCEEDED && usage != null) {
            runtime.applyFinalUsage(completion.tenantId(), completion.workItemId(), usage);
            billing.settle(usage);
            runtime.markSettlementSettled(completion.tenantId(), completion.workItemId());
        } else {
            UUID reservationId = runtime.activeReservationForWorkItem(completion.tenantId(), completion.workItemId()).orElse(null);
            if (reservationId != null) {
                String reason = completion.status() == ProductionRuntimeModels.AttemptStatus.SUCCEEDED
                        ? "NO_BILLABLE_PROVIDER_USAGE"
                        : failureReason == null ? "WORK_ITEM_FAILED" : failureReason;
                billing.release(completion.tenantId(), reservationId, reason);
            }
        }
    }

    public interface WorkerGateway {
        WorkerGatewayResult dispatch(DispatchEnvelope envelope);
        default WorkerGatewayResult reconcile(DispatchEnvelope envelope) { return WorkerGatewayResult.UNKNOWN; }
    }

    public enum WorkerGatewayResult { ACKED, REJECTED, UNKNOWN }
    public enum DispatchStatus { ACKED, ALREADY_COMPLETED, WAITING_FOR_CREDIT, RELEASED_AFTER_REJECTION, PROVIDER_OR_WORKER_OUTCOME_UNKNOWN }

    public record DispatchRequest(
            UUID tenantId,
            UUID projectId,
            UUID jobId,
            UUID workItemId,
            UUID walletId,
            UUID workerId,
            BigDecimal estimatedCredits,
            java.time.Instant reservationExpiresAt,
            Duration leaseDuration,
            String reservationIdempotencyKey,
            String dispatchIdempotencyKey,
            Map<String, Object> payload
    ) {
        public DispatchRequest {
            ProductionRuntimeModels.require(tenantId, "tenantId"); ProductionRuntimeModels.require(projectId, "projectId"); ProductionRuntimeModels.require(jobId, "jobId"); ProductionRuntimeModels.require(workItemId, "workItemId"); ProductionRuntimeModels.require(walletId, "walletId"); ProductionRuntimeModels.require(workerId, "workerId");
            if (estimatedCredits == null || estimatedCredits.signum() <= 0) throw new IllegalArgumentException("estimatedCredits must be positive");
            ProductionRuntimeModels.requireText(reservationIdempotencyKey, "reservationIdempotencyKey", 240); ProductionRuntimeModels.requireText(dispatchIdempotencyKey, "dispatchIdempotencyKey", 240);
            if (reservationExpiresAt == null || !reservationExpiresAt.isAfter(java.time.Instant.now())) throw new IllegalArgumentException("reservationExpiresAt must be in the future");
            if (leaseDuration == null) throw new IllegalArgumentException("leaseDuration is required");
            payload = payload == null ? Map.of() : Map.copyOf(payload);
        }
    }

    public record DispatchOutcome(DispatchIntent intent, DispatchEnvelope envelope, DispatchStatus status) {}
}
