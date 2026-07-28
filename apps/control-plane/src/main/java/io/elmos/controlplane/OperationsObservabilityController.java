package io.elmos.controlplane;

import io.elmos.persistence.JdbcUserActivityStore;
import io.elmos.persistence.JdbcUserActivityStore.ActivityEvent;
import io.elmos.persistence.JdbcUserActivityStore.ActivitySummary;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/operations-observability")
public final class OperationsObservabilityController {
    private final JdbcUserActivityStore store;
    private final Clock clock;
    private final String apiKey;

    public OperationsObservabilityController(
            JdbcUserActivityStore store,
            Clock clock,
            @Value("${elmos.operations.api-key:}") String apiKey
    ) {
        this.store = Objects.requireNonNull(store, "store");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.apiKey = apiKey == null ? "" : apiKey.trim();
    }

    public record EventBatch(List<ActivityEvent> events) {}
    public record AppendResult(int accepted, String persistence, String requestId) {}

    @PostMapping("/events")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public AppendResult append(
            @RequestHeader("X-ELMOS-Operations-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestHeader("X-ELMOS-Actor-ID") String actorId,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId,
            @RequestBody EventBatch batch
    ) {
        authorize(presentedKey);
        String resolvedRequestId = requestId == null || requestId.isBlank()
                ? UUID.randomUUID().toString() : requestId;
        int accepted = store.append(organizationId, actorId, resolvedRequestId, batch.events());
        return new AppendResult(accepted, "POSTGRES_APPEND_ONLY", resolvedRequestId);
    }

    @GetMapping("/summary")
    public ActivitySummary summary(
            @RequestHeader("X-ELMOS-Operations-Key") String presentedKey,
            @RequestHeader("X-ELMOS-Organization-ID") String organizationId,
            @RequestParam(defaultValue = "24") int hours,
            @RequestParam(defaultValue = "ALL") String businessLine,
            @RequestParam(defaultValue = "ALL") String result,
            @RequestParam(defaultValue = "50") int limit
    ) {
        authorize(presentedKey);
        if (hours < 1 || hours > 24 * 31) {
            throw new IllegalArgumentException("hours must be between 1 and 744");
        }
        Instant to = clock.instant();
        return store.summary(
                organizationId, to.minus(hours, ChronoUnit.HOURS), to,
                businessLine, result, limit);
    }

    private void authorize(String presentedKey) {
        if (apiKey.length() < 24) throw new ObservabilityUnavailableException();
        byte[] expected = apiKey.getBytes(StandardCharsets.UTF_8);
        byte[] presented = (presentedKey == null ? "" : presentedKey).getBytes(StandardCharsets.UTF_8);
        if (expected.length != presented.length || !MessageDigest.isEqual(expected, presented)) {
            throw new SecurityException("operations observability authorization failed");
        }
    }

    @ExceptionHandler(SecurityException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    Map<String, Object> forbidden() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_FORBIDDEN",
                "message", "Operations observability authorization failed.", "retryable", false);
    }

    @ExceptionHandler(ObservabilityUnavailableException.class)
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    Map<String, Object> unavailable() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_NOT_CONFIGURED",
                "message", "Operations observability is not configured.", "retryable", false);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    Map<String, Object> invalid() {
        return Map.of("errorCode", "OPERATIONS_OBSERVABILITY_REQUEST_INVALID",
                "message", "The observability request was rejected by its contract.", "retryable", false);
    }

    private static final class ObservabilityUnavailableException extends RuntimeException {}
}
