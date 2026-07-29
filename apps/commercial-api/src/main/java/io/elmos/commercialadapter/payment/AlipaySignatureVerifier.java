package io.elmos.commercialadapter.payment;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.PublicKey;
import java.security.Signature;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * 支付宝异步通知（notify）的 RSA2 验签。
 *
 * <p>规范化规则（顺序错一步验签就不过，而错误信息只会是"验签失败"，
 * 因此把规则写在这里而不是散落在调用方）：
 *
 * <ol>
 *   <li>剔除 {@code sign} 与 {@code sign_type} 两个参数</li>
 *   <li>剔除值为空的参数</li>
 *   <li>其余参数按参数名 ASCII 升序排列</li>
 *   <li>以 {@code k=v} 用 {@code &} 连接，值不做 URL 编码</li>
 *   <li>以支付宝公钥用 SHA256withRSA 验证 Base64 签名</li>
 * </ol>
 *
 * <p><b>失败关闭</b>：任何异常（缺签名、Base64 非法、公钥不匹配、算法不可用）
 * 一律返回 {@code false}，绝不因为"看起来像临时故障"而放行。
 * 验签不通过时调用方必须拒绝回调且<b>不创建订阅</b>。
 *
 * <p>只依赖 JDK，无第三方 SDK。
 */
public final class AlipaySignatureVerifier {

    private static final String ALGORITHM = "SHA256withRSA";
    private static final String SIGN_FIELD = "sign";
    private static final String SIGN_TYPE_FIELD = "sign_type";
    private static final String EXPECTED_SIGN_TYPE = "RSA2";

    private final PublicKey alipayPublicKey;

    public AlipaySignatureVerifier(PublicKey alipayPublicKey) {
        if (alipayPublicKey == null) {
            throw new IllegalArgumentException("支付宝公钥未配置");
        }
        this.alipayPublicKey = alipayPublicKey;
    }

    /**
     * 校验一次回调。
     *
     * @param parameters 回调的全部表单参数（含 sign / sign_type）
     * @return 验签是否通过；任何异常情形均为 {@code false}
     */
    public boolean verify(Map<String, String> parameters) {
        if (parameters == null) {
            return false;
        }
        String signature = parameters.get(SIGN_FIELD);
        if (signature == null || signature.isEmpty()) {
            return false;
        }
        String signType = parameters.get(SIGN_TYPE_FIELD);
        // 只接受 RSA2。历史 RSA(SHA1) 已不安全，缺失也不放行。
        if (signType != null && !EXPECTED_SIGN_TYPE.equals(signType)) {
            return false;
        }

        byte[] signatureBytes;
        try {
            signatureBytes = Base64.getDecoder().decode(signature);
        } catch (IllegalArgumentException invalidBase64) {
            return false;
        }

        byte[] content = canonicalContent(parameters).getBytes(StandardCharsets.UTF_8);
        try {
            Signature verifier = Signature.getInstance(ALGORITHM);
            verifier.initVerify(alipayPublicKey);
            verifier.update(content);
            return verifier.verify(signatureBytes);
        } catch (GeneralSecurityException failure) {
            return false;
        }
    }

    /**
     * 构造待验签串。单独暴露是为了让"签名不过"能被诊断——
     * 排查时可以直接比对这一串，而不是靠猜。
     */
    public static String canonicalContent(Map<String, String> parameters) {
        List<String> names = new ArrayList<>();
        for (Map.Entry<String, String> entry : parameters.entrySet()) {
            String name = entry.getKey();
            String value = entry.getValue();
            if (SIGN_FIELD.equals(name) || SIGN_TYPE_FIELD.equals(name)) {
                continue;
            }
            if (value == null || value.isEmpty()) {
                continue;
            }
            names.add(name);
        }
        Collections.sort(names);

        StringBuilder builder = new StringBuilder();
        for (String name : names) {
            if (builder.length() > 0) {
                builder.append('&');
            }
            builder.append(name).append('=').append(parameters.get(name));
        }
        return builder.toString();
    }
}
