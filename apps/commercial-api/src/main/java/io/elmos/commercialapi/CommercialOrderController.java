package io.elmos.commercialapi;

import io.elmos.commercial.CommercialOrderPort;
import io.elmos.commercial.PricingPlanCatalog;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Purchasable Credit packs, one-project orders, and generation funding. */
@RestController
@Validated
@RequestMapping("/commercial/v1/billing")
@ConditionalOnExpression("'${ELMOS_COMMERCIAL_DATABASE_URL:}' != ''")
public class CommercialOrderController {
    private static final String IDEMPOTENCY = "Idempotency-Key";
    private static final String ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}";

    public record CreditPackOrderRequest(@NotBlank String sku) {}
    public record ProjectGenerationOrderRequest(
            @NotBlank String sku,
            @Pattern(regexp = ID_PATTERN) String projectId) {}
    public record OrderHandoff(
            CommercialOrderPort.Order order, String paymentProvider,
            String checkoutUrl, String qrCodeUrl) {}
    public record GenerationReserveRequest(
            @Pattern(regexp = ID_PATTERN) String actorId,
            @Pattern(regexp = ID_PATTERN) String projectId,
            @Pattern(regexp = ID_PATTERN) String jobId,
            @NotNull @Positive BigDecimal requestedCredits,
            @Min(30) @Max(3600) int expiresInSeconds) {}
    public record GenerationSettleRequest(
            @Pattern(regexp = ID_PATTERN) String actorId,
            @NotBlank String reservationId,
            @NotNull @Min(0) BigDecimal actualCredits) {}
    public record GenerationReleaseRequest(
            @Pattern(regexp = ID_PATTERN) String actorId,
            @NotBlank String reservationId) {}

    private final CommercialOrderPort orders;
    private final PaymentProviderRouter router;
    private final boolean liveEnabled;

    public CommercialOrderController(
            CommercialOrderPort orders,
            PaymentProviderRouter router,
            @Value("${elmos.billing.live-enabled:false}") boolean liveEnabled) {
        this.orders = orders;
        this.router = router;
        this.liveEnabled = liveEnabled;
    }

    @PostMapping("/orders/credit-packs")
    OrderHandoff buyCredits(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody CreditPackOrderRequest request) {
        var product = PricingPlanCatalog.requireCreditPack(request.sku());
        return createOrder(jwt, idempotencyKey, product.sku(), null, product.displayName());
    }

    @PostMapping("/orders/project-generations")
    OrderHandoff buyProjectGeneration(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody ProjectGenerationOrderRequest request) {
        var product = PricingPlanCatalog.requireOneTimeProduct(request.sku());
        return createOrder(jwt, idempotencyKey, product.sku(), request.projectId(),
                product.displayName());
    }

    @GetMapping("/orders")
    List<CommercialOrderPort.Order> orderHistory(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "SELF") @Pattern(regexp = "SELF|ORGANIZATION") String scope,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        var principal = principal(jwt, "commercial:usage:read");
        boolean organization = organizationScope(principal, scope);
        return orders.orders(principal.organizationId(), principal.actorId(), limit, offset, organization);
    }

    @GetMapping("/orders/{orderId}")
    CommercialOrderPort.Order order(
            @AuthenticationPrincipal Jwt jwt, @PathVariable String orderId) {
        var principal = principal(jwt, "commercial:usage:read");
        var order = orders.findOrder(principal.organizationId(), orderId)
                .orElseThrow(() -> new BillingApiException(
                        404, "COMMERCIAL_ORDER_UNKNOWN", "No such order.", false));
        if (!order.actorId().equals(principal.actorId())
                && !principal.scopes().contains("commercial:usage:admin")) {
            throw new BillingApiException(403, "COMMERCIAL_ORDER_FORBIDDEN",
                    "The order belongs to another actor.", false);
        }
        return order;
    }

    @GetMapping("/credits")
    CommercialOrderPort.CreditBalance creditBalance(@AuthenticationPrincipal Jwt jwt) {
        var principal = principal(jwt, "commercial:usage:read");
        return orders.creditBalance(principal.organizationId());
    }

    @GetMapping("/credits/ledger")
    List<CommercialOrderPort.CreditLedgerEntry> creditLedger(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "SELF") @Pattern(regexp = "SELF|ORGANIZATION") String scope,
            @RequestParam(defaultValue = "50") @Min(1) @Max(200) int limit,
            @RequestParam(defaultValue = "0") @Min(0) int offset) {
        var principal = principal(jwt, "commercial:usage:read");
        boolean organization = organizationScope(principal, scope);
        return orders.creditLedger(
                principal.organizationId(), principal.actorId(), limit, offset, organization);
    }

    @PostMapping("/generation/reservations")
    CommercialOrderPort.GenerationReservation reserveGeneration(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody GenerationReserveRequest request) {
        var principal = principal(jwt, "commercial:meter:write");
        String billedActor = delegatedActor(principal, request.actorId());
        var result = orders.reserveGeneration(
                "credit-res-" + UUID.randomUUID(), principal.organizationId(), billedActor,
                request.projectId(), request.jobId(), request.requestedCredits(),
                exactIdempotencyKey(idempotencyKey), request.expiresInSeconds());
        if (!"RESERVED".equals(result.decision())) {
            throw new BillingApiException(402, result.decision(),
                    "No purchased Credit or matching one-time project entitlement is available.", false);
        }
        return result;
    }

    @PostMapping("/generation/settlements")
    Map<String, String> settleGeneration(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody GenerationSettleRequest request) {
        var principal = principal(jwt, "commercial:meter:write");
        String billedActor = delegatedActor(principal, request.actorId());
        return Map.of("status", orders.settleGeneration(
                principal.organizationId(), billedActor,
                request.reservationId(), request.actualCredits()));
    }

    @PostMapping("/generation/releases")
    Map<String, String> releaseGeneration(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody GenerationReleaseRequest request) {
        var principal = principal(jwt, "commercial:meter:write");
        String billedActor = delegatedActor(principal, request.actorId());
        return Map.of("status", orders.releaseGeneration(
                principal.organizationId(), billedActor, request.reservationId()));
    }

    private OrderHandoff createOrder(Jwt jwt, String idempotencyKey, String sku,
                                     String projectId, String subject) {
        var principal = principal(jwt, "commercial:billing:write");
        if (!liveEnabled) {
            throw new BillingApiException(503, "LIVE_BILLING_DISABLED",
                    "Live billing is disabled.", false);
        }
        try {
            PricingPlanCatalog.requireOrderable();
        } catch (IllegalStateException blocked) {
            throw new BillingApiException(503, "PRICING_CATALOG_NOT_ORDERABLE",
                    "The pricing catalog has not passed its publication gates.", false, blocked);
        }
        PaymentProvider provider = router.active();
        if (provider == PaymentProvider.STRIPE_CHECKOUT) {
            throw new BillingApiException(503, "COMMERCIAL_ORDER_CHANNEL_NOT_SUPPORTED",
                    "CNY product orders require a mainland China payment channel.", false);
        }
        PaymentProviderRouter.CheckoutGateway gateway;
        try {
            gateway = router.checkoutGateway();
        } catch (IllegalStateException missing) {
            throw new BillingApiException(503, "CHECKOUT_NOT_CONFIGURED",
                    "Payment checkout is not configured.", false, missing);
        }
        String exactKey = exactIdempotencyKey(idempotencyKey);
        String orderId = "order-" + UUID.randomUUID();
        String requestHash = sha256(String.join("\0", principal.organizationId(),
                principal.actorId(), sku, projectId == null ? "" : projectId,
                PricingPlanCatalog.CATALOG_VERSION));
        String persisted = orders.createOrder(
                orderId, principal.organizationId(), principal.actorId(), sku, projectId,
                provider.name(), orderId, exactKey, requestHash, 1800);
        var order = orders.findOrder(principal.organizationId(), persisted)
                .orElseThrow(() -> new BillingApiException(500,
                        "COMMERCIAL_ORDER_MISSING_AFTER_CREATE", "Order readback failed.", true));
        try {
            var handoff = gateway.prepare(
                    order.outTradeNo(), order.amountMinor().longValueExact(), subject);
            orders.markOrderAwaitingPayment(
                    principal.organizationId(), principal.actorId(), order.orderId());
            var ready = orders.findOrder(principal.organizationId(), order.orderId()).orElseThrow();
            return new OrderHandoff(
                    ready, provider.name(), handoff.redirectUrl(), handoff.qrCodeUrl());
        } catch (RuntimeException failure) {
            boolean unknown = gateway.contactsProviderDuringPrepare();
            try {
                orders.markOrderPreparationFailed(
                        principal.organizationId(), principal.actorId(), order.orderId(), unknown,
                        unknown ? "CHECKOUT_PREPARE_OUTCOME_UNKNOWN" : "CHECKOUT_PREPARE_FAILED");
            } catch (RuntimeException stateFailure) {
                failure.addSuppressed(stateFailure);
            }
            throw new BillingApiException(gateway.contactsProviderDuringPrepare() ? 502 : 503,
                    "COMMERCIAL_ORDER_PROVIDER_UNAVAILABLE",
                    "The payment channel could not open this order.",
                    gateway.contactsProviderDuringPrepare(), failure);
        }
    }

    private static boolean organizationScope(CommercialPrincipal principal, String scope) {
        if (!"ORGANIZATION".equals(scope)) return false;
        principal.requireScope("commercial:usage:admin");
        return true;
    }

    private static String delegatedActor(CommercialPrincipal principal, String requested) {
        if (requested == null || requested.equals(principal.actorId())) return principal.actorId();
        principal.requireScope("commercial:meter:delegate");
        return requested;
    }

    private static CommercialPrincipal principal(Jwt jwt, String scope) {
        var principal = CommercialPrincipal.from(jwt);
        principal.requireScope(scope);
        return principal;
    }

    private static String exactIdempotencyKey(String value) {
        String trimmed = value == null ? "" : value.trim();
        if (trimmed.length() < 8 || trimmed.length() > 160) {
            throw new BillingApiException(400, "IDEMPOTENCY_KEY_INVALID",
                    "Idempotency-Key must be 8 to 160 characters.", false);
        }
        return trimmed;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
