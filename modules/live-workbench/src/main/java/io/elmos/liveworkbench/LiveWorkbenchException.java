package io.elmos.liveworkbench;

import org.springframework.http.HttpStatus;

/** Stable API failure taxonomy. Unknown provider results are conflicts, never implicit success. */
public final class LiveWorkbenchException extends RuntimeException {
    private final HttpStatus status;
    private final String code;

    public LiveWorkbenchException(HttpStatus status, String code, String message) {
        super(message); this.status = status; this.code = code;
    }
    public HttpStatus status() { return status; }
    public String code() { return code; }

    public static LiveWorkbenchException notFound() { return new LiveWorkbenchException(HttpStatus.NOT_FOUND, "SESSION_NOT_FOUND", "session not found"); }
    public static LiveWorkbenchException notFound(String code) { return new LiveWorkbenchException(HttpStatus.NOT_FOUND, code, code); }
    public static LiveWorkbenchException conflict(String code) { return new LiveWorkbenchException(HttpStatus.CONFLICT, code, code); }
    public static LiveWorkbenchException denied(String code) { return new LiveWorkbenchException(HttpStatus.FORBIDDEN, code, code); }
    public static LiveWorkbenchException exhausted() { return new LiveWorkbenchException(HttpStatus.TOO_MANY_REQUESTS, "EXECUTION_SLOT_QUOTA_EXCEEDED", "execution slot quota exceeded"); }
    public static LiveWorkbenchException unavailable(String code) { return new LiveWorkbenchException(HttpStatus.SERVICE_UNAVAILABLE, code, code); }
}
