package io.elmos.commercialadapter.payment;

import java.util.Optional;

/**
 * 支付回调的处理管线。
 *
 * <p><b>这些步骤的顺序不可调换：</b>
 *
 * <ol start="0">
 *   <li><b>时间窗</b>——{@link ProviderAdapter#acceptsTimestamp}。只用于拒绝，
 *       从不用于放行，所以放在验签之前是安全的，而且能让伪造报文在做 RSA 之前就出局。</li>
 *   <li><b>验签</b>——不通过就到此为止。跳过它等于接受任何人构造的报文。</li>
 *   <li><b>幂等去重</b>——必须在任何有副作用的动作之前。提供方会重发回调，
 *       重复放行会导致重复发放额度。</li>
 *   <li><b>金额比对</b>——必须在写订阅之前。回调金额可被篡改，
 *       只验签不比金额等于接受"付 1 分钱开通年付"。</li>
 *   <li><b>写 provider event</b>——先落原始事实，再动业务状态。
 *       顺序反了会出现"订阅已开通但没有对应事件"的孤儿状态，对账时无从追溯。
 *       非付款成功的事件同样要落，否则退款/关单在库里查无痕迹。</li>
 *   <li><b>判定是否付款成功</b>——{@link ProviderAdapter#indicatesPaymentSuccess}。
 *       必须在事件落库<b>之后</b>、动订阅<b>之前</b>。</li>
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
        /**
         * 时间戳超出容差窗口 —— 陈旧或未来报文，典型的重放。
         * 在验签<b>之前</b>判定，理由见 {@link ProviderAdapter#acceptsTimestamp}。
         */
        STALE_TIMESTAMP,
        /** 验签失败。拒绝回调，不重试——重试一个伪造回调仍然是伪造回调。 */
        SIGNATURE_REJECTED,
        /** 幂等键已处理过。对提供方返回成功，但不重复执行任何副作用。 */
        DUPLICATE_IGNORED,
        /** 本地找不到该订单。开对账案件。 */
        ORDER_UNKNOWN,
        /** 回调金额与本地订单不一致。开对账案件，绝不更新订阅。 */
        AMOUNT_MISMATCH,
        /**
         * 事件合法且已落库，但它不是"支付成功"——例如支付宝的 {@code TRADE_CLOSED}
         * 或微信的 {@code CLOSED} / {@code REVOKED} / {@code PAYERROR}。
         *
         * <p>对提供方返回成功（我们确实正确处理了这条通知），但<b>绝不激活订阅</b>。
         * 少了这一步，一条关单通知会被当成付款通知，凭空开通订阅——
         * 而验签、幂等、金额比对全都拦不住它：关单通知的签名是真的，
         * 事件 ID 是新的，金额字段与订单一致。
         */
        NOT_A_PAYMENT_SUCCESS,
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

    /**
     * 订单类型。决定第 5 步动的是订阅还是钱包。
     *
     * <p>写成枚举而不是 {@code planId == null} 的隐含约定：后者能工作，
     * 但"套餐为空所以是充值"是一条只存在于某个人脑子里的规则，
     * 下一个加订单类型的人不会知道它，而编译器也不会提醒他。
     */
    public enum OrderKind { SUBSCRIPTION, TOPUP }

    /** 本地订单。充值订单没有套餐，{@code planId} 为 {@code null}。 */
    public record LocalOrder(String orderId, String organizationId, String planId,
                             long expectedAmountFen, OrderKind kind) {
        public LocalOrder {
            requireNonNull(kind, "kind");
            if (kind == OrderKind.SUBSCRIPTION && (planId == null || planId.isEmpty())) {
                throw new IllegalArgumentException("订阅订单必须带套餐");
            }
        }

        /** 既有订阅路径的构造形态，逐字保持不变。 */
        public LocalOrder(String orderId, String organizationId, String planId,
                          long expectedAmountFen) {
            this(orderId, organizationId, planId, expectedAmountFen, OrderKind.SUBSCRIPTION);
        }
    }

    /** 提供方相关的验签与归一化。实现见各自的 Verifier / Cipher。 */
    public interface ProviderAdapter {
        /** 第 1 步。任何异常情形返回 {@code false}，不得抛出。 */
        boolean verifySignature(RawCallback raw);

        /** 仅在验签通过后调用。 */
        NormalizedCallback normalize(RawCallback raw);

        /**
         * 第 0 步：时间戳是否落在容差窗口内（{@link CallbackReplayGuard}）。
         *
         * <p><b>为什么放在验签之前。</b>这里读的是<b>未经验签</b>的字段
         * （微信的 {@code Wechatpay-Timestamp} 头、支付宝的 {@code notify_time}），
         * 看上去违反"不信任未验签数据"的原则。区别在于方向：
         * 我们只用它<b>拒绝</b>，从不用它<b>放行</b>。基于伪造输入拒绝一个报文是安全的
         * （最坏结果是拒绝了本来就该被验签拒绝的东西）；基于伪造输入放行才是危险的。
         * 换来的是：伪造报文在做一次 RSA 验签之前就被挡掉，验签是这条路径上最贵的一步。
         *
         * <p>默认返回 {@code true}，即"不做时间校验"。这样既有的测试替身无需改动，
         * 但<b>真实适配器必须覆写</b>——见 {@code AlipayCallbackAdapter} /
         * {@code WechatPayCallbackAdapter}。
         */
        default boolean acceptsTimestamp(RawCallback raw) {
            return true;
        }

        /**
         * 该事件是否表示"支付成功"。
         *
         * <p>默认返回 {@code true} 是为了兼容既有替身；真实适配器<b>必须</b>覆写，
         * 否则关单/退款通知会被当成付款通知。见 {@link Outcome#NOT_A_PAYMENT_SUCCESS}。
         */
        default boolean indicatesPaymentSuccess(NormalizedCallback callback) {
            return true;
        }
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

    /**
     * 第 4 步：写入不可改写的提供方事件。
     *
     * <p><b>{@code order} 必须传进来，不能由实现方持有一个固定的组织。</b>
     * {@code payment_provider_events.organization_id} 是 NOT NULL 且带
     * {@code FORCE ROW LEVEL SECURITY}（V49 第 425 行起的租户表清单里就有它），
     * 策略是 {@code organization_id = current_setting('app.organization_id')}。
     * 因此实现必须：① 用本次订单的组织，② 在同一事务里先
     * {@code set_config('app.organization_id', ...)}，否则 WITH CHECK 直接拒绝插入。
     *
     * <p>管线在第 3 步已经解析出订单，此处传参不需要任何额外查询。
     */
    public interface ProviderEventStore {
        void record(LocalOrder order, NormalizedCallback callback, String rawBody);
    }

    /** 第 5 步（订阅）：更新订阅。 */
    public interface SubscriptionActivator {
        void activate(LocalOrder order, NormalizedCallback callback);
    }

    /**
     * 第 5 步（充值）：把已确认收款的充值单入账。
     *
     * <p>与 {@link SubscriptionActivator} 并列而不是复用它：两者唯一的共同点是
     * "都在第 5 步"，而实现完全不同——一个开订阅期发额度，一个走钱包记账函数。
     * 合成一个接口会逼实现方在内部按类型 if-else，那就把这里的分派又下沉了一层。
     */
    public interface WalletCreditor {
        void credit(LocalOrder order, NormalizedCallback callback);
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
    private final WalletCreditor wallet;
    private final ReconciliationCases reconciliation;

    public PaymentCallbackPipeline(ProviderAdapter adapter,
                                   ProcessedEventLog processedEvents,
                                   OrderLookup orders,
                                   ProviderEventStore events,
                                   SubscriptionActivator subscriptions,
                                   WalletCreditor wallet,
                                   ReconciliationCases reconciliation) {
        this.adapter = requireNonNull(adapter, "adapter");
        this.processedEvents = requireNonNull(processedEvents, "processedEvents");
        this.orders = requireNonNull(orders, "orders");
        this.events = requireNonNull(events, "events");
        this.subscriptions = requireNonNull(subscriptions, "subscriptions");
        this.wallet = requireNonNull(wallet, "wallet");
        this.reconciliation = requireNonNull(reconciliation, "reconciliation");
    }

    /**
     * 只装配订阅路径的构造形态。
     *
     * <p>钱包端口缺席时不是"跳过充值"，而是让充值回调直接失败：提供方会重发，
     * 运维会看到错误。静默跳过的后果是我们收了钱、用户没到账、而日志一片正常。
     */
    public PaymentCallbackPipeline(ProviderAdapter adapter,
                                   ProcessedEventLog processedEvents,
                                   OrderLookup orders,
                                   ProviderEventStore events,
                                   SubscriptionActivator subscriptions,
                                   ReconciliationCases reconciliation) {
        this(adapter, processedEvents, orders, events, subscriptions,
                (order, callback) -> {
                    throw new IllegalStateException("WALLET_CREDITOR_NOT_CONFIGURED");
                },
                reconciliation);
    }

    /**
     * 按固定顺序处理一次回调。
     *
     * <p>注意返回 {@link Outcome#SIGNATURE_REJECTED} 时，连归一化都没做过——
     * 未验签的报文不应被解析，更不应进入任何日志的业务字段。
     */
    public Outcome process(RawCallback raw) {
        // 第 0 步 · 时间窗（只用于拒绝，不用于放行）
        if (!adapter.acceptsTimestamp(raw)) {
            return Outcome.STALE_TIMESTAMP;
        }

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

        // 第 4 步 · 先落原始事实。非成功事件也要落，否则退款/关单在库里查无痕迹。
        events.record(order, callback, raw.rawBody());

        // 第 4.5 步 · 事件落库之后、动订阅之前，判断它到底是不是"付款成功"
        if (!adapter.indicatesPaymentSuccess(callback)) {
            return Outcome.NOT_A_PAYMENT_SUCCESS;
        }

        // 第 5 步 · 最后才动客户可见状态，按订单类型分派
        if (order.kind() == OrderKind.TOPUP) {
            wallet.credit(order, callback);
        } else {
            subscriptions.activate(order, callback);
        }
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
