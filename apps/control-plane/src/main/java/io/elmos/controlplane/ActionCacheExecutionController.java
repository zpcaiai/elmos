package io.elmos.controlplane;

import io.elmos.cas.ActionKey;
import io.elmos.cas.ActionKeyBuilder;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

/**
 * Tenant-facing ActionCache execution boundary.
 *
 * <p>The existing dispatcher deliberately owns cache lookup, current-trust checks, authorization,
 * payload sanitization, idempotency and durable enqueue. This controller is the missing HTTP seam:
 * it constructs the exact canonical ActionKey supplied by the tenant, binds the reader to the
 * authenticated database-backed principal, derives the runner profile from the key/business line,
 * and serializes only the dispatcher outcome. No request field can override tenant or actor
 * identity.</p>
 *
 * <p>The controller is conditional on the opt-in dispatcher. A deployment that has not supplied a
 * real current-trust provider, authorizer and payload policy therefore has no executable endpoint
 * instead of an unsafe compatibility path.</p>
 */
@RestController
@RequestMapping("/api/v1/action-cache/executions")
@ConditionalOnBean(ActionCacheExecutionJobDispatcher.class)
public class ActionCacheExecutionController {

    private static final String IMAGE_PATTERN =
            "^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$";

    private final ActionCacheExecutionJobDispatcher dispatcher;
    private final String dataResidency;
    private final CasAccessPolicy.SecurityTier clearance;

    public ActionCacheExecutionController(
            ActionCacheExecutionJobDispatcher dispatcher,
            @Value("${elmos.action-cache.data-residency:}") String dataResidency,
            @Value("${elmos.action-cache.security-tier:CONFIDENTIAL}") String securityTier
    ) {
        this.dispatcher = dispatcher;
        this.dataResidency = dataResidency == null ? "" : dataResidency.trim();
        try {
            this.clearance = CasAccessPolicy.SecurityTier.valueOf(
                    securityTier == null ? "CONFIDENTIAL"
                            : securityTier.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw new IllegalStateException(
                    "elmos.action-cache.security-tier is invalid", error);
        }
    }

    /** Exposed to the actuator status bean without exposing deployment policy to callers. */
    boolean deploymentPolicyConfigured() {
        return !dataResidency.isBlank();
    }

    /** Compact wire representation avoids accepting a digest without its byte-size binding. */
    public record ActionKeyRequest(
            String digest,
            String tenantId,
            Map<String, String> components
    ) {}

    public record DispatchRequest(
            ActionKeyRequest actionKey,
            String businessLine,
            String jobKind,
            String idempotencyKey,
            Map<String, Object> payload,
            Short priority,
            Integer budgetWallSeconds,
            Short maxAttempts,
            Boolean bypassCache,
            String mode,
            String expectedPriorRequestDigest
    ) {}

    @PostMapping
    public ResponseEntity<?> dispatch(
            @RequestBody DispatchRequest request,
            @RequestHeader(value = "X-ELMOS-Request-ID", required = false) String requestId
    ) {
        return dispatchInternal(request, requestId, true);
    }

    /** Compatibility entry point for direct callers; HTTP requests use the header-bound method. */
    public ResponseEntity<?> dispatch(DispatchRequest request) {
        return dispatchInternal(request, "", false);
    }

    private ResponseEntity<?> dispatchInternal(
            DispatchRequest request,
            String requestId,
            boolean requireRequestId
    ) {
        if (request == null || request.actionKey() == null) {
            throw invalid("ELMOS_ACTION_CACHE_REQUEST_INVALID");
        }
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new org.springframework.security.access.AccessDeniedException(
                        "CONTROL_PLANE_AUTH_REQUIRED"));
        ExecutionJobPort.BusinessLine line = parseBusinessLine(request.businessLine());
        principal.require(principal.organizationId(), principal.actorId(), permissionFor(line));

        ActionKey key = parseActionKey(request.actionKey());
        if (!principal.organizationId().equals(key.tenantId())
                || !principal.organizationId().equals(key.components().get("tenant_id"))) {
            throw new org.springframework.security.access.AccessDeniedException(
                    "CONTROL_PLANE_TENANT_MISMATCH");
        }
        if (dataResidency.isBlank()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of(
                    "status", "CONFIGURATION_REQUIRED",
                    "code", "ELMOS_ACTION_CACHE_DATA_RESIDENCY_NOT_CONFIGURED"));
        }
        if (!dataResidency.equals(key.components().get("data_residency"))) {
            throw invalid("ELMOS_ACTION_CACHE_DATA_RESIDENCY_MISMATCH");
        }

        String image = key.components().get("toolchain_image");
        if (image == null || !image.matches(IMAGE_PATTERN)) {
            throw invalid("ELMOS_ACTION_CACHE_RUNNER_IMAGE_INVALID");
        }
        String requiredCapability = capabilityFor(line);
        if (request.payload() == null) {
            request = new DispatchRequest(request.actionKey(), request.businessLine(),
                    request.jobKind(), request.idempotencyKey(), Map.of(), request.priority(),
                    request.budgetWallSeconds(), request.maxAttempts(), request.bypassCache(),
                    request.mode(), request.expectedPriorRequestDigest());
        }
        ActionCacheExecutionJobDispatcher.DispatchSpec spec;
        try {
            spec = new ActionCacheExecutionJobDispatcher.DispatchSpec(
                    principal.actorId(), line, require(request.jobKind(), 64,
                            "ELMOS_ACTION_CACHE_JOB_KIND_INVALID"),
                    require(request.idempotencyKey(), 160,
                            "ELMOS_ACTION_CACHE_IDEMPOTENCY_KEY_INVALID"),
                    request.payload(), requiredCapability, image,
                    request.priority() == null ? (short) 100 : request.priority(),
                    request.budgetWallSeconds() == null ? 3600 : request.budgetWallSeconds(),
                    request.maxAttempts() == null ? (short) 1 : request.maxAttempts(),
                    principal.accountId(),
                    requireRequestId
                            ? require(requestId, 160,
                                    "ELMOS_ACTION_CACHE_REQUEST_ID_INVALID")
                            : "",
                    workloadClassFor(line),
                    resourceUnitsFor(line));
        } catch (IllegalArgumentException error) {
            throw invalid("ELMOS_ACTION_CACHE_DISPATCH_SPEC_INVALID");
        }

        CasAccessPolicy.ReaderContext reader = new CasAccessPolicy.ReaderContext(
                principal.organizationId(), principal.permissions(), dataResidency,
                clearance, false);
        ActionCacheExecutionJobDispatcher.Mode mode = parseMode(request.mode());
        Optional<CasDigest> expected = parseExpectedDigest(request.expectedPriorRequestDigest());
        ActionCacheExecutionJobDispatcher.Request dispatcherRequest =
                new ActionCacheExecutionJobDispatcher.Request(
                        key, reader, spec,
                        Boolean.TRUE.equals(request.bypassCache()), mode, expected);
        return response(dispatcher.dispatch(dispatcherRequest));
    }

    private ActionKey parseActionKey(ActionKeyRequest input) {
        try {
            if (input.digest() == null || input.tenantId() == null || input.components() == null) {
                throw new IllegalArgumentException("missing action key field");
            }
            Map<String, String> components = new LinkedHashMap<>(input.components());
            ActionKey key = new ActionKey(
                    CasDigest.parseCompact(input.digest()), input.tenantId(), components);
            ActionKeyBuilder.verifyCanonical(key);
            return key;
        } catch (RuntimeException invalid) {
            throw invalid("ELMOS_ACTION_CACHE_ACTION_KEY_INVALID");
        }
    }

    private ResponseEntity<?> response(ActionCacheExecutionJobDispatcher.Outcome outcome) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", outcome.kind().name());
        body.put("reason", outcome.reason());
        outcome.jobId().ifPresent(value -> body.put("jobId", value));
        outcome.requestDigest().ifPresent(value -> body.put("requestDigest", value.compact()));
        outcome.cacheOutcome().ifPresent(value -> body.put("cacheOutcome", value.name()));
        outcome.result().ifPresent(value -> body.put("result", value));
        body.put("idempotentReplay", outcome.idempotentReplay());
        HttpStatus status = switch (outcome.kind()) {
            case CACHE_HIT, NOT_ENQUEUED -> HttpStatus.OK;
            case DURABLE_JOB_ACCEPTED -> HttpStatus.ACCEPTED;
            case BLOCKED -> blockedStatus(outcome.reason());
            case UNKNOWN_RECONCILIATION_REQUIRED -> HttpStatus.CONFLICT;
        };
        return ResponseEntity.status(status).body(body);
    }

    private static HttpStatus blockedStatus(String reason) {
        String normalized = reason == null ? "" : reason.toUpperCase(Locale.ROOT);
        return normalized.contains("AUTHORIZATION")
                || normalized.contains("ACCESS_DENIED")
                || normalized.contains("TENANT_MISMATCH")
                ? HttpStatus.FORBIDDEN : HttpStatus.UNPROCESSABLE_ENTITY;
    }

    private static ExecutionJobPort.BusinessLine parseBusinessLine(String value) {
        try {
            return ExecutionJobPort.BusinessLine.valueOf(require(value, 64,
                    "ELMOS_ACTION_CACHE_BUSINESS_LINE_INVALID").toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw invalid("ELMOS_ACTION_CACHE_BUSINESS_LINE_INVALID");
        }
    }

    private static String permissionFor(ExecutionJobPort.BusinessLine line) {
        return switch (line) {
            case GENERATION -> "generation:execute";
            case TRANSLATION -> "translation:execute";
            case SPRING_UPGRADE -> "spring:execute";
            case REPOSITORY_WORKSPACE -> "repository:write";
            case MODERNIZATION_PROOF -> "modernization:execute";
        };
    }

    private static String capabilityFor(ExecutionJobPort.BusinessLine line) {
        return switch (line) {
            case GENERATION -> "generation:multi";
            case TRANSLATION -> "translation:multi";
            case SPRING_UPGRADE -> "spring:upgrade";
            case REPOSITORY_WORKSPACE -> "repository:workspace";
            case MODERNIZATION_PROOF -> "modernization:proof-loop";
        };
    }

    private static String workloadClassFor(ExecutionJobPort.BusinessLine line) {
        return switch (line) {
            case GENERATION -> "GENERATION";
            case TRANSLATION, SPRING_UPGRADE -> "CONVERSION";
            case REPOSITORY_WORKSPACE -> "PARSING";
            case MODERNIZATION_PROOF -> "VALIDATION";
        };
    }

    private static int resourceUnitsFor(ExecutionJobPort.BusinessLine line) {
        return switch (line) {
            case GENERATION, MODERNIZATION_PROOF -> 2;
            case TRANSLATION, SPRING_UPGRADE -> 3;
            case REPOSITORY_WORKSPACE -> 1;
        };
    }

    private static ActionCacheExecutionJobDispatcher.Mode parseMode(String value) {
        if (value == null || value.isBlank()) {
            return ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE;
        }
        try {
            return ActionCacheExecutionJobDispatcher.Mode.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException error) {
            throw invalid("ELMOS_ACTION_CACHE_MODE_INVALID");
        }
    }

    private static Optional<CasDigest> parseExpectedDigest(String value) {
        if (value == null || value.isBlank()) return Optional.empty();
        try {
            return Optional.of(CasDigest.parseCompact(value.trim()));
        } catch (RuntimeException error) {
            throw invalid("ELMOS_ACTION_CACHE_EXPECTED_DIGEST_INVALID");
        }
    }

    private static String require(String value, int max, String code) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > max
                || candidate.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > max * 4) {
            throw invalid(code);
        }
        return candidate;
    }

    private static ExecutionJobPort.ExecutionStateException invalid(String code) {
        return new ExecutionJobPort.ExecutionStateException(code);
    }

    @ExceptionHandler(ExecutionJobPort.ExecutionStateException.class)
    ResponseEntity<?> executionError(ExecutionJobPort.ExecutionStateException ex) {
        HttpStatus status = ex.code().contains("AUTHORIZATION")
                ? HttpStatus.FORBIDDEN : HttpStatus.BAD_REQUEST;
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", ex.code()));
    }
}
