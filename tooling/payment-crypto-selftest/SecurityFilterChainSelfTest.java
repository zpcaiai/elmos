package io.elmos.commercialapi;

import io.elmos.commercialadapter.payment.PaymentCallbackPorts;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.PropertySourcesPlaceholderConfigurer;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.filter.DelegatingFilterProxy;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

/**
 * 真跑 Spring Security 过滤器链，验证支付回调路径的放行范围。
 *
 * <h2>为什么不是 &#64;SpringBootTest</h2>
 *
 * <p>仓库里的 {@code PaymentCallbackSecurityTest} 用的是 {@code @SpringBootTest}，
 * 那需要 spring-boot-test（test scope，不在应用的 fat jar 里）。
 * 本自检改用 {@code AnnotationConfigWebApplicationContext} + {@code MockServletContext}
 * 直接装配{@link CommercialSecurityConfiguration} 定义的<b>那一个真实的
 * {@code SecurityFilterChain} Bean</b>，再用 {@code DelegatingFilterProxy}
 * 把请求打进去。
 *
 * <p>被验的是同一份配置、同一条过滤器链、同一套 {@code requestMatchers} 规则。
 * 差别只在于上下文是手工装的，而不是 Boot 自动装的。
 *
 * <h2>它顺带回答了一个悬着的问题</h2>
 *
 * <p>之前写 {@code PaymentCallbackSecurityTest} 时不确定：未放行路径对匿名请求
 * 到底是 401 还是 403？{@code anyRequest().denyAll()} 与
 * {@code authenticated()} 的翻译方式不同。下面的断言把两者分开测，
 * 实际结果直接打印出来。
 */
public final class SecurityFilterChainSelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) throws Exception {
        AnnotationConfigWebApplicationContext context = new AnnotationConfigWebApplicationContext();
        context.setServletContext(new MockServletContext());
        context.register(Wiring.class, CommercialSecurityConfiguration.class,
                PaymentCallbackController.class);
        context.refresh();

        MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
                .addFilters(new DelegatingFilterProxy("springSecurityFilterChain", context))
                .build();

        System.out.println("== 放行的两条回调路径 ==");
        int alipay = status(mvc, post("/commercial/v1/billing/callbacks/alipay")
                .contentType("application/x-www-form-urlencoded")
                .param("out_trade_no", "ord-1"));
        check("支付宝回调被放行（状态 " + alipay + "，只要不是 401）", alipay != 401);

        int wechat = status(mvc, post("/commercial/v1/billing/callbacks/wechat")
                .contentType("application/json")
                .header("Wechatpay-Timestamp", "1793923200")
                .header("Wechatpay-Nonce", "8f3c1a2b4d5e6f70")
                .header("Wechatpay-Signature", "c2ln")
                .header("Wechatpay-Serial", "SERIAL01")
                .content("{}"));
        check("微信回调被放行（状态 " + wechat + "，只要不是 401）", wechat != 401);

        System.out.println();
        System.out.println("== 未列出的 callbacks 子路径必须挡住 ==");
        // 这三条是这组测试真正的价值：把"只放行两条精确路径"变成可回归的约束。
        // 若有人图省事把配置改成 /commercial/v1/billing/callbacks/**，这里立刻失败。
        for (String path : new String[] {
                "/commercial/v1/billing/callbacks/paypal",
                "/commercial/v1/billing/callbacks/alipay/refund",
                "/commercial/v1/billing/callbacks"}) {
            int code = status(mvc, post(path).contentType("application/json").content("{}"));
            check(path + " 被拦下（状态 " + code + "）", code == 401 || code == 403);
        }

        System.out.println();
        System.out.println("== 其余计费路径仍需认证 ==");
        int reservations = status(mvc, post("/commercial/v1/billing/usage/reservations")
                .contentType("application/json").content("{}"));
        check("/billing/usage/reservations 需要认证（状态 " + reservations + "）",
                reservations == 401 || reservations == 403);
        check("且它给的是 401 —— authenticated() 对匿名请求走 AuthenticationEntryPoint",
                reservations == 401);

        System.out.println();
        System.out.println("== 既有的公开路径没被改坏 ==");
        int catalog = status(mvc, get("/commercial/v1/pricing/catalog"));
        check("定价目录仍然公开（状态 " + catalog + "，不是 401）", catalog != 401);
        int health = status(mvc, get("/livez"));
        check("/livez 仍然公开（状态 " + health + "，不是 401）", health != 401);

        System.out.println();
        System.out.println("== anyRequest().denyAll() ==");
        int unknown = status(mvc, get("/commercial/v1/something-nobody-defined"));
        check("未定义路径被拒（状态 " + unknown + "）", unknown == 401 || unknown == 403);

        System.out.println();
        System.out.println("说明：denyAll 对匿名请求实测返回 " + unknown
                + "，authenticated() 返回 " + reservations + "。");
        System.out.println("     仓库里的 PaymentCallbackSecurityTest 对未列出路径断言的是 "
                + "isUnauthorized()，与实测" + (unknown == 401 ? "一致" : "不一致，需改成 " + unknown) + "。");

        context.close();
        System.out.println();
        System.out.println("结果：" + passed + " 通过，" + failed + " 失败");
        if (failed > 0) {
            System.exit(1);
        }
    }

    private static int status(MockMvc mvc,
                              org.springframework.test.web.servlet.RequestBuilder request)
            throws Exception {
        return mvc.perform(request).andReturn().getResponse().getStatus();
    }

    /**
     * 补上 Boot 自动配置本来会做的两件事：启用 Web MVC，
     * 以及用 {@code @EnableWebSecurity} 把 {@code SecurityFilterChain} Bean
     * 组装成 {@code springSecurityFilterChain}。
     *
     * <p>刻意<b>不</b>提供 {@link PaymentCallbackPorts}：本测试只关心过滤器链，
     * 控制器拿不到端口时返回 503，而 503 同样不是 401，
     * 「被放行」这个判据依然成立。
     */
    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    static class Wiring {
        @Bean
        static PropertySourcesPlaceholderConfigurer placeholders() {
            return new PropertySourcesPlaceholderConfigurer();
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
