package io.elmos.commercialadapter.payment;

import java.util.EnumMap;
import java.util.Map;

/**
 * 按定价目录声明的 {@code paymentProvider} 选择下单网关与回调适配器。
 *
 * <p><b>失败关闭</b>：目录声明的通道没有注册实现时抛异常，不回退到其它通道。
 * 「找不到就用默认的」在支付场景等于钱进错账户。
 *
 * <p>本类同时承担一个契约校验职责：目录币种与通道必须相容
 * （见 {@link PaymentProvider#assertCompatibleWith}）。
 */
public final class PaymentProviderRouter {

    /** 下单网关。返回值随通道不同：支付宝是跳转 URL，微信是二维码 code_url。 */
    public interface CheckoutGateway {
        PaymentProvider provider();

        /**
         * 准备一次支付。
         *
         * @param outTradeNo 本地订单号
         * @param amountFen  金额（分），由服务端根据 planId 决定，不接受客户端传入
         * @param subject    商品标题
         * @return 前端所需的支付入口
         */
        CheckoutHandoff prepare(String outTradeNo, long amountFen, String subject);
    }

    /** 前端支付入口。两种形态互斥，二者必有其一。 */
    public record CheckoutHandoff(PaymentProvider provider, String redirectUrl, String qrCodeUrl) {
        public CheckoutHandoff {
            boolean hasRedirect = redirectUrl != null && !redirectUrl.isEmpty();
            boolean hasQr = qrCodeUrl != null && !qrCodeUrl.isEmpty();
            if (hasRedirect == hasQr) {
                throw new IllegalArgumentException(
                        "支付入口必须且只能是跳转 URL 或二维码之一");
            }
        }
    }

    private final Map<PaymentProvider, CheckoutGateway> gateways =
            new EnumMap<>(PaymentProvider.class);
    private final Map<PaymentProvider, PaymentCallbackPipeline.ProviderAdapter> adapters =
            new EnumMap<>(PaymentProvider.class);
    private final PaymentProvider active;

    /**
     * @param catalogProvider 目录声明的通道名（原样字符串，严格解析）
     * @param catalogCurrency 目录币种，用于相容性检查
     */
    public PaymentProviderRouter(String catalogProvider, String catalogCurrency) {
        this.active = PaymentProvider.parse(catalogProvider);
        this.active.assertCompatibleWith(catalogCurrency);
    }

    public PaymentProviderRouter register(CheckoutGateway gateway) {
        if (gateway == null) {
            throw new IllegalArgumentException("网关为空");
        }
        gateways.put(gateway.provider(), gateway);
        return this;
    }

    public PaymentProviderRouter register(PaymentProvider provider,
                                          PaymentCallbackPipeline.ProviderAdapter adapter) {
        if (provider == null || adapter == null) {
            throw new IllegalArgumentException("回调适配器注册参数为空");
        }
        adapters.put(provider, adapter);
        return this;
    }

    /** 目录当前生效的通道。 */
    public PaymentProvider active() {
        return active;
    }

    /**
     * 取当前生效通道的下单网关。
     *
     * @throws IllegalStateException 该通道没有注册实现——这是配置错误，必须暴露
     */
    public CheckoutGateway checkoutGateway() {
        CheckoutGateway gateway = gateways.get(active);
        if (gateway == null) {
            throw new IllegalStateException(
                    "定价目录声明 " + active + "，但该通道没有注册下单网关实现");
        }
        return gateway;
    }

    /**
     * 取指定通道的回调适配器。
     *
     * <p>按回调端点的通道取，而不是按目录当前通道取：切换通道后，
     * 旧通道仍可能有在途回调需要正确处理。
     *
     * @throws IllegalStateException 未注册
     */
    public PaymentCallbackPipeline.ProviderAdapter callbackAdapter(PaymentProvider provider) {
        PaymentCallbackPipeline.ProviderAdapter adapter = adapters.get(provider);
        if (adapter == null) {
            throw new IllegalStateException(provider + " 没有注册回调适配器");
        }
        return adapter;
    }
}
