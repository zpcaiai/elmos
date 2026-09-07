package io.elmos.commercialadapter.payment;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Map;

/**
 * 支付宝异步通知的 {@link PaymentCallbackPipeline.ProviderAdapter} 实现。
 *
 * <p>把三样已经各自验证过的零件接起来：{@link AlipaySignatureVerifier}（验签）、
 * {@link CallbackReplayGuard}（时间窗）、{@link MoneyConversion}（元→分）。
 * 本类自己只做两件容易被忽略的事，都写在下面。
 *
 * <h2>一、必须校验 app_id</h2>
 *
 * <p>支付宝的异步通知是用<b>支付宝的私钥</b>签的，对应的公钥是所有商户共用的同一把。
 * 也就是说，发给<b>别的商户</b>的一份合法通知，拿到我们这里验签<b>照样通过</b>。
 *
 * <p>唯一能把"这单是我们的"和"这单是别人的"分开的字段就是 {@code app_id}。
 * 不校验它，攻击者只要搞到任意一份真实的支付宝通知，改一下 {@code out_trade_no}
 * 就能……不，改了签名就不过了。但他可以拿一份<b>金额更小的、属于自己商户的</b>
 * 真实通知直接转发过来；如果那笔的 {@code out_trade_no} 恰好撞上我们的订单号
 * （订单号是我们自己生成的，格式可推测），验签、金额比对都可能过。
 * 校验 {@code app_id} 把这条路彻底堵死。
 *
 * <h2>二、TRADE_CLOSED 不是付款成功</h2>
 *
 * <p>同一笔订单会收到多次通知：{@code WAIT_BUYER_PAY} → {@code TRADE_SUCCESS}
 * → 可能还有 {@code TRADE_CLOSED}（退款完成或超时关闭）。
 * 这些通知<b>签名都是真的</b>、{@code notify_id} 都是新的、金额字段都和订单一致——
 * 验签、幂等、金额比对<b>没有一道拦得住它们</b>。
 * 只有 {@link #indicatesPaymentSuccess} 能。
 */
public final class AlipayCallbackAdapter implements PaymentCallbackPipeline.ProviderAdapter {

    /** 支付宝 {@code notify_time} 的时区。文档规定为北京时间，报文里不带时区。 */
    private static final ZoneId NOTIFY_ZONE = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter NOTIFY_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final AlipaySignatureVerifier verifier;
    private final CallbackReplayGuard replayGuard;
    private final String expectedAppId;

    public AlipayCallbackAdapter(AlipaySignatureVerifier verifier,
                                 CallbackReplayGuard replayGuard,
                                 String expectedAppId) {
        if (verifier == null) {
            throw new IllegalArgumentException("AlipaySignatureVerifier 未注入");
        }
        if (replayGuard == null) {
            throw new IllegalArgumentException("CallbackReplayGuard 未注入");
        }
        if (expectedAppId == null || expectedAppId.isBlank()) {
            // 空 app_id 等于关掉商户归属校验，见类注释第一节。
            throw new IllegalArgumentException("ELMOS_ALIPAY_APP_ID 未配置，无法校验通知归属");
        }
        this.verifier = verifier;
        this.replayGuard = replayGuard;
        this.expectedAppId = expectedAppId;
    }

    /**
     * 时间窗校验。{@code notify_time} 缺失或格式不对一律拒绝——
     * 拒绝的成本是提供方重发，接受的成本是打开重放窗口。
     */
    @Override
    public boolean acceptsTimestamp(PaymentCallbackPipeline.RawCallback raw) {
        String notifyTime = raw.formParameters().get("notify_time");
        if (notifyTime == null || notifyTime.isBlank()) {
            return false;
        }
        Instant parsed;
        try {
            parsed = LocalDateTime.parse(notifyTime.trim(), NOTIFY_TIME)
                    .atZone(NOTIFY_ZONE)
                    .toInstant();
        } catch (DateTimeParseException malformed) {
            return false;
        }
        return replayGuard.check(parsed) == CallbackReplayGuard.Verdict.ACCEPTED;
    }

    /**
     * 验签 + 商户归属校验。任何异常都收敛成 {@code false}，
     * 接口约定这里不得抛出——抛出会让一个伪造报文变成 500，
     * 而 500 会让提供方以为是我们的故障并持续重发。
     */
    @Override
    public boolean verifySignature(PaymentCallbackPipeline.RawCallback raw) {
        try {
            Map<String, String> parameters = raw.formParameters();
            if (parameters == null || parameters.isEmpty()) {
                return false;
            }
            // 先看归属再验签：字符串比较比 RSA 便宜得多，
            // 而且归属不符时根本不需要知道签名对不对。
            if (!expectedAppId.equals(parameters.get("app_id"))) {
                return false;
            }
            return verifier.verify(parameters);
        } catch (RuntimeException anything) {
            return false;
        }
    }

    @Override
    public PaymentCallbackPipeline.NormalizedCallback normalize(
            PaymentCallbackPipeline.RawCallback raw) {
        Map<String, String> parameters = raw.formParameters();
        String notifyId = required(parameters, "notify_id");
        String outTradeNo = required(parameters, "out_trade_no");
        String tradeStatus = required(parameters, "trade_status");
        // total_amount 是"订单总金额"。刻意不用 receipt_amount（商家实收）：
        // 后者会因优惠券、集分宝等小于订单金额，用它比对必然误报金额不符。
        long amountFen = MoneyConversion.fromAlipayYuan(required(parameters, "total_amount"));
        return new PaymentCallbackPipeline.NormalizedCallback(
                PaymentProvider.ALIPAY_CHECKOUT, notifyId, outTradeNo, amountFen, tradeStatus);
    }

    /**
     * 只有这两个状态才是"钱已经到账、可以开通服务"。
     *
     * <ul>
     *   <li>{@code TRADE_SUCCESS}：支付成功（可退款期内）</li>
     *   <li>{@code TRADE_FINISHED}：交易结束（不可退款）</li>
     * </ul>
     *
     * <p>其余一律不激活：{@code WAIT_BUYER_PAY} 是还没付，
     * {@code TRADE_CLOSED} 是超时关闭或已全额退款——把后者当成付款成功，
     * 等于给一个退了款的人开通订阅。
     */
    @Override
    public boolean indicatesPaymentSuccess(PaymentCallbackPipeline.NormalizedCallback callback) {
        String status = callback.tradeStatus();
        return "TRADE_SUCCESS".equals(status) || "TRADE_FINISHED".equals(status);
    }

    private static String required(Map<String, String> parameters, String field) {
        String value = parameters == null ? null : parameters.get(field);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("支付宝通知缺少必需字段: " + field);
        }
        return value;
    }
}
