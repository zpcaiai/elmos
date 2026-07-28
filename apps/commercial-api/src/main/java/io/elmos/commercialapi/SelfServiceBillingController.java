package io.elmos.commercialapi;

import io.elmos.commercial.PricingPlanCatalog;
import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.ProviderEvent;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@Validated
@RequestMapping("/commercial/v1/billing")
@ConditionalOnExpression("'${ELMOS_COMMERCIAL_DATABASE_URL:}' != ''")
public class SelfServiceBillingController {
    private static final String IDEMPOTENCY = "Idempotency-Key";
    private final SelfServiceBillingPort billing;
    private final StripeCheckoutGateway stripe;
    private final BillingMetrics metrics;
    private final boolean liveEnabled;
    private final boolean emailAlertsEnabled;
    private final String trialIdentityPepper;

    public SelfServiceBillingController(
            SelfServiceBillingPort billing,
            StripeCheckoutGateway stripe,
            BillingMetrics metrics,
            @Value("${elmos.billing.live-enabled:false}") boolean liveEnabled,
            @Value("${elmos.billing.email-alerts-enabled:false}") boolean emailAlertsEnabled,
            @Value("${ELMOS_TRIAL_IDENTITY_PEPPER:}") String trialIdentityPepper
    ) {
        this.billing = billing;
        this.stripe = stripe;
        this.metrics = metrics;
        this.liveEnabled = liveEnabled;
        this.emailAlertsEnabled = emailAlertsEnabled;
        this.trialIdentityPepper = trialIdentityPepper;
    }

    public record ReserveRequest(
            @NotBlank String subscriptionId,
            @Pattern(regexp = "repository-discovery|migration-or-translation-plan|verified-generation-or-migration|isolated-runner-minute|evidence-pack-verification|model-inference") String operationKey,
            @NotNull @PositiveOrZero BigDecimal requestedTokens,
            @NotNull @PositiveOrZero BigDecimal requestedCredits,
            @Min(30) @Max(3600) int expiresInSeconds
    ) {}

    public record SettleRequest(
            @NotBlank String reservationId,
            @NotNull @PositiveOrZero BigDecimal actualTokens,
            @NotNull @PositiveOrZero BigDecimal actualCredits,
            @Pattern(regexp = "INPUT|OUTPUT|CACHE_READ|CACHE_WRITE") String tokenClass,
            String provider,
            String providerReceiptRef,
            @Pattern(regexp = "[A-Z]{3}") String providerCostCurrency,
            @PositiveOrZero BigDecimal providerCostMinor,
            @NotNull Instant occurredAt
    ) {}

    public record ReleaseRequest(@NotBlank String reservationId, @NotBlank String reasonCode) {}

    public record CorrectionRequest(
            @NotBlank String originalLedgerEntryId,
            @NotNull @Positive BigDecimal quantity,
            @NotBlank String reasonCode
    ) {}

    public record AlertPreferenceRequest(
            @Pattern(regexp = "ACTOR|ORGANIZATION") String scope,
            @NotNull List<Integer> thresholdBps,
            boolean emailEnabled,
            boolean inAppEnabled,
            @PositiveOrZero long expectedVersion
    ) {}

    public record CheckoutRequest(
            @Pattern(regexp = "elmos-pro-monthly|elmos-pro-annual") String planId
    ) {}

    public record CustomerSubscription(
            String planId,
            String status,
            Instant currentPeriodEnd,
            boolean cancelAtPeriodEnd,
            boolean canCancel
    ) {}

    public record ReconciliationResolutionRequest(
            @NotBlank String reconciliationCaseId,
            @Pattern(regexp = "RESOLVED|REJECTED") String resolutionStatus,
            @Pattern(regexp = "[A-Za-z0-9][A-Za-z0-9._:/-]{7,254}") String resolutionRef
    ) {}

    @GetMapping("/usage/current")
    Object current(@AuthenticationPrincipal Jwt jwt) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:read");
        return billing.currentUsage(principal.organizationId(), principal.actorId());
    }

    @GetMapping("/usage/history")
    Object history(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam Instant from,
            @RequestParam Instant to,
            @RequestParam(defaultValue = "DAY") String bucket
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:read");
        return Map.of(
                "schemaVersion", "1.0.0",
                "from", from,
                "to", to,
                "bucket", bucket.toUpperCase(),
                "items", billing.usageHistory(
                        principal.organizationId(), principal.actorId(), from, to, bucket)
        );
    }

    @GetMapping(value = "/usage/export", produces = "text/csv;charset=UTF-8")
    ResponseEntity<String> export(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam Instant from,
            @RequestParam Instant to,
            @RequestParam(defaultValue = "DAY") String bucket
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:export");
        var points = billing.usageHistory(
                principal.organizationId(), principal.actorId(), from, to, bucket);
        StringBuilder csv = new StringBuilder(
                "\uFEFFbucket_starts_at,meter_id,token_class,actor_id,provider,debited,credited,net\n");
        for (var point : points) {
            csv.append(csv(point.bucketStartsAt().toString())).append(',')
                    .append(csv(point.meterId())).append(',')
                    .append(csv(point.tokenClass())).append(',')
                    .append(csv(point.actorId())).append(',')
                    .append(csv(point.provider())).append(',')
                    .append(point.debited().toPlainString()).append(',')
                    .append(point.credited().toPlainString()).append(',')
                    .append(point.net().toPlainString()).append('\n');
        }
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"elmos-usage.csv\"")
                .contentType(MediaType.parseMediaType("text/csv;charset=UTF-8"))
                .body(csv.toString());
    }

    @PostMapping("/usage/reservations")
    Object reserve(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody ReserveRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:meter:write");
        if (request.requestedTokens().signum() == 0 && request.requestedCredits().signum() == 0) {
            throw new BillingApiException(
                    400, "USAGE_RESERVATION_EMPTY", "A reservation must request usage.", false);
        }
        var reservation = billing.reserve(
                principal.organizationId(),
                principal.actorId(),
                request.subscriptionId(),
                "usage-res-" + UUID.randomUUID(),
                exactIdempotencyKey(idempotencyKey),
                request.operationKey(),
                request.requestedTokens(),
                request.requestedCredits(),
                Instant.now().plusSeconds(request.expiresInSeconds())
        );
        metrics.reservation(reservation.decision());
        return reservation;
    }

    @PostMapping("/usage/settlements")
    Object settle(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody SettleRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:meter:write");
        if (request.actualTokens().signum() == 0 && request.actualCredits().signum() == 0) {
            throw new BillingApiException(
                    400, "USAGE_SETTLEMENT_EMPTY", "A settlement must contain actual usage.", false);
        }
        return billing.settle(
                principal.organizationId(),
                principal.actorId(),
                request.reservationId(),
                "usage-event-" + sha256(exactIdempotencyKey(idempotencyKey)).substring(0, 48),
                request.actualTokens(),
                request.actualCredits(),
                request.tokenClass(),
                request.provider(),
                request.providerReceiptRef(),
                request.providerCostCurrency(),
                request.providerCostMinor(),
                request.occurredAt()
        );
    }

    @PostMapping("/usage/releases")
    Map<String, Object> release(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody ReleaseRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:meter:write");
        billing.release(
                principal.organizationId(), principal.actorId(),
                request.reservationId(), request.reasonCode());
        return Map.of("status", "RELEASED");
    }

    @PostMapping("/usage/corrections")
    Map<String, Object> correct(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody CorrectionRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:admin");
        String exactKey = exactIdempotencyKey(idempotencyKey);
        billing.correct(
                principal.organizationId(),
                principal.actorId(),
                "usage-correction-" + sha256(exactKey).substring(0, 48),
                request.originalLedgerEntryId(),
                request.quantity(),
                request.reasonCode(),
                exactKey
        );
        return Map.of("status", "CORRECTED");
    }

    @GetMapping("/usage/alerts")
    Object alertPreference(@AuthenticationPrincipal Jwt jwt) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:read");
        return billing.alertPreference(principal.organizationId(), principal.actorId());
    }

    @GetMapping("/usage/alerts/events")
    Object usageAlerts(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "30") @Min(1) @Max(366) int days
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:read");
        return Map.of(
                "schemaVersion", "1.0.0",
                "items", billing.usageAlerts(
                        principal.organizationId(), principal.actorId(),
                        Instant.now().minus(days, ChronoUnit.DAYS))
        );
    }

    @PutMapping("/usage/alerts")
    Object saveAlertPreference(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody AlertPreferenceRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:usage:write");
        if ("ORGANIZATION".equals(request.scope())) {
            principal.requireScope("commercial:usage:admin");
        }
        if (request.emailEnabled() && !emailAlertsEnabled) {
            throw new BillingApiException(
                    503, "USAGE_EMAIL_ALERTS_NOT_CONFIGURED",
                    "Email usage alerts are not configured.", false);
        }
        return billing.saveAlertPreference(
                principal.organizationId(), principal.actorId(), request.scope(),
                request.thresholdBps(), request.emailEnabled(), request.inAppEnabled(),
                request.expectedVersion());
    }

    @PostMapping("/trial")
    Object trial(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:write");
        if (trialIdentityPepper.length() < 32) {
            throw new BillingApiException(
                    503, "TRIAL_IDENTITY_PROTECTION_NOT_CONFIGURED",
                    "Trial identity protection is not configured.", false);
        }
        String verifiedIdentity = verifiedIdentity(jwt);
        String identityHash = hmacSha256(
                trialIdentityPepper,
                jwt.getIssuer() + "\0" + verifiedIdentity.toLowerCase());
        return billing.grantTrial(
                principal.organizationId(), principal.actorId(), identityHash,
                exactIdempotencyKey(idempotencyKey));
    }

    @PostMapping("/checkout")
    Object checkout(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody CheckoutRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:write");
        if (!liveEnabled) {
            throw new BillingApiException(
                    503, "LIVE_BILLING_DISABLED", "Live billing is disabled.", false);
        }
        try {
            PricingPlanCatalog.requireOrderable();
        } catch (IllegalStateException error) {
            throw new BillingApiException(
                    503, "PRICING_CATALOG_NOT_ORDERABLE",
                    "The pricing catalog has not passed its publication gates.", false, error);
        }
        if (!stripe.checkoutConfigured()) {
            throw new BillingApiException(
                    503, "STRIPE_CHECKOUT_NOT_CONFIGURED",
                    "Payment checkout is not configured.", false);
        }
        String exactKey = exactIdempotencyKey(idempotencyKey);
        String requestHash = sha256(String.join("\0",
                principal.organizationId(), principal.actorId(), request.planId(),
                PricingPlanCatalog.CATALOG_VERSION));
        billing.prepareCheckout(
                principal.organizationId(), principal.actorId(),
                "checkout-" + UUID.randomUUID(), request.planId(),
                Instant.now().plus(30, ChronoUnit.MINUTES), exactKey, requestHash);
        StripeCheckoutGateway.CheckoutSession provider;
        try {
            provider = stripe.createSubscriptionSession(
                    principal.organizationId(), principal.actorId(), request.planId(), exactKey);
        } catch (BillingApiException error) {
            metrics.checkout("provider_error");
            if ("STRIPE_CHECKOUT_REJECTED".equals(error.code())) {
                billing.markCheckoutFailed(
                        principal.organizationId(), principal.actorId(), exactKey, error.code());
            } else {
                billing.markCheckoutReconciliationRequired(
                        principal.organizationId(), principal.actorId(), exactKey, error.code());
            }
            throw error;
        }
        metrics.checkout("created");
        return billing.completeCheckout(
                principal.organizationId(), principal.actorId(), exactKey,
                provider.id(), provider.url(), provider.expiresAt());
    }

    @GetMapping("/subscriptions/current")
    CustomerSubscription currentSubscription(@AuthenticationPrincipal Jwt jwt) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:write");
        var subscription = billing.currentSubscription(
                principal.organizationId(), principal.actorId());
        return new CustomerSubscription(
                subscription.planId(),
                subscription.status(),
                subscription.currentPeriodEnd(),
                subscription.cancelAtPeriodEnd(),
                "STRIPE_CHECKOUT".equals(subscription.provider())
                        && !subscription.cancelAtPeriodEnd()
        );
    }

    @PostMapping("/subscriptions/cancel")
    Map<String, Object> cancel(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:write");
        var subscription = billing.currentSubscription(
                principal.organizationId(), principal.actorId());
        if (!"STRIPE_CHECKOUT".equals(subscription.provider())) {
            throw new BillingApiException(
                    409, "SUBSCRIPTION_PROVIDER_UNSUPPORTED",
                    "The subscription cannot be changed through Stripe.", false);
        }
        stripe.scheduleCancellation(
                subscription.providerSubscriptionRef(), exactIdempotencyKey(idempotencyKey));
        billing.scheduleCancellation(
                principal.organizationId(), principal.actorId(), subscription.subscriptionId());
        return Map.of(
                "status", "CANCEL_SCHEDULED",
                "effectiveAt", subscription.currentPeriodEnd()
        );
    }

    @GetMapping("/reconciliation")
    Object reconciliationCases(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "OPEN") String status,
            @RequestParam(defaultValue = "100") @Min(1) @Max(200) int limit
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:admin");
        return Map.of(
                "schemaVersion", "1.0.0",
                "items", billing.reconciliationCases(
                        principal.organizationId(), principal.actorId(), status, limit)
        );
    }

    @PostMapping("/reconciliation/resolve")
    Map<String, Object> resolveReconciliationCase(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody ReconciliationResolutionRequest request
    ) {
        CommercialPrincipal principal = principal(jwt, "commercial:billing:admin");
        billing.resolveReconciliationCase(
                principal.organizationId(), principal.actorId(),
                request.reconciliationCaseId(), request.resolutionStatus(),
                request.resolutionRef(), exactIdempotencyKey(idempotencyKey));
        return Map.of("status", request.resolutionStatus());
    }

    @PostMapping(
            value = "/webhooks/stripe",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    Map<String, Object> stripeWebhook(
            @RequestHeader("Stripe-Signature") String signature,
            @RequestBody String payload
    ) {
        var verified = stripe.verifyAndNormalize(payload, signature);
        if (!PricingPlanCatalog.requirePlan(verified.planId()).planId().equals(verified.planId())) {
            throw new BillingApiException(
                    409, "STRIPE_PLAN_INVALID", "Payment event plan is invalid.", false);
        }
        String processingStatus = verified.currency() == null
                || "CNY".equals(verified.currency()) ? "APPLIED" : "RECONCILIATION_REQUIRED";
        String providerSubscription = verified.subscriptionRef();
        String localSubscriptionId = providerSubscription == null ? null
                : "sub-stripe-" + sha256(providerSubscription).substring(0, 48);
        String quotaAllocationId = verified.periodStart() == null || providerSubscription == null
                ? null : "quota-stripe-" + sha256(
                        providerSubscription + "\0" + verified.periodStart()).substring(0, 48);
        ProviderEvent event = new ProviderEvent(
                verified.eventId(),
                verified.eventType(),
                verified.objectRef(),
                verified.subscriptionRef(),
                verified.customerRef(),
                verified.invoiceRef(),
                BigDecimal.valueOf(verified.amountMinor()),
                verified.currency(),
                verified.eventCreatedAt(),
                verified.payloadSha256(),
                processingStatus,
                verified.eventId()
        );
        boolean applied = billing.applyProviderEvent(
                verified.organizationId(), verified.actorId(), event, verified.planId(),
                localSubscriptionId, quotaAllocationId, verified.periodStart(), verified.periodEnd());
        metrics.webhook(
                verified.eventType(),
                !applied ? "duplicate"
                        : "APPLIED".equals(processingStatus) ? "accepted" : "reconciliation"
        );
        return Map.of("received", true, "duplicate", !applied);
    }

    private static CommercialPrincipal principal(Jwt jwt, String scope) {
        CommercialPrincipal principal = CommercialPrincipal.from(jwt);
        principal.requireScope(scope);
        return principal;
    }

    private static String verifiedIdentity(Jwt jwt) {
        if (Boolean.TRUE.equals(jwt.getClaim("email_verified"))) {
            String email = jwt.getClaimAsString("email");
            if (email != null && !email.isBlank()) return "email:" + email;
        }
        if (Boolean.TRUE.equals(jwt.getClaim("phone_number_verified"))) {
            String phone = jwt.getClaimAsString("phone_number");
            if (phone != null && !phone.isBlank()) return "phone:" + phone;
        }
        throw new BillingApiException(
                403, "TRIAL_VERIFIED_IDENTITY_REQUIRED",
                "A verified email address or phone number is required for a trial.", false);
    }

    private static String exactIdempotencyKey(String value) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{7,159}")) {
            throw new BillingApiException(
                    400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key is invalid.", false);
        }
        return value;
    }

    private static String csv(String value) {
        if (value == null) return "";
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static String hmacSha256(String secret, String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
