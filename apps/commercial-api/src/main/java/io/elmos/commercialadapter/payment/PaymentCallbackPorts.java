package io.elmos.commercialadapter.payment;

/**
 * 回调链路的全部依赖，打成一个整体。
 *
 * <p>把六个依赖收成一个记录，是为了让"支付回调有没有配置好"变成<b>一个</b>
 * 可判定的事实，而不是六个可能各自缺失的事实。控制器于是只需要问一次
 * "有没有 {@code PaymentCallbackPorts}"，而不是逐个检查再拼出一个半通的管线。
 *
 * <p>构造时全部非空校验：一个装了一半的端口组比没有端口更危险——
 * 前者会让"配好了"的判断成立，然后在第三步炸掉，此时提供方已经扣过款。
 */
public record PaymentCallbackPorts(
        PaymentProviderRouter router,
        PaymentCallbackPipeline.ProcessedEventLog processedEvents,
        PaymentCallbackPipeline.OrderLookup orders,
        PaymentCallbackPipeline.ProviderEventStore events,
        PaymentCallbackPipeline.SubscriptionActivator subscriptions,
        PaymentCallbackPipeline.WalletCreditor wallet,
        PaymentCallbackPipeline.ReconciliationCases reconciliation) {

    public PaymentCallbackPorts {
        require(router, "router");
        require(processedEvents, "processedEvents");
        require(orders, "orders");
        require(events, "events");
        require(subscriptions, "subscriptions");
        require(wallet, "wallet");
        require(reconciliation, "reconciliation");
    }

    /**
     * 只有订阅路径的装配形态。
     *
     * <p>保留它是为了让既有调用点与测试逐字不变。钱包端口在这里不是"可选依赖"
     * 而是"未配置"：装出来的管线遇到充值回调会抛，而不是当作成功忽略——
     * 后者意味着钱收了、账没入、日志干净。
     */
    public PaymentCallbackPorts(
            PaymentProviderRouter router,
            PaymentCallbackPipeline.ProcessedEventLog processedEvents,
            PaymentCallbackPipeline.OrderLookup orders,
            PaymentCallbackPipeline.ProviderEventStore events,
            PaymentCallbackPipeline.SubscriptionActivator subscriptions,
            PaymentCallbackPipeline.ReconciliationCases reconciliation) {
        this(router, processedEvents, orders, events, subscriptions,
                (order, callback) -> {
                    throw new IllegalStateException("WALLET_CREDITOR_NOT_CONFIGURED");
                },
                reconciliation);
    }

    /** 按回调所属通道装配一条管线。 */
    public PaymentCallbackPipeline pipelineFor(PaymentProvider provider) {
        return new PaymentCallbackPipeline(
                router.callbackAdapter(provider),
                processedEvents, orders, events, subscriptions, wallet, reconciliation);
    }

    private static void require(Object value, String name) {
        if (value == null) {
            throw new IllegalArgumentException(name + " 未注入");
        }
    }
}
