package io.elmos.commercialapi;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class OrderExpiryGuardTest {
    private static final Instant NOW = Instant.parse("2026-09-14T00:00:00Z");

    @Test
    void payableOrderMustHaveStrictlyFutureExpiry() {
        assertDoesNotThrow(() -> CommercialOrderController.requirePayableBefore(
                NOW.plusSeconds(1), NOW, "ORDER_EXPIRED", "expired"));
        for (Instant expiresAt : new Instant[]{null, NOW, NOW.minusSeconds(1)}) {
            BillingApiException error = assertThrows(BillingApiException.class,
                    () -> CommercialOrderController.requirePayableBefore(
                            expiresAt, NOW, "ORDER_EXPIRED", "expired"));
            assertEquals(409, error.httpStatus());
            assertEquals("ORDER_EXPIRED", error.code());
            assertEquals(false, error.retryable());
        }
    }
}
