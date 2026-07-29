import io.elmos.commercialadapter.payment.AlipayCheckoutGateway;
import io.elmos.commercialadapter.payment.AlipaySignatureVerifier;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import io.elmos.commercialadapter.payment.WechatPayNativeGateway;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Base64;
import java.util.Map;

/** 下单网关的请求构造与签名自检。 */
public final class CheckoutGatewaySelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) throws Exception {
        alipay();
        wechat();

        System.out.println();
        System.out.printf("结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) {
            System.exit(1);
        }
    }

    private static void alipay() throws Exception {
        section("支付宝下单");

        KeyPair keys = rsa();
        Clock fixed = Clock.fixed(Instant.parse("2026-09-01T02:03:04Z"), ZoneId.of("UTC"));
        AlipayCheckoutGateway gateway = new AlipayCheckoutGateway(
                "2021000000000000", "https://openapi.alipay.com/gateway.do",
                "https://pay.example.cn/callbacks/alipay",
                "https://pay.example.cn/pricing", keys.getPrivate(), fixed);

        check("provider 正确", gateway.provider() == PaymentProvider.ALIPAY_CHECKOUT);

        Map<String, String> params = gateway.publicParameters("elmos-order-1", 12900, "专业月付");
        check("金额写入 biz_content 且为元（129.00）",
                params.get("biz_content").contains("\"total_amount\":\"129.00\""));
        check("biz_content 含订单号", params.get("biz_content").contains("elmos-order-1"));
        check("sign_type 为 RSA2", "RSA2".equals(params.get("sign_type")));
        check("timestamp 使用注入时钟",
                "2026-09-01 02:03:04".equals(params.get("timestamp")));
        check("参数里不含 sign", !params.containsKey("sign"));

        // 用与验签完全相同的规范化规则签名 -> 自洽
        String content = AlipaySignatureVerifier.canonicalContent(params);
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(keys.getPrivate());
        signer.update(content.getBytes(StandardCharsets.UTF_8));
        String signature = Base64.getEncoder().encodeToString(signer.sign());

        java.util.Map<String, String> verifiable = new java.util.LinkedHashMap<>(params);
        verifiable.put("sign", signature);
        check("下单参数能被自家验签器验过（签名/验签规则一致）",
                new AlipaySignatureVerifier(keys.getPublic()).verify(verifiable));

        PaymentProviderRouter.CheckoutHandoff handoff =
                gateway.prepare("elmos-order-1", 12900, "专业月付");
        check("产出跳转 URL 而不是二维码",
                handoff.redirectUrl() != null && handoff.qrCodeUrl() == null);
        check("跳转 URL 指向网关",
                handoff.redirectUrl().startsWith("https://openapi.alipay.com/gateway.do?"));
        check("跳转 URL 已 URL 编码（中文标题不裸奔）",
                !handoff.redirectUrl().contains("专业月付"));
        check("跳转 URL 含签名", handoff.redirectUrl().contains("sign="));

        check("金额为 0 -> 拒绝",
                throwsIllegalArgument(() -> gateway.publicParameters("o", 0, "s")));
        check("金额为负 -> 拒绝",
                throwsIllegalArgument(() -> gateway.publicParameters("o", -1, "s")));
        check("订单号为空 -> 拒绝",
                throwsIllegalArgument(() -> gateway.publicParameters("", 12900, "s")));
        check("标题含引号被转义（不破坏 JSON）",
                gateway.publicParameters("o", 12900, "a\"b").get("biz_content")
                        .contains("a\\\"b"));

        check("回调地址非 HTTPS -> 构造即拒绝", throwsIllegalArgument(() ->
                new AlipayCheckoutGateway("app", "https://g", "http://insecure",
                        "https://r", keys.getPrivate(), fixed)));
        check("私钥未加载 -> 构造即拒绝", throwsIllegalArgument(() ->
                new AlipayCheckoutGateway("app", "https://g", "https://n",
                        "https://r", null, fixed)));
    }

    private static void wechat() throws Exception {
        section("微信支付 Native 下单");

        KeyPair keys = rsa();
        final String[] captured = new String[3];
        WechatPayNativeGateway.HttpTransport transport = (url, authorization, body) -> {
            captured[0] = url;
            captured[1] = authorization;
            captured[2] = body;
            return "{\"code_url\":\"weixin://wxpay/bizpayurl?pr=ABC123\"}";
        };
        WechatPayNativeGateway gateway = new WechatPayNativeGateway(
                "1900000109", "wx8888888888888888", "5157F09EFDC096DE15EBE81A47059FE7",
                "https://pay.example.cn/callbacks/wechat", keys.getPrivate(), transport);

        String body = gateway.requestBody("elmos-order-2", 12900, "专业月付");
        check("金额为分且是整数（12900，不是 129.00）",
                body.contains("\"total\":12900") && !body.contains("129.00"));
        check("币种为 CNY", body.contains("\"currency\":\"CNY\""));
        check("含订单号与回调地址",
                body.contains("elmos-order-2") && body.contains("callbacks/wechat"));

        String auth = gateway.authorization("POST", "/v3/pay/transactions/native",
                "1793923200", "NONCE123", body);
        check("Authorization 使用 WECHATPAY2-SHA256-RSA2048",
                auth.startsWith("WECHATPAY2-SHA256-RSA2048 "));
        check("含 mchid / nonce_str / signature / timestamp / serial_no",
                auth.contains("mchid=\"1900000109\"") && auth.contains("nonce_str=\"NONCE123\"")
                        && auth.contains("signature=\"") && auth.contains("timestamp=\"1793923200\"")
                        && auth.contains("serial_no=\"5157F09EFDC096DE15EBE81A47059FE7\""));

        // 五段签名串（每段后换行，含最后一段）
        String expected = "POST\n/v3/pay/transactions/native\n1793923200\nNONCE123\n" + body + "\n";
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(keys.getPublic());
        verifier.update(expected.getBytes(StandardCharsets.UTF_8));
        String signature = auth.substring(auth.indexOf("signature=\"") + 11);
        signature = signature.substring(0, signature.indexOf('"'));
        check("签名对的是「方法\\n路径\\n时间戳\\n随机串\\n体\\n」五段串",
                verifier.verify(Base64.getDecoder().decode(signature)));

        check("传完整 URL 而不是路径 -> 拒绝", throwsIllegalArgument(() ->
                gateway.authorization("POST", "https://api.mch.weixin.qq.com/v3/pay",
                        "1", "n", body)));

        PaymentProviderRouter.CheckoutHandoff handoff =
                gateway.prepare("elmos-order-2", 12900, "专业月付");
        check("产出二维码而不是跳转 URL",
                handoff.qrCodeUrl() != null && handoff.redirectUrl() == null);
        check("code_url 取自响应",
                "weixin://wxpay/bizpayurl?pr=ABC123".equals(handoff.qrCodeUrl()));
        check("请求发往 native 接口",
                "https://api.mch.weixin.qq.com/v3/pay/transactions/native".equals(captured[0]));

        check("响应缺 code_url -> 抛异常（不返回空串）", throwsAny(() ->
                WechatPayNativeGateway.extractCodeUrl("{\"code\":\"PARAM_ERROR\"}")));
        check("响应 code_url 为空 -> 抛异常", throwsAny(() ->
                WechatPayNativeGateway.extractCodeUrl("{\"code_url\":\"\"}")));
        check("响应为 null -> 抛异常",
                throwsAny(() -> WechatPayNativeGateway.extractCodeUrl(null)));

        WechatPayNativeGateway failing = new WechatPayNativeGateway(
                "1900000109", "wx", "SERIAL", "https://pay.example.cn/cb",
                keys.getPrivate(), (url, authorization, requestBody) -> {
                    throw new java.io.IOException("connect timeout");
                });
        check("下单调用失败 -> 抛异常（由上层开对账案件，不盲重试）",
                throwsAny(() -> failing.prepare("o", 12900, "s")));

        check("回调地址非 HTTPS -> 构造即拒绝", throwsIllegalArgument(() ->
                new WechatPayNativeGateway("m", "a", "s", "http://x",
                        keys.getPrivate(), transport)));
        check("HttpTransport 未注入 -> 构造即拒绝", throwsIllegalArgument(() ->
                new WechatPayNativeGateway("m", "a", "s", "https://x",
                        keys.getPrivate(), null)));
    }

    // ---------------------------------------------------------------- 工具

    private static KeyPair rsa() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

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
