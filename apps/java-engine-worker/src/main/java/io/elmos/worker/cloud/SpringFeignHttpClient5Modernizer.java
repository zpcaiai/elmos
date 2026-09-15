package io.elmos.worker.cloud;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Enterprise Spring Cloud OpenFeign & Apache HttpClient 5 Modernizer.
 *
 * <p>Modernizes declarative REST clients for Spring Cloud 2023 / Spring Boot 3.x:
 * <ol>
 *   <li><b>Dependency Modernization:</b>
 *       Replaces legacy Apache HttpClient 4.x ({@code io.github.openfeign:feign-httpclient})
 *       with modern {@code io.github.openfeign:feign-hc5}.</li>
 *   <li><b>Connection Pool & Timeout Governance:</b>
 *       Generates {@code FeignHttpClient5Configuration.java} with {@code PoolingHttpClientConnectionManager}
 *       ({@code maxTotal=500}, {@code defaultMaxPerRoute=50}, 5s inactivity validation, and idle connection eviction).</li>
 *   <li><b>Full-Chain Header & Trace Propagation:</b>
 *       Generates {@code FeignHeaderPropagationRequestInterceptor.java} to propagate
 *       {@code Authorization}, {@code X-Request-Id}, and distributed tracing headers across microservices.</li>
 *   <li><b>Configuration Normalization:</b>
 *       Enables {@code spring.cloud.openfeign.httpclient.hc5.enabled: true} in {@code application.yml}.</li>
 * </ol>
 */
public final class SpringFeignHttpClient5Modernizer {

    public record FeignModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static FeignModernizationResult empty() {
            return new FeignModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_FEIGN_HTTPCLIENT = Pattern.compile(
            "<dependency>\\s*<groupId>io\\.github\\.openfeign</groupId>\\s*<artifactId>feign-httpclient</artifactId>(?:\\s*<version>[^<]+</version>)?\\s*</dependency>",
            Pattern.DOTALL
    );

    private static final String MODERN_FEIGN_HC5_DEPENDENCY =
            """
                    <dependency>
                        <groupId>io.github.openfeign</groupId>
                        <artifactId>feign-hc5</artifactId>
                    </dependency>""";

    /**
     * Executes Feign HTTP Client 5 modernization across the project workspace.
     */
    public FeignModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return FeignModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Upgrade Feign dependency in pom.xml
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            String pomContent = Files.readString(pomPath, StandardCharsets.UTF_8);
            Matcher feignMatcher = LEGACY_FEIGN_HTTPCLIENT.matcher(pomContent);
            if (feignMatcher.find()) {
                String updatedPom = feignMatcher.replaceAll(MODERN_FEIGN_HC5_DEPENDENCY);
                Files.writeString(pomPath, updatedPom, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(pomPath.toString());
                rulesApplied.add("REPLACE_FEIGN_HTTPCLIENT_WITH_FEIGN_HC5");
            }
        }

        // 2. Generate FeignHttpClient5Configuration
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/config");
        Files.createDirectories(configDir);
        Path feignConfigFile = configDir.resolve("FeignHttpClient5Configuration.java");
        if (!Files.exists(feignConfigFile)) {
            String configSource = generateHttpClient5Config();
            Files.writeString(feignConfigFile, configSource, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(feignConfigFile.toString());
            generatedArtifacts.add(feignConfigFile.toString());
            rulesApplied.add("GENERATE_FEIGN_HTTPCLIENT5_POOL_CONFIG");
        }

        // 3. Generate FeignHeaderPropagationRequestInterceptor
        Path interceptorFile = configDir.resolve("FeignHeaderPropagationRequestInterceptor.java");
        if (!Files.exists(interceptorFile)) {
            String interceptorSource = generateHeaderInterceptor();
            Files.writeString(interceptorFile, interceptorSource, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(interceptorFile.toString());
            generatedArtifacts.add(interceptorFile.toString());
            rulesApplied.add("GENERATE_FEIGN_HEADER_PROPAGATION_INTERCEPTOR");
        }

        // 4. Inject Feign HC5 settings in application.yml
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("httpclient:")) {
                String feignConfig =
                        """

                        spring:
                          cloud:
                            openfeign:
                              httpclient:
                                hc5:
                                  enabled: true
                                  pool:
                                    max-connections: 500
                                    max-connections-per-route: 50
                                  connection-timeout: 3000
                                  socket-timeout: 10000
                              compression:
                                request:
                                  enabled: true
                                response:
                                  enabled: true
                        """;
                Files.writeString(ymlPath, ymlContent + feignConfig, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("CONFIGURE_FEIGN_HC5_POOL_IN_YML");
            }
        }

        return new FeignModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateHttpClient5Config() {
        return """
                package io.elmos.generated.config;

                import org.apache.hc.client5.http.config.ConnectionConfig;
                import org.apache.hc.client5.http.config.RequestConfig;
                import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
                import org.apache.hc.client5.http.impl.classic.HttpClients;
                import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
                import org.apache.hc.core5.util.TimeValue;
                import org.apache.hc.core5.util.Timeout;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                import java.util.concurrent.TimeUnit;

                /**
                 * High-throughput Apache HttpClient 5 Connection Pool for Spring Cloud OpenFeign.
                 */
                @Configuration
                public class FeignHttpClient5Configuration {

                    @Bean
                    public CloseableHttpClient feignHttpClient() {
                        PoolingHttpClientConnectionManager connectionManager = new PoolingHttpClientConnectionManager();
                        connectionManager.setMaxTotal(500);
                        connectionManager.setDefaultMaxPerRoute(50);

                        ConnectionConfig connectionConfig = ConnectionConfig.custom()
                                .setConnectTimeout(Timeout.ofMilliseconds(3000))
                                .setValidateAfterInactivity(TimeValue.ofSeconds(5))
                                .setTimeToLive(TimeValue.ofMinutes(15))
                                .build();
                        connectionManager.setDefaultConnectionConfig(connectionConfig);

                        RequestConfig requestConfig = RequestConfig.custom()
                                .setResponseTimeout(Timeout.ofMilliseconds(10000))
                                .setConnectionRequestTimeout(Timeout.ofMilliseconds(3000))
                                .build();

                        return HttpClients.custom()
                                .setConnectionManager(connectionManager)
                                .setDefaultRequestConfig(requestConfig)
                                .evictIdleConnections(TimeValue.ofSeconds(30))
                                .evictExpiredConnections()
                                .build();
                    }
                }
                """;
    }

    private static String generateHeaderInterceptor() {
        return """
                package io.elmos.generated.config;

                import feign.RequestInterceptor;
                import feign.RequestTemplate;
                import jakarta.servlet.http.HttpServletRequest;
                import org.springframework.stereotype.Component;
                import org.springframework.web.context.request.RequestContextHolder;
                import org.springframework.web.context.request.ServletRequestAttributes;

                import java.util.Enumeration;
                import java.util.Set;

                /**
                 * Microservice Security & Trace Header Propagation Interceptor for OpenFeign.
                 */
                @Component
                public class FeignHeaderPropagationRequestInterceptor implements RequestInterceptor {

                    private static final Set<String> PROPAGATED_HEADERS = Set.of(
                            "authorization",
                            "x-request-id",
                            "x-forwarded-for",
                            "x-b3-traceid",
                            "x-b3-spanid",
                            "x-tenant-id"
                    );

                    @Override
                    public void apply(RequestTemplate template) {
                        ServletRequestAttributes attributes = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
                        if (attributes == null) {
                            return;
                        }
                        HttpServletRequest request = attributes.getRequest();
                        Enumeration<String> headerNames = request.getHeaderNames();
                        if (headerNames != null) {
                            while (headerNames.hasMoreElements()) {
                                String name = headerNames.nextElement();
                                if (PROPAGATED_HEADERS.contains(name.toLowerCase())) {
                                    String value = request.getHeader(name);
                                    if (value != null && !template.headers().containsKey(name)) {
                                        template.header(name, value);
                                    }
                                }
                            }
                        }
                    }
                }
                """;
    }
}
