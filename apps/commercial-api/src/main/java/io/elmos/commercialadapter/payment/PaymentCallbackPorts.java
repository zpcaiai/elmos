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
        PaymentCallbackPipeline.ReconciliationCases reconciliation) {

    public PaymentCallbackPorts {
        require(router, "router");
        require(processedEvents, "processedEvents");
        require(orders, "orders");
        require(events, "events");
        require(subscriptions, "subscriptions");
        require(reconciliation, "reconciliation");
    }

    /** 按回调所属通道装配一条管线。 */
    public PaymentCallbackPipeline pipelineFor(PaymentProvider provider) {
        return new PaymentCallbackPipeline(
                router.callbackAdapter(provider),
                processedEvents, orders, events, subscriptions, reconciliation);
    }

    private static void require(Object value, String name) {
        if (value == null) {
            throw new IllegalArgumentException(name + " 未注入");
        }
    }
}
