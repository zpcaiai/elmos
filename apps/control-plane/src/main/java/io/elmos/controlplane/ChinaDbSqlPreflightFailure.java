package io.elmos.controlplane;

import org.springframework.http.HttpStatus;

/** Sanitized failure that does not expose worker URLs, SQL, or upstream diagnostics. */
final class ChinaDbSqlPreflightFailure extends RuntimeException {
    enum Kind {
        REQUEST_REJECTED,
        REQUEST_TOO_LARGE,
        UNAVAILABLE,
        PROTOCOL_ERROR
    }

    private final Kind kind;

    ChinaDbSqlPreflightFailure(Kind kind) {
        super(kind.name());
        this.kind = kind;
    }

    HttpStatus status() {
        return switch (kind) {
            case REQUEST_REJECTED -> HttpStatus.BAD_REQUEST;
            case REQUEST_TOO_LARGE -> HttpStatus.PAYLOAD_TOO_LARGE;
            case UNAVAILABLE -> HttpStatus.SERVICE_UNAVAILABLE;
            case PROTOCOL_ERROR -> HttpStatus.BAD_GATEWAY;
        };
    }

    String errorCode() {
        return switch (kind) {
            case REQUEST_REJECTED -> "CHINADB_SQL_PREFLIGHT_REQUEST_REJECTED";
            case REQUEST_TOO_LARGE -> "CHINADB_SQL_PREFLIGHT_REQUEST_TOO_LARGE";
            case UNAVAILABLE -> "CHINADB_SQL_PREFLIGHT_UNAVAILABLE";
            case PROTOCOL_ERROR -> "CHINADB_SQL_PREFLIGHT_PROTOCOL_ERROR";
        };
    }

    String safeMessage() {
        return switch (kind) {
            case REQUEST_REJECTED -> "The ChinaDB SQL preflight request was rejected by its contract.";
            case REQUEST_TOO_LARGE -> "The ChinaDB SQL preflight request exceeded its byte limit.";
            case UNAVAILABLE -> "The ChinaDB SQL preflight service is unavailable.";
            case PROTOCOL_ERROR -> "The ChinaDB SQL preflight service returned an invalid response.";
        };
    }

    boolean retryable() {
        return kind == Kind.UNAVAILABLE;
    }
}
