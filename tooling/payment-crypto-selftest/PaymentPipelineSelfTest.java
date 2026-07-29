import io.elmos.commercialadapter.payment.PaymentCallbackPipeline;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.LocalOrder;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.NormalizedCallback;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.Outcome;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.RawCallback;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * 回调管线的顺序断言。
 *
 * <p>这些测试的重点不是"结果对不对"，而是<b>每一步在什么条件下被执行、
 * 什么条件下必须不被执行</b>。顺序错误在生产中的表现是资损或孤儿状态，
 * 而单看返回值完全正常。
 */
public final class PaymentPipelineSelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) {
        happyPathOrder();
        signatureRejectedStopsImmediately();
        duplicateStopsBeforeSideEffects();
        amountMismatchNeverTouchesSubscription();
        unknownOrderOpensCase();
        idempotencyKeyRules();
        routerFailsClosed();

        System.out.println();
        System.out.printf("结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) {
            System.exit(1);
        }
    }

    // ------------------------------------------------------------------ 用例

    private static void happyPathOrder() {
        section("正常路径：五步顺序");
        Ports ports = new Ports();
        Outcome outcome = pipeline(ports).process(raw());

        check("结果为 ACCEPTED", outcome == Outcome.ACCEPTED);
        check("调用顺序恰好是 验签→幂等→查单→写事件→更新订阅",
                ports.calls.equals(List.of("verify", "normalize", "registerIfAbsent",
                        "findByOutTradeNo", "record", "activate")));
        check("写事件严格早于更新订阅",
                ports.calls.indexOf("record") < ports.calls.indexOf("activate"));
        check("幂等去重严格早于写事件",
                ports.calls.indexOf("registerIfAbsent") < ports.calls.indexOf("record"));
        check("金额比对（查单）严格早于更新订阅",
                ports.calls.indexOf("findByOutTradeNo") < ports.calls.indexOf("activate"));
        check("未开对账案件", !ports.calls.contains("openCase"));
    }

    private static void signatureRejectedStopsImmediately() {
        section("验签失败：必须立刻停止");
        Ports ports = new Ports();
        ports.signatureValid = false;
        Outcome outcome = pipeline(ports).process(raw());

        check("结果为 SIGNATURE_REJECTED", outcome == Outcome.SIGNATURE_REJECTED);
        check("只调用了验签，连归一化都没做", ports.calls.equals(List.of("verify")));
        check("未登记幂等键（否则会挡掉后续合法回调）",
                !ports.calls.contains("registerIfAbsent"));
        check("未写事件", !ports.calls.contains("record"));
        check("未更新订阅", !ports.calls.contains("activate"));
    }

    private static void duplicateStopsBeforeSideEffects() {
        section("重复回调：在任何副作用之前停止");
        Ports ports = new Ports();
        PaymentCallbackPipeline pipeline = pipeline(ports);

        check("首次 ACCEPTED", pipeline.process(raw()) == Outcome.ACCEPTED);
        int activationsAfterFirst = ports.activations;

        ports.calls.clear();
        Outcome second = pipeline.process(raw());

        check("重发结果为 DUPLICATE_IGNORED", second == Outcome.DUPLICATE_IGNORED);
        check("重发只走到幂等检查",
                ports.calls.equals(List.of("verify", "normalize", "registerIfAbsent")));
        check("订阅只被激活一次", ports.activations == activationsAfterFirst);
        check("事件只写入一次", ports.recorded == 1);
    }

    private static void amountMismatchNeverTouchesSubscription() {
        section("金额被篡改：绝不更新订阅");
        Ports ports = new Ports();
        ports.callbackAmountFen = 1;          // 期望 12900 分，回调声称 1 分
        Outcome outcome = pipeline(ports).process(raw());

        check("结果为 AMOUNT_MISMATCH", outcome == Outcome.AMOUNT_MISMATCH);
        check("未更新订阅", !ports.calls.contains("activate"));
        check("未写 provider event", !ports.calls.contains("record"));
        check("已开对账案件（原始事实不丢）", ports.calls.contains("openCase"));
        check("案件原因为 AMOUNT_MISMATCH", "AMOUNT_MISMATCH".equals(ports.caseReason));
        check("案件详情含双方金额",
                ports.caseDetail != null && ports.caseDetail.contains("12900")
                        && ports.caseDetail.contains("1 分"));
        check("金额不符时订单已知 -> 可写入需要 organization_id 的对账表",
                Boolean.TRUE.equals(ports.caseHadOrder));
    }

    private static void unknownOrderOpensCase() {
        section("订单未知：开案件而不是静默丢弃");
        Ports ports = new Ports();
        ports.orderExists = false;
        Outcome outcome = pipeline(ports).process(raw());

        check("结果为 ORDER_UNKNOWN", outcome == Outcome.ORDER_UNKNOWN);
        check("已开对账案件", "ORDER_UNKNOWN".equals(ports.caseReason));
        check("订单未知时不传订单 -> 必须落无租户的滞留表",
                Boolean.FALSE.equals(ports.caseHadOrder));
        check("未写事件也未更新订阅",
                !ports.calls.contains("record") && !ports.calls.contains("activate"));
    }

    private static void idempotencyKeyRules() {
        section("幂等键规则");
        NormalizedCallback callback = new NormalizedCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "evt-1", "order-1", 12900, "TRADE_SUCCESS");
        check("幂等键含通道与事件 ID",
                "ALIPAY_CHECKOUT:evt-1".equals(PaymentCallbackPipeline.idempotencyKey(callback)));

        NormalizedCallback sameOrderDifferentEvent = new NormalizedCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "evt-2", "order-1", 12900, "TRADE_REFUND");
        check("同一订单的不同事件幂等键不同（退款不会被当成重复）",
                !PaymentCallbackPipeline.idempotencyKey(callback)
                        .equals(PaymentCallbackPipeline.idempotencyKey(sameOrderDifferentEvent)));

        NormalizedCallback crossProvider = new NormalizedCallback(
                PaymentProvider.WECHAT_PAY_NATIVE, "evt-1", "order-1", 12900, "SUCCESS");
        check("不同通道的同名事件 ID 不冲突",
                !PaymentCallbackPipeline.idempotencyKey(callback)
                        .equals(PaymentCallbackPipeline.idempotencyKey(crossProvider)));

        NormalizedCallback noEventId = new NormalizedCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "", "order-1", 12900, "TRADE_SUCCESS");
        check("缺事件 ID -> 抛异常（不允许退化成订单号）",
                throwsIllegalArgument(() -> PaymentCallbackPipeline.idempotencyKey(noEventId)));
    }

    private static void routerFailsClosed() {
        section("路由器：失败关闭");
        check("未知通道名 -> 拒绝",
                throwsIllegalArgument(() -> PaymentProvider.parse("PAYPAL")));
        check("空通道名 -> 拒绝", throwsIllegalArgument(() -> PaymentProvider.parse("")));
        check("小写不接受（大小写敏感）",
                throwsIllegalArgument(() -> PaymentProvider.parse("alipay_checkout")));
        check("带空白不接受",
                throwsIllegalArgument(() -> PaymentProvider.parse(" ALIPAY_CHECKOUT")));

        check("Stripe + CNY -> 拒绝（D-01 大陆主体）", throwsAny(
                () -> new PaymentProviderRouter("STRIPE_CHECKOUT", "CNY")));
        check("Stripe + USD -> 允许（境外主体场景）", !throwsAny(
                () -> new PaymentProviderRouter("STRIPE_CHECKOUT", "USD")));
        check("支付宝 + CNY -> 允许", !throwsAny(
                () -> new PaymentProviderRouter("ALIPAY_CHECKOUT", "CNY")));

        PaymentProviderRouter router = new PaymentProviderRouter("ALIPAY_CHECKOUT", "CNY");
        check("目录声明的通道未注册网关 -> 抛异常而不是回退",
                throwsAny(router::checkoutGateway));
        check("未注册回调适配器 -> 抛异常",
                throwsAny(() -> router.callbackAdapter(PaymentProvider.WECHAT_PAY_NATIVE)));

        router.register(new StubGateway(PaymentProvider.ALIPAY_CHECKOUT));
        check("注册后可取到网关",
                router.checkoutGateway().provider() == PaymentProvider.ALIPAY_CHECKOUT);
        check("注册了支付宝不代表微信可用",
                throwsAny(() -> router.callbackAdapter(PaymentProvider.WECHAT_PAY_NATIVE)));

        check("支付入口必须二选一：都给 -> 拒绝", throwsIllegalArgument(() ->
                new PaymentProviderRouter.CheckoutHandoff(
                        PaymentProvider.ALIPAY_CHECKOUT, "https://x", "weixin://y")));
        check("支付入口必须二选一：都不给 -> 拒绝", throwsIllegalArgument(() ->
                new PaymentProviderRouter.CheckoutHandoff(
                        PaymentProvider.ALIPAY_CHECKOUT, null, null)));
        check("只给跳转 URL -> 允许", !throwsAny(() ->
                new PaymentProviderRouter.CheckoutHandoff(
                        PaymentProvider.ALIPAY_CHECKOUT, "https://x", null)));
        check("只给二维码 -> 允许", !throwsAny(() ->
                new PaymentProviderRouter.CheckoutHandoff(
                        PaymentProvider.WECHAT_PAY_NATIVE, null, "weixin://y")));

        check("端口未注入 -> 构造即拒绝", throwsIllegalArgument(() ->
                new PaymentCallbackPipeline(null, null, null, null, null, null)));
    }

    // ------------------------------------------------------------ 记录型测试替身

    /** 记录调用顺序的全套端口替身。 */
    private static final class Ports {
        final List<String> calls = new ArrayList<>();
        final Set<String> seenKeys = new HashSet<>();
        boolean signatureValid = true;
        boolean orderExists = true;
        long callbackAmountFen = 12900;
        int activations;
        int recorded;
        String caseReason;
        String caseDetail;
        Boolean caseHadOrder;
    }

    private static PaymentCallbackPipeline pipeline(Ports ports) {
        return new PaymentCallbackPipeline(
                new PaymentCallbackPipeline.ProviderAdapter() {
                    @Override
                    public boolean verifySignature(RawCallback raw) {
                        ports.calls.add("verify");
                        return ports.signatureValid;
                    }

                    @Override
                    public NormalizedCallback normalize(RawCallback raw) {
                        ports.calls.add("normalize");
                        return new NormalizedCallback(PaymentProvider.ALIPAY_CHECKOUT,
                                "evt-1", "order-1", ports.callbackAmountFen, "TRADE_SUCCESS");
                    }
                },
                key -> {
                    ports.calls.add("registerIfAbsent");
                    return ports.seenKeys.add(key);
                },
                outTradeNo -> {
                    ports.calls.add("findByOutTradeNo");
                    return ports.orderExists
                            ? Optional.of(new LocalOrder("order-1", "org-1",
                                    "elmos-pro-monthly", 12900))
                            : Optional.empty();
                },
                (callback, body) -> {
                    ports.calls.add("record");
                    ports.recorded++;
                },
                (order, callback) -> {
                    ports.calls.add("activate");
                    ports.activations++;
                },
                (reason, callback, order, detail) -> {
                    ports.calls.add("openCase");
                    ports.caseReason = reason;
                    ports.caseDetail = detail;
                    ports.caseHadOrder = order != null;
                });
    }

    private static RawCallback raw() {
        return new RawCallback(PaymentProvider.ALIPAY_CHECKOUT, "{}", Map.of(), Map.of());
    }

    private record StubGateway(PaymentProvider provider)
            implements PaymentProviderRouter.CheckoutGateway {
        @Override
        public PaymentProviderRouter.CheckoutHandoff prepare(String outTradeNo, long amountFen,
                                                             String subject) {
            return new PaymentProviderRouter.CheckoutHandoff(provider, "https://example", null);
        }
    }

    // ---------------------------------------------------------------- 工具

    private interface Block {
        void run() throws Exception;
    }

    private static boolean throwsIllegalArgument(Block block) {
        try {
            block.run();
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        } catch (Exception other) {
            return false;
        }
    }

    private static boolean throwsAny(Block block) {
        try {
            block.run();
            return false;
        } catch (Exception expected) {
            return true;
        }
    }

    private static void section(String title) {
        System.out.println();
        System.out.println("== " + title + " ==");
    }

    private static void check(String name, boolean condition) {
        if (condition) {
            passed++;
            System.out.println("  [PASS] " + name);
        } else {
            failed++;
            System.out.println("  [FAIL] " + name);
        }
    }
}
