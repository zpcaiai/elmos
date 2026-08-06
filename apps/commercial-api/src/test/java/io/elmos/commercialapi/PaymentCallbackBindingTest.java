package io.elmos.commercialapi;

import io.elmos.commercialadapter.payment.PaymentCallbackPipeline;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.LocalOrder;
import io.elmos.commercialadapter.payment.PaymentCallbackPorts;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.NormalizedCallback;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline.RawCallback;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 两个回调端点的**参数绑定**验证。
 *
 * <p>用 {@code standaloneSetup} 而不是 {@code @SpringBootTest}：
 * 控制器的六个依赖目前还没有 Bean 实现（见 {@link PaymentCallbackController} 类注释），
 * 而这里要验的恰恰是 Spring MVC 的参数解析行为，不需要完整上下文。
 * standaloneSetup 用的是真实的 {@code RequestMappingHandlerAdapter} 与
 * 真实的参数解析器，因此 {@code @RequestParam Map}、{@code @RequestBody String}、
 * {@code @RequestHeader} 都是真跑，不是模拟。
 *
 * <p>端口全部用手写替身，不引入 Mockito：这些替身要记录"收到了什么"，
 * 手写比打桩更直观，也不受 mock 框架版本影响。
 *
 * <p><b>2026-07-29 更新。</b>控制器现在是被扫描的 {@code @RestController}
 * （Spring 6.2 起，只有类型级 {@code @RequestMapping} 不会建立任何请求映射，
 * 详见该类注释），六个依赖收成了 {@link PaymentCallbackPorts}。
 * 本测试用它的直接构造函数装配，走的还是同一条参数绑定路径。
 */
class PaymentCallbackBindingTest {

    /** 记录管线实际收到的 RawCallback，供断言检查绑定结果。 */
    private final List<RawCallback> received = new ArrayList<>();
    private final Set<String> seenKeys = new HashSet<>();

    private MockMvc mockMvc() {
        PaymentProviderRouter router =
                new PaymentProviderRouter("ALIPAY_CHECKOUT", "CNY");
        PaymentCallbackPipeline.ProviderAdapter adapter =
                new PaymentCallbackPipeline.ProviderAdapter() {
                    @Override
                    public boolean verifySignature(RawCallback raw) {
                        received.add(raw);
                        return true;
                    }

                    @Override
                    public NormalizedCallback normalize(RawCallback raw) {
                        return new NormalizedCallback(raw.provider(), "evt-1",
                                "ord-1", 12900, "SUCCESS");
                    }
                };
        router.register(PaymentProvider.ALIPAY_CHECKOUT, adapter);
        router.register(PaymentProvider.WECHAT_PAY_NATIVE, adapter);

        PaymentCallbackController controller = new PaymentCallbackController(
                new PaymentCallbackPorts(
                        router,
                        key -> seenKeys.add(key),
                        outTradeNo -> Optional.of(new LocalOrder("ord-1", "org-1",
                                "elmos-pro-monthly", 12900)),
                        (order, callback, rawBody) -> { },
                        (order, callback) -> { },
                        (reason, callback, order, detail) -> { }));
        return MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void alipayFormParametersReachThePipeline() throws Exception {
        mockMvc().perform(post("/commercial/v1/billing/callbacks/alipay")
                        .contentType("application/x-www-form-urlencoded")
                        .param("out_trade_no", "ord-1")
                        .param("total_amount", "129.00")
                        .param("trade_status", "TRADE_SUCCESS")
                        .param("sign", "cGxhY2Vob2xkZXI=")
                        .param("sign_type", "RSA2"))
                .andExpect(status().isOk())
                // 支付宝要求响应体恰好是 success，多一个字符都会被判失败并持续重发
                .andExpect(content().string("success"));

        assertEquals(1, received.size());
        RawCallback raw = received.get(0);
        assertEquals(PaymentProvider.ALIPAY_CHECKOUT, raw.provider());
        // 表单参数确实被注入，且一个不少——验签串是按参数表算的，漏一个就验不过
        assertEquals("ord-1", raw.formParameters().get("out_trade_no"));
        assertEquals("129.00", raw.formParameters().get("total_amount"));
        assertEquals("TRADE_SUCCESS", raw.formParameters().get("trade_status"));
        assertEquals("cGxhY2Vob2xkZXI=", raw.formParameters().get("sign"));
        assertEquals("RSA2", raw.formParameters().get("sign_type"));
        assertEquals(5, raw.formParameters().size());
    }

    @Test
    void wechatRawBodyIsNotReserialized() throws Exception {
        // 刻意用非规范化的 JSON：键顺序、空格、Unicode 转义都保留原样。
        // 微信验签对的是原始字节对应的文本，任何重新序列化都会让验签必失败。
        String body = "{\"id\":\"evt-1\", \"summary\":\"\\u652f\\u4ed8\","
                + "  \"resource\":{\"ciphertext\":\"AA==\"},\"create_time\":\"2026-09-01T12:00:00+08:00\"}";

        mockMvc().perform(post("/commercial/v1/billing/callbacks/wechat")
                        .contentType("application/json")
                        .header("Wechatpay-Timestamp", "1793923200")
                        .header("Wechatpay-Nonce", "8f3c1a2b4d5e6f70")
                        .header("Wechatpay-Signature", "c2ln")
                        .header("Wechatpay-Serial", "SERIAL01")
                        .content(body))
                .andExpect(status().isOk());

        assertEquals(1, received.size());
        RawCallback raw = received.get(0);
        assertEquals(PaymentProvider.WECHAT_PAY_NATIVE, raw.provider());
        // 逐字节一致：这条断言就是"没有被重新序列化"的判据
        assertEquals(body, raw.rawBody());
        assertTrue(raw.rawBody().contains("\\u652f"), "Unicode 转义必须原样保留");
        assertTrue(raw.rawBody().contains("\"summary\":\"\\u652f\\u4ed8\","),
                "键顺序与空白必须原样保留");
    }

    @Test
    void wechatHeadersReachThePipeline() throws Exception {
        mockMvc().perform(post("/commercial/v1/billing/callbacks/wechat")
                        .contentType("application/json")
                        .header("Wechatpay-Timestamp", "1793923200")
                        .header("Wechatpay-Nonce", "8f3c1a2b4d5e6f70")
                        .header("Wechatpay-Signature", "c2ln")
                        .header("Wechatpay-Serial", "SERIAL01")
                        .content("{}"))
                .andExpect(status().isOk());

        RawCallback raw = received.get(0);
        // 四个头都要到位：验签串用前三个，Serial 用于选平台证书
        assertEquals("1793923200", raw.headers().get("Wechatpay-Timestamp"));
        assertEquals("8f3c1a2b4d5e6f70", raw.headers().get("Wechatpay-Nonce"));
        assertEquals("c2ln", raw.headers().get("Wechatpay-Signature"));
        assertEquals("SERIAL01", raw.headers().get("Wechatpay-Serial"));
    }

    @Test
    void wechatMissingSignatureHeaderIsRejectedBeforeReachingThePipeline() throws Exception {
        // 缺必需头时 Spring 直接返回 400，管线根本不该被调用——
        // 未验签的报文不应进入任何业务路径
        mockMvc().perform(post("/commercial/v1/billing/callbacks/wechat")
                        .contentType("application/json")
                        .header("Wechatpay-Timestamp", "1793923200")
                        .header("Wechatpay-Nonce", "8f3c1a2b4d5e6f70")
                        .header("Wechatpay-Serial", "SERIAL01")
                        .content("{}"))
                .andExpect(status().isBadRequest());

        assertTrue(received.isEmpty(), "缺签名头时管线不得被调用");
    }

    @Test
    void duplicateCallbackStillReportsSuccessToProvider() throws Exception {
        MockMvc mvc = mockMvc();
        mvc.perform(post("/commercial/v1/billing/callbacks/alipay")
                        .contentType("application/x-www-form-urlencoded")
                        .param("out_trade_no", "ord-1"))
                .andExpect(status().isOk())
                .andExpect(content().string("success"));

        // 重发：幂等台账已登记过，管线返回 DUPLICATE_IGNORED。
        // 仍须回 200，否则提供方会无限重发。
        mvc.perform(post("/commercial/v1/billing/callbacks/alipay")
                        .contentType("application/x-www-form-urlencoded")
                        .param("out_trade_no", "ord-1"))
                .andExpect(status().isOk())
                .andExpect(content().string("success"));
    }

    @Test
    void failureResponseLeaksNoInternalDetail() throws Exception {
        // 订单查不到 -> ORDER_UNKNOWN -> 对提供方回失败。
        // 响应体必须是固定文案，不得含订单号、异常信息或任何内部结构。
        PaymentProviderRouter router = new PaymentProviderRouter("ALIPAY_CHECKOUT", "CNY");
        router.register(PaymentProvider.ALIPAY_CHECKOUT,
                new PaymentCallbackPipeline.ProviderAdapter() {
                    @Override
                    public boolean verifySignature(RawCallback raw) {
                        return true;
                    }

                    @Override
                    public NormalizedCallback normalize(RawCallback raw) {
                        return new NormalizedCallback(raw.provider(), "evt-missing",
                                "ord-does-not-exist", 12900, "SUCCESS");
                    }
                });
        PaymentCallbackController controller = new PaymentCallbackController(
                new PaymentCallbackPorts(
                        router,
                        key -> true,
                        outTradeNo -> Optional.empty(),
                        (order, callback, rawBody) -> { },
                        (order, callback) -> { },
                        (reason, callback, order, detail) -> { }));

        MockMvcBuilders.standaloneSetup(controller).build()
                .perform(post("/commercial/v1/billing/callbacks/alipay")
                        .contentType("application/x-www-form-urlencoded")
                        .param("out_trade_no", "ord-does-not-exist"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("fail"));
    }
}
