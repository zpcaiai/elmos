package io.elmos.commercialapi;

import io.elmos.commercial.PricingPlanCatalog;
import io.elmos.commercial.SelfServiceBillingPort;
import io.elmos.commercial.SelfServiceBillingPort.ProviderEvent;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;

import org.springframework.security.oauth2.jwt.Jwt;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 结账端点的通道分流自检。
 *
 * <h2>为什么能跑起来</h2>
 *
 * <p>{@code checkout()} 的第二道门是 {@code PricingPlanCatalog.requireOrderable()}，
 * 真实目录是 {@code DRAFT}，一路都走不到收单逻辑。
 * 因此本测试用<b>放在 classpath 更前面的一份 PUBLISHED 目录</b>把这道门打开——
 * {@code catalogVersion} 保持不变（不变它加载时就会被拒），
 * 只把四个状态位改成已配置。
 *
 * <p>这样测的是<b>真正的入口方法</b>，包括 {@code requireOrderable()} 本身，
 * 而不是绕过它去直接调用私有方法。
 *
 * <p>配套的 {@link #main} 还会用<b>真实目录</b>跑一次（另一个 JVM，见 run 脚本），
 * 断言 DRAFT 状态下依然一步也走不动——否则"打开门"的做法就可能掩盖真实行为。
 */
public final class CheckoutRoutingSelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) {
        boolean catalogIsOrderable = isOrderable();

        if (!catalogIsOrderable) {
            // 真实目录（DRAFT）下的那一轮：只验"门是关着的"
            draftCatalogBlocksEveryChannel();
        } else {
            alipayReturnsRedirectOnly();
            wechatReturnsQrCodeOnly();
            amountComesFromCatalogNotClient();
            outTradeNoMatchesTheCheckoutSessionId();
            localPrepareFailureIsMarkedFailed();
            networkPrepareFailureGoesToReconciliation();
            unconfiguredChannelIsFiveOhThreeNotFiveHundred();
            stripeBranchIsUnchanged();
            liveDisabledStillBlocks();
        }

        System.out.println();
        System.out.println("目录状态：" + (catalogIsOrderable ? "PUBLISHED（测试用）" : "DRAFT（真实）")
                + " —— " + passed + " 通过，" + failed + " 失败");
        if (failed > 0) {
            System.exit(1);
        }
    }

    private static boolean isOrderable() {
        try {
            PricingPlanCatalog.requireOrderable();
            return true;
        } catch (IllegalStateException notOrderable) {
            return false;
        }
    }

    // =======================================================================

    /** 真实目录下：无论目录声明哪个通道，都不该走到收单。 */
    private static void draftCatalogBlocksEveryChannel() {
        for (String[] combination : new String[][] {
                {"ALIPAY_CHECKOUT", "CNY"}, {"WECHAT_PAY_NATIVE", "CNY"},
                {"STRIPE_CHECKOUT", "USD"}}) {
            FakeBilling billing = new FakeBilling();
            var controller = controller(billing,
                    new PaymentProviderRouter(combination[0], combination[1]));
            BillingApiException failure = expectFailure(controller, billing);
            check(combination[0] + "：DRAFT 目录 -> 503 PRICING_CATALOG_NOT_ORDERABLE",
                    failure != null && failure.httpStatus() == 503
                            && "PRICING_CATALOG_NOT_ORDERABLE".equals(failure.code()));
            check(combination[0] + "：DRAFT 目录 -> 一张订单都没建",
                    billing.prepared.isEmpty());
        }
    }

    // =======================================================================

    private static void alipayReturnsRedirectOnly() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.ALIPAY_CHECKOUT, false,
                new PaymentProviderRouter.CheckoutHandoff(PaymentProvider.ALIPAY_CHECKOUT,
                        "https://openapi.alipay.com/gateway.do?sign=x", null));
        var response = successfulCheckout(billing, "ALIPAY_CHECKOUT", gateway);

        check("支付宝：paymentProvider 回传正确",
                "ALIPAY_CHECKOUT".equals(response.paymentProvider()));
        check("支付宝：给的是跳转地址",
                "https://openapi.alipay.com/gateway.do?sign=x".equals(response.checkoutUrl()));
        check("支付宝：不给二维码（否则前端无法判定形态）", response.qrCodeUrl() == null);
        check("支付宝：走的是路由器而不是 Stripe", gateway.calls == 1);
        check("支付宝：订单被标记完成", billing.completed.size() == 1);
        check("支付宝：没有开对账案件", billing.reconciliation.isEmpty());
    }

    private static void wechatReturnsQrCodeOnly() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.WECHAT_PAY_NATIVE, true,
                new PaymentProviderRouter.CheckoutHandoff(PaymentProvider.WECHAT_PAY_NATIVE,
                        null, "weixin://wxpay/bizpayurl?pr=abcdefg"));
        var response = successfulCheckout(billing, "WECHAT_PAY_NATIVE", gateway);

        check("微信：paymentProvider 回传正确",
                "WECHAT_PAY_NATIVE".equals(response.paymentProvider()));
        check("微信：给的是二维码内容",
                "weixin://wxpay/bizpayurl?pr=abcdefg".equals(response.qrCodeUrl()));
        check("微信：不给跳转地址（weixin:// 拿去跳转在桌面浏览器上毫无反应）",
                response.checkoutUrl() == null);
    }

    /** 金额必须来自目录。客户端传什么都不影响——请求体里根本就只有 planId。 */
    private static void amountComesFromCatalogNotClient() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.ALIPAY_CHECKOUT, false,
                new PaymentProviderRouter.CheckoutHandoff(PaymentProvider.ALIPAY_CHECKOUT,
                        "https://openapi.alipay.com/gateway.do", null));
        successfulCheckout(billing, "ALIPAY_CHECKOUT", gateway);

        check("金额取自目录：月付 129.00 元 = 12900 分", gateway.amountFen == 12900);
        check("商品标题取自目录的套餐名",
                PricingPlanCatalog.requirePlan("elmos-pro-monthly")
                        .displayName().equals(gateway.subject));
    }

    /**
     * 这条最容易被忽略：传给网关的 {@code out_trade_no} 必须与写进
     * {@code payment_checkout_sessions} 的 {@code checkout_session_id} 是同一个值。
     * 不一致的话，付款成功回调回来会找不到订单，全部变成无主回调。
     */
    private static void outTradeNoMatchesTheCheckoutSessionId() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.ALIPAY_CHECKOUT, false,
                new PaymentProviderRouter.CheckoutHandoff(PaymentProvider.ALIPAY_CHECKOUT,
                        "https://openapi.alipay.com/gateway.do", null));
        var response = successfulCheckout(billing, "ALIPAY_CHECKOUT", gateway);

        check("传给网关的 out_trade_no = 落库的 checkout_session_id",
                billing.prepared.get(0).equals(gateway.outTradeNo));
        check("响应里的会话 ID 也是同一个",
                billing.prepared.get(0).equals(response.checkoutSessionId()));
        check("providerSessionRef 也用本地订单号（该列有唯一约束，不能为空）",
                billing.prepared.get(0).equals(billing.completedProviderRef));
    }

    /** 支付宝下单纯本地：失败可以确定"提供方那边什么都没发生"，直接判失败。 */
    private static void localPrepareFailureIsMarkedFailed() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.ALIPAY_CHECKOUT, false, null);
        gateway.explode = new IllegalStateException("支付宝下单签名失败");
        var controller = controller(billing, routerWith("ALIPAY_CHECKOUT", "CNY", gateway));
        BillingApiException failure = expectFailure(controller, billing);

        check("支付宝下单失败 -> 503 CHECKOUT_NOT_CONFIGURED",
                failure != null && failure.httpStatus() == 503
                        && "CHECKOUT_NOT_CONFIGURED".equals(failure.code()));
        check("支付宝下单失败 -> 订单标记 FAILED", billing.failed.size() == 1);
        check("支付宝下单失败 -> 不开对账案件（结果是确定的，没有挂账）",
                billing.reconciliation.isEmpty());
    }

    /** 微信下单发过网络请求：失败时结果未知，必须进对账而不是判失败。 */
    private static void networkPrepareFailureGoesToReconciliation() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.WECHAT_PAY_NATIVE, true, null);
        gateway.explode = new IllegalStateException("微信支付下单调用失败");
        var controller = controller(billing, routerWith("WECHAT_PAY_NATIVE", "CNY", gateway));
        BillingApiException failure = expectFailure(controller, billing);

        check("微信下单失败 -> 502 CHECKOUT_PROVIDER_UNAVAILABLE",
                failure != null && failure.httpStatus() == 502
                        && "CHECKOUT_PROVIDER_UNAVAILABLE".equals(failure.code()));
        check("微信下单失败 -> 可重试标记为 true", failure != null && failure.retryable());
        check("微信下单失败 -> 开对账案件（对面建没建单未知）",
                billing.reconciliation.size() == 1);
        check("微信下单失败 -> 不标记 FAILED（那等于单方面认定没建单）",
                billing.failed.isEmpty());
    }

    /** 目录切了通道但没配密钥：503 + 明确错误码，不是 500。 */
    private static void unconfiguredChannelIsFiveOhThreeNotFiveHundred() {
        FakeBilling billing = new FakeBilling();
        // 路由器里没注册任何下单网关
        var controller = controller(billing, new PaymentProviderRouter("ALIPAY_CHECKOUT", "CNY"));
        BillingApiException failure = expectFailure(controller, billing);

        check("未注册网关 -> 503 CHECKOUT_NOT_CONFIGURED",
                failure != null && failure.httpStatus() == 503
                        && "CHECKOUT_NOT_CONFIGURED".equals(failure.code()));
        check("未注册网关 -> 不建订单（不留下一堆永远付不了的挂单）",
                billing.prepared.isEmpty());
    }

    /**
     * Stripe 分支必须与改动前行为一致。
     *
     * <p>这里用一个没有配置的 {@code StripeCheckoutGateway}：
     * 原实现在这种情况下返回 503 {@code STRIPE_CHECKOUT_NOT_CONFIGURED}。
     * 能拿到这个码，就说明分流之后请求确实还是走到了 Stripe 分支，
     * 而且那一段没有被改坏。
     */
    private static void stripeBranchIsUnchanged() {
        FakeBilling billing = new FakeBilling();
        // 币种用 USD：CNY + Stripe 会被 assertCompatibleWith 直接拒绝（这是对的）
        var controller = controller(billing, new PaymentProviderRouter("STRIPE_CHECKOUT", "USD"));
        BillingApiException failure = expectFailure(controller, billing);

        check("Stripe 分支仍然可达，且未配置时仍是 503 STRIPE_CHECKOUT_NOT_CONFIGURED",
                failure != null && failure.httpStatus() == 503
                        && "STRIPE_CHECKOUT_NOT_CONFIGURED".equals(failure.code()));
    }

    /** live-enabled=false 时，任何通道都不该动。 */
    private static void liveDisabledStillBlocks() {
        FakeBilling billing = new FakeBilling();
        FakeGateway gateway = new FakeGateway(PaymentProvider.ALIPAY_CHECKOUT, false,
                new PaymentProviderRouter.CheckoutHandoff(PaymentProvider.ALIPAY_CHECKOUT,
                        "https://openapi.alipay.com/gateway.do", null));
        var controller = new SelfServiceBillingController(
                billing, unconfiguredStripe(), routerWith("ALIPAY_CHECKOUT", "CNY", gateway),
                new BillingMetrics(new io.micrometer.core.instrument.simple.SimpleMeterRegistry()),
                false, false, "0123456789abcdef0123456789abcdef");
        BillingApiException failure = expectFailure(controller, billing);

        check("live-enabled=false -> 503 LIVE_BILLING_DISABLED",
                failure != null && "LIVE_BILLING_DISABLED".equals(failure.code()));
        check("live-enabled=false -> 网关一次都没被调用", gateway.calls == 0);
    }

    // =======================================================================
    // 装配
    // =======================================================================

    private static SelfServiceBillingController.CheckoutHandoffResponse successfulCheckout(
            FakeBilling billing, String provider, FakeGateway gateway) {
        var controller = controller(billing, routerWith(provider, "CNY", gateway));
        Object result = controller.checkout(jwt(), "idem-0123456789abcdef",
                new SelfServiceBillingController.CheckoutRequest("elmos-pro-monthly"));
        return (SelfServiceBillingController.CheckoutHandoffResponse) result;
    }

    private static PaymentProviderRouter routerWith(String provider, String currency,
                                                    FakeGateway gateway) {
        return new PaymentProviderRouter(provider, currency).register(gateway);
    }

    private static SelfServiceBillingController controller(FakeBilling billing,
                                                           PaymentProviderRouter router) {
        return new SelfServiceBillingController(
                billing, unconfiguredStripe(), router,
                new BillingMetrics(new io.micrometer.core.instrument.simple.SimpleMeterRegistry()),
                true, false, "0123456789abcdef0123456789abcdef");
    }

    /** 一个没有任何配置的 Stripe 网关：{@code checkoutConfigured()} 恒为 false。 */
    private static StripeCheckoutGateway unconfiguredStripe() {
        return new StripeCheckoutGateway(
                new com.fasterxml.jackson.databind.ObjectMapper(),
                "", "", "", "", "", "", "https://api.stripe.com");
    }

    private static Jwt jwt() {
        return Jwt.withTokenValue("token")
                .header("alg", "none")
                .claim("sub", "actor-1")
                .claim("organization_id", "org-1")
                .claim("scope", "commercial:billing:write")
                .issuer("https://issuer.example.com")
                .build();
    }

    private static BillingApiException expectFailure(SelfServiceBillingController controller,
                                                     FakeBilling billing) {
        try {
            controller.checkout(jwt(), "idem-0123456789abcdef",
                    new SelfServiceBillingController.CheckoutRequest("elmos-pro-monthly"));
            return null;
        } catch (BillingApiException expected) {
            return expected;
        }
    }

    // =======================================================================

    /** 记录"被调用了什么"的下单网关替身。 */
    private static final class FakeGateway implements PaymentProviderRouter.CheckoutGateway {
        private final PaymentProvider provider;
        private final boolean contactsProvider;
        private final PaymentProviderRouter.CheckoutHandoff handoff;
        RuntimeException explode;
        int calls;
        String outTradeNo;
        long amountFen;
        String subject;

        FakeGateway(PaymentProvider provider, boolean contactsProvider,
                    PaymentProviderRouter.CheckoutHandoff handoff) {
            this.provider = provider;
            this.contactsProvider = contactsProvider;
            this.handoff = handoff;
        }

        @Override
        public PaymentProvider provider() {
            return provider;
        }

        @Override
        public PaymentProviderRouter.CheckoutHandoff prepare(String outTradeNo, long amountFen,
                                                             String subject) {
            this.calls += 1;
            this.outTradeNo = outTradeNo;
            this.amountFen = amountFen;
            this.subject = subject;
            if (explode != null) {
                throw explode;
            }
            return handoff;
        }

        @Override
        public boolean contactsProviderDuringPrepare() {
            return contactsProvider;
        }
    }

    /** 只实现结账相关的四个方法，其余抛异常——被意外调用时应当暴露而不是静默。 */
    private static class FakeBilling implements SelfServiceBillingPort {
        final List<String> prepared = new ArrayList<>();
        final List<String> completed = new ArrayList<>();
        final List<String> failed = new ArrayList<>();
        final List<String> reconciliation = new ArrayList<>();
        String completedProviderRef;

        @Override
        public CheckoutRecord prepareCheckout(String organizationId, String actorId,
                                              String checkoutSessionId, String planId,
                                              Instant expiresAt, String idempotencyKey,
                                              String requestHash) {
            prepared.add(checkoutSessionId);
            return new CheckoutRecord(checkoutSessionId, planId,
                    PricingPlanCatalog.CATALOG_VERSION, "CNY", new BigDecimal("12900"),
                    null, null, "CREATING", expiresAt);
        }

        @Override
        public CheckoutRecord completeCheckout(String organizationId, String actorId,
                                               String idempotencyKey, String providerSessionRef,
                                               String checkoutUrl, Instant expiresAt) {
            completed.add(idempotencyKey);
            completedProviderRef = providerSessionRef;
            return new CheckoutRecord(prepared.get(prepared.size() - 1), "elmos-pro-monthly",
                    PricingPlanCatalog.CATALOG_VERSION, "CNY", new BigDecimal("12900"),
                    providerSessionRef, checkoutUrl, "OPEN", expiresAt);
        }

        @Override
        public void markCheckoutFailed(String organizationId, String actorId,
                                       String idempotencyKey, String reasonCode) {
            failed.add(reasonCode);
        }

        @Override
        public void markCheckoutReconciliationRequired(String organizationId, String actorId,
                                                       String idempotencyKey, String reasonCode) {
            reconciliation.add(reasonCode);
        }

        // 以下方法结账路径不该碰。被调用就抛异常——静默返回 null 会让一个
        // "多调了一次不该调的东西"的 bug 顺利通过测试。
        private static UnsupportedOperationException unexpected(String method) {
            return new UnsupportedOperationException("结账路径不应调用 " + method);
        }

        @Override public UsageSnapshot currentUsage(String a, String b) { throw unexpected("currentUsage"); }
        @Override public List<UsageHistoryPoint> usageHistory(String a, String b, Instant c, Instant d, String e) { throw unexpected("usageHistory"); }
        @Override public UsageReservation reserve(String a, String b, String c, String d, String e, String f, BigDecimal g, BigDecimal h, Instant i) { throw unexpected("reserve"); }
        @Override public UsageSettlement settle(String a, String b, String c, String d, BigDecimal e, BigDecimal f, String g, String h, String i, String j, BigDecimal k, Instant l) { throw unexpected("settle"); }
        @Override public void release(String a, String b, String c, String d) { throw unexpected("release"); }
        @Override public void correct(String a, String b, String c, String d, BigDecimal e, String f, String g) { throw unexpected("correct"); }
        @Override public TrialGrant grantTrial(String a, String b, String c, String d) { throw unexpected("grantTrial"); }
        @Override public AlertPreference alertPreference(String a, String b) { throw unexpected("alertPreference"); }
        @Override public List<UsageAlert> usageAlerts(String a, String b, Instant c) { throw unexpected("usageAlerts"); }
        @Override public AlertPreference saveAlertPreference(String a, String b, String c, List<Integer> d, boolean e, boolean f, long g) { throw unexpected("saveAlertPreference"); }
        @Override public boolean applyProviderEvent(String a, String b, ProviderEvent c, String d, String e, String f, Instant g, Instant h) { throw unexpected("applyProviderEvent"); }
        @Override public List<ReconciliationCase> reconciliationCases(String a, String b, String c, int d) { throw unexpected("reconciliationCases"); }
        @Override public void resolveReconciliationCase(String a, String b, String c, String d, String e, String f) { throw unexpected("resolveReconciliationCase"); }
        @Override public QuotaAdministrationView quotaForAdministration(String a) { throw unexpected("quotaForAdministration"); }
        @Override public QuotaAdministrationView adjustQuota(String a, String b, String c, BigDecimal d, BigDecimal e, long f, String g) { throw unexpected("adjustQuota"); }
        @Override public SubscriptionBinding currentSubscription(String a, String b) { throw unexpected("currentSubscription"); }
        @Override public void scheduleCancellation(String a, String b, String c) { throw unexpected("scheduleCancellation"); }
    }

    private static void check(String what, boolean condition) {
        if (condition) {
            passed++;
            System.out.println("  [PASS] " + what);
        } else {
            failed++;
            System.out.println("  [FAIL] " + what);
        }
    }
}
