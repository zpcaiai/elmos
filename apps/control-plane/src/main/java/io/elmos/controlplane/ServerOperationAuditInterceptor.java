package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.HandlerMapping;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Server-authoritative request audit for every control-plane business operation.
 *
 * <p>The configured tenant/actor binding is used rather than caller-controlled
 * identity headers. The attempt is durable before controller execution; the
 * completion event is best effort so a completed side effect is never retried
 * merely because completion logging failed.</p>
 */
final class ServerOperationAuditInterceptor implements HandlerInterceptor {
    private static final String START = ServerOperationAuditInterceptor.class.getName() + ".start";
    private static final String REQUEST_ID = ServerOperationAuditInterceptor.class.getName() + ".requestId";
    private final JdbcUserActivityStore store;
    private final Clock clock;
    private final String organizationId;
    private final String actorId;

    ServerOperationAuditInterceptor(
            JdbcUserActivityStore store,
            Clock clock,
            @Value("${elmos.operations.organization-id:}") String organizationId,
            @Value("${elmos.operations.actor-id:}") String actorId
    ) {
        this.store = Objects.requireNonNull(store, "store");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.organizationId = organizationId == null ? "" : organizationId.trim();
        this.actorId = actorId == null ? "" : actorId.trim();
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) {
        if (!enabledFor(request)) return true;
        Instant start = clock.instant();
        String requestId = safeRequestId(request.getHeader("X-Request-ID"));
        request.setAttribute(START, start);
        request.setAttribute(REQUEST_ID, requestId);
        append(request, requestId, start, null, "SERVER_ATTEMPT", "SUCCESS", null);
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception
    ) {
        Instant start = (Instant) request.getAttribute(START);
        String requestId = (String) request.getAttribute(REQUEST_ID);
        if (start == null || requestId == null) return;
        int status = response.getStatus();
        String result = status >= 400 || exception != null ? "FAILURE" : "SUCCESS";
        String errorCode = "FAILURE".equals(result)
                ? "HTTP_" + Math.max(400, status)
                : null;
        int duration = (int) Math.min(
                3_600_000,
                Math.max(0, Duration.between(start, clock.instant()).toMillis()));
        try {
            append(request, requestId, clock.instant(), duration,
                    "SERVER_OPERATION", result, errorCode);
        } catch (RuntimeException ignored) {
            // The durable attempt event already exists. Do not replay controller side effects.
        }
    }

    private boolean enabledFor(HttpServletRequest request) {
        String path = request.getRequestURI();
        boolean hasVerifiedPrincipal = ControlPlanePrincipal.current().isPresent();
        boolean hasBoundServiceIdentity = !organizationId.isBlank() && !actorId.isBlank();
        return (hasVerifiedPrincipal || hasBoundServiceIdentity)
                && (path.startsWith("/api/v1/") || path.startsWith("/api/webhooks/"))
                && !path.equals("/api/v1/operations-observability/events")
                && !path.equals("/api/v1/operations-observability/audit-events");
    }

    private void append(
            HttpServletRequest request,
            String requestId,
            Instant occurredAt,
            Integer durationMs,
            String eventKind,
            String result,
            String errorCode
    ) {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current().orElse(null);
        String resolvedOrganizationId = principal == null
                ? organizationId
                : principal.auditOrganizationId(
                        request.getHeader("X-ELMOS-Organization-ID"));
        String resolvedActorId = principal == null ? actorId : principal.actorId();
        String route = routePattern(request);
        String method = request.getMethod().toUpperCase(Locale.ROOT);
        store.append(resolvedOrganizationId, resolvedActorId, requestId, List.of(new ActivityEvent(
                UUID.randomUUID().toString(),
                requestId,
                eventKind,
                "HTTP_" + method,
                OperationsBusinessLineRegistry.classify(request.getRequestURI()),
                route,
                route,
                occurredAt,
                durationMs,
                result,
                errorCode,
                null,
                null,
                Map.of(
                        "HTTP_METHOD", method,
                        "STATUS_PHASE", eventKind.equals("SERVER_ATTEMPT") ? "ATTEMPT" : "COMPLETION",
                        "SERVER_SIDE", "true"
                )
        )));
    }

    private static String routePattern(HttpServletRequest request) {
        Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        String value = pattern instanceof String text ? text : request.getRequestURI();
        if (value == null || value.isBlank() || value.length() > 160
                || value.indexOf('?') >= 0 || value.indexOf('#') >= 0) {
            return "/";
        }
        return value;
    }

    private static String safeRequestId(String value) {
        if (value != null && value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            return value;
        }
        return UUID.randomUUID().toString();
    }
}
