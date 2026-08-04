package io.elmos.commercialadapter.payment;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.Signature;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

/**
 * 支付宝电脑网站支付（{@code alipay.trade.page.pay}）下单网关。
 *
 * <p>下单是<b>纯参数构造 + 签名 + 跳转</b>，不需要服务端发请求：
 * 支付宝这一接口的产物是一个带签名的跳转 URL。所以这里没有 HTTP 客户端，
 * 也就没有超时、重试、连接池这些需要额外验证的东西。
 *
 * <p>三条硬约束写在实现里：
 *
 * <ul>
 *   <li><b>金额由服务端决定</b>。{@code amountFen} 来自定价目录，
 *       调用方不得从请求体里取——否则客户端可以自定价格。</li>
 *   <li><b>签名内容与验签内容用同一套规范化规则</b>
 *       （{@link AlipaySignatureVerifier#canonicalContent}），
 *       两边规则不一致是"签名怎么都不过"的经典原因。</li>
 *   <li><b>回调地址必须是已备案域名下的 HTTPS 地址</b>，构造时校验。</li>
 * </ul>
 */
public final class AlipayCheckoutGateway implements PaymentProviderRouter.CheckoutGateway {

    private static final String METHOD = "alipay.trade.page.pay";
    private static final String PRODUCT_CODE = "FAST_INSTANT_TRADE_PAY";
    private static final String SIGN_TYPE = "RSA2";
    private static final String CHARSET = "utf-8";
    private static final String VERSION = "1.0";
    private static final DateTimeFormatter TIMESTAMP =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final String appId;
    private final String gatewayUrl;
    private final String notifyUrl;
    private final String returnUrl;
    private final PrivateKey applicationPrivateKey;
    private final Clock clock;

    public AlipayCheckoutGateway(String appId, String gatewayUrl, String notifyUrl,
                                 String returnUrl, PrivateKey applicationPrivateKey, Clock clock) {
        this.appId = requireText(appId, "ELMOS_ALIPAY_APP_ID");
        this.gatewayUrl = requireHttps(gatewayUrl, "ELMOS_ALIPAY_GATEWAY_URL");
        this.notifyUrl = requireHttps(notifyUrl, "ELMOS_ALIPAY_NOTIFY_URL");
        this.returnUrl = requireHttps(returnUrl, "ELMOS_ALIPAY_RETURN_URL");
        if (applicationPrivateKey == null) {
            throw new IllegalArgumentException("ELMOS_ALIPAY_PRIVATE_KEY_FILE 未加载");
        }
        this.applicationPrivateKey = applicationPrivateKey;
        this.clock = clock == null ? Clock.systemDefaultZone() : clock;
    }

    @Override
    public PaymentProvider provider() {
        return PaymentProvider.ALIPAY_CHECKOUT;
    }

    /**
     * 支付宝电脑网站支付下单<b>不发任何网络请求</b>：产物就是一个带签名的跳转 URL。
     * 因此 {@link #prepare} 失败时可以确定提供方那边什么都没发生。
     */
    @Override
    public boolean contactsProviderDuringPrepare() {
        return false;
    }

    @Override
    public PaymentProviderRouter.CheckoutHandoff prepare(String outTradeNo, long amountFen,
                                                         String subject) {
        Map<String, String> parameters = publicParameters(outTradeNo, amountFen, subject);
        String content = AlipaySignatureVerifier.canonicalContent(parameters);
        parameters.put("sign", sign(content));
        return new PaymentProviderRouter.CheckoutHandoff(
                provider(), gatewayUrl + "?" + urlEncoded(parameters), null);
    }

    /**
     * 构造待签名的公共参数（不含 sign）。单独暴露以便测试与排障：
     * 签名不过时可以直接比对这份参数，而不是靠猜。
     */
    public Map<String, String> publicParameters(String outTradeNo, long amountFen,
                                                String subject) {
        requireText(outTradeNo, "outTradeNo");
        requireText(subject, "subject");
        // 金额换算在这里失败关闭：0、负数、超上限一律拒绝
        String totalAmount = MoneyConversion.toAlipayYuan(amountFen);

        Map<String, String> parameters = new TreeMap<>();
        parameters.put("app_id", appId);
        parameters.put("method", METHOD);
        parameters.put("charset", CHARSET);
        parameters.put("sign_type", SIGN_TYPE);
        parameters.put("timestamp", LocalDateTime.now(clock).format(TIMESTAMP));
        parameters.put("version", VERSION);
        parameters.put("notify_url", notifyUrl);
        parameters.put("return_url", returnUrl);
        parameters.put("biz_content", bizContent(outTradeNo, totalAmount, subject));
        return parameters;
    }

    private static String bizContent(String outTradeNo, String totalAmount, String subject) {
        // 手写最小 JSON：只有四个已知字段，且全部经过校验，无需引入序列化库
        return "{\"out_trade_no\":\"" + jsonEscape(outTradeNo)
                + "\",\"total_amount\":\"" + totalAmount
                + "\",\"subject\":\"" + jsonEscape(subject)
                + "\",\"product_code\":\"" + PRODUCT_CODE + "\"}";
    }

    private String sign(String content) {
        try {
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(applicationPrivateKey);
            signer.update(content.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(signer.sign());
        } catch (GeneralSecurityException failure) {
            // 签名失败是配置或密钥问题，不是可重试的临时故障
            throw new IllegalStateException("支付宝下单签名失败", failure);
        }
    }

    private static String urlEncoded(Map<String, String> parameters) {
        StringBuilder builder = new StringBuilder();
        for (Map.Entry<String, String> entry : new LinkedHashMap<>(parameters).entrySet()) {
            if (builder.length() > 0) {
                builder.append('&');
            }
            builder.append(java.net.URLEncoder.encode(entry.getKey(), StandardCharsets.UTF_8))
                    .append('=')
                    .append(java.net.URLEncoder.encode(entry.getValue(), StandardCharsets.UTF_8));
        }
        return builder.toString();
    }

    private static String jsonEscape(String value) {
        StringBuilder builder = new StringBuilder(value.length() + 8);
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> builder.append("\\\"");
                case '\\' -> builder.append("\\\\");
                case '\n' -> builder.append("\\n");
                case '\r' -> builder.append("\\r");
                case '\t' -> builder.append("\\t");
                default -> {
                    if (character < 0x20) {
                        builder.append(String.format("\\u%04x", (int) character));
                    } else {
                        builder.append(character);
                    }
                }
            }
        }
        return builder.toString();
    }

    private static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " 未配置");
        }
        return value;
    }

    private static String requireHttps(String value, String name) {
        requireText(value, name);
        if (!value.startsWith("https://")) {
            throw new IllegalArgumentException(
                    name + " 必须是 HTTPS 地址（且需为已备案域名）: " + value);
        }
        return value;
    }
}
