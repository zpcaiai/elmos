package io.elmos.commercialapi;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.UncategorizedSQLException;

import java.sql.SQLException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class BillingApiErrorAdviceTest {
    private final BillingApiErrorAdvice advice = new BillingApiErrorAdvice(
            new BillingMetrics(new SimpleMeterRegistry())
    );

    @Test
    void mapsAllowlistedPostgresStateRuleWithoutLeakingSql() {
        var error = new UncategorizedSQLException(
                "settle",
                "select private_operation()",
                new SQLException("ERROR: USAGE_RESERVATION_EXPIRED\n  Where: private details", "P0001")
        );

        var response = advice.database(error);

        assertEquals(409, response.getStatusCode().value());
        assertEquals("USAGE_RESERVATION_EXPIRED", response.getBody().get("code"));
        assertEquals(
                "The billing operation was rejected by an authoritative state rule.",
                response.getBody().get("message")
        );
    }

    @Test
    void unknownDatabaseFailureRemainsRetryableAndOpaque() {
        var error = new UncategorizedSQLException(
                "query",
                "select secret",
                new SQLException("connection dropped with private details", "08006")
        );

        var response = advice.database(error);

        assertEquals(503, response.getStatusCode().value());
        assertEquals("BILLING_DATABASE_UNAVAILABLE", response.getBody().get("code"));
        assertEquals(true, response.getBody().get("retryable"));
    }

    @Test
    void applicationAndStateErrorsNeverExposeTheirExceptionMessages() {
        var application = advice.billing(new BillingApiException(
                409,
                "BILLING_CONFLICT",
                "private provider response and tenant details",
                false
        ));
        var state = advice.state(new io.elmos.persistence.JdbcSelfServiceBillingStore.BillingStateException(
                "SUBSCRIPTION_NOT_CANCELLABLE",
                "private subscription state and internal identifier"
        ));

        assertEquals("The billing operation was rejected.", application.getBody().get("message"));
        assertEquals(
                "The billing operation was rejected by an authoritative state rule.",
                state.getBody().get("message")
        );
        assertFalse(application.getBody().toString().contains("private provider"));
        assertFalse(state.getBody().toString().contains("private subscription"));
    }
}
