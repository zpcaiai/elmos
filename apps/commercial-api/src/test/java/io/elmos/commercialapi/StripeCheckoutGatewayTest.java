package io.elmos.commercialapi;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HexFormat;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class StripeCheckoutGatewayTest {
    private static final Instant NOW = Instant.parse("2026-07-28T10:00:00Z");
    private static final String WEBHOOK_SECRET = "whsec_test_exact_signature_secret";

    @Test
    void verifiesSignedInvoiceAndNormalizesSubscriptionMetadata() throws Exception {
        String payload = """
                {
                  "id":"evt_invoice_paid_1",
                  "type":"invoice.paid",
                  "created":1785232800,
                  "data":{"object":{
                    "id":"in_1",
                    "customer":"cus_1",
                    "currency":"cny",
                    "amount_paid":12900,
                    "parent":{"subscription_details":{
                      "subscription":"sub_provider_1",
                      "metadata":{
                        "organization_id":"org-a",
                        "actor_id":"actor-a",
                        "plan_id":"elmos-pro-monthly",
                        "catalog_version":"2026-07-28.2"
                      }
                    }},
                    "lines":{"data":[{"period":{"start":1785232800,"end":1787911200}}]}
                  }}
                }
                """;
        var gateway = gateway(NOW);
        var event = gateway.verifyAndNormalize(payload, signature(payload, NOW));

        assertEquals("evt_invoice_paid_1", event.eventId());
        assertEquals("org-a", event.organizationId());
        assertEquals("elmos-pro-monthly", event.planId());
        assertEquals("sub_provider_1", event.subscriptionRef());
        assertEquals("CNY", event.currency());
        assertEquals(12900, event.amountMinor());
        assertEquals(Instant.ofEpochSecond(1785232800), event.periodStart());
        assertEquals(Instant.ofEpochSecond(1787911200), event.periodEnd());
    }

    @Test
    void rejectsInvalidAndStaleSignatures() throws Exception {
        String payload = """
                {"id":"evt_1","type":"checkout.session.completed","created":1785232800,
                 "data":{"object":{"id":"cs_1","metadata":{}}}}
                """;
        var gateway = gateway(NOW);

        BillingApiException invalid = assertThrows(
                BillingApiException.class,
                () -> gateway.verifyAndNormalize(payload, "t=1785232800,v1=00"));
        assertEquals("STRIPE_WEBHOOK_SIGNATURE_INVALID", invalid.code());

        Instant stale = NOW.minusSeconds(301);
        BillingApiException timestamp = assertThrows(
                BillingApiException.class,
                () -> gateway.verifyAndNormalize(payload, signature(payload, stale)));
        assertEquals("STRIPE_WEBHOOK_TIMESTAMP_INVALID", timestamp.code());
    }

    private static StripeCheckoutGateway gateway(Instant now) {
        return new StripeCheckoutGateway(
                HttpClient.newHttpClient(),
                new ObjectMapper(),
                Clock.fixed(now, ZoneOffset.UTC),
                "https://api.stripe.com",
                "sk_test_configured_but_not_called",
                WEBHOOK_SECRET,
                "price_monthly",
                "price_annual",
                "https://elmos.example/billing/success",
                "https://elmos.example/billing/cancel"
        );
    }

    private static String signature(String payload, Instant at) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(
                WEBHOOK_SECRET.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signed = at.getEpochSecond() + "." + payload;
        return "t=" + at.getEpochSecond() + ",v1=" + HexFormat.of().formatHex(
                mac.doFinal(signed.getBytes(StandardCharsets.UTF_8)));
    }
}
