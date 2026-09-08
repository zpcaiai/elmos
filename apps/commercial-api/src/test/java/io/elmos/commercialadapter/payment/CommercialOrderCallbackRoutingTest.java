package io.elmos.commercialadapter.payment;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CommercialOrderCallbackRoutingTest {
    private final List<String> subscriptions = new ArrayList<>();
    private final List<String> wallet = new ArrayList<>();
    private final List<String> commercial = new ArrayList<>();
    private final Set<String> processed = new HashSet<>();

    @Test void creditPackPaymentFulfillsOnlyTheCommercialOrder() {
        var outcome = pipeline(PaymentCallbackPipeline.OrderKind.CREDIT_PACK).process(raw());
        assertEquals(PaymentCallbackPipeline.Outcome.ACCEPTED, outcome);
        assertEquals(List.of("commercial-order-1"), commercial);
        assertTrue(subscriptions.isEmpty());
        assertTrue(wallet.isEmpty());
    }

    @Test void oneTimeProjectPaymentFulfillsOnlyTheCommercialOrder() {
        var outcome = pipeline(PaymentCallbackPipeline.OrderKind.PROJECT_GENERATION_ONCE).process(raw());
        assertEquals(PaymentCallbackPipeline.Outcome.ACCEPTED, outcome);
        assertEquals(List.of("commercial-order-1"), commercial);
        assertTrue(subscriptions.isEmpty());
        assertTrue(wallet.isEmpty());
    }

    @Test void failedFulfillmentReleasesTheCallbackClaimForSafeRetry() {
        class RecoverableLog implements PaymentCallbackPipeline.ProcessedEventLog {
            boolean available = true;
            boolean completed;
            @Override public boolean registerIfAbsent(String key) {
                if (!available || completed) return false;
                available = false;
                return true;
            }
            @Override public void markCompleted(String key) { completed = true; }
            @Override public void markFailed(String key) { available = true; }
        }
        var log = new RecoverableLog();
        var attempts = new AtomicInteger();
        var pipeline = new PaymentCallbackPipeline(adapter(), log,
                trade -> Optional.of(new PaymentCallbackPipeline.LocalOrder(
                        "commercial-order-1", "org-1", null, 3900,
                        PaymentCallbackPipeline.OrderKind.CREDIT_PACK,
                        PaymentProvider.ALIPAY_CHECKOUT)),
                (order, callback, body) -> { }, (order, callback) -> { },
                (order, callback) -> { },
                (order, callback) -> {
                    if (attempts.incrementAndGet() == 1) throw new IllegalStateException("transient");
                },
                (reason, callback, order, detail) -> { });

        org.junit.jupiter.api.Assertions.assertThrows(
                IllegalStateException.class, () -> pipeline.process(raw()));
        assertEquals(PaymentCallbackPipeline.Outcome.ACCEPTED, pipeline.process(raw()));
        assertEquals(PaymentCallbackPipeline.Outcome.DUPLICATE_IGNORED, pipeline.process(raw()));
        assertEquals(2, attempts.get());
    }

    private PaymentCallbackPipeline pipeline(PaymentCallbackPipeline.OrderKind kind) {
        return new PaymentCallbackPipeline(adapter(), processed::add,
                trade -> Optional.of(new PaymentCallbackPipeline.LocalOrder(
                        "commercial-order-1", "org-1", null, 3900, kind,
                        PaymentProvider.ALIPAY_CHECKOUT)),
                (order, callback, body) -> { },
                (order, callback) -> subscriptions.add(order.orderId()),
                (order, callback) -> wallet.add(order.orderId()),
                (order, callback) -> commercial.add(order.orderId()),
                (reason, callback, order, detail) -> { });
    }

    private static PaymentCallbackPipeline.ProviderAdapter adapter() {
        return new PaymentCallbackPipeline.ProviderAdapter() {
            @Override public boolean verifySignature(PaymentCallbackPipeline.RawCallback raw) {
                return true;
            }
            @Override public PaymentCallbackPipeline.NormalizedCallback normalize(
                    PaymentCallbackPipeline.RawCallback raw) {
                return new PaymentCallbackPipeline.NormalizedCallback(
                        raw.provider(), "event-1", "commercial-order-1", 3900, "SUCCESS");
            }
        };
    }

    private static PaymentCallbackPipeline.RawCallback raw() {
        return new PaymentCallbackPipeline.RawCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "{}", Map.of(), Map.of());
    }
}
