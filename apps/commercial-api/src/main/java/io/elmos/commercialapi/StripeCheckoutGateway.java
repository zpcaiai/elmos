package io.elmos.commercialapi;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercial.PricingPlanCatalog;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

@Component
public final class StripeCheckoutGateway {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(15);
    private static final Duration SIGNATURE_TOLERANCE = Duration.ofMinutes(5);

    public record CheckoutSession(String id, String url, Instant expiresAt) {}

    public record VerifiedEvent(
            String eventId,
            String eventType,
            String objectRef,
            String organizationId,
            String actorId,
            String planId,
            String customerRef,
            String subscriptionRef,
            String invoiceRef,
            long amountMinor,
            String currency,
            Instant eventCreatedAt,
            Instant periodStart,
            Instant periodEnd,
            String payloadSha256
    ) {}

    private final HttpClient http;
    private final ObjectMapper json;
    private final Clock clock;
    private final String apiBase;
    private final String secretKey;
    private final String webhookSecret;
    private final String monthlyPriceId;
    private final String annualPriceId;
    private final String successUrl;
    private final String cancelUrl;

    @Autowired
    public StripeCheckoutGateway(
            ObjectMapper json,
            @Value("${elmos.billing.stripe.secret-key:}") String secretKey,
            @Value("${elmos.billing.stripe.webhook-secret:}") String webhookSecret,
            @Value("${elmos.billing.stripe.monthly-price-id:}") String monthlyPriceId,
            @Value("${elmos.billing.stripe.annual-price-id:}") String annualPriceId,
            @Value("${elmos.billing.stripe.success-url:}") String successUrl,
            @Value("${elmos.billing.stripe.cancel-url:}") String cancelUrl,
            @Value("${elmos.billing.stripe.api-base:https://api.stripe.com}") String apiBase
    ) {
        this(HttpClient.newBuilder().connectTimeout(REQUEST_TIMEOUT).build(), json, Clock.systemUTC(),
                apiBase, secretKey, webhookSecret, monthlyPriceId, annualPriceId, successUrl, cancelUrl);
    }

    StripeCheckoutGateway(
            HttpClient http,
            ObjectMapper json,
            Clock clock,
            String apiBase,
            String secretKey,
            String webhookSecret,
            String monthlyPriceId,
            String annualPriceId,
            String successUrl,
            String cancelUrl
    ) {
        this.http = http;
        this.json = json;
        this.clock = clock;
        this.apiBase = apiBase;
        this.secretKey = secretKey;
        this.webhookSecret = webhookSecret;
        this.monthlyPriceId = monthlyPriceId;
        this.annualPriceId = annualPriceId;
        this.successUrl = successUrl;
        this.cancelUrl = cancelUrl;
    }

    public boolean checkoutConfigured() {
        return notBlank(secretKey) && notBlank(monthlyPriceId) && notBlank(annualPriceId)
                && validReturnUrl(successUrl) && validReturnUrl(cancelUrl);
    }

    public boolean webhookConfigured() {
        return notBlank(webhookSecret);
    }

    public CheckoutSession createSubscriptionSession(
            String organizationId,
            String actorId,
            String planId,
            String idempotencyKey
    ) {
        if (!checkoutConfigured()) {
            throw new BillingApiException(503, "STRIPE_CHECKOUT_NOT_CONFIGURED",
                    "Payment checkout is not configured.", true);
        }
        String priceId = switch (planId) {
            case "elmos-pro-monthly" -> monthlyPriceId;
            case "elmos-pro-annual" -> annualPriceId;
            default -> throw new BillingApiException(
                    400, "PLAN_NOT_PURCHASABLE", "The selected plan cannot be purchased.", false);
        };
        var plan = PricingPlanCatalog.requirePlan(planId);
        if (!"CNY".equals(plan.price().currency())) {
            throw new BillingApiException(
                    503, "CHECKOUT_CURRENCY_MISMATCH", "The configured catalog currency is invalid.", false);
        }

        Map<String, String> fields = Map.ofEntries(
                Map.entry("mode", "subscription"),
                Map.entry("line_items[0][price]", priceId),
                Map.entry("line_items[0][quantity]", "1"),
                Map.entry("client_reference_id", organizationId),
                Map.entry("metadata[organization_id]", organizationId),
                Map.entry("metadata[actor_id]", actorId),
                Map.entry("metadata[plan_id]", planId),
                Map.entry("metadata[catalog_version]", PricingPlanCatalog.CATALOG_VERSION),
                Map.entry("subscription_data[metadata][organization_id]", organizationId),
                Map.entry("subscription_data[metadata][actor_id]", actorId),
                Map.entry("subscription_data[metadata][plan_id]", planId),
                Map.entry("subscription_data[metadata][catalog_version]", PricingPlanCatalog.CATALOG_VERSION),
                Map.entry("success_url", successUrl),
                Map.entry("cancel_url", cancelUrl)
        );
        HttpRequest request = HttpRequest.newBuilder(URI.create(apiBase + "/v1/checkout/sessions"))
                .timeout(REQUEST_TIMEOUT)
                .header("Authorization", "Bearer " + secretKey)
                .header("Idempotency-Key", idempotencyKey)
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString(form(fields)))
                .build();
        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode body = json.readTree(response.body());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new BillingApiException(
                        502, "STRIPE_CHECKOUT_REJECTED", "The payment provider rejected checkout.", true);
            }
            String id = requiredText(body, "id");
            String url = requiredText(body, "url");
            long expiresAt = body.path("expires_at").asLong(0);
            if (!id.startsWith("cs_") || !url.startsWith("https://") || expiresAt <= clock.instant().getEpochSecond()) {
                throw new BillingApiException(
                        502, "STRIPE_CHECKOUT_RESPONSE_INVALID", "The payment provider response is invalid.", true);
            }
            return new CheckoutSession(id, url, Instant.ofEpochSecond(expiresAt));
        } catch (IOException error) {
            throw new BillingApiException(
                    502, "STRIPE_CHECKOUT_UNAVAILABLE", "The payment provider is unavailable.", true, error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new BillingApiException(
                    503, "STRIPE_CHECKOUT_INTERRUPTED", "Checkout was interrupted.", true, error);
        }
    }

    public void scheduleCancellation(String providerSubscriptionRef, String idempotencyKey) {
        if (!checkoutConfigured()) {
            throw new BillingApiException(503, "STRIPE_CHECKOUT_NOT_CONFIGURED",
                    "Payment checkout is not configured.", true);
        }
        if (providerSubscriptionRef == null || !providerSubscriptionRef.startsWith("sub_")) {
            throw new BillingApiException(
                    409, "STRIPE_SUBSCRIPTION_BINDING_INVALID",
                    "The subscription is not bound to the payment provider.", false);
        }
        HttpRequest request = HttpRequest.newBuilder(
                        URI.create(apiBase + "/v1/subscriptions/" + encode(providerSubscriptionRef)))
                .timeout(REQUEST_TIMEOUT)
                .header("Authorization", "Bearer " + secretKey)
                .header("Idempotency-Key", idempotencyKey)
                .header("Content-Type", "application/x-www-form-urlencoded")
                .POST(HttpRequest.BodyPublishers.ofString("cancel_at_period_end=true"))
                .build();
        try {
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode body = json.readTree(response.body());
            if (response.statusCode() < 200 || response.statusCode() >= 300
                    || !providerSubscriptionRef.equals(body.path("id").asText())
                    || !body.path("cancel_at_period_end").asBoolean(false)) {
                throw new BillingApiException(
                        502, "STRIPE_CANCELLATION_NOT_CONFIRMED",
                        "The payment provider did not confirm cancellation.", true);
            }
        } catch (IOException error) {
            throw new BillingApiException(
                    502, "STRIPE_CANCELLATION_UNAVAILABLE",
                    "The payment provider is unavailable.", true, error);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new BillingApiException(
                    503, "STRIPE_CANCELLATION_INTERRUPTED", "Cancellation was interrupted.", true, error);
        }
    }

    public VerifiedEvent verifyAndNormalize(String payload, String signatureHeader) {
        if (!webhookConfigured()) {
            throw new BillingApiException(
                    503, "STRIPE_WEBHOOK_NOT_CONFIGURED", "Payment webhook verification is not configured.", true);
        }
        Signature signature = parseSignature(signatureHeader);
        long age = Math.abs(clock.instant().getEpochSecond() - signature.timestamp());
        if (age > SIGNATURE_TOLERANCE.toSeconds()) {
            throw new BillingApiException(
                    400, "STRIPE_WEBHOOK_TIMESTAMP_INVALID", "Payment webhook timestamp is outside tolerance.", false);
        }
        byte[] expected = hmac(webhookSecret, signature.timestamp() + "." + payload);
        boolean verified = signature.v1().stream().map(StripeCheckoutGateway::hex)
                .anyMatch(candidate -> candidate != null && MessageDigest.isEqual(expected, candidate));
        if (!verified) {
            throw new BillingApiException(
                    401, "STRIPE_WEBHOOK_SIGNATURE_INVALID", "Payment webhook signature is invalid.", false);
        }
        try {
            JsonNode root = json.readTree(payload);
            JsonNode object = root.path("data").path("object");
            String eventId = requiredText(root, "id");
            String eventType = requiredText(root, "type");
            String objectRef = requiredText(object, "id");
            JsonNode metadata = metadataFor(eventType, object);
            String organizationId = requiredText(metadata, "organization_id");
            String actorId = requiredText(metadata, "actor_id");
            String planId = requiredText(metadata, "plan_id");
            if (!PricingPlanCatalog.CATALOG_VERSION.equals(requiredText(metadata, "catalog_version"))) {
                throw new BillingApiException(
                        409, "STRIPE_CATALOG_VERSION_MISMATCH", "Payment event catalog version is not current.", false);
            }
            String customer = reference(object.path("customer"));
            String subscription = subscriptionReference(object);
            String invoice = eventType.startsWith("invoice.") ? objectRef : reference(object.path("invoice"));
            long created = root.path("created").asLong(0);
            if (created <= 0) {
                throw new BillingApiException(
                        400, "STRIPE_WEBHOOK_CREATED_INVALID", "Payment webhook creation time is invalid.", false);
            }
            JsonNode period = firstPeriod(object);
            Instant periodStart = epoch(period.path("start").asLong(0));
            Instant periodEnd = epoch(period.path("end").asLong(0));
            String currency = object.path("currency").asText("").toUpperCase();
            long amount = object.path("amount_paid").asLong(object.path("amount_total").asLong(0));
            return new VerifiedEvent(
                    eventId, eventType, objectRef, organizationId, actorId, planId,
                    emptyToNull(customer), emptyToNull(subscription), emptyToNull(invoice),
                    amount, emptyToNull(currency), Instant.ofEpochSecond(created),
                    periodStart, periodEnd, sha256(payload)
            );
        } catch (BillingApiException error) {
            throw error;
        } catch (IOException error) {
            throw new BillingApiException(
                    400, "STRIPE_WEBHOOK_PAYLOAD_INVALID", "Payment webhook payload is invalid.", false, error);
        }
    }

    private static JsonNode metadataFor(String eventType, JsonNode object) {
        if ("checkout.session.completed".equals(eventType)) return object.path("metadata");
        JsonNode current = object.path("parent").path("subscription_details").path("metadata");
        if (!current.isObject()) current = object.path("subscription_details").path("metadata");
        if (!current.isObject()) current = object.path("metadata");
        return current;
    }

    private static String subscriptionReference(JsonNode object) {
        String direct = reference(object.path("subscription"));
        if (notBlank(direct)) return direct;
        String nested = reference(object.path("parent").path("subscription_details").path("subscription"));
        if (notBlank(nested)) return nested;
        return reference(object.path("subscription_details").path("subscription"));
    }

    private static JsonNode firstPeriod(JsonNode object) {
        JsonNode lines = object.path("lines").path("data");
        if (lines.isArray() && !lines.isEmpty()) return lines.get(0).path("period");
        return object.path("period");
    }

    private static Instant epoch(long value) {
        return value <= 0 ? null : Instant.ofEpochSecond(value);
    }

    private static String reference(JsonNode value) {
        if (value.isTextual()) return value.asText();
        if (value.isObject()) return value.path("id").asText("");
        return "";
    }

    private static String requiredText(JsonNode node, String field) {
        String value = node.path(field).asText("");
        if (value.isBlank()) {
            throw new BillingApiException(
                    400, "STRIPE_WEBHOOK_FIELD_MISSING", "Payment webhook is missing a required field.", false);
        }
        return value;
    }

    private static Signature parseSignature(String header) {
        if (!notBlank(header)) {
            throw new BillingApiException(
                    401, "STRIPE_WEBHOOK_SIGNATURE_REQUIRED", "Payment webhook signature is required.", false);
        }
        long timestamp = 0;
        List<String> v1 = new ArrayList<>();
        for (String part : header.split(",")) {
            String[] pair = part.trim().split("=", 2);
            if (pair.length != 2) continue;
            if ("t".equals(pair[0])) {
                try {
                    timestamp = Long.parseLong(pair[1]);
                } catch (NumberFormatException ignored) {
                    timestamp = 0;
                }
            } else if ("v1".equals(pair[0])) {
                v1.add(pair[1]);
            }
        }
        if (timestamp <= 0 || v1.isEmpty()) {
            throw new BillingApiException(
                    401, "STRIPE_WEBHOOK_SIGNATURE_INVALID", "Payment webhook signature is invalid.", false);
        }
        return new Signature(timestamp, List.copyOf(v1));
    }

    private static byte[] hmac(String key, String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(payload.getBytes(StandardCharsets.UTF_8));
        } catch (Exception error) {
            throw new IllegalStateException("Unable to verify payment webhook.", error);
        }
    }

    private static byte[] hex(String value) {
        try {
            return HexFormat.of().parseHex(value);
        } catch (IllegalArgumentException error) {
            return null;
        }
    }

    private static String form(Map<String, String> values) {
        return values.entrySet().stream()
                .map(entry -> encode(entry.getKey()) + "=" + encode(entry.getValue()))
                .sorted()
                .reduce((left, right) -> left + "&" + right)
                .orElse("");
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private static boolean validReturnUrl(String value) {
        if (!notBlank(value)) return false;
        try {
            URI uri = URI.create(value);
            return "https".equalsIgnoreCase(uri.getScheme()) && notBlank(uri.getHost());
        } catch (IllegalArgumentException error) {
            return false;
        }
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static boolean notBlank(String value) {
        return value != null && !value.isBlank();
    }

    private static String emptyToNull(String value) {
        return notBlank(value) ? value : null;
    }

    private record Signature(long timestamp, List<String> v1) {}
}
