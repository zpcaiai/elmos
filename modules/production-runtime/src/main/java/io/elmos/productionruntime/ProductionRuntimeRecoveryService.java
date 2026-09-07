package io.elmos.productionruntime;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGateway;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGatewayResult;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchIntent;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchState;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;

import java.time.Instant;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Replays only durable dispatch inputs; unknown external outcomes remain non-success. */
public final class ProductionRuntimeRecoveryService {
    private final ProductionRuntimeStore runtime;
    private final ProductionBillingPort billing;
    private final ObjectMapper json;

    public ProductionRuntimeRecoveryService(ProductionRuntimeStore runtime, ProductionBillingPort billing, ObjectMapper json) {
        this.runtime = Objects.requireNonNull(runtime, "runtime");
        this.billing = Objects.requireNonNull(billing, "billing");
        this.json = Objects.requireNonNull(json, "json");
    }

    public RecoveryReport recover(int limit, WorkerGateway gateway) {
        Objects.requireNonNull(gateway, "gateway");
        int inspected = 0;
        int advanced = 0;
        int waitingForCredit = 0;
        int unknown = 0;
        List<DispatchIntent> candidates = runtime.recoveryCandidates(limit);
        for (DispatchIntent intent : candidates) {
            inspected++;
            try {
                DispatchIntent current = intent;
                if (current.state() == DispatchState.RESERVING) {
                    if (!current.reservationExpiresAt().isAfter(Instant.now())) {
                        runtime.abortDispatch(current.tenantId(), current.id(), "RESERVATION_EXPIRED_BEFORE_BILLING");
                        continue;
                    }
                    ReservationResult reservation = billing.reserve(new ProductionRuntimeModels.ReserveRequest(
                            current.tenantId(), current.walletId(), current.projectId(), current.jobId(), current.workItemId(),
                            current.reservationIdempotencyKey(), current.estimatedCredits(), current.reservationExpiresAt()));
                    current = runtime.attachReservation(current.tenantId(), current.id(), reservation.reservationId());
                    advanced++;
                }
                if (current.state() == DispatchState.RESERVED || current.state() == DispatchState.ATTEMPT_CREATED || current.state() == DispatchState.DISPATCHING) {
                    var payload = payload(current.payloadJson());
                    var envelope = runtime.createAttempt(current.tenantId(), current.id(), current.workerId(), Duration.ofSeconds(30), payload);
                    WorkerGatewayResult result = current.attemptId() != null && current.attemptId().equals(envelope.attemptId())
                            ? gateway.reconcile(envelope) : gateway.dispatch(envelope);
                    if (result == WorkerGatewayResult.ACKED) {
                        runtime.acknowledge(envelope.tenantId(), envelope.attemptId(), envelope.workerId(), envelope.fencingToken());
                        advanced++;
                    } else if (result == WorkerGatewayResult.REJECTED) {
                        runtime.abortDispatch(current.tenantId(), current.id(), "WORKER_REJECTED_DURING_RECOVERY");
                        if (current.reservationId() != null) billing.release(current.tenantId(), current.reservationId(), "WORKER_REJECTED_DURING_RECOVERY");
                        advanced++;
                    } else {
                        unknown++;
                    }
                }
            } catch (ProductionRuntimeException ex) {
                if ("CREDIT_EXHAUSTED".equals(ex.code())) {
                    runtime.markWaitingForCredit(intent.tenantId(), intent.workItemId(), ex.code());
                    waitingForCredit++;
                } else if ("WORKER_NOT_ACTIVE".equals(ex.code()) || "WORKER_NOT_FOUND".equals(ex.code())) {
                    unknown++;
                } else {
                    throw ex;
                }
            }
        }
        return new RecoveryReport(inspected, advanced, waitingForCredit, unknown);
    }

    private Map<String, Object> payload(String payloadJson) {
        if (payloadJson == null || payloadJson.isBlank()) return Map.of();
        try { return json.readValue(payloadJson, new TypeReference<>() {}); }
        catch (Exception ex) { throw new ProductionRuntimeException("DISPATCH_PAYLOAD_INVALID", "durable dispatch payload cannot be decoded", ex); }
    }

    public record RecoveryReport(int inspected, int advanced, int waitingForCredit, int unknown) {}
}
