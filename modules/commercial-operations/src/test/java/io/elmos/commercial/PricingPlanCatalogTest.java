package io.elmos.commercial;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class PricingPlanCatalogTest {
    @Test
    void activePriceVersionIsImmutable() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals(PricingPlanCatalog.CATALOG_VERSION, catalog.catalogVersion());
        assertThrows(UnsupportedOperationException.class, () -> catalog.plans().clear());
        assertThrows(UnsupportedOperationException.class, () -> catalog.meters().clear());
        assertThrows(UnsupportedOperationException.class, () -> catalog.plans().getFirst().features().clear());
        assertEquals("contracts/pricing-catalog-schema/elmos-cny-self-serve-v1.json",
                catalog.authoritativeSource());
        assertEquals(PricingPlanCatalog.AllowanceScope.ORGANIZATION, catalog.allowanceScope());
        assertEquals(4, catalog.tokenClasses().size());
    }

    @Test
    void cnyPlansExposeExactTokenAndCreditAllowances() {
        var trial = PricingPlanCatalog.requirePlan("elmos-free-trial");
        var monthly = PricingPlanCatalog.requirePlan("elmos-pro-monthly");
        var annual = PricingPlanCatalog.requirePlan("elmos-pro-annual");

        assertEquals(new BigDecimal("0.00"), trial.price().amount());
        assertEquals(new BigDecimal("2000000"), trial.allowance().modelTokens());
        assertEquals(new BigDecimal("60"), trial.allowance().platformCredits());

        assertEquals(new BigDecimal("129.00"), monthly.price().amount());
        assertEquals(new BigDecimal("20000000"), monthly.allowance().modelTokens());
        assertEquals(new BigDecimal("600"), monthly.allowance().platformCredits());

        assertEquals(new BigDecimal("1290.00"), annual.price().amount());
        assertEquals(new BigDecimal("25000000"), annual.allowance().modelTokens());
        assertEquals(new BigDecimal("750"), annual.allowance().platformCredits());
        assertEquals(new BigDecimal("300000000"), annual.annualTokenCeiling());
        assertEquals(new BigDecimal("9000"), annual.annualCreditCeiling());
        assertEquals("CNY", annual.price().currency());
        assertFalse(annual.allowance().rollover());
        assertEquals(PricingPlanCatalog.BillingPeriod.YEAR, annual.billingPeriod());
    }

    @Test
    void draftCatalogCannotFulfillOrders() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals(PricingPlanCatalog.CatalogStatus.DRAFT, catalog.status());
        assertEquals("NOT_CONFIGURED", catalog.paymentStatus());
        assertEquals("NOT_RUN", catalog.costValidationStatus());
        assertThrows(IllegalStateException.class, PricingPlanCatalog::requireOrderable);
    }

    @Test
    void missingUsageIsNotPresentedAsZero() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertTrue(catalog.limitations().stream()
                .anyMatch(value -> value.contains("未对账") && value.contains("零用量")));
        assertEquals("HARD_STOP_NO_AUTOMATIC_CHARGE", catalog.overagePolicy());
    }

    @Test
    void tokenAndCreditLimitsAreEvaluatedTogether() {
        var allowed = PricingPlanCatalog.previewUsage(
                "elmos-pro-monthly",
                new BigDecimal("19000000"),
                new BigDecimal("560"),
                new BigDecimal("1000000"),
                new BigDecimal("40")
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.ALLOW, allowed.decision());
        assertEquals(BigDecimal.ZERO, allowed.remainingTokens());
        assertEquals(BigDecimal.ZERO, allowed.remainingCredits());

        var tokenDenied = PricingPlanCatalog.previewUsage(
                "elmos-pro-monthly",
                new BigDecimal("19000000"),
                new BigDecimal("0"),
                new BigDecimal("1000001"),
                BigDecimal.ZERO
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.DENY_TOKEN_LIMIT, tokenDenied.decision());
        assertEquals(new BigDecimal("1000000"), tokenDenied.remainingTokens());

        var creditDenied = PricingPlanCatalog.previewUsage(
                "elmos-pro-annual",
                BigDecimal.ZERO,
                new BigDecimal("749"),
                BigDecimal.ZERO,
                new BigDecimal("2")
        );
        assertEquals(PricingPlanCatalog.UsageDecisionType.DENY_CREDIT_LIMIT, creditDenied.decision());
        assertEquals(BigDecimal.ONE, creditDenied.remainingCredits());
    }

    @Test
    void creditScheduleUsesExactIntegerQuantities() {
        assertEquals(new BigDecimal("40"),
                PricingPlanCatalog.priceCredits("verified-generation-or-migration", BigDecimal.ONE));
        assertEquals(new BigDecimal("90"),
                PricingPlanCatalog.priceCredits("migration-or-translation-plan", new BigDecimal("6")));
        assertThrows(IllegalArgumentException.class,
                () -> PricingPlanCatalog.priceCredits("isolated-runner-minute", new BigDecimal("0.5")));
    }

    // =======================================================================
    // 以下为 2026-07-29 新增：支付通道契约
    //
    // paymentProvider 这个字段被 5 处独立实现读取，任何一处漂移都在运行期才暴露：
    //   contracts/pricing-catalog-schema/elmos-pricing-catalog.schema.json  (enum)
    //   apps/web-console/app/lib/pricingCatalog.ts                          (联合类型 + 装载期校验)
    //   apps/commercial-api/.../payment/PaymentProvider.java                (Java 枚举)
    //   scripts/commercial/validate_pricing_catalog_publication.py          (发布门禁)
    //   modules/persistence/.../V54__multi_provider_payment_callbacks.sql   (两处 CHECK 约束)
    //
    // 本类所在模块看不到上面任何一个（commercial-operations 不依赖 commercial-api），
    // 所以这里用字面量重述取值域。字面量重复是有意的：它让"目录改了但别处没改"
    // 变成一个编译期就写死、测试期就失败的事实，而不是上线后才发现的事实。
    // =======================================================================

    @Test
    void paymentProviderIsWithinTheContractedDomain() {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertTrue(
                List.of("STRIPE_CHECKOUT", "ALIPAY_CHECKOUT", "WECHAT_PAY_NATIVE")
                        .contains(catalog.paymentProvider()),
                "paymentProvider 超出契约取值域；改动时必须同步 schema / TS / Java 枚举 / "
                        + "发布门禁 / V54 的两处 CHECK 约束");
    }

    @Test
    void stripeIsNotUsableWithCnyPricing() {
        // D-01（2026-07-28）：选定中国大陆主体。Stripe 不为大陆主体收单，
        // 因此 STRIPE_CHECKOUT + CNY 是一个必须在发布前被挡住的组合。
        // 同一条规则另有两处实现（PaymentProvider.assertCompatibleWith 与
        // validate_pricing_catalog_publication.py），三处必须一致。
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals("CNY", catalog.currency());
        assertNotEquals("STRIPE_CHECKOUT", catalog.paymentProvider(),
                "currency=CNY 与 STRIPE_CHECKOUT 需要境外经营主体，与 D-01 冲突");
    }

    @Test
    void planTermDaysAreExactBecauseSubscriptionExpiryDependsOnThem() {
        // JdbcOrderPorts.subscriptionActivator 用 termDays 算订阅到期日。
        // 这三个数字一旦漂移，客户拿到的是一个错误的到期时间，
        // 而且只有到期那天才会有人发现。
        assertEquals(14, PricingPlanCatalog.requirePlan("elmos-free-trial").termDays());
        assertEquals(31, PricingPlanCatalog.requirePlan("elmos-pro-monthly").termDays());
        assertEquals(365, PricingPlanCatalog.requirePlan("elmos-pro-annual").termDays());
    }

    @Test
    void paidPlanAmountsMatchWhatTheCallbackWillCompare() {
        // 回调管线第 3 步拿 callback.amountFen 与订单 amount_minor 比对，
        // 而订单金额来自这里。用「分」写死是刻意的：
        // 支付宝回调传的是元字符串（"129.00"），微信传的是分整数（12900），
        // 两条路径最终都必须落到同一个数上。
        assertEquals(0, new BigDecimal("129.00")
                .movePointRight(2)
                .compareTo(new BigDecimal(12900)));
        assertEquals(new BigDecimal("129.00"),
                PricingPlanCatalog.requirePlan("elmos-pro-monthly").price().amount());
        assertEquals(new BigDecimal("1290.00"),
                PricingPlanCatalog.requirePlan("elmos-pro-annual").price().amount());
    }

    @Test
    void catalogRemainsUnorderableUntilPaymentIsConfigured() {
        // 回归：接了支付适配器不等于可以卖。paymentStatus 仍是 NOT_CONFIGURED
        // （商户号还没下来），requireOrderable 必须继续拒绝。
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();

        assertEquals("NOT_CONFIGURED", catalog.paymentStatus());
        assertEquals("NOT_CONFIGURED", catalog.sellerLegalEntityStatus());
        assertThrows(IllegalStateException.class, PricingPlanCatalog::requireOrderable,
                "代码写好了不等于能收款：营业执照、商户号、成本核算三道门禁都还没过");
    }
}
