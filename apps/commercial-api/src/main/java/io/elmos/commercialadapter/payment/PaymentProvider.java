package io.elmos.commercialadapter.payment;

/**
 * 定价目录 {@code paymentProvider} 字段的取值域。
 *
 * <p>目录 Schema 原本写成 {@code const: "STRIPE_CHECKOUT"}。D-01（2026-07-28）
 * 选定中国大陆主体 + 支付宝/微信后必须扩为枚举；本类是 Java 侧的权威定义。
 *
 * <p><b>不提供默认值，也不提供"未知即回退"。</b>解析不出来就抛异常：
 * 支付通道选错的后果是钱进错账户或根本收不到，静默回退比直接失败危险得多。
 */
public enum PaymentProvider {

    /** 已实现，但 D-01 后不启用：Stripe 不为大陆主体收单。 */
    STRIPE_CHECKOUT(false),

    /** 支付宝电脑网站支付。 */
    ALIPAY_CHECKOUT(true),

    /** 微信支付 Native（扫码）。 */
    WECHAT_PAY_NATIVE(true);

    private final boolean chinaMainland;

    PaymentProvider(boolean chinaMainland) {
        this.chinaMainland = chinaMainland;
    }

    /** 是否为面向中国大陆的收单通道（决定发票、ICP 备案等前置要求）。 */
    public boolean isChinaMainland() {
        return chinaMainland;
    }

    /**
     * 严格解析。大小写敏感、不裁剪空白、不接受别名。
     *
     * @throws IllegalArgumentException 值为空或不在取值域内
     */
    public static PaymentProvider parse(String value) {
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("paymentProvider 未配置");
        }
        for (PaymentProvider provider : values()) {
            if (provider.name().equals(value)) {
                return provider;
            }
        }
        throw new IllegalArgumentException("未知的 paymentProvider: " + value);
    }

    /**
     * 目录币种与通道的相容性检查。
     *
     * <p>CNY + Stripe 需要境外经营主体，与 D-01 的大陆主体决定冲突。
     * 这条检查同时存在于 {@code scripts/commercial/validate_pricing_catalog_publication.py}，
     * 两侧必须保持一致。
     */
    public void assertCompatibleWith(String currency) {
        if (this == STRIPE_CHECKOUT && "CNY".equals(currency)) {
            throw new IllegalStateException(
                    "STRIPE_CHECKOUT 与 currency=CNY 需要境外经营主体；"
                            + "D-01 已选择大陆主体，应改为 ALIPAY_CHECKOUT 或 WECHAT_PAY_NATIVE");
        }
    }
}
