package io.elmos.commercialadapter.payment;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Base64;
import java.util.HexFormat;

/**
 * 微信支付 Native（扫码）下单网关。
 *
 * <p>与支付宝不同，微信下单<b>必须由服务端发一次 HTTPS 请求</b>，
 * 拿回 {@code code_url} 交给前端渲染二维码。HTTP 发送经
 * {@link HttpTransport} 注入，因此请求构造与签名可以脱离网络单独验证——
 * 这两部分恰恰是最容易写错的。
 *
 * <p>APIv3 请求签名串是五段，<b>每段后面都有换行，包括最后一段</b>：
 *
 * <pre>
 *   HTTP方法\nURL路径\n时间戳\n随机串\n请求体\n
 * </pre>
 *
 * <p>少一个换行或把完整 URL（含域名）当成路径，都会得到 401，
 * 而错误信息不会告诉你是哪一种。
 */
public final class WechatPayNativeGateway implements PaymentProviderRouter.CheckoutGateway {

    private static final String HOST = "https://api.mch.weixin.qq.com";
    private static final String PATH = "/v3/pay/transactions/native";
    private static final String SCHEMA = "WECHATPAY2-SHA256-RSA2048";

    /** HTTP 发送端口。返回响应体文本；非 2xx 应抛异常。 */
    public interface HttpTransport {
        String post(String url, String authorization, String body) throws Exception;
    }

    private final String mchId;
    private final String appId;
    private final String certSerialNo;
    private final String notifyUrl;
    private final PrivateKey merchantPrivateKey;
    private final HttpTransport transport;
    private final SecureRandom random = new SecureRandom();

    public WechatPayNativeGateway(String mchId, String appId, String certSerialNo,
                                  String notifyUrl, PrivateKey merchantPrivateKey,
                                  HttpTransport transport) {
        this.mchId = requireText(mchId, "ELMOS_WECHATPAY_MCHID");
        this.appId = requireText(appId, "微信支付 appid");
        this.certSerialNo = requireText(certSerialNo, "ELMOS_WECHATPAY_CERT_SERIAL_NO");
        this.notifyUrl = requireHttps(notifyUrl, "ELMOS_WECHATPAY_NOTIFY_URL");
        if (merchantPrivateKey == null) {
            throw new IllegalArgumentException("ELMOS_WECHATPAY_PRIVATE_KEY_FILE 未加载");
        }
        this.merchantPrivateKey = merchantPrivateKey;
        if (transport == null) {
            throw new IllegalArgumentException("HttpTransport 未注入");
        }
        this.transport = transport;
    }

    @Override
    public PaymentProvider provider() {
        return PaymentProvider.WECHAT_PAY_NATIVE;
    }

    /**
     * 微信 Native 下单<b>必须</b>发一次 HTTPS 请求换 {@code code_url}。
     * 因此 {@link #prepare} 抛异常时，提供方那边可能已经建了单——必须进对账。
     */
    @Override
    public boolean contactsProviderDuringPrepare() {
        return true;
    }

    @Override
    public PaymentProviderRouter.CheckoutHandoff prepare(String outTradeNo, long amountFen,
                                                         String subject) {
        String body = requestBody(outTradeNo, amountFen, subject);
        String timestamp = Long.toString(System.currentTimeMillis() / 1000);
        String nonce = randomNonce();
        String authorization = authorization("POST", PATH, timestamp, nonce, body);

        String response;
        try {
            response = transport.post(HOST + PATH, authorization, body);
        } catch (Exception failure) {
            // 结果未知不得盲重试：上层应据此开对账案件
            throw new IllegalStateException("微信支付下单调用失败", failure);
        }
        String codeUrl = extractCodeUrl(response);
        return new PaymentProviderRouter.CheckoutHandoff(provider(), null, codeUrl);
    }

    /** 构造请求体。单独暴露以便测试。 */
    public String requestBody(String outTradeNo, long amountFen, String subject) {
        requireText(outTradeNo, "outTradeNo");
        requireText(subject, "subject");
        int total = MoneyConversion.toWechatFen(amountFen);   // 微信用「分」，整数
        return "{\"appid\":\"" + jsonEscape(appId)
                + "\",\"mchid\":\"" + jsonEscape(mchId)
                + "\",\"description\":\"" + jsonEscape(subject)
                + "\",\"out_trade_no\":\"" + jsonEscape(outTradeNo)
                + "\",\"notify_url\":\"" + jsonEscape(notifyUrl)
                + "\",\"amount\":{\"total\":" + total + ",\"currency\":\"CNY\"}}";
    }

    /**
     * 构造 Authorization 头。单独暴露：401 时可直接比对签名串，不必靠猜。
     */
    public String authorization(String method, String path, String timestamp, String nonce,
                                String body) {
        if (path == null || !path.startsWith("/")) {
            throw new IllegalArgumentException("签名用的必须是 URL 路径而不是完整地址: " + path);
        }
        String message = method + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + body + "\n";
        String signature = sign(message);
        return SCHEMA + " mchid=\"" + mchId + "\",nonce_str=\"" + nonce
                + "\",signature=\"" + signature + "\",timestamp=\"" + timestamp
                + "\",serial_no=\"" + certSerialNo + "\"";
    }

    /** 从响应中提取 code_url。缺失即失败，不返回空串。 */
    public static String extractCodeUrl(String response) {
        if (response == null) {
            throw new IllegalStateException("微信支付下单响应为空");
        }
        int keyIndex = response.indexOf("\"code_url\"");
        if (keyIndex < 0) {
            throw new IllegalStateException("微信支付下单响应缺少 code_url: " + response);
        }
        int start = response.indexOf('"', response.indexOf(':', keyIndex) + 1);
        int end = start < 0 ? -1 : response.indexOf('"', start + 1);
        if (start < 0 || end < 0) {
            throw new IllegalStateException("微信支付下单响应 code_url 格式非法: " + response);
        }
        String codeUrl = response.substring(start + 1, end);
        if (codeUrl.isEmpty()) {
            throw new IllegalStateException("微信支付下单响应 code_url 为空");
        }
        return codeUrl;
    }

    private String sign(String message) {
        try {
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(merchantPrivateKey);
            signer.update(message.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(signer.sign());
        } catch (GeneralSecurityException failure) {
            throw new IllegalStateException("微信支付请求签名失败", failure);
        }
    }

    private String randomNonce() {
        byte[] raw = new byte[16];
        random.nextBytes(raw);
        return HexFormat.of().withUpperCase().formatHex(raw);
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
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
