package com.giftfuture.chinapubcf.web;

import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler({IllegalArgumentException.class, NumberFormatException.class})
    ProblemDetail badRequest(RuntimeException error) {
        return problem(HttpStatus.BAD_REQUEST, error.getMessage());
    }

    @ExceptionHandler(SecurityException.class)
    ProblemDetail forbidden(SecurityException error) {
        return problem(HttpStatus.FORBIDDEN, error.getMessage());
    }

    @ExceptionHandler(DataAccessException.class)
    ProblemDetail databaseUnavailable(DataAccessException ignored) {
        return problem(HttpStatus.SERVICE_UNAVAILABLE, "database operation failed");
    }

    private static ProblemDetail problem(HttpStatus status, String detail) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status,
                detail == null ? status.getReasonPhrase() : detail);
        problem.setTitle(status.getReasonPhrase());
        return problem;
    }
}
