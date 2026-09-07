import io.elmos.commercialadapter.payment.AlipayCallbackAdapter;
import io.elmos.commercialadapter.payment.AlipaySignatureVerifier;
import io.elmos.commercialadapter.payment.CallbackReplayGuard;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.LocalOrder;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.NormalizedCallback;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.Outcome;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.RawCallback;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.WechatPayCallbackAdapter;
import io.elmos.commercialadapter.payment.WechatPayCallbackCipher;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;

/**
 * 两个真实回调适配器 + 管线新增两步的自检。
 *
 * <p>用真的 RSA 密钥对和真的 AES-256-GCM 加密，不打桩验签也不打桩解密：
 * 这两处正是"看起来对、实际上不对"最容易发生的地方。
 */
public final class CallbackAdapterSelfTest {

    private static int passed;
    private static int failed;

    private static final String APP_ID = "2021000000000000";
    private static final String MCH_ID = "1900000109";
    private static final ZoneId SHANGHAI = ZoneId.of("Asia/Shanghai");
    private static final DateTimeFormatter NOTIFY_TIME =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    /** 固定"现在"：2026-09-01T04:00:00Z = 北京时间 12:00:00 */
    private static final Instant NOW = Instant.parse("2026-09-01T04:00:00Z");
    private static final Clock FIXED = Clock.fixed(NOW, ZoneOffset.UTC);

    private static KeyPair alipayKeys;
    private static byte[] apiV3Key;
    private static KeyPair wechatKeys;

    public static void main(String[] args) throws Exception {
        alipayKeys = KeyPairGenerator.getInstance("RSA").generateKeyPair();
        wechatKeys = KeyPairGenerator.getInstance("RSA").generateKeyPair();
        apiV3Key = "0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8);

        alipayRejectsForeignAppId();
        alipayAcceptsOwnValidNotification();
        alipayTimestampWindow();
        alipayNormalisesTheRightFields();
        alipayTradeStatusGate();
        alipayVerifyNeverThrows();

        wechatVerifyNeverThrowsOnMissingHeaders();
        wechatRejectsForeignMerchant();
        wechatRejectsNonCnyCurrency();
        wechatNormalisesTheRightFields();
        wechatTradeStateGate();

        pipelineRejectsStaleTimestampBeforeVerifying();
        pipelineRecordsButDoesNotActivateNonSuccess();

        System.out.println();
        System.out.println("结果：" + passed + " 通过，" + failed + " 失败");
        if (failed > 0) {
            System.exit(1);
        }
    }

    // =======================================================================
    // 支付宝
    // =======================================================================

    /**
     * 这条是本组最重要的断言。
     *
     * <p>支付宝的通知由<b>支付宝的私钥</b>签名，公钥全体商户共用。
     * 下面这份报文的签名是<b>真的</b>——用同一把私钥、同一套规范化规则签出来的，
     * 只是 {@code app_id} 是别人的。若不校验归属，它会验签通过。
     */
    private static void alipayRejectsForeignAppId() throws Exception {
        Map<String, String> parameters = alipayNotification("TRADE_SUCCESS", "129.00");
        parameters.put("app_id", "2099999999999999");   // 别的商户
        sign(parameters);

        AlipayCallbackAdapter adapter = alipayAdapter();
        check("支付宝：签名真实但 app_id 是别人的 -> 拒绝",
                !adapter.verifySignature(rawAlipay(parameters)));

        // 反证：同一份报文换回我们的 app_id 并重签，必须通过。
        // 少了这个反证，上一条断言可能只是因为"什么都验不过"而侥幸成立。
        parameters.put("app_id", APP_ID);
        sign(parameters);
        check("支付宝：换回自家 app_id 并重签 -> 通过",
                adapter.verifySignature(rawAlipay(parameters)));
    }

    private static void alipayAcceptsOwnValidNotification() throws Exception {
        Map<String, String> parameters = alipayNotification("TRADE_SUCCESS", "129.00");
        sign(parameters);
        check("支付宝：自家合法通知 -> 验签通过",
                alipayAdapter().verifySignature(rawAlipay(parameters)));

        // 篡改金额后签名必然失效
        parameters.put("total_amount", "0.01");
        check("支付宝：改了金额没重签 -> 验签失败",
                !alipayAdapter().verifySignature(rawAlipay(parameters)));
    }

    private static void alipayTimestampWindow() {
        AlipayCallbackAdapter adapter = alipayAdapter();

        Map<String, String> now = alipayNotification("TRADE_SUCCESS", "129.00");
        check("支付宝时间窗：当前时间 -> 接受", adapter.acceptsTimestamp(rawAlipay(now)));

        Map<String, String> old = alipayNotification("TRADE_SUCCESS", "129.00");
        old.put("notify_time", LocalDateTime.ofInstant(NOW.minusSeconds(600), SHANGHAI)
                .format(NOTIFY_TIME));
        check("支付宝时间窗：10 分钟前 -> 拒绝（陈旧重放）",
                !adapter.acceptsTimestamp(rawAlipay(old)));

        Map<String, String> future = alipayNotification("TRADE_SUCCESS", "129.00");
        future.put("notify_time", LocalDateTime.ofInstant(NOW.plusSeconds(600), SHANGHAI)
                .format(NOTIFY_TIME));
        check("支付宝时间窗：10 分钟后 -> 拒绝（未来时间戳会延长重放窗口）",
                !adapter.acceptsTimestamp(rawAlipay(future)));

        Map<String, String> missing = alipayNotification("TRADE_SUCCESS", "129.00");
        missing.remove("notify_time");
        check("支付宝时间窗：缺 notify_time -> 拒绝",
                !adapter.acceptsTimestamp(rawAlipay(missing)));

        Map<String, String> malformed = alipayNotification("TRADE_SUCCESS", "129.00");
        malformed.put("notify_time", "昨天下午");
        check("支付宝时间窗：格式非法 -> 拒绝",
                !adapter.acceptsTimestamp(rawAlipay(malformed)));

        // 时区必须按北京时间解析。若误按 UTC 解析，同一串会偏移 8 小时而被判陈旧。
        Map<String, String> beijing = alipayNotification("TRADE_SUCCESS", "129.00");
        beijing.put("notify_time", "2026-09-01 12:00:00");   // 北京时间 = NOW
        check("支付宝时间窗：notify_time 按 Asia/Shanghai 解析",
                adapter.acceptsTimestamp(rawAlipay(beijing)));
    }

    private static void alipayNormalisesTheRightFields() {
        Map<String, String> parameters = alipayNotification("TRADE_SUCCESS", "129.00");
        parameters.put("receipt_amount", "99.00");   // 有优惠时实收小于订单金额
        NormalizedCallback callback = alipayAdapter().normalize(rawAlipay(parameters));

        check("支付宝归一化：通道正确",
                callback.provider() == PaymentProvider.ALIPAY_CHECKOUT);
        check("支付宝归一化：事件 ID 取 notify_id（不是 trade_no）",
                "notify-1".equals(callback.providerEventId()));
        check("支付宝归一化：订单号取 out_trade_no", "order-1".equals(callback.outTradeNo()));
        check("支付宝归一化：金额取 total_amount 而非 receipt_amount（否则有券必误报金额不符）",
                callback.amountFen() == 12900);
        check("支付宝归一化：状态原样带出", "TRADE_SUCCESS".equals(callback.tradeStatus()));

        Map<String, String> noNotifyId = alipayNotification("TRADE_SUCCESS", "129.00");
        noNotifyId.remove("notify_id");
        boolean threw = false;
        try {
            alipayAdapter().normalize(rawAlipay(noNotifyId));
        } catch (IllegalStateException expected) {
            threw = true;
        }
        check("支付宝归一化：缺 notify_id -> 抛异常（不得编一个幂等键）", threw);
    }

    private static void alipayTradeStatusGate() {
        AlipayCallbackAdapter adapter = alipayAdapter();
        check("TRADE_SUCCESS -> 激活", adapter.indicatesPaymentSuccess(status("TRADE_SUCCESS")));
        check("TRADE_FINISHED -> 激活", adapter.indicatesPaymentSuccess(status("TRADE_FINISHED")));
        check("WAIT_BUYER_PAY -> 不激活（还没付钱）",
                !adapter.indicatesPaymentSuccess(status("WAIT_BUYER_PAY")));
        check("TRADE_CLOSED -> 不激活（超时关闭或已全额退款）",
                !adapter.indicatesPaymentSuccess(status("TRADE_CLOSED")));
        check("未知状态 -> 不激活（默认不放行）",
                !adapter.indicatesPaymentSuccess(status("SOMETHING_NEW")));
    }

    /** 接口约定 verifySignature 不得抛异常：抛出会变成 500，让提供方以为是我们故障。 */
    private static void alipayVerifyNeverThrows() {
        AlipayCallbackAdapter adapter = alipayAdapter();
        boolean threw = false;
        try {
            adapter.verifySignature(new RawCallback(
                    PaymentProvider.ALIPAY_CHECKOUT, "", Map.of(), Map.of()));
            adapter.verifySignature(new RawCallback(
                    PaymentProvider.ALIPAY_CHECKOUT, "", Map.of(),
                    Map.of("app_id", APP_ID, "sign", "!!!not base64!!!")));
        } catch (RuntimeException unexpected) {
            threw = true;
        }
        check("支付宝：空参数表与垃圾签名都不抛异常，只返回 false", !threw);
    }

    // =======================================================================
    // 微信支付
    // =======================================================================

    private static void wechatVerifyNeverThrowsOnMissingHeaders() {
        WechatPayCallbackAdapter adapter = wechatAdapter();
        boolean threw = false;
        boolean verified = true;
        try {
            verified = adapter.verifySignature(new RawCallback(
                    PaymentProvider.WECHAT_PAY_NATIVE, "{}", Map.of(), Map.of()));
        } catch (RuntimeException unexpected) {
            threw = true;
        }
        check("微信：缺请求头时不抛异常", !threw);
        check("微信：缺请求头时验签失败", !verified);
    }

    private static void wechatRejectsForeignMerchant() throws Exception {
        String body = wechatEnvelope(resourceJson("order-1", "SUCCESS", 12900, "1999999999", "CNY"));
        boolean threw = false;
        try {
            wechatAdapter().normalize(rawWechat(body));
        } catch (IllegalStateException expected) {
            threw = expected.getMessage().contains("mchid");
        }
        check("微信：mchid 是别人的 -> 拒绝处理", threw);
    }

    private static void wechatRejectsNonCnyCurrency() throws Exception {
        String body = wechatEnvelope(resourceJson("order-1", "SUCCESS", 12900, MCH_ID, "USD"));
        boolean threw = false;
        try {
            wechatAdapter().normalize(rawWechat(body));
        } catch (IllegalStateException expected) {
            threw = expected.getMessage().contains("CNY");
        }
        check("微信：币种非 CNY -> 拒绝（不能按面值当人民币记账）", threw);
    }

    private static void wechatNormalisesTheRightFields() throws Exception {
        String body = wechatEnvelope(resourceJson("order-1", "SUCCESS", 12900, MCH_ID, "CNY"));
        NormalizedCallback callback = wechatAdapter().normalize(rawWechat(body));

        check("微信归一化：通道正确",
                callback.provider() == PaymentProvider.WECHAT_PAY_NATIVE);
        check("微信归一化：事件 ID 取外层 id（不是 transaction_id）",
                "evt-outer-1".equals(callback.providerEventId()));
        check("微信归一化：订单号来自解密后的明文", "order-1".equals(callback.outTradeNo()));
        check("微信归一化：金额单位是分，直接取 amount.total",
                callback.amountFen() == 12900);
        check("微信归一化：状态取 trade_state", "SUCCESS".equals(callback.tradeStatus()));
    }

    private static void wechatTradeStateGate() {
        WechatPayCallbackAdapter adapter = wechatAdapter();
        check("微信 SUCCESS -> 激活", adapter.indicatesPaymentSuccess(status("SUCCESS")));
        check("微信 REFUND -> 不激活（已退款，激活等于白送）",
                !adapter.indicatesPaymentSuccess(status("REFUND")));
        check("微信 CLOSED -> 不激活", !adapter.indicatesPaymentSuccess(status("CLOSED")));
        check("微信 PAYERROR -> 不激活", !adapter.indicatesPaymentSuccess(status("PAYERROR")));
    }

    // =======================================================================
    // 管线新增的两步
    // =======================================================================

    /** 时间窗不过时，验签根本不该被调用。 */
    private static void pipelineRejectsStaleTimestampBeforeVerifying() {
        List<String> calls = new ArrayList<>();
        PaymentCallbackPipeline.ProviderAdapter adapter =
                new PaymentCallbackPipeline.ProviderAdapter() {
                    @Override
                    public boolean acceptsTimestamp(RawCallback raw) {
                        calls.add("acceptsTimestamp");
                        return false;
                    }

                    @Override
                    public boolean verifySignature(RawCallback raw) {
                        calls.add("verifySignature");
                        return true;
                    }

                    @Override
                    public NormalizedCallback normalize(RawCallback raw) {
                        calls.add("normalize");
                        return status("TRADE_SUCCESS");
                    }
                };

        Outcome outcome = pipeline(adapter, calls).process(new RawCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "{}", Map.of(), Map.of()));

        check("时间窗不过 -> STALE_TIMESTAMP", outcome == Outcome.STALE_TIMESTAMP);
        check("时间窗不过 -> 验签未被调用（省一次 RSA）",
                !calls.contains("verifySignature"));
        check("时间窗不过 -> 未归一化（未验签的报文不该被解析）",
                !calls.contains("normalize"));
        check("时间窗不过 -> 没有任何副作用",
                !calls.contains("record") && !calls.contains("activate"));
    }

    /** 关单/退款通知：事件要落库，订阅绝不能动。 */
    private static void pipelineRecordsButDoesNotActivateNonSuccess() {
        List<String> calls = new ArrayList<>();
        PaymentCallbackPipeline.ProviderAdapter adapter =
                new PaymentCallbackPipeline.ProviderAdapter() {
                    @Override
                    public boolean verifySignature(RawCallback raw) {
                        calls.add("verifySignature");
                        return true;
                    }

                    @Override
                    public NormalizedCallback normalize(RawCallback raw) {
                        return status("TRADE_CLOSED");
                    }

                    @Override
                    public boolean indicatesPaymentSuccess(NormalizedCallback callback) {
                        return "TRADE_SUCCESS".equals(callback.tradeStatus());
                    }
                };

        Outcome outcome = pipeline(adapter, calls).process(new RawCallback(
                PaymentProvider.ALIPAY_CHECKOUT, "{}", Map.of(), Map.of()));

        check("关单通知 -> NOT_A_PAYMENT_SUCCESS", outcome == Outcome.NOT_A_PAYMENT_SUCCESS);
        check("关单通知 -> 事件已落库（退款/关单必须留痕）", calls.contains("record"));
        check("关单通知 -> 订阅未被激活", !calls.contains("activate"));
        check("关单通知 -> 未开对账案件（这是正常事件，不是异常）",
                !calls.contains("openCase"));
    }

    // =======================================================================
    // 装配helpers
    // =======================================================================

    private static PaymentCallbackPipeline pipeline(
            PaymentCallbackPipeline.ProviderAdapter adapter, List<String> calls) {
        Set<String> seen = new HashSet<>();
        return new PaymentCallbackPipeline(
                adapter,
                key -> {
                    calls.add("registerIfAbsent");
                    return seen.add(key);
                },
                outTradeNo -> {
                    calls.add("findByOutTradeNo");
                    return Optional.of(new LocalOrder(
                            "order-1", "org-1", "elmos-pro-monthly", 12900));
                },
                (order, callback, body) -> calls.add("record"),
                (order, callback) -> calls.add("activate"),
                (reason, callback, order, detail) -> calls.add("openCase"));
    }

    private static AlipayCallbackAdapter alipayAdapter() {
        return new AlipayCallbackAdapter(
                new AlipaySignatureVerifier(alipayKeys.getPublic()),
                new CallbackReplayGuard(FIXED, Duration.ofMinutes(5)),
                APP_ID);
    }

    private static WechatPayCallbackAdapter wechatAdapter() {
        return new WechatPayCallbackAdapter(
                new WechatPayCallbackCipher(wechatKeys.getPublic(), apiV3Key),
                new CallbackReplayGuard(FIXED, Duration.ofMinutes(5)),
                new MinimalJsonReader(),
                MCH_ID);
    }

    private static Map<String, String> alipayNotification(String tradeStatus, String totalAmount) {
        Map<String, String> parameters = new TreeMap<>();
        parameters.put("app_id", APP_ID);
        parameters.put("notify_id", "notify-1");
        parameters.put("notify_type", "trade_status_sync");
        parameters.put("notify_time", LocalDateTime.ofInstant(NOW, SHANGHAI).format(NOTIFY_TIME));
        parameters.put("out_trade_no", "order-1");
        parameters.put("trade_no", "2026090122001400000000000001");
        parameters.put("trade_status", tradeStatus);
        parameters.put("total_amount", totalAmount);
        parameters.put("sign_type", "RSA2");
        return parameters;
    }

    private static void sign(Map<String, String> parameters) throws Exception {
        parameters.remove("sign");
        String content = AlipaySignatureVerifier.canonicalContent(parameters);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign((PrivateKey) alipayKeys.getPrivate());
        signer.update(content.getBytes(StandardCharsets.UTF_8));
        parameters.put("sign", Base64.getEncoder().encodeToString(signer.sign()));
    }

    private static RawCallback rawAlipay(Map<String, String> parameters) {
        return new RawCallback(PaymentProvider.ALIPAY_CHECKOUT, "",
                Map.of(), new HashMap<>(parameters));
    }

    private static RawCallback rawWechat(String body) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Wechatpay-Timestamp", Long.toString(NOW.getEpochSecond()));
        headers.put("Wechatpay-Nonce", "8f3c1a2b4d5e6f70");
        headers.put("Wechatpay-Signature", "c2ln");
        headers.put("Wechatpay-Serial", "SERIAL01");
        return new RawCallback(PaymentProvider.WECHAT_PAY_NATIVE, body, headers, Map.of());
    }

    private static String resourceJson(String outTradeNo, String tradeState, long total,
                                       String mchId, String currency) {
        return "{\"transaction_id\":\"4200001\",\"out_trade_no\":\"" + outTradeNo
                + "\",\"trade_state\":\"" + tradeState + "\",\"mchid\":\"" + mchId
                + "\",\"amount\":{\"total\":" + total + ",\"currency\":\"" + currency + "\"}}";
    }

    /** 用真实的 AES-256-GCM 加密出一份可解密的外层报文。 */
    private static String wechatEnvelope(String resourcePlaintext) throws Exception {
        String nonce = "abcdefghijkl";           // 12 字节
        String associatedData = "transaction";
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE,
                new SecretKeySpec(apiV3Key, "AES"),
                new GCMParameterSpec(128, nonce.getBytes(StandardCharsets.UTF_8)));
        cipher.updateAAD(associatedData.getBytes(StandardCharsets.UTF_8));
        String ciphertext = Base64.getEncoder().encodeToString(
                cipher.doFinal(resourcePlaintext.getBytes(StandardCharsets.UTF_8)));
        return "{\"id\":\"evt-outer-1\",\"event_type\":\"TRANSACTION.SUCCESS\","
                + "\"resource\":{\"algorithm\":\"AEAD_AES_256_GCM\",\"ciphertext\":\"" + ciphertext
                + "\",\"associated_data\":\"" + associatedData
                + "\",\"nonce\":\"" + nonce + "\",\"original_type\":\"transaction\"}}";
    }

    private static NormalizedCallback status(String tradeStatus) {
        return new NormalizedCallback(PaymentProvider.ALIPAY_CHECKOUT,
                "evt-1", "order-1", 12900, tradeStatus);
    }

    /**
     * 极简 JSON 读取，仅供本自检使用。
     *
     * <p><b>生产走的是 {@code JacksonWechatNotificationReader}。</b>
     * 这里手写是为了让本文件不依赖 Jackson（payment 包只依赖 JDK），
     * 而它能这么随便，正是因为输入是本文件自己构造的、格式已知的报文。
     */
    private static final class MinimalJsonReader
            implements WechatPayCallbackAdapter.NotificationReader {
        @Override
        public WechatPayCallbackAdapter.Envelope readEnvelope(String rawBody) {
            return new WechatPayCallbackAdapter.Envelope(
                    field(rawBody, "id"),
                    field(rawBody, "event_type"),
                    field(rawBody, "ciphertext"),
                    field(rawBody, "nonce"),
                    field(rawBody, "associated_data"));
        }

        @Override
        public WechatPayCallbackAdapter.Resource readResource(String plaintext) {
            return new WechatPayCallbackAdapter.Resource(
                    field(plaintext, "out_trade_no"),
                    field(plaintext, "transaction_id"),
                    field(plaintext, "trade_state"),
                    Long.parseLong(number(plaintext, "total")),
                    field(plaintext, "mchid"),
                    field(plaintext, "currency"));
        }

        private static String field(String json, String name) {
            String marker = "\"" + name + "\":\"";
            int start = json.indexOf(marker);
            if (start < 0) {
                throw new IllegalStateException("字段缺失: " + name);
            }
            start += marker.length();
            return json.substring(start, json.indexOf('"', start));
        }

        private static String number(String json, String name) {
            String marker = "\"" + name + "\":";
            int start = json.indexOf(marker) + marker.length();
            int end = start;
            while (end < json.length() && Character.isDigit(json.charAt(end))) {
                end++;
            }
            return json.substring(start, end);
        }
    }

    private static void check(String what, boolean condition) {
        if (condition) {
            passed++;
            System.out.println("  [PASS] " + what);
        } else {
            failed++;
            System.out.println("  [FAIL] " + what);
        }
    }
}
