import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercialadapter.payment.PaymentCallbackPorts;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import io.elmos.commercialapi.PaymentCallbackConfiguration;
import io.elmos.commercialapi.PaymentCallbackController;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.PropertySourcesPlaceholderConfigurer;
import org.springframework.core.env.MapPropertySource;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import javax.sql.DataSource;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.sql.Connection;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.logging.Logger;

/**
 * 真跑 Spring 上下文，验证支付回调的装配。
 *
 * <p>这不是"对着桩编译通过"。用的是从 {@code elmos-commercial-api-*-exec.jar}
 * 里取出的<b>真实</b> spring-context / spring-web / spring-webmvc / spring-boot
 * （6.2.8 / 3.5.3），真实 refresh 一个 {@code AnnotationConfigApplicationContext}，
 * 再用真实的 {@code RequestMappingHandlerMapping} 检测请求映射。
 *
 * <h2>这组测试抓到的第一个真问题</h2>
 *
 * <p>控制器原先只带类型级 {@code @RequestMapping}、不带 stereotype 注解，
 * 依据是 {@code isHandler()} 认 {@code @Controller} 或 {@code @RequestMapping}。
 * 本测试在真 jar 上跑出来 {@code handlerMethods = 0}，反编译确认
 * spring-webmvc 6.2.8 的 {@code isHandler} 只剩：
 *
 * <pre>return AnnotatedElementUtils.hasAnnotation(beanType, Controller.class);</pre>
 *
 * <p>也就是说那个写法会让两个回调路径<b>一律 404 且不报错</b>。
 * 下面 {@link #callbackPathsAreMapped()} 现在把这条钉死。
 *
 * <p>仍然验不了的：Security 过滤器链的实际放行（需要 spring-test 的 MockMvc，
 * 本环境拿不到 Maven Central）。
 */
public final class SpringWiringSelfTest {

    private static int passed;
    private static int failed;

    public static void main(String[] args) throws Exception {
        withoutDatabaseTheEndpointStillExistsButFailsClosed();
        withDatabaseAllPortsAreRegistered();
        callbackPathsAreMapped();
        controllerCarriesControllerStereotype();
        routerTakesProviderFromPricingCatalog();
        unconfiguredProviderFailsClosed();
        configuredAlipayKeysRegisterTheAdapter();
        replayGuardToleranceIsBounded();
        planTermsComeFromCatalog();

        System.out.println();
        System.out.println("通过 " + passed + " 项，失败 " + failed + " 项");
        if (failed > 0) {
            System.exit(1);
        }
    }

    // -----------------------------------------------------------------------

    /**
     * 没配数据库时：上下文正常启动，控制器在，但端口组不在，调用返回 503。
     *
     * <p>这是"加了 {@code @RestController} 会不会弄挂无数据库环境"的直接答案：
     * 不会——因为控制器注入的是 {@code ObjectProvider}，不是六个硬依赖。
     */
    private static void withoutDatabaseTheEndpointStillExistsButFailsClosed() {
        try (AnnotationConfigApplicationContext context = context(Map.of())) {
            check("无数据库时上下文照常启动", context.isActive());
            check("无数据库时控制器仍被注册（因为它是被扫描的 @RestController）",
                    context.containsBean("paymentCallbackController"));
            check("无数据库时端口组不注册",
                    context.getBeanNamesForType(PaymentCallbackPorts.class).length == 0);

            PaymentCallbackController controller =
                    context.getBean(PaymentCallbackController.class);
            ResponseEntity<String> alipay = controller.alipay(Map.of("out_trade_no", "ord-1"));
            check("未配置时支付宝回调返回 503", alipay.getStatusCode().value() == 503);
            check("未配置时支付宝响应体是 fail（不是 success）",
                    "fail".equals(alipay.getBody()));

            ResponseEntity<String> wechat =
                    controller.wechat("{}", "1", "n", "s", "serial");
            check("未配置时微信回调返回 503", wechat.getStatusCode().value() == 503);
            check("未配置时微信响应体不含内部细节",
                    wechat.getBody() != null && !wechat.getBody().contains("ObjectProvider"));
        }
    }

    /** 配了数据库时，端口组装得起来，控制器能拿到它。 */
    private static void withDatabaseAllPortsAreRegistered() {
        try (AnnotationConfigApplicationContext context = context(withDatabase())) {
            PaymentCallbackPorts ports = context.getBean(PaymentCallbackPorts.class);
            check("ProcessedEventLog 已注册", ports.processedEvents() != null);
            check("OrderLookup 已注册", ports.orders() != null);
            check("ProviderEventStore 已注册", ports.events() != null);
            check("SubscriptionActivator 已注册", ports.subscriptions() != null);
            check("ReconciliationCases 已注册", ports.reconciliation() != null);
            check("Router 已注册", ports.router() != null);
            check("控制器已注册", context.getBean(PaymentCallbackController.class) != null);
        }
    }

    /**
     * 两个回调路径必须真的被建立映射。
     *
     * <p>这条断言就是本轮抓到的那个 bug 的回归测试：
     * 把 {@code @RestController} 去掉，它会失败。
     */
    private static void callbackPathsAreMapped() {
        try (AnnotationConfigApplicationContext context = context(withDatabase())) {
            RequestMappingHandlerMapping mapping = new RequestMappingHandlerMapping();
            mapping.setApplicationContext(context);
            mapping.afterPropertiesSet();

            String mapped = mapping.getHandlerMethods().keySet().toString();
            check("支付宝回调路径已建立映射",
                    mapped.contains("/commercial/v1/billing/callbacks/alipay"));
            check("微信回调路径已建立映射",
                    mapped.contains("/commercial/v1/billing/callbacks/wechat"));
            check("两个端点都限定 POST", mapped.contains("POST"));
            check("恰好只映射这两个端点", mapping.getHandlerMethods().size() == 2);
        }
    }

    /**
     * 直接盯住 Spring 6.2 的判定条件本身。
     *
     * <p>上一条测的是"结果对"，这一条测的是"依据对"：
     * 有人若把 {@code @RestController} 换回裸 {@code @RequestMapping}，
     * 这里会立刻指出原因，而不是只报一个"路径没映射"。
     */
    private static void controllerCarriesControllerStereotype() {
        boolean hasControllerStereotype = org.springframework.core.annotation.AnnotatedElementUtils
                .hasAnnotation(PaymentCallbackController.class,
                        org.springframework.stereotype.Controller.class);
        check("控制器带 @Controller 语义（@RestController 是它的组合注解）",
                hasControllerStereotype);
        check("类型级 @RequestMapping 也在（决定路径前缀）",
                PaymentCallbackController.class.getAnnotation(
                        org.springframework.web.bind.annotation.RequestMapping.class) != null);
    }

    /** 路由器的生效通道来自定价目录，不是写死的。 */
    private static void routerTakesProviderFromPricingCatalog() {
        try (AnnotationConfigApplicationContext context = context(withDatabase())) {
            PaymentProviderRouter router = context.getBean(PaymentProviderRouter.class);
            check("生效通道 = 目录声明的 ALIPAY_CHECKOUT",
                    router.active() == PaymentProvider.ALIPAY_CHECKOUT);
        }
    }

    /** 密钥没配齐时不注册适配器，取用时抛异常而不是静默放行。 */
    private static void unconfiguredProviderFailsClosed() {
        try (AnnotationConfigApplicationContext context = context(withDatabase())) {
            PaymentProviderRouter router = context.getBean(PaymentProviderRouter.class);
            check("未配密钥时取支付宝适配器抛异常（失败关闭）",
                    throwsIllegalState(() -> router.callbackAdapter(PaymentProvider.ALIPAY_CHECKOUT)));
            check("未配密钥时取微信适配器抛异常（失败关闭）",
                    throwsIllegalState(() -> router.callbackAdapter(PaymentProvider.WECHAT_PAY_NATIVE)));
        }
    }

    /** 配齐支付宝公钥与 app_id 后，适配器真的被注册进路由器。 */
    private static void configuredAlipayKeysRegisterTheAdapter() throws Exception {
        KeyPair keyPair = KeyPairGenerator.getInstance("RSA").generateKeyPair();
        Path pem = Files.createTempFile("alipay-public", ".pem");
        Files.writeString(pem,
                "-----BEGIN PUBLIC KEY-----\n"
                        + Base64.getMimeEncoder(64, "\n".getBytes(StandardCharsets.UTF_8))
                                .encodeToString(keyPair.getPublic().getEncoded())
                        + "\n-----END PUBLIC KEY-----\n",
                StandardCharsets.UTF_8);

        Map<String, Object> properties = withDatabase();
        properties.put("elmos.billing.alipay.app-id", "2021000000000000");
        properties.put("elmos.billing.alipay.public-key-file", pem.toString());

        try (AnnotationConfigApplicationContext context = context(properties)) {
            PaymentProviderRouter router = context.getBean(PaymentProviderRouter.class);
            check("配齐密钥后支付宝适配器已注册",
                    router.callbackAdapter(PaymentProvider.ALIPAY_CHECKOUT) != null);
            // 微信仍未配置，必须还是失败关闭——不能因为支付宝配好了就放松
            check("支付宝配好不影响微信仍然失败关闭",
                    throwsIllegalState(() -> router.callbackAdapter(PaymentProvider.WECHAT_PAY_NATIVE)));
        } finally {
            Files.deleteIfExists(pem);
        }
    }

    /**
     * 容差可配，但配得离谱时上下文必须起不来。
     *
     * <p>容差就是重放窗口。一个"为了少报错"把它调到 6 小时的运维改动，
     * 必须在启动时就被拒绝，而不是安静地把重放窗口放大 72 倍。
     */
    private static void replayGuardToleranceIsBounded() {
        Map<String, Object> properties = withDatabase();
        properties.put("elmos.billing.callback.timestamp-tolerance-seconds", "21600");
        boolean threw = false;
        try (AnnotationConfigApplicationContext context = context(properties)) {
            context.getBean("paymentCallbackReplayGuard");
        } catch (RuntimeException expected) {
            threw = true;
        }
        check("容差超过 1 小时时启动失败", threw);

        properties.put("elmos.billing.callback.timestamp-tolerance-seconds", "300");
        try (AnnotationConfigApplicationContext context = context(properties)) {
            check("默认量级的容差可以正常启动",
                    context.getBean("paymentCallbackReplayGuard") != null);
        }
    }

    /**
     * 套餐期限必须来自定价目录。
     *
     * <p>写死 30/365 天会在目录调整时静默给出错误的到期日，
     * 而客户只会在到期那天才发现。
     */
    private static void planTermsComeFromCatalog() {
        check("月付套餐期限 = 目录里的 31 天",
                io.elmos.commercial.PricingPlanCatalog.requirePlan("elmos-pro-monthly")
                        .termDays() == 31);
        check("年付套餐期限 = 目录里的 365 天",
                io.elmos.commercial.PricingPlanCatalog.requirePlan("elmos-pro-annual")
                        .termDays() == 365);
    }

    // -----------------------------------------------------------------------

    private static boolean throwsIllegalState(Runnable action) {
        try {
            action.run();
            return false;
        } catch (IllegalStateException expected) {
            return true;
        }
    }

    private static Map<String, Object> withDatabase() {
        Map<String, Object> properties = new HashMap<>();
        // 值本身不会被连接：本测试不碰数据库，只验证条件与装配。
        properties.put("ELMOS_COMMERCIAL_DATABASE_URL", "jdbc:postgresql://localhost:5432/elmos");
        return properties;
    }

    /**
     * 显式注册控制器，模拟真实应用里的组件扫描
     * （{@code CommercialApiApplication} 的 scanBasePackages 覆盖 {@code io.elmos.commercialapi}）。
     */
    private static AnnotationConfigApplicationContext context(Map<String, Object> properties) {
        AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext();
        context.getEnvironment().getPropertySources()
                .addFirst(new MapPropertySource("selftest", new HashMap<>(properties)));
        context.register(TestSupport.class,
                PaymentCallbackConfiguration.class,
                PaymentCallbackController.class);
        context.refresh();
        return context;
    }

    /**
     * 提供本测试所需的两个外部 Bean。
     *
     * <p>{@code DataSource} 是个一调用就抛异常的替身：配置类只应<b>持有</b>它，
     * 不应在装配阶段建立连接。若哪天有人在 {@code @Bean} 方法里加了
     * {@code getConnection()}，这个替身会让本测试立刻失败——这是有意的。
     */
    @Configuration
    static class TestSupport {
        @Bean
        static PropertySourcesPlaceholderConfigurer placeholders() {
            return new PropertySourcesPlaceholderConfigurer();
        }

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        DataSource commercialBillingDataSource() {
            return new ExplodingDataSource();
        }
    }

    static final class ExplodingDataSource implements DataSource {
        @Override
        public Connection getConnection() {
            throw new UnsupportedOperationException("装配阶段不得建立数据库连接");
        }

        @Override
        public Connection getConnection(String username, String password) {
            throw new UnsupportedOperationException("装配阶段不得建立数据库连接");
        }

        @Override
        public PrintWriter getLogWriter() {
            return null;
        }

        @Override
        public void setLogWriter(PrintWriter out) {
        }

        @Override
        public void setLoginTimeout(int seconds) {
        }

        @Override
        public int getLoginTimeout() {
            return 0;
        }

        @Override
        public Logger getParentLogger() throws SQLFeatureNotSupportedException {
            throw new SQLFeatureNotSupportedException();
        }

        @Override
        public <T> T unwrap(Class<T> type) {
            throw new UnsupportedOperationException();
        }

        @Override
        public boolean isWrapperFor(Class<?> type) {
            return false;
        }
    }

    private static void check(String what, boolean condition) {
        if (condition) {
            passed++;
            System.out.println("  PASS  " + what);
        } else {
            failed++;
            System.out.println("  FAIL  " + what);
        }
    }
}
