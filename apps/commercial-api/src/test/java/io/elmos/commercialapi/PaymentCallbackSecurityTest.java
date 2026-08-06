package io.elmos.commercialapi;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 支付回调路径的 Security 放行范围。
 *
 * <p><b>放行的判据是「不是 401」，而不是某个具体成功码。</b>理由有两条：
 *
 * <ol>
 *   <li>控制器是否因数据库条件而注册、请求是否缺少提供方签名头，会让业务状态码
 *       在 404/400/503 之间变化；这些都不是 Security 放行契约本身。</li>
 *   <li>断言「不是 401」能精确证明请求已穿过认证入口，又不会把处理器装配条件
 *       错当成 Security 的职责。</li>
 * </ol>
 *
 * <p>反过来，未放行路径的 401 是由 {@code AuthenticationEntryPoint} 直接产生的，
 * 不经过错误转发，所以可以稳定断言。
 *
 * <p>最关键的是最后那个用例：放行必须<b>只覆盖两条精确路径</b>。
 * 若有人图省事改成 {@code /commercial/v1/billing/callbacks/**}，
 * 将来任何新增的 callbacks 子路径都会自动变成公网无认证可达，
 * 而新增路径未必带验签。
 */
@SpringBootTest
@AutoConfigureMockMvc
class PaymentCallbackSecurityTest {
    private static final int UNAUTHORIZED = 401;

    @Autowired MockMvc mvc;

    @Test
    void alipayCallbackIsReachableWithoutAuthentication() throws Exception {
        mvc.perform(post("/commercial/v1/billing/callbacks/alipay")
                        .contentType("application/x-www-form-urlencoded")
                        .param("out_trade_no", "ord-1"))
                .andExpect(result -> assertNotEquals(UNAUTHORIZED,
                        result.getResponse().getStatus(),
                        "支付宝回调路径必须被 Security 放行；401 表示未放行"));
    }

    @Test
    void wechatCallbackIsReachableWithoutAuthentication() throws Exception {
        mvc.perform(post("/commercial/v1/billing/callbacks/wechat")
                        .contentType("application/json")
                        .header("Wechatpay-Timestamp", "1793923200")
                        .header("Wechatpay-Nonce", "8f3c1a2b4d5e6f70")
                        .header("Wechatpay-Signature", "c2ln")
                        .header("Wechatpay-Serial", "SERIAL01")
                        .content("{}"))
                .andExpect(result -> assertNotEquals(UNAUTHORIZED,
                        result.getResponse().getStatus(),
                        "微信回调路径必须被 Security 放行；401 表示未放行"));
    }

    @Test
    void stripeWebhookRemainsPermitted() throws Exception {
        // 回归：新增两条放行不得影响既有的 Stripe webhook。
        // 无数据库时 SelfServiceBillingController 不注册，响应会是 404；有数据库
        // 且缺 Stripe-Signature 时是 400。两种状态都必须不是认证入口产生的 401。
        mvc.perform(post("/commercial/v1/billing/webhooks/stripe")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(result -> assertNotEquals(UNAUTHORIZED,
                        result.getResponse().getStatus(),
                        "Stripe webhook 必须继续被 Security 精确放行"));
    }

    @Test
    void otherBillingRoutesStillRequireAuthentication() throws Exception {
        // 放行范围没有扩大：计费主路径仍然 401
        mvc.perform(post("/commercial/v1/billing/usage/reservations")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void unlistedCallbackPathsAreNotPermitted() throws Exception {
        // 关键断言：放行的是两条精确路径，不是 /callbacks/**。
        // 这三个请求必须 401（被过滤器链拦下），而不是穿过去。
        mvc.perform(post("/commercial/v1/billing/callbacks/paypal")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/commercial/v1/billing/callbacks/alipay/refund")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/commercial/v1/billing/callbacks")
                        .contentType("application/json")
                        .content("{}"))
                .andExpect(status().isUnauthorized());
    }
}
