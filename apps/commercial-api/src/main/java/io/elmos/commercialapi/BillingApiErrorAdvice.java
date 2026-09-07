package io.elmos.commercialapi;

import io.elmos.commercial.SelfServiceBillingPort.BillingStateException;
import jakarta.validation.ConstraintViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice(assignableTypes = SelfServiceBillingController.class)
public final class BillingApiErrorAdvice {
    private final BillingMetrics metrics;

    public BillingApiErrorAdvice(BillingMetrics metrics) {
        this.metrics = metrics;
    }

    @ExceptionHandler(BillingApiException.class)
    ResponseEntity<Map<String, Object>> billing(BillingApiException error) {
        metrics.error(error.code());
        return response(
                error.httpStatus(),
                error.code(),
                "The billing operation was rejected.",
                error.retryable()
        );
    }

    @ExceptionHandler(BillingStateException.class)
    ResponseEntity<Map<String, Object>> state(BillingStateException error) {
        metrics.error(error.code());
        int status = "ACTIVE_SUBSCRIPTION_NOT_FOUND".equals(error.code()) ? 404 : 409;
        return response(
                status,
                error.code(),
                "The billing operation was rejected by an authoritative state rule.",
                false
        );
    }

    @ExceptionHandler({
            IllegalArgumentException.class,
            ConstraintViolationException.class,
            MethodArgumentNotValidException.class
    })
    ResponseEntity<Map<String, Object>> invalid(Exception error) {
        metrics.error("BILLING_REQUEST_INVALID");
        return response(400, "BILLING_REQUEST_INVALID", "The billing request is invalid.", false);
    }

    public static ResponseEntity<Map<String, Object>> response(
            int status, String code, String message, boolean retryable
    ) {
        return ResponseEntity.status(status).body(Map.of(
                "status", status == 503 ? "NOT_CONFIGURED" : "ERROR",
                "code", code,
                "message", message,
                "retryable", retryable
        ));
    }
}
