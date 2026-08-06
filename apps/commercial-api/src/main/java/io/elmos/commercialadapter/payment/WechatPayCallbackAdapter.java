package io.elmos.commercialadapter.payment;

import java.util.Map;

/**
 * 微信支付 APIv3 回调的 {@link PaymentCallbackPipeline.ProviderAdapter} 实现。
 *
 * <p>与支付宝的结构性差别：报文体是<b>加密</b>的。流程是
 * 验签（对原始体）→ 解密 {@code resource} → 从明文里取业务字段。
 * 解密只有在验签通过后才做，所以 {@link #normalize} 里才有解密调用，
 * 而不是在 {@link #verifySignature} 里。
 *
 * <h2>JSON 解析为什么是注入的</h2>
 *
 * <p>{@code payment} 包刻意只依赖 JDK，好让整包能脱离 Spring 与 Maven 单独编译和自检。
 * 但手写 JSON 解析器去处理一段<b>解密出来的、直接决定收钱结果</b>的报文是不能接受的。
 * 因此把解析抽成 {@link NotificationReader} 端口，由外层注入 Jackson 实现——
 * 与 {@link WechatPayNativeGateway.HttpTransport} 是同一个手法。
 *
 * <h2>必须校验 mchid</h2>
 *
 * <p>和支付宝同理：平台证书是所有商户共用的，别的商户收到的合法通知在我们这里
 * 验签同样能过。{@code mchid} 是唯一的归属凭据。
 */
public final class WechatPayCallbackAdapter implements PaymentCallbackPipeline.ProviderAdapter {

    /** 外层通知报文的必要字段。 */
    public record Envelope(String id, String eventType, String resourceCiphertext,
                           String resourceNonce, String resourceAssociatedData) {
    }

    /** 解密后的交易资源。 */
    public record Resource(String outTradeNo, String transactionId, String tradeState,
                           long amountTotalFen, String merchantId, String currency) {
    }

    /** JSON 解析端口。解析失败必须抛异常，不得返回带空字段的对象。 */
    public interface NotificationReader {
        Envelope readEnvelope(String rawBody);

        Resource readResource(String plaintext);
    }

    private final WechatPayCallbackCipher cipher;
    private final CallbackReplayGuard replayGuard;
    private final NotificationReader reader;
    private final String expectedMerchantId;

    public WechatPayCallbackAdapter(WechatPayCallbackCipher cipher,
                                    CallbackReplayGuard replayGuard,
                                    NotificationReader reader,
                                    String expectedMerchantId) {
        if (cipher == null) {
            throw new IllegalArgumentException("WechatPayCallbackCipher 未注入");
        }
        if (replayGuard == null) {
            throw new IllegalArgumentException("CallbackReplayGuard 未注入");
        }
        if (reader == null) {
            throw new IllegalArgumentException("NotificationReader 未注入");
        }
        if (expectedMerchantId == null || expectedMerchantId.isBlank()) {
            throw new IllegalArgumentException("ELMOS_WECHATPAY_MCHID 未配置，无法校验通知归属");
        }
        this.cipher = cipher;
        this.replayGuard = replayGuard;
        this.reader = reader;
        this.expectedMerchantId = expectedMerchantId;
    }

    /**
     * {@code Wechatpay-Timestamp} 是 Unix 秒。
     *
     * <p>它同时是验签串的第一段，所以这里拒绝的报文即便继续走验签也不会通过——
     * 但先在这里拒掉能省下一次 RSA 运算，而且给出的是更准确的失败原因。
     */
    @Override
    public boolean acceptsTimestamp(PaymentCallbackPipeline.RawCallback raw) {
        return replayGuard.accepts(header(raw, "Wechatpay-Timestamp"));
    }

    /**
     * APIv3 验签：{@code timestamp\nnonce\nbody\n}。
     *
     * <p>{@code body} 必须是<b>原始字节对应的文本</b>。控制器用
     * {@code @RequestBody String} 取原文而不是 DTO，就是为了这一步；
     * 任何"反序列化再重新序列化"都会让这里必然失败。
     */
    @Override
    public boolean verifySignature(PaymentCallbackPipeline.RawCallback raw) {
        try {
            return cipher.verify(
                    header(raw, "Wechatpay-Timestamp"),
                    header(raw, "Wechatpay-Nonce"),
                    raw.rawBody(),
                    header(raw, "Wechatpay-Signature"));
        } catch (RuntimeException anything) {
            return false;
        }
    }

    @Override
    public PaymentCallbackPipeline.NormalizedCallback normalize(
            PaymentCallbackPipeline.RawCallback raw) {
        Envelope envelope = reader.readEnvelope(raw.rawBody());
        requireText(envelope.id(), "id");
        requireText(envelope.resourceCiphertext(), "resource.ciphertext");
        requireText(envelope.resourceNonce(), "resource.nonce");

        String plaintext;
        try {
            plaintext = cipher.decryptResource(
                    envelope.resourceAssociatedData(),
                    envelope.resourceNonce(),
                    envelope.resourceCiphertext());
        } catch (Exception failure) {
            // 验签已过却解不开，说明 APIv3 密钥配错了。这是配置故障，
            // 不是可重试的临时问题，必须炸出来而不是静默当成"金额不符"。
            throw new IllegalStateException("微信回调资源解密失败", failure);
        }

        Resource resource = reader.readResource(plaintext);
        if (!expectedMerchantId.equals(resource.merchantId())) {
            throw new IllegalStateException("微信回调 mchid 与本商户不符，拒绝处理");
        }
        if (!"CNY".equals(resource.currency())) {
            // 目录币种是 CNY，收到别的币种说明配置或路由出了问题，不能按面值当人民币记账。
            throw new IllegalStateException("微信回调币种非 CNY: " + resource.currency());
        }
        requireText(resource.outTradeNo(), "out_trade_no");
        requireText(resource.tradeState(), "trade_state");

        return new PaymentCallbackPipeline.NormalizedCallback(
                PaymentProvider.WECHAT_PAY_NATIVE,
                envelope.id(),
                resource.outTradeNo(),
                resource.amountTotalFen(),
                resource.tradeState());
    }

    /**
     * 微信的 {@code trade_state} 只有 {@code SUCCESS} 表示已支付。
     *
     * <p>其余取值 {@code REFUND}、{@code NOTPAY}、{@code CLOSED}、
     * {@code REVOKED}、{@code USERPAYING}、{@code PAYERROR} 一律不激活。
     * 尤其 {@code REFUND}：那是已退款，把它当付款成功就是白送。
     */
    @Override
    public boolean indicatesPaymentSuccess(PaymentCallbackPipeline.NormalizedCallback callback) {
        return "SUCCESS".equals(callback.tradeStatus());
    }

    private static String header(PaymentCallbackPipeline.RawCallback raw, String name) {
        Map<String, String> headers = raw.headers();
        String value = headers == null ? null : headers.get(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("微信回调缺少必需请求头: " + name);
        }
        return value;
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("微信回调缺少必需字段: " + field);
        }
    }
}
