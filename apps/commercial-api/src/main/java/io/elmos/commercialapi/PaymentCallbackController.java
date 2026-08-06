package io.elmos.commercialapi;

import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.Outcome;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.RawCallback;
import io.elmos.commercialadapter.payment.PaymentCallbackPorts;
import io.elmos.commercialadapter.payment.PaymentProvider;

import java.util.Map;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 支付回调端点。
 *
 * <h2>为什么必须有 {@code @RestController}（Spring 6.2 起）</h2>
 *
 * <p>本类先前只带类型级 {@code @RequestMapping}、刻意不加 stereotype 注解，
 * 依据是"{@code RequestMappingHandlerMapping.isHandler()} 认 {@code @Controller}
 * <b>或</b> {@code @RequestMapping}"。这个依据在 Spring Framework 6.2 上<b>已经不成立</b>：
 *
 * <pre>
 * // spring-webmvc 6.2.8, RequestMappingHandlerMapping
 * protected boolean isHandler(Class&lt;?&gt; beanType) {
 *     return AnnotatedElementUtils.hasAnnotation(beanType, Controller.class);
 * }
 * </pre>
 *
 * <p>{@code @RequestMapping} 那一支已被移除。少了 stereotype 注解的后果不是报错，
 * 而是<b>两个回调路径压根不建立映射</b>——Bean 注册成功，请求一律 404，
 * 提供方无限重发，日志里看不出任何异常。这个结论是在真实的 spring-webmvc 6.2.8
 * 上跑出来的（{@code SpringWiringSelfTest}），不是读文档推的。
 *
 * <h2>那"没配数据库就别注册端点"怎么办</h2>
 *
 * <p>加了 {@code @RestController} 就会被组件扫描无条件发现，于是不能再让构造函数
 * 直接要那六个只在配了数据库时才存在的 Bean。改成注入
 * {@link ObjectProvider}&lt;{@link PaymentCallbackPorts}&gt;：
 *
 * <ul>
 *   <li>没配 → 端点存在、映射建立、调用时返回 <b>503</b> 并带明确的失败语义；</li>
 *   <li>配了 → 正常走管线。</li>
 * </ul>
 *
 * <p>这比"没配就没有端点"其实更好：404 会让人以为路径写错了，
 * 503 明确说的是"这台机器没配置收款"。而两者都不会让应用启动失败。
 *
 * <h2>四条注意事项</h2>
 *
 * <ul>
 *   <li><b>回调路径不做认证</b>——提供方不会带我们的令牌，安全性由验签保证。
 *       Security 里逐条列出精确路径，不用通配。</li>
 *   <li><b>微信请求体必须取原文</b>。验签对的是原始字节对应的文本；
 *       任何"先反序列化再重新序列化"都会让验签必失败。因此用
 *       {@code @RequestBody String}，不是某个 DTO。</li>
 *   <li><b>重复回调返回成功</b>。{@link Outcome#DUPLICATE_IGNORED} 对提供方回 200，
 *       否则提供方会持续重发。这不是"假装成功"——首次处理确实成功了。</li>
 *   <li><b>非付款成功的事件也返回成功</b>。{@link Outcome#NOT_A_PAYMENT_SUCCESS}
 *       是关单/退款一类的合法通知，我们已经正确记录、只是没有激活订阅。
 *       对它回失败会让提供方无限重发一条我们本来就处理对了的通知。</li>
 * </ul>
 *
 * <p>失败时的响应体<b>不含任何内部细节</b>：回调端点公网可达，错误信息会成为探测工具。
 */
@RestController
@RequestMapping("/commercial/v1/billing/callbacks")
public class PaymentCallbackController {

    /** 支付宝要求成功时响应体恰好是这个词，多一个字符都会被判失败并持续重发。 */
    private static final String ALIPAY_SUCCESS = "success";
    private static final String ALIPAY_FAILURE = "fail";
    /** 微信要求失败时返回非 2xx 且带错误码；成功时空体 200。 */
    private static final String WECHAT_FAILURE = "{\"code\":\"FAIL\",\"message\":\"NOT ACCEPTED\"}";

    private final ObjectProvider<PaymentCallbackPorts> ports;

    @Autowired
    public PaymentCallbackController(ObjectProvider<PaymentCallbackPorts> ports) {
        if (ports == null) {
            throw new IllegalArgumentException("PaymentCallbackPorts 提供者未注入");
        }
        this.ports = ports;
    }

    /** 测试与手工装配用：直接给一组确定的端口。 */
    public PaymentCallbackController(PaymentCallbackPorts ports) {
        this(new FixedPorts(ports));
    }

    /**
     * 支付宝异步通知。表单编码，验签对象是全部表单参数。
     *
     * <p>这里<b>不能</b>同时用 {@code @RequestBody String} 取原文：
     * 请求是 {@code application/x-www-form-urlencoded}，Spring MVC 的参数绑定
     * 会消费掉请求体，再声明 {@code @RequestBody} 会拿到空串或直接冲突。
     * 支付宝验签的对象本来就是「参数表」而不是原始体，取参数表才是正确做法。
     */
    @PostMapping("/alipay")
    public ResponseEntity<String> alipay(@RequestParam Map<String, String> formParameters) {
        PaymentCallbackPorts resolved = ports.getIfAvailable();
        if (resolved == null) {
            return ResponseEntity.status(503).body(ALIPAY_FAILURE);
        }
        Outcome outcome = resolved
                .pipelineFor(PaymentProvider.ALIPAY_CHECKOUT)
                .process(new RawCallback(
                        PaymentProvider.ALIPAY_CHECKOUT, "", Map.of(), formParameters));
        return accepted(outcome)
                ? ResponseEntity.ok(ALIPAY_SUCCESS)
                : ResponseEntity.badRequest().body(ALIPAY_FAILURE);
    }

    /**
     * 微信支付回调。JSON，验签对象是三段串 {@code timestamp\nnonce\nbody\n}。
     */
    @PostMapping("/wechat")
    public ResponseEntity<String> wechat(
            @RequestBody String rawBody,
            @RequestHeader("Wechatpay-Timestamp") String timestamp,
            @RequestHeader("Wechatpay-Nonce") String nonce,
            @RequestHeader("Wechatpay-Signature") String signature,
            @RequestHeader("Wechatpay-Serial") String serial) {
        PaymentCallbackPorts resolved = ports.getIfAvailable();
        if (resolved == null) {
            return ResponseEntity.status(503).body(WECHAT_FAILURE);
        }
        Map<String, String> headers = Map.of(
                "Wechatpay-Timestamp", timestamp,
                "Wechatpay-Nonce", nonce,
                "Wechatpay-Signature", signature,
                "Wechatpay-Serial", serial);
        Outcome outcome = resolved
                .pipelineFor(PaymentProvider.WECHAT_PAY_NATIVE)
                .process(new RawCallback(
                        PaymentProvider.WECHAT_PAY_NATIVE, rawBody, headers, Map.of()));
        return accepted(outcome)
                ? ResponseEntity.ok("")
                : ResponseEntity.badRequest().body(WECHAT_FAILURE);
    }

    /**
     * 哪些结果对提供方回成功。
     *
     * <p>判据不是"我们激活了订阅"，而是<b>"这条通知已经被正确处理完，
     * 再发一遍也不会有不同结果"</b>：
     *
     * <ul>
     *   <li>{@link Outcome#ACCEPTED}——订阅已开通。</li>
     *   <li>{@link Outcome#DUPLICATE_IGNORED}——首次已处理成功，重发无需再做。</li>
     *   <li>{@link Outcome#NOT_A_PAYMENT_SUCCESS}——关单/退款通知，
     *       事实已落库，本来就不该激活订阅。</li>
     * </ul>
     *
     * <p>反过来，{@code ORDER_UNKNOWN} 与 {@code AMOUNT_MISMATCH} 虽已开对账案件，
     * 仍回失败：让提供方保留这笔待处理，避免我们单方面"认下"一笔对不上的钱。
     * {@code STALE_TIMESTAMP} 与 {@code SIGNATURE_REJECTED} 更是直接失败。
     */
    private static boolean accepted(Outcome outcome) {
        return outcome == Outcome.ACCEPTED
                || outcome == Outcome.DUPLICATE_IGNORED
                || outcome == Outcome.NOT_A_PAYMENT_SUCCESS;
    }

    /** 把一组确定的端口包成 {@link ObjectProvider}，供非 Spring 场景使用。 */
    private record FixedPorts(PaymentCallbackPorts value)
            implements ObjectProvider<PaymentCallbackPorts> {
        private FixedPorts {
            if (value == null) {
                throw new IllegalArgumentException("PaymentCallbackPorts 为空");
            }
        }

        @Override
        public PaymentCallbackPorts getObject() {
            return value;
        }

        @Override
        public PaymentCallbackPorts getObject(Object... args) {
            return value;
        }

        @Override
        public PaymentCallbackPorts getIfAvailable() {
            return value;
        }

        @Override
        public PaymentCallbackPorts getIfUnique() {
            return value;
        }
    }
}
