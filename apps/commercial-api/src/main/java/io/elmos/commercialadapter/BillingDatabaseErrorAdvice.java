package io.elmos.commercialadapter;

import io.elmos.commercialapi.BillingApiErrorAdvice;
import io.elmos.commercialapi.BillingMetrics;
import io.elmos.commercialapi.SelfServiceBillingController;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * PostgreSQL-specific exception translation kept outside the public API package.
 */
@RestControllerAdvice(assignableTypes = SelfServiceBillingController.class)
public final class BillingDatabaseErrorAdvice {
    private static final Map<String, Integer> POSTGRES_DOMAIN_ERRORS = postgresDomainErrors();
    private final BillingMetrics metrics;

    public BillingDatabaseErrorAdvice(BillingMetrics metrics) {
        this.metrics = metrics;
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<Map<String, Object>> database(DataAccessException error) {
        metrics.error("BILLING_DATABASE_ERROR");
        SQLException sql = sqlException(error);
        if (sql != null && "23505".equals(sql.getSQLState())) {
            return BillingApiErrorAdvice.response(
                    409,
                    "BILLING_IDEMPOTENCY_OR_ELIGIBILITY_CONFLICT",
                    "The request conflicts with an existing billing record.",
                    false
            );
        }
        String domainCode = PostgresBillingDomainErrorClassifier.classify(
                sql,
                POSTGRES_DOMAIN_ERRORS.keySet()
        );
        if (domainCode != null) {
            return BillingApiErrorAdvice.response(
                    POSTGRES_DOMAIN_ERRORS.get(domainCode),
                    domainCode,
                    "The billing operation was rejected by an authoritative state rule.",
                    false
            );
        }
        return BillingApiErrorAdvice.response(
                503,
                "BILLING_DATABASE_UNAVAILABLE",
                "Billing state is temporarily unavailable.",
                true
        );
    }

    private static Map<String, Integer> postgresDomainErrors() {
        Map<String, Integer> errors = new LinkedHashMap<>();
        for (String code : new String[]{
                "BILLING_PERIOD_INVALID", "PAYMENT_RECONCILIATION_REFERENCE_INVALID",
                "PAYMENT_RECONCILIATION_RESOLUTION_INVALID", "TOKEN_PROVIDER_RECEIPT_REQUIRED",
                "TRIAL_VERIFIED_SUBJECT_INVALID", "USAGE_ALERT_QUANTITY_INVALID",
                "USAGE_CORRECTION_QUANTITY_INVALID", "USAGE_OPERATION_KEY_INVALID",
                "USAGE_RESERVATION_EXPIRY_INVALID", "USAGE_RESERVATION_QUANTITY_INVALID",
                "USAGE_SETTLEMENT_QUANTITY_INVALID"
        }) errors.put(code, 400);
        for (String code : new String[]{
                "PAYMENT_RECONCILIATION_CASE_NOT_FOUND", "USAGE_ORIGINAL_DEBIT_NOT_FOUND",
                "USAGE_RESERVATION_NOT_FOUND"
        }) errors.put(code, 404);
        for (String code : new String[]{
                "ACTIVE_ALLOWANCE_NOT_FOUND", "PAID_PLAN_INVALID",
                "PAYMENT_RECONCILIATION_CASE_ALREADY_CLOSED",
                "PAYMENT_RECONCILIATION_IDEMPOTENCY_CONFLICT", "TRIAL_ALREADY_USED",
                "USAGE_ACTUAL_EXCEEDS_RESERVATION", "USAGE_CORRECTION_EXCEEDS_ORIGINAL",
                "USAGE_CORRECTION_NEGATIVE_BALANCE", "USAGE_RESERVATION_EXPIRED",
                "USAGE_RELEASE_IDEMPOTENCY_CONFLICT",
                "USAGE_RESERVATION_IDEMPOTENCY_CONFLICT",
                "USAGE_RESERVATION_NOT_RELEASABLE", "USAGE_RESERVATION_NOT_SETTLEABLE",
                "USAGE_SETTLEMENT_IDEMPOTENCY_CONFLICT"
        }) errors.put(code, 409);
        return Map.copyOf(errors);
    }

    private static SQLException sqlException(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof SQLException sql) return sql;
            current = current.getCause();
        }
        return null;
    }
}
