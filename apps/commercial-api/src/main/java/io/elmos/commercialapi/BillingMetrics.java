package io.elmos.commercialapi;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public final class BillingMetrics {
    private static final Set<String> WEBHOOK_TYPES = Set.of(
            "checkout.session.completed",
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.deleted",
            "other"
    );
    private final MeterRegistry meters;

    public BillingMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void reservation(String decision) {
        String outcome = decision != null && decision.startsWith("DENY_") ? "denied" : "reserved";
        meters.counter("elmos.billing.usage.reservations", "outcome", outcome).increment();
    }

    public void webhook(String eventType, String outcome) {
        String normalized = WEBHOOK_TYPES.contains(eventType) ? eventType : "other";
        meters.counter(
                "elmos.billing.webhook.events",
                "event_type", normalized,
                "outcome", outcome
        ).increment();
    }

    public void checkout(String outcome) {
        meters.counter("elmos.billing.checkout.requests", "outcome", outcome).increment();
    }

    public void error(String code) {
        String family = code == null ? "unknown"
                : code.startsWith("STRIPE_") ? "provider"
                : code.startsWith("USAGE_") ? "usage"
                : code.startsWith("TRIAL_") ? "trial"
                : code.startsWith("BILLING_") ? "database"
                : "other";
        meters.counter("elmos.billing.api.errors", "family", family).increment();
    }
}
