package io.elmos.databasedata;

import org.springframework.http.HttpStatus;

import java.util.LinkedHashMap;
import java.util.Map;

/** Sanitized failure that is safe to map across the worker HTTP boundary. */
final class ChinaDbSqlPreflightFailure extends RuntimeException {
    enum Kind {
        REQUEST_REJECTED,
        REQUEST_TOO_LARGE,
        STALE_SNAPSHOT,
        UNAVAILABLE,
        PROTOCOL_ERROR
    }

    private final Kind kind;

    ChinaDbSqlPreflightFailure(Kind kind) {
        super(kind.name());
        this.kind = kind;
    }

    Kind kind() {
        return kind;
    }

    HttpStatus status() {
        return switch (kind) {
            case REQUEST_REJECTED -> HttpStatus.BAD_REQUEST;
            case REQUEST_TOO_LARGE -> HttpStatus.PAYLOAD_TOO_LARGE;
            case STALE_SNAPSHOT -> HttpStatus.CONFLICT;
            case UNAVAILABLE -> HttpStatus.SERVICE_UNAVAILABLE;
            case PROTOCOL_ERROR -> HttpStatus.BAD_GATEWAY;
        };
    }

    String errorCode() {
        return switch (kind) {
            case REQUEST_REJECTED -> "CHINADB_SQL_PREFLIGHT_REQUEST_REJECTED";
            case REQUEST_TOO_LARGE -> "CHINADB_SQL_PREFLIGHT_REQUEST_TOO_LARGE";
            case STALE_SNAPSHOT -> "CHINADB_SQL_PREFLIGHT_CAPABILITY_SNAPSHOT_STALE";
            case UNAVAILABLE -> "CHINADB_SQL_PREFLIGHT_UNAVAILABLE";
            case PROTOCOL_ERROR -> "CHINADB_SQL_PREFLIGHT_PROTOCOL_ERROR";
        };
    }

    String safeMessage() {
        return switch (kind) {
            case REQUEST_REJECTED -> "The ChinaDB SQL preflight request was rejected by its contract.";
            case REQUEST_TOO_LARGE -> "The ChinaDB SQL preflight request exceeded its byte limit.";
            case STALE_SNAPSHOT -> "The ChinaDB SQL capability snapshot is stale.";
            case UNAVAILABLE -> "The ChinaDB SQL preflight service is unavailable.";
            case PROTOCOL_ERROR -> "The ChinaDB SQL preflight service returned an invalid response.";
        };
    }

    boolean retryable() {
        return kind == Kind.UNAVAILABLE;
    }

    Map<String, Object> body() {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("schemaVersion", "1.0");
        body.put("status", "BLOCKED");
        body.put("errorCode", errorCode());
        body.put("message", safeMessage());
        body.put("retryable", retryable());
        body.put("targetSql", null);
        body.put("verification", notRunVerification());
        body.put("certification", "NOT_CERTIFIED");
        return body;
    }

    private static Map<String, String> notRunVerification() {
        Map<String, String> verification = new LinkedHashMap<>();
        verification.put("sourceParse", "NOT_RUN");
        verification.put("targetAdapter", "NOT_RUN");
        verification.put("targetEmit", "NOT_RUN");
        verification.put("targetReparse", "NOT_RUN");
        verification.put("sourceExecution", "NOT_RUN");
        verification.put("targetExecution", "NOT_RUN");
        verification.put("resultEquivalence", "NOT_RUN");
        verification.put("externalExecution", "NOT_RUN");
        return verification;
    }
}
