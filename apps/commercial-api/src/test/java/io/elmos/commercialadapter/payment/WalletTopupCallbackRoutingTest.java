package io.elmos.commercialadapter.payment;

import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.LocalOrder;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.NormalizedCallback;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.OrderKind;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.Outcome;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.RawCallback;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 第 5 步的分派：一条回调管线，两种订单，动的必须是对应的那一侧。
 *
 * <p>全内存假件，不碰数据库——这里要验的是<b>路由</b>，不是记账。
 * 记账的正确性由 V73 的真库测试负责（{@code wallet_behaviour_test.sql} /
 * {@code WalletLedgerLiveTest}），在这里再验一遍只会得到一个假的安心感。
 *
 * <p>值得单独立一个测试的原因：把充值接进既有订阅管线，最容易出的错不是崩溃，
 * 而是<b>走错分支还返回成功</b>——充值回调把某个组织的订阅期往后推一个月，
 * 或者订阅回调去给钱包加钱。两者都会返回 {@code ACCEPTED}，日志一片正常。
 */
class WalletTopupCallbackRoutingTest {

    private final List<String> subscriptionActivations = new ArrayList<>();
    private final List<String> walletCredits = new ArrayList<>();
    private final List<String> reconciliationCases = new ArrayList<>();
    private final Set<String> processedKeys = new HashSet<>();

    @Test void aTopUpCallbackCreditsTheWalletAndNeverTouchesSubscriptions() {
        Outcome outcome = pipeline(topupOrder(50_000L)).process(rawCallback());

        assertEquals(Outcome.ACCEPTED, outcome);
        assertEquals(List.of("topup-1"), walletCredits);
        assertTrue(subscriptionActivations.isEmpty(),
                () -> "充值回调不得触碰订阅，却调用了 " + subscriptionActivations);
    }

    @Test void aSubscriptionCallbackStillActivatesSubscriptionsAndNeverTouchesTheWallet() {
        Outcome outcome = pipeline(subscriptionOrder(50_000L)).process(rawCallback());

        assertEquals(Outcome.ACCEPTED, outcome);
        assertEquals(List.of("ord-1"), subscriptionActivations);
        assertTrue(walletCredits.isEmpty(),
                () -> "订阅回调不得动钱包，却调用了 " + walletCredits);
    }

    /**
     * 金额比对必须发生在分派<b>之前</b>。
     *
     * <p>否则一笔金额被篡改的回调会先入账、再被记成对账工单——钱已经进去了，
     * 工单只是事后说明。
     */
    @Test void aTopUpWhoseAmountDisagreesIsReconciledRatherThanCredited() {
        Outcome outcome = pipeline(topupOrder(99_999L)).process(rawCallback());

        assertEquals(Outcome.AMOUNT_MISMATCH, outcome);
        assertTrue(walletCredits.isEmpty(), "金额不符时不得入账");
        assertEquals(List.of("AMOUNT_MISMATCH"), reconciliationCases);
    }

    /** 幂等去重早于任何副作用，充值这条路径也不例外。 */
    @Test void aReplayedTopUpCallbackIsIgnoredBeforeItReachesTheWallet() {
        PaymentCallbackPipeline pipeline = pipeline(topupOrder(50_000L));

        assertEquals(Outcome.ACCEPTED, pipeline.process(rawCallback()));
        assertEquals(Outcome.DUPLICATE_IGNORED, pipeline.process(rawCallback()));

        assertEquals(1, walletCredits.size(), "重放的回调只能入账一次");
    }

    /**
     * 钱包端口缺席时，充值回调必须<b>失败</b>。
     *
     * <p>这是 {@link PaymentCallbackPipeline} 那个只装订阅的构造器的行为契约。
     * 静默跳过看起来更"健壮"，实际后果是：钱收了、账没入、回调返 200、
     * 提供方不再重发、没有任何人会知道。失败反而是可恢复的。
     */
    @Test void anUnconfiguredWalletPortFailsLoudlyInsteadOfSilentlySkipping() {
        PaymentCallbackPipeline withoutWallet = new PaymentCallbackPipeline(
                adapter(),
                processedKeys::add,
                outTradeNo -> Optional.of(topupOrder(50_000L)),
                (order, callback, rawBody) -> { },
                (order, callback) -> subscriptionActivations.add(order.orderId()),
                (reason, callback, order, detail) -> reconciliationCases.add(reason));

        var failure = assertThrows(IllegalStateException.class,
                () -> withoutWallet.process(rawCallback()));
        assertTrue(failure.getMessage().contains("WALLET_CREDITOR_NOT_CONFIGURED"),
                failure::getMessage);
    }

    /** 充值订单没有套餐；订阅订单必须有，缺了要在构造时就拒绝。 */
    @Test void onlySubscriptionOrdersAreRequiredToCarryAPlan() {
        LocalOrder topup = new LocalOrder("topup-1", "org-1", null, 50_000L, OrderKind.TOPUP);
        assertEquals(OrderKind.TOPUP, topup.kind());

        assertThrows(IllegalArgumentException.class,
                () -> new LocalOrder("ord-1", "org-1", null, 50_000L, OrderKind.SUBSCRIPTION));
    }

    /** 既有的四参构造保持订阅语义，接进充值不应改变任何既有调用点的含义。 */
    @Test void theLegacyFourArgumentConstructorStillMeansSubscription() {
        assertEquals(OrderKind.SUBSCRIPTION,
                new LocalOrder("ord-1", "org-1", "elmos-pro-monthly", 12_900L).kind());
    }

    // ------------------------------------------------------------------

    private PaymentCallbackPipeline pipeline(LocalOrder order) {
        return new PaymentCallbackPipeline(
                adapter(),
                processedKeys::add,
                outTradeNo -> Optional.of(order),
                (o, callback, rawBody) -> { },
                (o, callback) -> subscriptionActivations.add(o.orderId()),
                (o, callback) -> walletCredits.add(o.orderId()),
                (reason, callback, o, detail) -> reconciliationCases.add(reason));
    }

    private static LocalOrder topupOrder(long expectedFen) {
        return new LocalOrder("topup-1", "org-1", null, expectedFen, OrderKind.TOPUP);
    }

    private static LocalOrder subscriptionOrder(long expectedFen) {
        return new LocalOrder("ord-1", "org-1", "elmos-pro-monthly", expectedFen,
                OrderKind.SUBSCRIPTION);
    }

    private static PaymentCallbackPipeline.ProviderAdapter adapter() {
        return new PaymentCallbackPipeline.ProviderAdapter() {
            @Override
            public boolean verifySignature(RawCallback raw) {
                return true;
            }

            @Override
            public NormalizedCallback normalize(RawCallback raw) {
                return new NormalizedCallback(raw.provider(), "evt-1", "topup-1",
                        50_000L, "SUCCESS");
            }
        };
    }

    private static RawCallback rawCallback() {
        return new RawCallback(PaymentProvider.ALIPAY_CHECKOUT, "{}", Map.of(), Map.of());
    }
}
