package io.elmos.commercialapi;

import io.elmos.commercial.CommercialOrderPort;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;

import java.math.BigDecimal;
import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CommercialOrderReconciliationApiTest {
    @Test
    void platformBillingAdminCanReadOnlyItsAuthenticatedOrganization() {
        CommercialOrderPort orders = mock(CommercialOrderPort.class);
        var expected = new CommercialOrderPort.CreditReconciliation(
                "org-a", new BigDecimal("500"), new BigDecimal("500"),
                new BigDecimal("100"), new BigDecimal("100"),
                BigDecimal.ZERO, BigDecimal.ZERO, 0);
        when(orders.creditReconciliation("org-a")).thenReturn(expected);
        var controller = new CommercialOrderController(
                orders, mock(PaymentProviderRouter.class), false);

        assertEquals(expected, controller.creditReconciliation(jwt(
                "commercial:usage:admin commercial:usage:read", true)));
        verify(orders).creditReconciliation("org-a");
    }

    @Test
    void ordinaryUsageReaderCannotReadAccountingReconciliation() {
        var controller = new CommercialOrderController(
                mock(CommercialOrderPort.class), mock(PaymentProviderRouter.class), false);

        assertThrows(AccessDeniedException.class, () -> controller.creditReconciliation(
                jwt("commercial:usage:read", false)));
    }

    private static Jwt jwt(String scope, boolean platformAdministrator) {
        var builder = Jwt.withTokenValue("token")
                .header("alg", "none")
                .subject("actor-a")
                .issuedAt(Instant.now().minusSeconds(5))
                .expiresAt(Instant.now().plusSeconds(300))
                .claim("organization_id", "org-a")
                .claim("scope", scope);
        if (platformAdministrator) {
            builder.claim("email", "zpchoney@gmail.com").claim("email_verified", true);
        }
        return builder.build();
    }
}
