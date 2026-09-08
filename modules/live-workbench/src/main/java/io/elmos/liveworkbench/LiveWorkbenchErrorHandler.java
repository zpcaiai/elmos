package io.elmos.liveworkbench;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.time.Instant;
import java.util.Map;

@RestControllerAdvice
public final class LiveWorkbenchErrorHandler {
    private static final Logger LOG = LoggerFactory.getLogger(LiveWorkbenchErrorHandler.class);
    @ExceptionHandler(LiveWorkbenchException.class)
    ResponseEntity<Map<String, Object>> workbench(LiveWorkbenchException error) {
        return response(error.status(), error.code(), error.getMessage());
    }
    @ExceptionHandler({IllegalArgumentException.class, MethodArgumentNotValidException.class})
    ResponseEntity<Map<String, Object>> invalid(Exception error) {
        return response(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "request rejected by lw.v1 contract");
    }
    @ExceptionHandler(Exception.class)
    ResponseEntity<Map<String, Object>> internal(Exception error) {
        LOG.error("Unhandled Live Workbench request failure type={}", error.getClass().getName(), error);
        return response(HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "internal error");
    }
    private static ResponseEntity<Map<String, Object>> response(HttpStatus status, String code, String message) {
        return ResponseEntity.status(status).body(Map.of("code", code, "message", message == null ? code : message,
                "timestamp", Instant.now().toString(), "requestId", java.util.Objects.toString(MDC.get("requestId"), "unavailable")));
    }
}
