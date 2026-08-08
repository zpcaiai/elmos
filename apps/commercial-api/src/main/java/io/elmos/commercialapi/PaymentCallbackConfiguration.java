package io.elmos.commercialapi;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.commercial.PricingPlanCatalog;
import io.elmos.commercialadapter.payment.AlipayCallbackAdapter;
import io.elmos.commercialadapter.payment.AlipaySignatureVerifier;
import io.elmos.commercialadapter.payment.CallbackReplayGuard;
import io.elmos.commercialadapter.payment.JdbcCallbackPorts;
import io.elmos.commercialadapter.payment.JdbcOrderPorts;
import io.elmos.commercialadapter.payment.PaymentCallbackPipeline;
import io.elmos.commercialadapter.payment.PaymentProvider;
import io.elmos.commercialadapter.payment.PaymentCallbackPorts;
import io.elmos.commercialadapter.payment.PaymentProviderRouter;
import io.elmos.commercialadapter.payment.WechatPayCallbackAdapter;
import io.elmos.commercialadapter.payment.WechatPayCallbackCipher;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.security.spec.X509EncodedKeySpec;
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;

/**
 * 支付回调链路的 Spring 装配。
 *
 * <h2>为什么整个类是条件化的</h2>
 *
 * <p>五个端口全部要 {@link DataSource}，而 {@code DataSource} 本身由
 * {@code BillingDatabaseConfiguration} 在 {@code ELMOS_COMMERCIAL_DATABASE_URL}
 * 非空时才注册。条件不一致就会出现"配置类要注入一个不存在的 Bean"，
 * 上下文起不来，连带把所有无关测试一起弄挂。因此这里用<b>同一个表达式</b>。
 *
 * <h2>控制器为什么不在这里注册</h2>
 *
 * <p>本来的设计是"控制器不带 stereotype 注解、由本类以 {@code @Bean} 注册"，
 * 依据是 {@code RequestMappingHandlerMapping.isHandler()} 认
 * {@code @Controller} <b>或</b> {@code @RequestMapping}。
 * 在真实的 spring-webmvc 6.2.8 上实测<b>这个依据已经不成立</b>——
 * {@code @RequestMapping} 那一支被移除了，只认 {@code @Controller}。
 * 那样写的净效果是回调路径一律 404，而且不报任何错。
 *
 * <p>所以控制器改成正常的被扫描的 {@code @RestController}，
 * 由本类只提供它需要的 {@link PaymentCallbackPorts}；
 * 控制器用 {@code ObjectProvider} 取用，取不到就返回 503。
 * 详见 {@link PaymentCallbackController} 的类注释。
 *
 * <h2>密钥缺失时的行为</h2>
 *
 * <p>某个通道的密钥没配齐，就<b>不注册那个通道的回调适配器</b>。
 * 此时该通道的回调会在 {@code router.callbackAdapter()} 处抛
 * {@link IllegalStateException}，端点返回 5xx，提供方重发。
 * 这是刻意的：配置缺失必须表现为"处理不了"，
 * 而不是"处理了但没验签"或"静默丢弃"。
 */
@Configuration
@ConditionalOnExpression("'${ELMOS_COMMERCIAL_DATABASE_URL:}' != ''")
public class PaymentCallbackConfiguration {

    /**
     * 回调事件记入订阅事件表时的操作者。
     *
     * <p>刻意不复用付款客户的 actor：回调不是交互式操作，
     * 把它记成客户本人会让审计日志分不清"用户点了什么"和"系统做了什么"。
     */
    private static final String CALLBACK_SYSTEM_ACTOR = "system:payment-callback";

    // -----------------------------------------------------------------------
    // 时间窗
    // -----------------------------------------------------------------------

    /**
     * 容差可配但有上限：{@link CallbackReplayGuard} 的构造函数拒绝超过 1 小时的值，
     * 因为容差就是重放窗口。默认 5 分钟与支付宝/微信的官方建议一致。
     */
    @Bean
    CallbackReplayGuard paymentCallbackReplayGuard(
            @Value("${elmos.billing.callback.timestamp-tolerance-seconds:300}") long toleranceSeconds) {
        return new CallbackReplayGuard(Clock.systemUTC(), Duration.ofSeconds(toleranceSeconds));
    }

    // -----------------------------------------------------------------------
    // 五个端口
    // -----------------------------------------------------------------------

    @Bean
    PaymentCallbackPipeline.ProcessedEventLog paymentProcessedEventLog(
            DataSource commercialBillingDataSource) {
        return JdbcCallbackPorts.processedEventLog(commercialBillingDataSource);
    }

    @Bean
    PaymentCallbackPipeline.ProviderEventStore paymentProviderEventStore(
            DataSource commercialBillingDataSource) {
        return JdbcCallbackPorts.providerEventStore(commercialBillingDataSource);
    }

    @Bean
    PaymentCallbackPipeline.ReconciliationCases paymentReconciliationCases(
            DataSource commercialBillingDataSource) {
        return JdbcCallbackPorts.reconciliationCases(commercialBillingDataSource);
    }

    @Bean
    PaymentCallbackPipeline.OrderLookup paymentOrderLookup(
            DataSource commercialBillingDataSource) {
        return JdbcOrderPorts.orderLookup(commercialBillingDataSource);
    }

    /**
     * 套餐期限来自定价目录，不写死。
     *
     * <p>{@code requirePlan} 找不到套餐时抛 {@code IllegalArgumentException}，
     * {@link JdbcOrderPorts#subscriptionActivator} 又会拒绝非正数的期限——
     * 两道都失败关闭，因为"猜一个期限"意味着给客户一个错误的到期日。
     */
    @Bean
    PaymentCallbackPipeline.SubscriptionActivator paymentSubscriptionActivator(
            DataSource commercialBillingDataSource) {
        JdbcOrderPorts.PlanTermDays planTerms =
                planId -> PricingPlanCatalog.requirePlan(planId).termDays();
        return JdbcOrderPorts.subscriptionActivator(
                commercialBillingDataSource, Clock.systemUTC(), planTerms, CALLBACK_SYSTEM_ACTOR);
    }

    // -----------------------------------------------------------------------
    // 路由器与回调适配器
    // -----------------------------------------------------------------------

    /**
     * 路由器按定价目录构造，构造时即校验「通道 × 币种」相容性
     * （{@code STRIPE_CHECKOUT + CNY} 直接抛异常，见 {@link PaymentProvider}）。
     *
     * <p>回调适配器按<b>通道</b>注册，而不是只注册目录当前生效的那个：
     * 切换通道之后，旧通道仍可能有在途回调需要正确处理。
     */
    @Bean
    PaymentProviderRouter paymentProviderRouter(
            CallbackReplayGuard paymentCallbackReplayGuard,
            ObjectMapper objectMapper,
            @Value("${elmos.billing.alipay.app-id:}") String alipayAppId,
            @Value("${elmos.billing.alipay.public-key-file:}") String alipayPublicKeyFile,
            @Value("${elmos.billing.wechatpay.mch-id:}") String wechatMerchantId,
            @Value("${elmos.billing.wechatpay.platform-certificate-file:}") String wechatCertificateFile,
            @Value("${elmos.billing.wechatpay.api-v3-key:}") String wechatApiV3Key) {
        var catalog = PricingPlanCatalog.chinaSelfServeDraft();
        PaymentProviderRouter router =
                new PaymentProviderRouter(catalog.paymentProvider(), catalog.currency());

        if (!alipayAppId.isBlank() && !alipayPublicKeyFile.isBlank()) {
            router.register(PaymentProvider.ALIPAY_CHECKOUT, new AlipayCallbackAdapter(
                    new AlipaySignatureVerifier(publicKeyFromPem(alipayPublicKeyFile)),
                    paymentCallbackReplayGuard,
                    alipayAppId));
        }

        if (!wechatMerchantId.isBlank() && !wechatCertificateFile.isBlank()
                && !wechatApiV3Key.isBlank()) {
            router.register(PaymentProvider.WECHAT_PAY_NATIVE, new WechatPayCallbackAdapter(
                    new WechatPayCallbackCipher(
                            publicKeyFromCertificate(wechatCertificateFile),
                            wechatApiV3Key.getBytes(StandardCharsets.UTF_8)),
                    paymentCallbackReplayGuard,
                    new JacksonWechatNotificationReader(objectMapper),
                    wechatMerchantId));
        }

        return router;
    }

    // -----------------------------------------------------------------------
    // 端口组
    // -----------------------------------------------------------------------

    /**
     * 六个依赖打成一个整体。
     *
     * <p>{@link PaymentCallbackController} 本身是被组件扫描的 {@code @RestController}
     * （Spring 6.2 起没有 stereotype 注解就<b>不会建立请求映射</b>），
     * 因此它不能直接要求这些只在配了数据库时才存在的 Bean。
     * 它注入的是 {@code ObjectProvider<PaymentCallbackPorts>}：
     * 本 Bean 在就正常工作，不在就返回 503。
     */
    @Bean
    PaymentCallbackPorts paymentCallbackPorts(
            PaymentProviderRouter paymentProviderRouter,
            PaymentCallbackPipeline.ProcessedEventLog paymentProcessedEventLog,
            PaymentCallbackPipeline.OrderLookup paymentOrderLookup,
            PaymentCallbackPipeline.ProviderEventStore paymentProviderEventStore,
            PaymentCallbackPipeline.SubscriptionActivator paymentSubscriptionActivator,
            PaymentCallbackPipeline.ReconciliationCases paymentReconciliationCases) {
        return new PaymentCallbackPorts(
                paymentProviderRouter,
                paymentProcessedEventLog,
                paymentOrderLookup,
                paymentProviderEventStore,
                paymentSubscriptionActivator,
                paymentReconciliationCases);
    }

    // -----------------------------------------------------------------------
    // 密钥装载
    // -----------------------------------------------------------------------

    /**
     * 从 PEM 文件读支付宝公钥（X.509 SubjectPublicKeyInfo）。
     *
     * <p>密钥走<b>文件</b>而不是环境变量：环境变量会出现在 {@code /proc},
     * 容器检查输出和崩溃转储里，而文件可以挂成 0400 的 secret。
     */
    private static PublicKey publicKeyFromPem(String path) {
        byte[] der = Base64.getMimeDecoder().decode(stripPemArmour(readText(path)));
        try {
            return KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(der));
        } catch (Exception failure) {
            throw new IllegalStateException("支付宝公钥文件无法解析: " + path, failure);
        }
    }

    /** 从 PEM 证书读微信支付平台公钥。 */
    private static PublicKey publicKeyFromCertificate(String path) {
        try {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            X509Certificate certificate = (X509Certificate) factory.generateCertificate(
                    new ByteArrayInputStream(readText(path).getBytes(StandardCharsets.UTF_8)));
            // 过期的平台证书必须拒绝：用它验签等于接受一把已经不该被信任的钥匙。
            certificate.checkValidity();
            return certificate.getPublicKey();
        } catch (Exception failure) {
            throw new IllegalStateException("微信支付平台证书无法解析或已过期: " + path, failure);
        }
    }

    private static String readText(String path) {
        try {
            return Files.readString(Path.of(path), StandardCharsets.UTF_8);
        } catch (Exception failure) {
            throw new IllegalStateException("密钥文件读取失败: " + path, failure);
        }
    }

    private static String stripPemArmour(String pem) {
        return pem.replaceAll("-----BEGIN [^-]+-----", "")
                .replaceAll("-----END [^-]+-----", "")
                .replaceAll("\\s", "");
    }
}
