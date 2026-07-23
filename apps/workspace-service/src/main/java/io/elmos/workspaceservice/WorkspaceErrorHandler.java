package io.elmos.workspaceservice;

import com.github.dockerjava.api.exception.DockerException;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice(assignableTypes = {WorkspaceController.class, SecretInjectionController.class})
final class WorkspaceErrorHandler {
    record WorkspaceApiError(String errorCode, String message, boolean retryable) {}

    @ExceptionHandler({
        IllegalArgumentException.class,
        HttpMessageNotReadableException.class,
        MethodArgumentTypeMismatchException.class
    })
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    WorkspaceApiError invalidRequest(Exception ignored) {
        return new WorkspaceApiError(
                "WORKSPACE_REQUEST_INVALID",
                "The workspace request is malformed or outside the supported contract.",
                false);
    }

    @ExceptionHandler(SecurityException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    WorkspaceApiError policyDenied(SecurityException ignored) {
        return new WorkspaceApiError(
                "WORKSPACE_POLICY_DENIED",
                "The workspace request violates an enforced security policy.",
                false);
    }

    @ExceptionHandler({IllegalStateException.class, DockerException.class, DataAccessException.class})
    @ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
    WorkspaceApiError serviceUnavailable(RuntimeException ignored) {
        return new WorkspaceApiError(
                "WORKSPACE_SERVICE_UNAVAILABLE",
                "The isolated workspace service is unavailable; no successful execution is recorded.",
                true);
    }
}
