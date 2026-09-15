package io.elmos.worker.web;

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
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for Spring WebClient, connection pool limits, and timeout isolation.
 *
 * <p>Key enterprise resilience challenges in non-blocking HTTP clients:
 * <ol>
 *   <li><b>AsyncRestTemplate Elimination:</b> {@code AsyncRestTemplate} was completely deprecated and removed in modern Spring.
 *       Replaces references with non-blocking {@code WebClient}.</li>
 *   <li><b>Unbounded Netty Connection Outages:</b> Default {@code WebClient.create()} lacks connection pool boundaries,
 *       TCP keepalives, and response timeouts, causing massive connection hoarding and thread starvation under network partitions.</li>
 *   <li><b>Enterprise WebClient Factory:</b> Generates {@code WebClientConfiguration.java} with bounded
 *       Reactor Netty {@code ConnectionProvider} (500 max connections), 5-second connect/response timeouts,
 *       and standard error handling.</li>
 * </ol>
 */
public final class SpringWebClientModernizer {

    public record WebClientModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static WebClientModernizationResult empty() {
            return new WebClientModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern OLD_ASYNC_REST_IMPORT = Pattern.compile(
            "import\\s+org\\.springframework\\.web\\.client\\.AsyncRestTemplate;?"
    );
    private static final String MODERN_WEBCLIENT_IMPORT =
            "import org.springframework.web.reactive.function.client.WebClient;";

    private static final Pattern ASYNC_REST_BEAN_PATTERN = Pattern.compile(
            "(?s)@Bean(?:\\([^)]*\\))?\\s+public\\s+AsyncRestTemplate\\s+[a-zA-Z0-9_]+\\s*\\([^)]*\\)\\s*\\{.*?return\\s+new\\s+AsyncRestTemplate\\s*\\([^)]*\\);?\\s*\\}"
    );

    private static final String WEBFLUX_STARTER_DEP = """
                    <dependency>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-webflux</artifactId>
                    </dependency>""";

    private SpringWebClientModernizer() {}

    public static WebClientModernizationResult modernize(Path projectRoot) {
        return modernize(projectRoot, true);
    }

    public static WebClientModernizationResult modernize(Path projectRoot, boolean updatePom) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return WebClientModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean webClientDetected = false;

        // 1. Scan Java files for AsyncRestTemplate and WebClient usage
        Path srcDir = projectRoot.resolve("src");
        if (Files.isDirectory(srcDir)) {
            try (Stream<Path> stream = Files.walk(srcDir)) {
                List<Path> javaFiles = stream.filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".java")).toList();
                Pattern asyncRestUsage = Pattern.compile("\\bAsyncRestTemplate\\b");

                for (Path javaFile : javaFiles) {
                    try {
                        String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (OLD_ASYNC_REST_IMPORT.matcher(updated).find()) {
                            updated = OLD_ASYNC_REST_IMPORT.matcher(updated).replaceAll(MODERN_WEBCLIENT_IMPORT);
                        }

                        if (ASYNC_REST_BEAN_PATTERN.matcher(updated).find()) {
                            updated = ASYNC_REST_BEAN_PATTERN.matcher(updated).replaceAll("""
                                    @Bean
                                    public WebClient webClient(WebClient.Builder builder) {
                                        return builder.build();
                                    }""");
                            rulesApplied.add("REPLACE_ASYNC_REST_TEMPLATE_BEAN_WITH_WEBCLIENT");
                        }

                        if (asyncRestUsage.matcher(updated).find()) {
                            updated = asyncRestUsage.matcher(updated).replaceAll("WebClient");
                            rulesApplied.add("REPLACE_ASYNC_REST_TEMPLATE_TYPE_WITH_WEBCLIENT");
                        }

                        if (content.contains("WebClient") || content.contains("AsyncRestTemplate")) {
                            webClientDetected = true;
                        }

                        if (!updated.equals(content)) {
                            webClientDetected = true;
                            Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(javaFile).toString().replace('\\', '/'));
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process Java file " + javaFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan src directory for WebClient: " + e.getMessage());
            }
        }

        // 2. Scan and inject spring-boot-starter-webflux into pom.xml if WebClient is used
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                if (webClientDetected && !pomContent.contains("spring-boot-starter-webflux")) {
                    if (updatePom) {
                        int insertIdx = pomContent.lastIndexOf("</dependencies>");
                        if (insertIdx != -1) {
                            String updated = pomContent.substring(0, insertIdx) +
                                    "    " + WEBFLUX_STARTER_DEP + "\n    " +
                                    pomContent.substring(insertIdx);
                            Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add("pom.xml");
                            rulesApplied.add("INJECT_SPRING_BOOT_STARTER_WEBFLUX_DEPENDENCY");
                            changes++;
                        }
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml for WebClient dependencies: " + e.getMessage());
            }
        }

        // 3. Generate production WebClientConfiguration.java if WebClient is detected
        if (webClientDetected) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/webclient");
            try {
                Files.createDirectories(targetPackageDir);
                Path configFile = targetPackageDir.resolve("WebClientConfiguration.java");
                if (!Files.exists(configFile)) {
                    String configSource = generateWebClientConfigSource();
                    Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                    rulesApplied.add("GENERATE_WEBCLIENT_CONNECTION_POOL_CONFIGURATION");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate WebClientConfiguration: " + e.getMessage());
            }
        }

        return new WebClientModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateWebClientConfigSource() {
        return """
                package io.elmos.generated.webclient;

                import io.netty.channel.ChannelOption;
                import io.netty.handler.timeout.ReadTimeoutHandler;
                import io.netty.handler.timeout.WriteTimeoutHandler;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.http.client.reactive.ReactorClientHttpConnector;
                import org.springframework.web.reactive.function.client.WebClient;
                import reactor.netty.http.client.HttpClient;
                import reactor.netty.resources.ConnectionProvider;

                import java.time.Duration;
                import java.util.concurrent.TimeUnit;

                /**
                 * Enterprise-grade WebClient configuration with bounded connection pools and strict timeouts.
                 *
                 * <p>Protects services against socket leakage, thread starvation, and connection hoarding.</p>
                 */
                @Configuration(proxyBeanMethods = false)
                @ConditionalOnClass(WebClient.class)
                public class WebClientConfiguration {

                    @Bean
                    @ConditionalOnMissingBean
                    public WebClient.Builder webClientBuilder() {
                        ConnectionProvider provider = ConnectionProvider.builder("elmos-webclient-pool")
                                .maxConnections(500)
                                .pendingAcquireMaxCount(1000)
                                .pendingAcquireTimeout(Duration.ofSeconds(5))
                                .maxIdleTime(Duration.ofSeconds(20))
                                .build();

                        HttpClient httpClient = HttpClient.create(provider)
                                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5000)
                                .responseTimeout(Duration.ofSeconds(5))
                                .doOnConnected(conn -> conn
                                        .addHandlerLast(new ReadTimeoutHandler(5, TimeUnit.SECONDS))
                                        .addHandlerLast(new WriteTimeoutHandler(5, TimeUnit.SECONDS)));

                        return WebClient.builder()
                                .clientConnector(new ReactorClientHttpConnector(httpClient));
                    }

                    @Bean
                    @ConditionalOnMissingBean
                    public WebClient defaultWebClient(WebClient.Builder builder) {
                        return builder.build();
                    }
                }
                """;
    }
}
