package io.elmos.commercialadapter.payment;

import java.util.Optional;

/**
 * 支付回调的处理管线。
 *
 * <p><b>这五步的顺序不可调换：</b>
 *
 * <ol>
 *   <li><b>验签</b>——不通过就到此为止。跳过它等于接受任何人构造的报文。</li>
 *   <li><b>幂等去重</b>——必须在任何有副作用的动作之前。提供方会重发回调，
 *       重复放行会导致重复发放额度。</li>
 *   <li><b>金额比对</b>——必须在写订阅之前。回调金额可被篡改，
 *       只验签不比金额等于接受"付 1 分钱开通年付"。</li>
 *   <li><b>写 provider event</b>——先落原始事实，再动业务状态。
 *       顺序反了会出现"订阅已开通但没有对应事件"的孤儿状态，对账时无从追溯。</li>
 *   <li><b>更新订阅</b>——最后一步，也是唯一改变客户可见状态的一步。</li>
 * </ol>
 *
 * <p>任何一步不通过，后续步骤<b>一律不执行</b>。金额不符与订单未知会开对账案件，
 * 而不是静默丢弃——原始事实必须留痕，但不得据此改订阅。
 *
 * <p>本类不涉及 HTTP、Spring 或数据库，全部外部交互经由下方的端口接口注入，
 * 因此可以独立编译并对调用顺序做断言。
 */
public final class PaymentCallbackPipeline {

    /** 处理结果。除 {@link #ACCEPTED} 外都不得更新订阅。 */
    public enum Outcome {
        /** 验签失败。拒绝回调，不重试——重试一个伪造回调仍然是伪造回调。 */
        SIGNATURE_REJECTED,
        /** 幂等键已处理过。对提供方返回成功，但不重复执行任何副作用。 */
        DUPLICATE_IGNORED,
        /** 本地找不到该订单。开对账案件。 */
        ORDER_UNKNOWN,
        /** 回调金额与本地订单不一致。开对账案件，绝不更新订阅。 */
        AMOUNT_MISMATCH,
        /** 全部通过，订阅已更新。 */
        ACCEPTED
    }

    /** 提供方原始回调。{@code rawBody} 必须是未经解析与重新序列化的原文。 */
    public record RawCallback(PaymentProvider provider, String rawBody,
                              java.util.Map<String, String> headers,
                              java.util.Map<String, String> formParameters) {
    }

    /** 归一化后的回调事实。 */
    public record NormalizedCallback(PaymentProvider provider, String providerEventId,
                                     String outTradeNo, long amountFen, String tradeStatus) {
    }

    /** 本地订单。 */
    public record LocalOrder(String orderId, String organizationId, String planId,
                             long expectedAmountFen) {
    }

    /** 提供方相关的验签与归一化。实现见各自的 Verifier / Cipher。 */
    public interface ProviderAdapter {
        /** 第 1 步。任何异常情形返回 {@code false}，不得抛出。 */
        boolean verifySignature(RawCallback raw);

        /** 仅在验签通过后调用。 */
        NormalizedCallback normalize(RawCallback raw);
    }

    /** 幂等去重。实现必须是原子的（数据库唯一约束或条件插入）。 */
    public interface ProcessedEventLog {
        /**
         * 第 2 步。首次见到该幂等键返回 {@code true} 并原子登记；
         * 已存在返回 {@code false}。
         *
         * <p>用"先查后插"实现会在并发重发下同时返回 true，必须用唯一约束。
         */
        boolean registerIfAbsent(String idempotencyKey);
    }

    /** 第 3 步：订单查询。 */
    public interface OrderLookup {
        Optional<LocalOrder> findByOutTradeNo(String outTradeNo);
    }

    /** 第 4 步：写入不可改写的提供方事件。 */
    public interface ProviderEventStore {
        void record(NormalizedCallback callback, String rawBody);
    }

    /** 第 5 步：更新订阅。唯一改变客户可见状态的动作。 */
    public interface SubscriptionActivator {
        void activate(LocalOrder order, NormalizedCallback callback);
    }

    /**
     * 金额不符 / 订单未知时开对账案件。
     *
     * <p>{@code order} 在订单未知时为 {@code null}。这个区分是必须的：
     * {@code payment_reconciliation_cases.organization_id} 是 NOT NULL，
     * 而订单未知恰恰意味着组织未知，写不进那张表，
     * 需要落到不含租户列的 {@code payment_unmatched_callbacks} 滞留表。
     */
    public interface ReconciliationCases {
        void open(String reasonCode, NormalizedCallback callback, LocalOrder order, String detail);
    }

    private final ProviderAdapter adapter;
    private final ProcessedEventLog processedEvents;
    private final OrderLookup orders;
    private final ProviderEventStore events;
    private final SubscriptionActivator subscriptions;
    private final ReconciliationCases reconciliation;

    public PaymentCallbackPipeline(ProviderAdapter adapter,
                                   ProcessedEventLog processedEvents,
                                   OrderLookup orders,
                                   ProviderEventStore events,
                                   SubscriptionActivator subscriptions,
                                   ReconciliationCases reconciliation) {
        this.adapter = requireNonNull(adapter, "adapter");
        this.processedEvents = requireNonNull(processedEvents, "processedEvents");
        this.orders = requireNonNull(orders, "orders");
        this.events = requireNonNull(events, "events");
        this.subscriptions = requireNonNull(subscriptions, "subscriptions");
        this.reconciliation = requireNonNull(reconciliation, "reconciliation");
    }

    /**
     * 按固定顺序处理一次回调。
     *
     * <p>注意返回 {@link Outcome#SIGNATURE_REJECTED} 时，连归一化都没做过——
     * 未验签的报文不应被解析，更不应进入任何日志的业务字段。
     */
    public Outcome process(RawCallback raw) {
        // 第 1 步 · 验签
        if (!adapter.verifySignature(raw)) {
            return Outcome.SIGNATURE_REJECTED;
        }

        NormalizedCallback callback = adapter.normalize(raw);

        // 第 2 步 · 幂等去重（必须早于任何副作用）
        String idempotencyKey = idempotencyKey(callback);
        if (!processedEvents.registerIfAbsent(idempotencyKey)) {
            return Outcome.DUPLICATE_IGNORED;
        }

        // 第 3 步 · 订单查询与金额比对
        Optional<LocalOrder> found = orders.findByOutTradeNo(callback.outTradeNo());
        if (found.isEmpty()) {
            reconciliation.open("ORDER_UNKNOWN", callback, null,
                    "回调携带的 out_trade_no 在本地不存在");
            return Outcome.ORDER_UNKNOWN;
        }
        LocalOrder order = found.get();
        if (!MoneyConversion.matchesExpected(order.expectedAmountFen(), callback.amountFen())) {
            reconciliation.open("AMOUNT_MISMATCH", callback, order,
                    "期望 " + order.expectedAmountFen() + " 分，回调 "
                            + callback.amountFen() + " 分");
            return Outcome.AMOUNT_MISMATCH;
        }

        // 第 4 步 · 先落原始事实
        events.record(callback, raw.rawBody());

        // 第 5 步 · 最后才动订阅
        subscriptions.activate(order, callback);
        return Outcome.ACCEPTED;
    }

    /**
     * 幂等键 = 提供方 + 提供方事件 ID。
     *
     * <p>不使用 {@code out_trade_no}：同一订单会有多个事件（支付成功、退款、关单），
     * 用订单号做幂等键会把后续事件全部误判为重复。
     */
    public static String idempotencyKey(NormalizedCallback callback) {
        String eventId = callback.providerEventId();
        if (eventId == null || eventId.isEmpty()) {
            throw new IllegalArgumentException("提供方事件 ID 缺失，无法构造幂等键");
        }
        return callback.provider().name() + ":" + eventId;
    }

    private static <T> T requireNonNull(T value, String name) {
        if (value == null) {
            throw new IllegalArgumentException(name + " 未注入");
        }
        return value;
    }
}
