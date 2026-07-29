import io.elmos.commercialadapter.payment.AlipaySignatureVerifier;
import io.elmos.commercialadapter.payment.MoneyConversion;
import io.elmos.commercialadapter.payment.WechatPayCallbackCipher;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * 支付加密与金额换算的自检。可独立编译运行，不依赖 Spring、JUnit 或任何第三方库：
 *
 * <pre>
 *   javac -d out $(find . -name '*.java') && java -cp out PaymentCryptoSelfTest
 * </pre>
 *
 * 覆盖的是"错了会直接造成资损或长期挂账"的部分：金额单位换算、验签、回调解密。
 */
public final class PaymentCryptoSelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) throws Exception {
        moneyConversion();
        alipaySignature();
        wechatSignatureAndDecryption();

        System.out.println();
        System.out.printf("结果：%d 通过，%d 失败%n", passed, failed);
        if (failed > 0) {
            System.exit(1);
        }
    }

    // ---------------------------------------------------------------- 金额

    private static void moneyConversion() {
        section("金额换算（分 ↔ 元 / 分）");

        check("12900 分 -> 支付宝 129.00", "129.00".equals(MoneyConversion.toAlipayYuan(12900)));
        check("129000 分 -> 支付宝 1290.00", "1290.00".equals(MoneyConversion.toAlipayYuan(129000)));
        check("1 分 -> 支付宝 0.01", "0.01".equals(MoneyConversion.toAlipayYuan(1)));
        check("99 分 -> 支付宝 0.99", "0.99".equals(MoneyConversion.toAlipayYuan(99)));
        check("100 分 -> 支付宝 1.00", "1.00".equals(MoneyConversion.toAlipayYuan(100)));
        check("105 分 -> 支付宝 1.05（不是 1.5）", "1.05".equals(MoneyConversion.toAlipayYuan(105)));
        check("12900 分 -> 微信 12900", MoneyConversion.toWechatFen(12900) == 12900);

        check("0 分被拒", throwsIllegalArgument(() -> MoneyConversion.toAlipayYuan(0)));
        check("负数被拒", throwsIllegalArgument(() -> MoneyConversion.toAlipayYuan(-1)));
        check("超上限被拒", throwsIllegalArgument(() -> MoneyConversion.toAlipayYuan(20_000_000_000L)));

        check("回调 129.00 -> 12900", MoneyConversion.fromAlipayYuan("129.00") == 12900);
        check("回调 0.01 -> 1", MoneyConversion.fromAlipayYuan("0.01") == 1);
        check("回调 129 -> 12900（纯整数）", MoneyConversion.fromAlipayYuan("129") == 12900);
        check("三位小数被拒", throwsIllegalArgument(() -> MoneyConversion.fromAlipayYuan("129.000")));
        check("一位小数被拒", throwsIllegalArgument(() -> MoneyConversion.fromAlipayYuan("129.0")));
        check("带空白被拒", throwsIllegalArgument(() -> MoneyConversion.fromAlipayYuan(" 129.00")));
        check("科学计数法被拒", throwsIllegalArgument(() -> MoneyConversion.fromAlipayYuan("1.29e2")));
        check("负号被拒", throwsIllegalArgument(() -> MoneyConversion.fromAlipayYuan("-129.00")));

        // 往返一致性：全量遍历 0.01–99.99，再抽查大额
        boolean roundTrip = true;
        for (long fen = 1; fen <= 9999; fen++) {
            if (MoneyConversion.fromAlipayYuan(MoneyConversion.toAlipayYuan(fen)) != fen) {
                roundTrip = false;
                break;
            }
        }
        for (long fen : new long[] {12900, 129000, 100000, 999999, 1000000}) {
            if (MoneyConversion.fromAlipayYuan(MoneyConversion.toAlipayYuan(fen)) != fen) {
                roundTrip = false;
            }
        }
        check("1–9999 分及大额往返一致（浮点实现会在这里挂）", roundTrip);

        check("金额比对：相等通过", MoneyConversion.matchesExpected(12900, 12900));
        check("金额比对：差一分即拒", !MoneyConversion.matchesExpected(12900, 12899));
    }

    // -------------------------------------------------------------- 支付宝

    private static void alipaySignature() throws Exception {
        section("支付宝 RSA2 验签");

        KeyPair keyPair = rsaKeyPair();
        AlipaySignatureVerifier verifier = new AlipaySignatureVerifier(keyPair.getPublic());

        Map<String, String> notify = new LinkedHashMap<>();
        notify.put("trade_status", "TRADE_SUCCESS");
        notify.put("out_trade_no", "elmos-order-0001");
        notify.put("total_amount", "129.00");
        notify.put("app_id", "2021000000000000");
        notify.put("empty_field", "");
        notify.put("sign_type", "RSA2");

        String content = AlipaySignatureVerifier.canonicalContent(notify);
        String expectedContent = "app_id=2021000000000000&out_trade_no=elmos-order-0001"
                + "&total_amount=129.00&trade_status=TRADE_SUCCESS";
        check("待验签串按参数名升序", expectedContent.equals(content));
        check("空值参数被剔除", !content.contains("empty_field"));
        check("sign_type 被剔除", !content.contains("sign_type"));

        notify.put("sign", sign(keyPair.getPrivate(), content));
        check("合法签名通过", verifier.verify(notify));

        Map<String, String> tampered = new LinkedHashMap<>(notify);
        tampered.put("total_amount", "0.01");
        check("金额被篡改 -> 验签失败", !verifier.verify(tampered));

        Map<String, String> reordered = new TreeMap<>(notify);
        check("参数顺序变化不影响结果（规范化生效）", verifier.verify(reordered));

        Map<String, String> noSign = new LinkedHashMap<>(notify);
        noSign.remove("sign");
        check("缺签名 -> 拒绝", !verifier.verify(noSign));

        Map<String, String> badBase64 = new LinkedHashMap<>(notify);
        badBase64.put("sign", "!!!not-base64!!!");
        check("签名非 Base64 -> 拒绝（不抛异常）", !verifier.verify(badBase64));

        Map<String, String> sha1 = new LinkedHashMap<>(notify);
        sha1.put("sign_type", "RSA");
        check("sign_type=RSA（SHA1）-> 拒绝", !verifier.verify(sha1));

        AlipaySignatureVerifier otherKey = new AlipaySignatureVerifier(rsaKeyPair().getPublic());
        check("换一把公钥 -> 验签失败", !otherKey.verify(notify));

        check("null 参数 -> 拒绝", !verifier.verify(null));
    }

    // -------------------------------------------------------------- 微信支付

    private static void wechatSignatureAndDecryption() throws Exception {
        section("微信支付 APIv3 验签与回调解密");

        KeyPair platform = rsaKeyPair();
        byte[] apiV3Key = new byte[32];
        new SecureRandom().nextBytes(apiV3Key);
        WechatPayCallbackCipher cipher = new WechatPayCallbackCipher(platform.getPublic(), apiV3Key);

        String timestamp = "1793923200";
        String nonce = "8f3c1a2b4d5e6f70";
        String body = "{\"id\":\"evt-0001\",\"event_type\":\"TRANSACTION.SUCCESS\"}";
        String message = timestamp + "\n" + nonce + "\n" + body + "\n";
        String signature = sign(platform.getPrivate(), message);

        check("合法回调签名通过", cipher.verify(timestamp, nonce, body, signature));
        check("body 被改一个字符 -> 失败",
                !cipher.verify(timestamp, nonce, body.replace("evt-0001", "evt-0002"), signature));
        check("timestamp 被改 -> 失败", !cipher.verify("1793923201", nonce, body, signature));
        check("nonce 被改 -> 失败", !cipher.verify(timestamp, "0000000000000000", body, signature));
        check("缺签名 -> 拒绝", !cipher.verify(timestamp, nonce, body, null));
        check("签名非 Base64 -> 拒绝", !cipher.verify(timestamp, nonce, body, "@@@"));

        WechatPayCallbackCipher wrongKey =
                new WechatPayCallbackCipher(rsaKeyPair().getPublic(), apiV3Key);
        check("换一把平台公钥 -> 失败", !wrongKey.verify(timestamp, nonce, body, signature));

        // --- AES-256-GCM 回调解密 ---
        String plaintext = "{\"out_trade_no\":\"elmos-order-0001\",\"amount\":{\"total\":12900}}";
        String aad = "transaction";
        String gcmNonce = "abcdefghijkl";           // 12 字节
        String encrypted = aesGcmEncrypt(apiV3Key, gcmNonce, aad, plaintext);

        check("解密还原明文", plaintext.equals(cipher.decryptResource(aad, gcmNonce, encrypted)));
        check("AAD 不匹配 -> 抛异常（不是返回空串）",
                throwsAny(() -> cipher.decryptResource("wrong-aad", gcmNonce, encrypted)));
        check("密文被篡改 -> 抛异常",
                throwsAny(() -> cipher.decryptResource(aad, gcmNonce, flipLastByte(encrypted))));
        check("nonce 长度错 -> 抛异常",
                throwsAny(() -> cipher.decryptResource(aad, "short", encrypted)));
        check("密文非 Base64 -> 抛异常",
                throwsAny(() -> cipher.decryptResource(aad, gcmNonce, "@@@")));

        WechatPayCallbackCipher wrongApiKey = new WechatPayCallbackCipher(
                platform.getPublic(), new byte[32]);
        check("APIv3 密钥错 -> 抛异常",
                throwsAny(() -> wrongApiKey.decryptResource(aad, gcmNonce, encrypted)));

        check("APIv3 密钥长度非 32 -> 构造即拒绝",
                throwsIllegalArgument(() ->
                        new WechatPayCallbackCipher(platform.getPublic(), new byte[16])));
    }

    // ---------------------------------------------------------------- 工具

    private static KeyPair rsaKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String sign(PrivateKey key, String content) throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(content.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signer.sign());
    }

    private static String aesGcmEncrypt(byte[] key, String nonce, String aad, String plaintext)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"),
                new GCMParameterSpec(128, nonce.getBytes(StandardCharsets.UTF_8)));
        cipher.updateAAD(aad.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder()
                .encodeToString(cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8)));
    }

    private static String flipLastByte(String base64) {
        byte[] raw = Base64.getDecoder().decode(base64);
        raw[raw.length - 1] ^= 0x01;
        return Base64.getEncoder().encodeToString(raw);
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
