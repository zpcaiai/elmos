package io.elmos.commercialadapter.payment;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * 微信支付 APIv3 回调的验签与解密。
 *
 * <p>与支付宝的两点关键差异：
 *
 * <ul>
 *   <li>验签对象是<b>三段拼接串</b>：{@code timestamp\nnonce\nbody\n}（结尾也有换行），
 *       用<b>微信支付平台证书</b>的公钥验证，而不是商户自己的证书</li>
 *   <li>回调业务数据是<b>加密</b>的：AES-256-GCM，密钥为 APIv3 密钥（32 字节），
 *       {@code associated_data} 作为 AAD 参与认证，密文 Base64 内已含 16 字节认证标签</li>
 * </ul>
 *
 * <p><b>顺序不能反</b>：必须先验签通过，再解密。跳过验签直接解密，等于接受任何人构造的报文。
 *
 * <p><b>时间戳必须校验</b>：仅验签无法防重放。调用方还需检查 {@code timestamp}
 * 与当前时间的偏差（建议 ≤5 分钟），并对 {@code id} 做幂等去重。
 *
 * <p>只依赖 JDK，无第三方 SDK。
 */
public final class WechatPayCallbackCipher {

    private static final String SIGN_ALGORITHM = "SHA256withRSA";
    private static final String CIPHER_ALGORITHM = "AES/GCM/NoPadding";
    private static final int GCM_TAG_BITS = 128;
    private static final int NONCE_LENGTH = 12;
    private static final int API_V3_KEY_LENGTH = 32;

    private final PublicKey platformPublicKey;
    private final byte[] apiV3Key;

    /**
     * @param platformPublicKey 微信支付平台证书公钥
     * @param apiV3Key          APIv3 密钥，必须恰好 32 字节
     */
    public WechatPayCallbackCipher(PublicKey platformPublicKey, byte[] apiV3Key) {
        if (platformPublicKey == null) {
            throw new IllegalArgumentException("微信支付平台证书公钥未配置");
        }
        if (apiV3Key == null || apiV3Key.length != API_V3_KEY_LENGTH) {
            throw new IllegalArgumentException(
                    "APIv3 密钥必须为 " + API_V3_KEY_LENGTH + " 字节");
        }
        this.platformPublicKey = platformPublicKey;
        this.apiV3Key = apiV3Key.clone();
    }

    /**
     * 校验回调签名。任何异常一律 {@code false}。
     *
     * @param timestamp Wechatpay-Timestamp 头
     * @param nonce     Wechatpay-Nonce 头
     * @param body      原始请求体，必须是<b>未经任何解析或重新序列化</b>的字节对应文本
     * @param signature Wechatpay-Signature 头（Base64）
     */
    public boolean verify(String timestamp, String nonce, String body, String signature) {
        if (timestamp == null || nonce == null || body == null
                || signature == null || signature.isEmpty()) {
            return false;
        }
        byte[] signatureBytes;
        try {
            signatureBytes = Base64.getDecoder().decode(signature);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }
        String message = timestamp + "\n" + nonce + "\n" + body + "\n";
        try {
            Signature verifier = Signature.getInstance(SIGN_ALGORITHM);
            verifier.initVerify(platformPublicKey);
            verifier.update(message.getBytes(StandardCharsets.UTF_8));
            return verifier.verify(signatureBytes);
        } catch (GeneralSecurityException failure) {
            return false;
        }
    }

    /**
     * 解密回调中的 {@code resource} 字段。
     *
     * <p>只有在 {@link #verify} 返回 {@code true} 之后才允许调用。
     * 解密失败（密钥错、AAD 不匹配、密文被篡改）会抛异常而不是返回空字符串——
     * 返回空值会让调用方误以为"业务数据为空"，从而走进错误的分支。
     *
     * @throws GeneralSecurityException 认证失败或参数非法
     */
    public String decryptResource(String associatedData, String nonce, String ciphertextBase64)
            throws GeneralSecurityException {
        if (nonce == null || nonce.getBytes(StandardCharsets.UTF_8).length != NONCE_LENGTH) {
            throw new GeneralSecurityException("nonce 必须为 " + NONCE_LENGTH + " 字节");
        }
        if (ciphertextBase64 == null || ciphertextBase64.isEmpty()) {
            throw new GeneralSecurityException("密文为空");
        }
        byte[] ciphertext;
        try {
            ciphertext = Base64.getDecoder().decode(ciphertextBase64);
        } catch (IllegalArgumentException invalidBase64) {
            throw new GeneralSecurityException("密文不是合法 Base64", invalidBase64);
        }

        Cipher cipher = Cipher.getInstance(CIPHER_ALGORITHM);
        cipher.init(
                Cipher.DECRYPT_MODE,
                new SecretKeySpec(apiV3Key, "AES"),
                new GCMParameterSpec(GCM_TAG_BITS, nonce.getBytes(StandardCharsets.UTF_8)));
        if (associatedData != null && !associatedData.isEmpty()) {
            cipher.updateAAD(associatedData.getBytes(StandardCharsets.UTF_8));
        }
        return new String(cipher.doFinal(ciphertext), StandardCharsets.UTF_8);
    }
}
