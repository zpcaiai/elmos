package io.elmos.commercialapi;

import io.elmos.commercial.WalletPort;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
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
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/**
 * Prepaid wallet: balance, ledger and top-up.
 *
 * <p>Separate from {@link SelfServiceBillingController} because they are two
 * means of payment, not two views of one. A subscription grants an allowance
 * that resets; a wallet holds money that does not. Merging them would produce a
 * controller whose every method starts by asking which of the two it is in.
 *
 * <p>Registered under the same condition as the rest of billing, so either the
 * whole commercial surface is configured or none of it is.
 */
@RestController
@Validated
@RequestMapping("/commercial/v1/billing/wallet")
@ConditionalOnExpression("'${ELMOS_COMMERCIAL_DATABASE_URL:}' != ''")
public class WalletTopupController {

    private static final String IDEMPOTENCY = "Idempotency-Key";

    private final WalletPort wallet;
    private final PaymentProviderRouter paymentRouter;
    private final BillingMetrics metrics;
    private final boolean liveEnabled;

    public WalletTopupController(
            WalletPort wallet,
            PaymentProviderRouter paymentRouter,
            BillingMetrics metrics,
            @Value("${elmos.billing.live-enabled:false}") boolean liveEnabled
    ) {
        this.wallet = wallet;
        this.paymentRouter = paymentRouter;
        this.metrics = metrics;
        this.liveEnabled = liveEnabled;
    }

    /**
     * 充值请求。
     *
     * <p>金额由客户端提出——这与订阅结账不同，那里金额只能由服务端按套餐决定。
     * 但接受不等于信任：上下限和单日累计上限在 V73 的
     * {@code elmos_wallet_create_topup_order} 里强制，这里的 {@code @Min}/{@code @Max}
     * 只是把明显越界的请求挡在数据库之前，不是权威。
     */
    public record TopupRequest(
            @Min(1) @Max(100_000_000L) long amountMinor
    ) {}

    public record TopupHandoffResponse(
            String topupOrderId,
            String outTradeNo,
            String currency,
            BigDecimal amountMinor,
            String status,
            Instant expiresAt,
            String paymentProvider,
            String checkoutUrl,
            String qrCodeUrl
    ) {}

    public record WalletView(
            String currency,
            BigDecimal balanceMinor,
            BigDecimal reservedMinor,
            BigDecimal spendableMinor,
            String status,
            BigDecimal minTopupMinor,
            BigDecimal maxTopupMinor
    ) {}

    @GetMapping
    WalletView balance(@AuthenticationPrincipal Jwt jwt) {
        var principal = principal(jwt, "commercial:usage:read");
        WalletPort.WalletBalance balance = wallet.balance(principal.organizationId());
        WalletPort.TopupBounds bounds = wallet.topupBounds(principal.organizationId());
        return new WalletView(
                balance.currency(), balance.balanceMinor(), balance.reservedMinor(),
                balance.spendableMinor(), balance.status(),
                bounds.minAmountMinor(), bounds.maxAmountMinor());
    }

    @GetMapping("/ledger")
    List<WalletPort.LedgerEntry> ledger(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset
    ) {
        var principal = principal(jwt, "commercial:usage:read");
        return wallet.ledger(principal.organizationId(), limit, offset);
    }

    /**
     * 下单充值。
     *
     * <p>顺序是先建本地订单、再向提供方下单，不能反过来：先向提供方下单意味着
     * 存在一个时间窗，窗内用户已经能付款而我们没有任何本地记录，那笔钱回来时
     * 就是无主回调。
     *
     * <p>{@code outTradeNo} 由我们生成并传给提供方，回调时靠它反查
     * （见 {@code JdbcOrderPorts.orderLookup} 的充值分支）。
     */
    @PostMapping("/topup")
    TopupHandoffResponse topup(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader(IDEMPOTENCY) @NotBlank String idempotencyKey,
            @Valid @RequestBody TopupRequest request
    ) {
        var principal = principal(jwt, "commercial:billing:write");
        if (!liveEnabled) {
            throw new BillingApiException(
                    503, "LIVE_BILLING_DISABLED", "Live billing is disabled.", false);
        }

        PaymentProvider provider = paymentRouter.active();
        if (provider == PaymentProvider.STRIPE_CHECKOUT) {
            // 大陆主体 + CNY 的决定（D-01）下 Stripe 不收单。这里拒绝而不是回退，
            // 与订阅结账同一条理由：回退等于把钱收到另一个主体的账上。
            throw new BillingApiException(
                    503, "TOPUP_CHANNEL_NOT_SUPPORTED",
                    "Prepaid top-up requires a mainland China payment channel.", false);
        }

        BigDecimal amount = BigDecimal.valueOf(request.amountMinor());
        String topupOrderId = "topup-" + UUID.randomUUID();
        String outTradeNo = topupOrderId;

        String persistedOrderId;
        try {
            persistedOrderId = wallet.createTopupOrder(
                    topupOrderId, principal.organizationId(), principal.actorId(),
                    amount, providerName(provider), outTradeNo,
                    exactIdempotencyKey(idempotencyKey), 1800);
        } catch (WalletPort.WalletStateException refused) {
            metrics.checkout("wallet_order_refused");
            throw translate(refused);
        }

        // 幂等重放：拿回的是原来那张单，连同它原来的 out_trade_no。
        // 用新生成的号去向提供方下单会开出第二笔可付款的订单。
        WalletPort.TopupOrder order = wallet
                .findTopupOrder(principal.organizationId(), persistedOrderId)
                .orElseThrow(() -> new BillingApiException(
                        500, "TOPUP_ORDER_MISSING_AFTER_CREATE",
                        "The top-up order could not be read back.", true));

        PaymentProviderRouter.CheckoutHandoff handoff;
        try {
            handoff = paymentRouter.checkoutGateway().prepare(
                    order.outTradeNo(), order.amountMinor().longValueExact(),
                    "ELMOS 账户充值");
        } catch (RuntimeException failure) {
            metrics.checkout("provider_error");
            // 订单留在 CREATED，由过期机制收口。此处不标 FAILED：
            // 微信路径的 prepare 已经发过 HTTPS 请求，异常可能发生在收到响应
            // 之后，提供方那边到底建没建单我们并不知道，单方面认定"没建单"
            // 正是产生挂账的方式（见 CheckoutGateway#contactsProviderDuringPrepare）。
            throw new BillingApiException(
                    502, "TOPUP_PROVIDER_UNAVAILABLE",
                    "The payment channel could not open this top-up.", true, failure);
        }

        metrics.checkout("wallet_topup_opened");
        return new TopupHandoffResponse(
                order.topupOrderId(), order.outTradeNo(), order.currency(),
                order.amountMinor(), order.status(), order.expiresAt(),
                handoff.provider().name(), handoff.redirectUrl(), handoff.qrCodeUrl());
    }

    /** 供前端轮询：付款完成后由回调把状态推到 CREDITED。 */
    @GetMapping("/topup/{topupOrderId}")
    WalletPort.TopupOrder topupStatus(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable String topupOrderId
    ) {
        var principal = principal(jwt, "commercial:usage:read");
        return wallet.findTopupOrder(principal.organizationId(), topupOrderId)
                .orElseThrow(() -> new BillingApiException(
                        404, "TOPUP_ORDER_UNKNOWN", "No such top-up order.", false));
    }

    /**
     * 把数据库的拒绝码翻成 HTTP。
     *
     * <p>逐条映射而不是一律 400：余额不足是用户能自己解决的（402 引导充值），
     * 超出单日上限是策略限制（429 语义上更接近"稍后再来"），
     * 而钱包被冻结是运营动作，用户改不了参数就能绕过——三者混成一个状态码，
     * 前端就只能显示同一句话。
     */
    private static BillingApiException translate(WalletPort.WalletStateException refused) {
        return switch (refused.code()) {
            case "ELMOS_WALLET_TOPUP_BELOW_MINIMUM" -> new BillingApiException(
                    400, refused.code(), "Amount is below the minimum top-up.", false, refused);
            case "ELMOS_WALLET_TOPUP_ABOVE_MAXIMUM" -> new BillingApiException(
                    400, refused.code(), "Amount exceeds the maximum single top-up.", false, refused);
            case "ELMOS_WALLET_TOPUP_DAILY_LIMIT_EXCEEDED" -> new BillingApiException(
                    429, refused.code(), "Today's top-up limit is reached.", false, refused);
            case "ELMOS_WALLET_NOT_ACTIVE", "ELMOS_WALLET_CLOSED" -> new BillingApiException(
                    409, refused.code(), "This wallet cannot accept a top-up.", false, refused);
            case "ELMOS_WALLET_INSUFFICIENT_BALANCE" -> new BillingApiException(
                    402, refused.code(), "Insufficient wallet balance.", false, refused);
            default -> new BillingApiException(
                    400, refused.code(), "The wallet refused this request.", false, refused);
        };
    }

    private static String providerName(PaymentProvider provider) {
        return switch (provider) {
            case ALIPAY_CHECKOUT -> "ALIPAY";
            case WECHAT_PAY_NATIVE -> "WECHAT_PAY";
            case STRIPE_CHECKOUT -> "STRIPE";
        };
    }

    private static CommercialPrincipal principal(Jwt jwt, String scope) {
        CommercialPrincipal principal = CommercialPrincipal.from(jwt);
        principal.requireScope(scope);
        return principal;
    }

    private static String exactIdempotencyKey(String value) {
        String trimmed = value == null ? "" : value.trim();
        if (trimmed.length() < 8 || trimmed.length() > 160) {
            throw new BillingApiException(
                    400, "IDEMPOTENCY_KEY_INVALID",
                    "Idempotency-Key must be 8 to 160 characters.", false);
        }
        return trimmed;
    }
}
