package io.elmos.controlplane;

import io.elmos.productionruntime.ProductionRuntimeCoordinator;
import io.elmos.productionruntime.ProductionRuntimeModels.Checkpoint;
import io.elmos.productionruntime.ProductionRuntimeModels.Completion;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.OutputVerificationReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeStore;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

/** Scheduler-owned worker registration, lease, checkpoint and completion boundary. */
@RestController
@RequestMapping("/internal/v1/production-runtime")
@ConditionalOnProperty(prefix = "elmos.production-runtime", name = "enabled", havingValue = "true")
@ConditionalOnExpression("'${component:scheduler}' == 'scheduler'")
class ProductionRuntimeInternalController {
    private final ProductionRuntimeInternalAuthenticator authenticator;
    private final ProductionRuntimeStore runtime;
    private final ProductionRuntimeCoordinator coordinator;

    ProductionRuntimeInternalController(
            ProductionRuntimeInternalAuthenticator authenticator,
            ProductionRuntimeStore runtime,
            ProductionRuntimeCoordinator coordinator
    ) {
        this.authenticator = authenticator;
        this.runtime = runtime;
        this.coordinator = coordinator;
    }

    @PostMapping("/workers/register")
    Map<String, Object> register(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestHeader("X-ELMOS-Worker-Id") UUID workerId,
            @RequestBody WorkerRegistration registration
    ) {
        authenticator.require(authorization);
        if (!workerId.equals(registration.workerId())) {
            throw new IllegalArgumentException("worker registration header and body mismatch");
        }
        runtime.registerWorker(registration);
        return Map.of("status", "ACTIVE", "workerId", registration.workerId());
    }

    @PostMapping("/attempts/{attemptId}/heartbeat")
    Map<String, Object> heartbeat(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @PathVariable UUID attemptId,
            @RequestBody HeartbeatRequest request
    ) {
        authenticator.require(authorization);
        if (!attemptId.equals(request.attemptId())) {
            throw new IllegalArgumentException("attempt path and body mismatch");
        }
        runtime.heartbeat(request.tenantId(), request.attemptId(), request.workerId(),
                request.fencingToken(), request.leaseDuration());
        return Map.of("status", "LEASE_EXTENDED", "attemptId", attemptId);
    }

    @PostMapping("/checkpoints")
    Map<String, Object> checkpoint(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody CheckpointCommitRequest request
    ) {
        authenticator.require(authorization);
        runtime.checkpoint(
                request.checkpoint(), request.workerId(), request.fencingToken());
        return Map.of("status", "COMMITTED",
                "attemptId", request.checkpoint().attemptId(),
                "sequenceNo", request.checkpoint().sequenceNo());
    }

    @PostMapping("/completions")
    Map<String, Object> complete(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestBody CompletionRequest request
    ) {
        authenticator.require(authorization);
        if (request.completion().status()
                == io.elmos.productionruntime.ProductionRuntimeModels.AttemptStatus.SUCCEEDED) {
            if (request.outputVerification() == null) {
                throw new ProductionRuntimeException(
                        "OUTPUT_VERIFICATION_REQUIRED",
                        "successful production completion requires output verification");
            }
            coordinator.completeVerified(
                    request.completion(), request.outputVerification(),
                    request.usage(), request.failureReason());
        } else {
            if (request.outputVerification() != null) {
                throw new ProductionRuntimeException(
                        "OUTPUT_VERIFICATION_ON_FAILURE",
                        "failed completion cannot attach passing output verification");
            }
            coordinator.complete(
                    request.completion(), request.usage(), request.failureReason());
        }
        return Map.of("status", "COMMITTED", "attemptId", request.completion().attemptId());
    }

    @ExceptionHandler(AccessDeniedException.class)
    ResponseEntity<Map<String, String>> accessDenied(AccessDeniedException ex) {
        return ResponseEntity.status(401).body(Map.of("code", "UNAUTHORIZED"));
    }

    record HeartbeatRequest(
            UUID tenantId,
            UUID attemptId,
            UUID workerId,
            long fencingToken,
            Duration leaseDuration
    ) {}

    record CompletionRequest(
            Completion completion,
            OutputVerificationReceipt outputVerification,
            FinalUsage usage,
            String failureReason
    ) {}

    record CheckpointCommitRequest(
            Checkpoint checkpoint,
            UUID workerId,
            long fencingToken
    ) {}

}
