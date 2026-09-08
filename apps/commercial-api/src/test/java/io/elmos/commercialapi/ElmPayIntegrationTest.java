package io.elmos.commercialapi;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercialadapter.payment.CallbackReplayGuard;
import io.elmos.commercialadapter.payment.ElmPayCheckoutGateway;
import io.elmos.commercialadapter.payment.ElmPayWebhookAdapter;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline;
import io.elmos.commercialadapter.payment.PaymentProvider;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

class ElmPayIntegrationTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final UUID TENANT = UUID.fromString("00000000-0000-0000-0000-000000000101");
    private static final UUID PROJECT = UUID.fromString("00000000-0000-0000-0000-000000000202");
    private static final UUID INTENT = UUID.fromString("00000000-0000-0000-0000-000000000303");
    private static final UUID EVENT = UUID.fromString("00000000-0000-0000-0000-000000000404");
    private static final Instant NOW = Instant.parse("2026-09-08T00:00:00Z");
    private static final byte[] SECRET = "0123456789abcdef0123456789abcdef"
            .getBytes(StandardCharsets.UTF_8);

    @Test
    void checkoutUsesServerAmountAndStrictElmPayHeaders() throws Exception {
        AtomicReference<String> requestBody = new AtomicReference<>();
        ElmPayCheckoutGateway gateway = new ElmPayCheckoutGateway(
                PaymentProvider.ALIPAY_CHECKOUT, java.net.URI.create("https://pay.example/"),
                PROJECT, "elmos-payment-complete", false, () -> "mounted-token",
                (endpoint, token, projectId, idempotencyKey, requestId, traceparent, body) -> {
                    assertEquals("https://pay.example/v1/checkout-sessions", endpoint.toString());
                    assertEquals("mounted-token", token);
                    assertEquals(PROJECT, projectId);
                    assertTrue(idempotencyKey.matches("elmos-checkout-[0-9a-f]{64}"));
                    assertTrue(requestId.matches("elmos-[0-9a-f]{32}"));
                    assertTrue(traceparent.matches("00-[0-9a-f]{32}-[0-9a-f]{16}-01"));
                    requestBody.set(body);
                    return new ElmPayCheckoutGateway.Response(201, """
                            {"checkout_session_id":"session-1",
                             "payment_intent_id":"00000000-0000-0000-0000-000000000303",
                             "expires_at":"2026-09-08T00:10:00Z",
                             "checkout_url":"https://checkout.example/#session=session-1&token=opaque",
                             "status":"OPEN"}
                            """);
                }, JSON);

        var handoff = gateway.prepare("order-99", 9_900, "500 Credits");

        assertEquals(PaymentProvider.ALIPAY_CHECKOUT, handoff.provider());
        assertEquals("https://checkout.example/#session=session-1&token=opaque",
                handoff.redirectUrl());
        Map<?, ?> request = JSON.readValue(requestBody.get(), Map.class);
        assertEquals("order-99", request.get("business_order_no"));
        assertEquals(9_900, request.get("amount"));
        assertEquals("CNY", request.get("currency"));
        assertEquals("elmos-payment-complete", request.get("return_route_id"));
        assertTrue(gateway.contactsProviderDuringPrepare());
    }

    @Test
    void capturedWebhookVerifiesExactRawBodyAndNormalizesDigestLookup() throws Exception {
        ElmPayWebhookAdapter adapter = adapter();
        String body = capturedEnvelope(TENANT, PROJECT);
        String timestamp = Long.toString(NOW.getEpochSecond());
        PaymentCallbackPipeline.RawCallback raw = raw(body, timestamp, signature(timestamp, body));

        assertTrue(adapter.acceptsTimestamp(raw));
        assertTrue(adapter.verifySignature(raw));
        assertTrue(adapter.isCapturedEvent(raw));
        PaymentCallbackPipeline.NormalizedCallback callback = adapter.normalize(raw);
        assertEquals(PaymentProvider.ALIPAY_CHECKOUT, callback.provider());
        assertEquals(EVENT.toString(), callback.providerEventId());
        assertEquals("sha256:" + "a".repeat(64), callback.outTradeNo());
        assertEquals(9_900, callback.amountFen());
        assertTrue(adapter.indicatesPaymentSuccess(callback));
    }

    @Test
    void webhookRejectsBodyMutationAndCrossTenantEnvelope() throws Exception {
        ElmPayWebhookAdapter adapter = adapter();
        String body = capturedEnvelope(TENANT, PROJECT);
        String timestamp = Long.toString(NOW.getEpochSecond());
        assertFalse(adapter.verifySignature(raw(body.replace("9900", "3900"), timestamp,
                signature(timestamp, body))));

        String foreign = capturedEnvelope(
                UUID.fromString("00000000-0000-0000-0000-000000000999"), PROJECT);
        assertFalse(adapter.verifySignature(raw(foreign, timestamp, signature(timestamp, foreign))));
    }

    @Test
    void capturedWebhookRejectsFractionalMinorUnitsEvenWhenSigned() throws Exception {
        ElmPayWebhookAdapter adapter = adapter();
        String body = capturedEnvelope(TENANT, PROJECT).replace("9900", "9900.5");
        String timestamp = Long.toString(NOW.getEpochSecond());
        PaymentCallbackPipeline.RawCallback raw = raw(body, timestamp, signature(timestamp, body));
        assertTrue(adapter.verifySignature(raw));
        assertThrows(IllegalArgumentException.class, () -> adapter.normalize(raw));
    }

    @Test
    void capturedWebhookRejectsAggregateAndPayloadIdentityMismatch() throws Exception {
        ElmPayWebhookAdapter adapter = adapter();
        var envelope = (com.fasterxml.jackson.databind.node.ObjectNode)
                JSON.readTree(capturedEnvelope(TENANT, PROJECT));
        envelope.put("aggregate_id", "00000000-0000-0000-0000-000000000999");
        String body = JSON.writeValueAsString(envelope);
        String timestamp = Long.toString(NOW.getEpochSecond());
        PaymentCallbackPipeline.RawCallback raw = raw(body, timestamp, signature(timestamp, body));
        assertTrue(adapter.verifySignature(raw));
        assertThrows(IllegalArgumentException.class, () -> adapter.normalize(raw));
    }

    private static ElmPayWebhookAdapter adapter() {
        return new ElmPayWebhookAdapter(PaymentProvider.ALIPAY_CHECKOUT, TENANT, PROJECT,
                "elmos-key-1", () -> SECRET.clone(),
                new CallbackReplayGuard(Clock.fixed(NOW, ZoneOffset.UTC), Duration.ofMinutes(5)),
                JSON);
    }

    private static PaymentCallbackPipeline.RawCallback raw(
            String body, String timestamp, String signature) {
        return new PaymentCallbackPipeline.RawCallback(PaymentProvider.ALIPAY_CHECKOUT, body,
                Map.of("X-Elmpay-Signature", signature,
                        "X-Elmpay-Event-Id", EVENT.toString(),
                        "X-Elmpay-Event-Type", "payment_intent.captured",
                        "X-Elmpay-Timestamp", timestamp,
                        "X-Elmpay-Key-Id", "elmos-key-1"), Map.of());
    }

    private static String capturedEnvelope(UUID tenant, UUID project) throws Exception {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("payment_intent_id", INTENT.toString());
        payload.put("project_id", project.toString());
        payload.put("provider", "alipay");
        payload.put("captured_at", NOW.toString());
        payload.put("amount_minor", 9_900);
        payload.put("currency", "CNY");
        payload.put("business_order_digest", "a".repeat(64));
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("event_id", EVENT.toString());
        envelope.put("event_name", "payment_intent.captured");
        envelope.put("event_version", 1);
        envelope.put("tenant_id", tenant.toString());
        envelope.put("project_id", project.toString());
        envelope.put("aggregate_type", "payment_intent");
        envelope.put("aggregate_id", INTENT.toString());
        envelope.put("revision", 1);
        envelope.put("occurred_at", NOW.toString());
        envelope.put("recorded_at", NOW.toString());
        envelope.put("trace_id", "trace-elmos-1");
        envelope.put("payload", payload);
        return JSON.writeValueAsString(envelope);
    }

    private static String signature(String timestamp, String body) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(SECRET, "HmacSHA256"));
        String value = Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(
                (timestamp + "." + body).getBytes(StandardCharsets.UTF_8)));
        return "t=" + timestamp + ",v1=" + value;
    }
}
