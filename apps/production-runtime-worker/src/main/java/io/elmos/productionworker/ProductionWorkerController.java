package io.elmos.productionworker;

import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/internal/v1/production-runtime")
class ProductionWorkerController {
    private final ProductionWorkerAttemptService attempts;
    private final OwnerOnlyProviderCredentialFile credential;

    ProductionWorkerController(
            ProductionWorkerAttemptService attempts,
            OwnerOnlyProviderCredentialFile credential
    ) {
        this.attempts = attempts;
        this.credential = credential;
    }

    @PostMapping("/dispatch")
    ResponseEntity<Map<String, Object>> dispatch(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestHeader("X-ELMOS-Tenant-Id") UUID tenantId,
            @RequestHeader("X-ELMOS-Worker-Id") UUID workerId,
            @RequestHeader("X-ELMOS-Attempt-Id") UUID attemptId,
            @RequestHeader("X-ELMOS-Fencing-Token") long fencingToken,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestBody DispatchEnvelope envelope
    ) {
        requireAuthorization(authorization);
        if (!tenantId.equals(envelope.tenantId())
                || !workerId.equals(envelope.workerId())
                || !attemptId.equals(envelope.attemptId())
                || fencingToken != envelope.fencingToken()
                || !idempotencyKey.equals(envelope.dispatchIdempotencyKey())) {
            throw new ProductionRuntimeException(
                    "WORKER_DISPATCH_HEADER_MISMATCH",
                    "dispatch headers do not match the signed envelope fields");
        }
        var accepted = attempts.accept(envelope);
        return ResponseEntity.accepted().body(Map.of(
                "status", accepted.existing() ? "ALREADY_ACCEPTED" : "ACKED",
                "attemptId", envelope.attemptId()));
    }

    @GetMapping("/attempts/{attemptId}")
    ResponseEntity<Map<String, Object>> attempt(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestHeader("X-ELMOS-Tenant-Id") UUID tenantId,
            @RequestHeader("X-ELMOS-Worker-Id") UUID workerId,
            @RequestHeader("X-ELMOS-Attempt-Id") UUID headerAttemptId,
            @RequestHeader("X-ELMOS-Fencing-Token") long fencingToken,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @PathVariable UUID attemptId
    ) {
        requireAuthorization(authorization);
        var view = attempts.find(attemptId);
        if (view == null) {
            return ResponseEntity.status(404).body(Map.of("status", "NOT_FOUND"));
        }
        if (!tenantId.equals(view.tenantId())
                || !attemptId.equals(headerAttemptId)
                || !workerId.equals(view.workerId())
                || fencingToken != view.fencingToken()
                || !idempotencyKey.equals(view.dispatchIdempotencyKey())) {
            throw new ProductionRuntimeException(
                    "WORKER_RECONCILIATION_HEADER_MISMATCH",
                    "reconciliation headers do not match the durable attempt envelope");
        }
        return ResponseEntity.ok(Map.of(
                "status", view.status().name(),
                "attemptId", view.attemptId(),
                "updatedAt", view.updatedAt().toString(),
                "errorCode", view.errorCode() == null ? "" : view.errorCode()));
    }

    @PostMapping("/attempts/{attemptId}/checkpoints")
    ResponseEntity<Map<String, Object>> checkpoint(
            @RequestHeader(name = "Authorization", required = false) String authorization,
            @RequestHeader("X-ELMOS-Tenant-Id") UUID tenantId,
            @RequestHeader("X-ELMOS-Worker-Id") UUID workerId,
            @RequestHeader("X-ELMOS-Attempt-Id") UUID headerAttemptId,
            @RequestHeader("X-ELMOS-Fencing-Token") long fencingToken,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @PathVariable UUID attemptId,
            @RequestBody ProductionWorkerAttemptService.CheckpointInput checkpoint
    ) {
        requireAuthorization(authorization);
        var view = attempts.find(attemptId);
        if (view == null || !attemptId.equals(headerAttemptId)
                || !tenantId.equals(view.tenantId())
                || !workerId.equals(view.workerId())
                || fencingToken != view.fencingToken()
                || !idempotencyKey.equals(view.dispatchIdempotencyKey())) {
            throw new ProductionRuntimeException(
                    "WORKER_ATTEMPT_NOT_FOUND", "checkpoint references an unknown attempt");
        }
        // The service builds the authoritative checkpoint from the dispatch
        // envelope; untrusted engine input cannot override worker or fence.
        boolean committed = attempts.checkpoint(
                attemptId, workerId, fencingToken, idempotencyKey, checkpoint);
        if (!committed) {
            return ResponseEntity.status(503).body(Map.of(
                    "status", "UNKNOWN", "attemptId", attemptId,
                    "sequenceNo", checkpoint.sequenceNo()));
        }
        return ResponseEntity.ok(Map.of(
                "status", "COMMITTED", "attemptId", attemptId,
                "sequenceNo", checkpoint.sequenceNo(),
                "workerId", workerId,
                "fencingToken", fencingToken));
    }

    @ExceptionHandler(ProductionRuntimeException.class)
    ResponseEntity<Map<String, String>> conflict(ProductionRuntimeException ex) {
        int status = ex.code().startsWith("WORKER_AUTH_") ? 401
                : ex.code().contains("CAPACITY") ? 503 : 409;
        return ResponseEntity.status(status).body(Map.of("status", "REJECTED", "code", ex.code()));
    }

    private void requireAuthorization(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new ProductionRuntimeException(
                    "WORKER_AUTH_REQUIRED", "worker authorization is required");
        }
        if (!MessageDigest.isEqual(
                credential.read().getBytes(StandardCharsets.UTF_8),
                authorization.substring("Bearer ".length()).getBytes(StandardCharsets.UTF_8))) {
            throw new ProductionRuntimeException(
                    "WORKER_AUTH_INVALID", "worker authorization is invalid");
        }
    }
}
