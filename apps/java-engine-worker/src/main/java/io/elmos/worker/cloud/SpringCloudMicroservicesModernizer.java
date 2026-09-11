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
 * Industrial-grade transformer for Spring Cloud microservice components modernization (Boot 1.5/2.x to Boot 3.x/4.x).
 *
 * <p>Modernizes:
 * <ol>
 *   <li><b>Netflix Ribbon to Spring Cloud LoadBalancer:</b>
 *       Replaces {@code spring-cloud-starter-netflix-ribbon} with {@code spring-cloud-starter-loadbalancer},
 *       and converts {@code @RibbonClient} to {@code @LoadBalancerClient}.</li>
 *   <li><b>Netflix Zuul to Spring Cloud Gateway:</b>
 *       Replaces {@code spring-cloud-starter-netflix-zuul} with {@code spring-cloud-starter-gateway},
 *       removes {@code @EnableZuulProxy}, and converts {@code ZuulFilter} to {@code GlobalFilter}.</li>
 *   <li><b>Netflix Hystrix to Resilience4j:</b>
 *       Replaces {@code spring-cloud-starter-netflix-hystrix} with {@code resilience4j-spring-boot3},
 *       removes {@code @EnableCircuitBreaker}, and converts {@code @HystrixCommand} to {@code @CircuitBreaker}.</li>
 *   <li><b>Feign to OpenFeign:</b>
 *       Normalizes packages from {@code org.springframework.cloud.netflix.feign} to {@code org.springframework.cloud.openfeign}.</li>
 *   <li><b>Bootstrap Context Modernization:</b>
 *       Migrates {@code bootstrap.yml} / {@code bootstrap.properties} to {@code spring.config.import=optional:configserver:...}.</li>
 *   <li><b>Distributed Tracing:</b>
 *       Migrates {@code spring-cloud-starter-sleuth} to {@code micrometer-tracing-bridge-brave}.</li>
 * </ol>
 */
public final class SpringCloudMicroservicesModernizer {

    public record CloudModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied
    ) {
        public static CloudModernizationResult empty() {
            return new CloudModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList());
        }
    }

    private SpringCloudMicroservicesModernizer() {}

    public static CloudModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return CloudModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        int changesCount = 0;

        try (var stream = Files.walk(projectRoot)) {
            List<Path> allFiles = stream.filter(Files::isRegularFile).toList();

            for (Path file : allFiles) {
                String fileName = file.getFileName().toString();
                if (fileName.equals("pom.xml")) {
                    CloudModernizationResult pomRes = modernizePom(projectRoot, file);
                    if (pomRes.modified()) {
                        changesCount += pomRes.changesCount();
                        modifiedFiles.addAll(pomRes.modifiedFiles());
                        rulesApplied.addAll(pomRes.rulesApplied());
                    }
                } else if (fileName.endsWith(".java")) {
                    CloudModernizationResult javaRes = modernizeJava(projectRoot, file);
                    if (javaRes.modified()) {
                        changesCount += javaRes.changesCount();
                        modifiedFiles.addAll(javaRes.modifiedFiles());
                        rulesApplied.addAll(javaRes.rulesApplied());
                    }
                } else if (fileName.startsWith("bootstrap.") || fileName.startsWith("application.")) {
                    CloudModernizationResult configRes = modernizeConfig(projectRoot, file);
                    if (configRes.modified()) {
                        changesCount += configRes.changesCount();
                        modifiedFiles.addAll(configRes.modifiedFiles());
                        rulesApplied.addAll(configRes.rulesApplied());
                    }
                }
            }
        } catch (IOException e) {
            return CloudModernizationResult.empty();
        }

        return new CloudModernizationResult(
                changesCount > 0, changesCount,
                Collections.unmodifiableSet(modifiedFiles),
                Collections.unmodifiableList(rulesApplied)
        );
    }

    static CloudModernizationResult modernizePom(Path projectRoot, Path pom) {
        try {
            String original = Files.readString(pom, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // 1. Ribbon -> LoadBalancer
            if (content.contains("spring-cloud-starter-netflix-ribbon")) {
                content = content.replace("spring-cloud-starter-netflix-ribbon", "spring-cloud-starter-loadbalancer");
                rules.add("POM_RIBBON_TO_LOADBALANCER");
                changes++;
            }

            // 2. Zuul -> Gateway
            if (content.contains("spring-cloud-starter-netflix-zuul")) {
                content = content.replace("spring-cloud-starter-netflix-zuul", "spring-cloud-starter-gateway");
                rules.add("POM_ZUUL_TO_GATEWAY");
                changes++;
            }

            // 3. Hystrix -> Resilience4j
            if (content.contains("spring-cloud-starter-netflix-hystrix")) {
                content = content.replace(
                        "<artifactId>spring-cloud-starter-netflix-hystrix</artifactId>",
                        "<groupId>io.github.resilience4j</groupId>\n      <artifactId>resilience4j-spring-boot3</artifactId>"
                );
                // Also ensure AOP is present for annotations
                if (!content.contains("spring-boot-starter-aop")) {
                    content = content.replace("</dependencies>", "    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>spring-boot-starter-aop</artifactId>\n    </dependency>\n  </dependencies>");
                }
                rules.add("POM_HYSTRIX_TO_RESILIENCE4J");
                changes++;
            }

            // 4. Feign legacy groupId
            if (content.contains("spring-cloud-starter-feign")) {
                content = content.replace("spring-cloud-starter-feign", "spring-cloud-starter-openfeign");
                rules.add("POM_FEIGN_TO_OPENFEIGN");
                changes++;
            }

            // 5. Sleuth -> Micrometer Tracing
            if (content.contains("spring-cloud-starter-sleuth")) {
                content = content.replace(
                        "<artifactId>spring-cloud-starter-sleuth</artifactId>",
                        "<groupId>io.micrometer</groupId>\n      <artifactId>micrometer-tracing-bridge-brave</artifactId>"
                );
                rules.add("POM_SLEUTH_TO_MICROMETER_TRACING");
                changes++;
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(pom, content, StandardCharsets.UTF_8);
                String relPath = projectRoot.relativize(pom).toString().replace('\\', '/');
                return new CloudModernizationResult(true, changes, Set.of(relPath), rules);
            }
        } catch (IOException ignored) {}
        return CloudModernizationResult.empty();
    }

    static CloudModernizationResult modernizeJava(Path projectRoot, Path file) {
        try {
            String original = Files.readString(file, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // 1. Ribbon -> LoadBalancer
            if (content.contains("RibbonClient")) {
                content = content.replace(
                        "import org.springframework.cloud.netflix.ribbon.RibbonClient;",
                        "import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;"
                );
                content = content.replace("@RibbonClient", "@LoadBalancerClient");
                rules.add("JAVA_RIBBON_CLIENT_TO_LOADBALANCER_CLIENT");
                changes++;
            }
            if (content.contains("RibbonClients")) {
                content = content.replace(
                        "import org.springframework.cloud.netflix.ribbon.RibbonClients;",
                        "import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClients;"
                );
                content = content.replace("@RibbonClients", "@LoadBalancerClients");
                rules.add("JAVA_RIBBON_CLIENTS_TO_LOADBALANCER_CLIENTS");
                changes++;
            }

            // 2. Zuul -> Gateway
            if (content.contains("@EnableZuulProxy") || content.contains("@EnableZuulServer")) {
                content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.netflix\\.zuul\\.EnableZuulProxy;\\s*", "");
                content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.netflix\\.zuul\\.EnableZuulServer;\\s*", "");
                content = content.replaceAll("@EnableZuulProxy\\s*", "");
                content = content.replaceAll("@EnableZuulServer\\s*", "");
                content = ensureImport(content, "org.springframework.context.annotation.Configuration");
                if (!content.contains("@Configuration")) {
                    content = content.replace("public class", "@Configuration\npublic class");
                }
                rules.add("JAVA_REMOVE_ENABLE_ZUUL_PROXY");
                changes++;
            }
            if (content.contains("ZuulFilter")) {
                content = content.replaceAll("import\\s+com\\.netflix\\.zuul\\.ZuulFilter;\\s*", "");
                content = content.replaceAll("import\\s+com\\.netflix\\.zuul\\.context\\.RequestContext;\\s*", "");
                content = content.replaceAll("import\\s+com\\.netflix\\.zuul\\.exception\\.ZuulException;\\s*", "");
                content = ensureImport(content, "org.springframework.cloud.gateway.filter.GlobalFilter");
                content = ensureImport(content, "org.springframework.cloud.gateway.filter.GatewayFilterChain");
                content = ensureImport(content, "org.springframework.core.Ordered");
                content = ensureImport(content, "org.springframework.web.server.ServerWebExchange");
                content = ensureImport(content, "reactor.core.publisher.Mono");

                content = content.replace("extends ZuulFilter", "implements GlobalFilter, Ordered");

                // filterOrder() -> getOrder()
                if (content.contains("filterOrder()")) {
                    content = content.replace("public int filterOrder()", "@Override\n    public int getOrder()");
                    content = content.replace("int filterOrder()", "@Override\n    public int getOrder()");
                }

                // filterType() -> deprecated/noop helper
                if (content.contains("filterType()")) {
                    content = content.replace("public String filterType()", "// Replaced by Gateway filter chain position\n    public String filterType()");
                }

                // run() -> filter(ServerWebExchange exchange, GatewayFilterChain chain)
                Pattern runPattern = Pattern.compile("(@Override\\s+)?public\\s+Object\\s+run\\s*\\(\\s*\\)\\s*(?:throws\\s+[a-zA-Z0-9_]+)?\\s*\\{");
                Matcher runMatcher = runPattern.matcher(content);
                if (runMatcher.find()) {
                    String replacement = "@Override\n    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {";
                    content = runMatcher.replaceFirst(replacement);

                    // If body returns null, replace with return chain.filter(exchange);
                    int filterStart = content.indexOf(replacement);
                    if (filterStart >= 0) {
                        int bodyStart = filterStart + replacement.length();
                        int bodyEnd = findMatchingBrace(content, bodyStart - 1);
                        if (bodyEnd > bodyStart) {
                            String body = content.substring(bodyStart, bodyEnd);
                            if (body.contains("return null;")) {
                                body = body.replace("return null;", "return chain.filter(exchange);");
                            } else if (!body.contains("return chain.filter(exchange);")) {
                                body = body + "\n        return chain.filter(exchange);\n    ";
                            }
                            content = content.substring(0, bodyStart) + body + content.substring(bodyEnd);
                        }
                    }
                }

                rules.add("JAVA_ZUUL_FILTER_TO_GLOBAL_FILTER");
                changes++;
            }

            // 3. Ribbon IRule Modernization
            if (content.contains("IRule") || content.contains("RoundRobinRule") || content.contains("RandomRule")) {
                content = content.replaceAll("import\\s+com\\.netflix\\.loadbalancer\\.[a-zA-Z0-9_.*]+;\\s*", "");
                content = ensureImport(content, "org.springframework.cloud.client.ServiceInstance");
                content = ensureImport(content, "org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer");
                content = ensureImport(content, "org.springframework.cloud.loadbalancer.core.RoundRobinLoadBalancer");
                content = ensureImport(content, "org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory");
                content = ensureImport(content, "org.springframework.core.env.Environment");
                content = content.replaceAll("\\bIRule\\b", "ReactorLoadBalancer<ServiceInstance>");
                content = content.replaceAll("\\bRoundRobinRule\\b", "RoundRobinLoadBalancer");
                rules.add("JAVA_RIBBON_IRULE_TO_LOADBALANCER");
                changes++;
            }

            // 4. Hystrix -> Resilience4j
            if (content.contains("@EnableCircuitBreaker") || content.contains("@EnableHystrix") || content.contains("@EnableHystrixDashboard")) {
                content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.client\\.circuitbreaker\\.EnableCircuitBreaker;\\s*", "");
                content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.netflix\\.hystrix\\.EnableHystrix;\\s*", "");
                content = content.replaceAll("import\\s+org\\.springframework\\.cloud\\.netflix\\.hystrix\\.dashboard\\.EnableHystrixDashboard;\\s*", "");
                content = content.replaceAll("@EnableCircuitBreaker\\s*", "");
                content = content.replaceAll("@EnableHystrix\\s*", "");
                content = content.replaceAll("@EnableHystrixDashboard\\s*", "");
                rules.add("JAVA_REMOVE_ENABLE_HYSTRIX");
                changes++;
            }
            if (content.contains("@HystrixCommand")) {
                content = content.replace(
                        "import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;",
                        "import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;"
                );
                content = content.replaceAll("import\\s+com\\.netflix\\.hystrix\\.contrib\\.javanica\\.annotation\\.HystrixProperty;\\s*", "");

                // Strip commandProperties = { ... } from @HystrixCommand
                content = content.replaceAll(",\\s*commandProperties\\s*=\\s*\\{[^}]*\\}", "");
                content = content.replaceAll("commandProperties\\s*=\\s*\\{[^}]*\\}\\s*,?", "");

                // Replace @HystrixCommand(fallbackMethod = "xxx") with @CircuitBreaker(name = "defaultService", fallbackMethod = "xxx")
                Pattern hystrixPattern = Pattern.compile("@HystrixCommand\\s*\\(\\s*fallbackMethod\\s*=\\s*\"([^\"]+)\"\\s*\\)");
                Matcher hystrixMatcher = hystrixPattern.matcher(content);
                if (hystrixMatcher.find()) {
                    String fallback = hystrixMatcher.group(1);
                    content = hystrixMatcher.replaceAll("@CircuitBreaker(name = \"defaultService\", fallbackMethod = \"" + fallback + "\")");
                } else {
                    content = content.replace("@HystrixCommand", "@CircuitBreaker(name = \"defaultService\")");
                }
                rules.add("JAVA_HYSTRIX_COMMAND_TO_CIRCUIT_BREAKER");
                changes++;
            }

            // 5. OpenFeign Package normalization
            if (content.contains("org.springframework.cloud.netflix.feign")) {
                content = content.replace("org.springframework.cloud.netflix.feign", "org.springframework.cloud.openfeign");
                rules.add("JAVA_FEIGN_PACKAGE_MODERNIZATION");
                changes++;
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(file, content, StandardCharsets.UTF_8);
                String relPath = projectRoot.relativize(file).toString().replace('\\', '/');
                return new CloudModernizationResult(true, changes, Set.of(relPath), rules);
            }
        } catch (IOException ignored) {}
        return CloudModernizationResult.empty();
    }

    static CloudModernizationResult modernizeConfig(Path projectRoot, Path config) {
        try {
            String original = Files.readString(config, StandardCharsets.UTF_8);
            String content = original;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            String fileName = config.getFileName().toString();

            // 1. bootstrap.yml / bootstrap.properties migration
            if (fileName.startsWith("bootstrap.")) {
                Path appConfig = config.resolveSibling(fileName.replace("bootstrap.", "application."));
                String migrated = content;
                if (content.contains("spring.cloud.config.uri") || content.contains("uri:")) {
                    migrated = migrated + "\nspring.config.import=optional:configserver:${CONFIG_SERVER_URL:http://localhost:8888}\n";
                }
                if (Files.exists(appConfig)) {
                    String existing = Files.readString(appConfig, StandardCharsets.UTF_8);
                    Files.writeString(appConfig, existing + "\n# Migrated from " + fileName + "\n" + migrated, StandardCharsets.UTF_8);
                } else {
                    Files.writeString(appConfig, migrated, StandardCharsets.UTF_8);
                }
                Files.deleteIfExists(config);
                rules.add("CONFIG_BOOTSTRAP_TO_SPRING_CONFIG_IMPORT");
                changes++;
                String relPath = projectRoot.relativize(appConfig).toString().replace('\\', '/');
                return new CloudModernizationResult(true, changes, Set.of(relPath), rules);
            }

            // 2. Zuul routes to Gateway routes modernization
            if (content.contains("zuul.routes.")) {
                content = content.replaceAll("zuul\\.routes\\.([a-zA-Z0-9_-]+)\\.path\\s*=\\s*(.+)", "spring.cloud.gateway.routes[0].id=$1\nspring.cloud.gateway.routes[0].predicates[0]=Path=$2");
                content = content.replaceAll("zuul\\.routes\\.([a-zA-Z0-9_-]+)\\.url\\s*=\\s*(.+)", "spring.cloud.gateway.routes[0].uri=$2");
                rules.add("CONFIG_ZUUL_TO_GATEWAY_ROUTES");
                changes++;
            }

            // 3. Hystrix timeout to Resilience4j
            if (content.contains("hystrix.command.default.")) {
                content = content.replace("hystrix.command.default.execution.isolation.thread.timeoutInMilliseconds", "resilience4j.timelimiter.instances.default.timeout-duration");
                rules.add("CONFIG_HYSTRIX_TO_RESILIENCE4J");
                changes++;
            }

            if (changes > 0 && !content.equals(original)) {
                Files.writeString(config, content, StandardCharsets.UTF_8);
                String relPath = projectRoot.relativize(config).toString().replace('\\', '/');
                return new CloudModernizationResult(true, changes, Set.of(relPath), rules);
            }
        } catch (IOException ignored) {}
        return CloudModernizationResult.empty();
    }

    private static String ensureImport(String content, String fqcn) {
        if (content.contains("import " + fqcn + ";")) {
            return content;
        }
        int pkgIndex = content.indexOf("package ");
        if (pkgIndex >= 0) {
            int pkgEnd = content.indexOf(";", pkgIndex);
            if (pkgEnd >= 0) {
                return content.substring(0, pkgEnd + 1) + "\n\nimport " + fqcn + ";" + content.substring(pkgEnd + 1);
            }
        }
        return "import " + fqcn + ";\n" + content;
    }

    private static int findMatchingBrace(String text, int openBraceIdx) {
        int depth = 0;
        for (int i = openBraceIdx; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch == '{') {
                depth++;
            } else if (ch == '}') {
                depth--;
                if (depth == 0) {
                    return i;
                }
            }
        }
        return -1;
    }
}
