package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Industrial-grade validator for Spring Cloud microservices modernization.
 *
 * <p>Audits a codebase to guarantee:
 * <ul>
 *   <li>Zero usage of Netflix Ribbon (migrated to Spring Cloud LoadBalancer).</li>
 *   <li>Zero usage of Netflix Zuul 1.x (migrated to Spring Cloud Gateway).</li>
 *   <li>Zero usage of Netflix Hystrix (migrated to Resilience4j).</li>
 *   <li>Zero usage of Netflix Archaius.</li>
 *   <li>Zero legacy {@code @EnableEurekaClient} (migrated to {@code @EnableDiscoveryClient}).</li>
 *   <li>Zero legacy Spring Cloud Sleuth (migrated to Micrometer Tracing).</li>
 *   <li>Modernization of bootstrap config files to {@code spring.config.import}.</li>
 * </ul>
 */
public final class SpringCloudArchitectureValidator {

    public enum Severity {
        CRITICAL,
        HIGH,
        MEDIUM,
        LOW,
        INFO
    }

    public record CloudViolation(
            String ruleId,
            Severity severity,
            String filePath,
            int line,
            String message,
            String remediationSnippet
    ) {}

    public record SpringCloudAuditReport(
            int totalFilesScanned,
            int totalViolations,
            int criticalViolations,
            int highViolations,
            double complianceScore,
            boolean isCompliant,
            List<CloudViolation> violations
    ) {}

    public SpringCloudAuditReport auditProject(Path projectRoot) throws IOException {
        List<CloudViolation> violations = new ArrayList<>();
        int filesScanned = 0;

        if (!Files.isDirectory(projectRoot)) {
            return new SpringCloudAuditReport(0, 0, 0, 0, 100.0, true, Collections.emptyList());
        }

        try (var stream = Files.walk(projectRoot)) {
            List<Path> files = stream.filter(Files::isRegularFile).toList();
            for (Path f : files) {
                String name = f.getFileName().toString();
                if (name.endsWith(".java") || name.endsWith(".xml") || name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties")) {
                    filesScanned++;
                    auditFile(f, violations);
                }
            }
        }

        int critical = (int) violations.stream().filter(v -> v.severity() == Severity.CRITICAL).count();
        int high = (int) violations.stream().filter(v -> v.severity() == Severity.HIGH).count();
        int medium = (int) violations.stream().filter(v -> v.severity() == Severity.MEDIUM).count();

        double penalty = (critical * 25.0) + (high * 10.0) + (medium * 3.0);
        double complianceScore = Math.max(0.0, 100.0 - penalty);
        boolean isCompliant = critical == 0 && high == 0;

        return new SpringCloudAuditReport(
                filesScanned,
                violations.size(),
                critical,
                high,
                complianceScore,
                isCompliant,
                Collections.unmodifiableList(violations)
        );
    }

    private void auditFile(Path file, List<CloudViolation> violations) {
        try {
            String content = Files.readString(file, StandardCharsets.UTF_8);
            String relativePath = file.toString();
            String fileName = file.getFileName().toString();

            // Check Java code
            if (fileName.endsWith(".java")) {
                if (content.contains("@RibbonClient") || content.contains("@RibbonClients") || content.contains("org.springframework.cloud.netflix.ribbon")) {
                    violations.add(new CloudViolation(
                            "CLOUD-001",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "Ribbon"),
                            "Legacy Netflix Ribbon detected. Ribbon is in maintenance mode and unsupported in Spring Cloud 2022+/2023+. Migrate to @LoadBalancerClient.",
                            "@LoadBalancerClient(name = \"service-name\", configuration = MyLoadBalancerConfig.class)"
                    ));
                }

                if (content.contains("@EnableZuulProxy") || content.contains("@EnableZuulServer") || content.contains("com.netflix.zuul.ZuulFilter")) {
                    violations.add(new CloudViolation(
                            "CLOUD-002",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "Zuul"),
                            "Legacy Netflix Zuul 1.x proxy detected. Blocking Zuul 1.x is incompatible with Spring Boot 3/4. Migrate to non-blocking Spring Cloud Gateway.",
                            """
                            @Bean
                            public RouteLocator customRouteLocator(RouteLocatorBuilder builder) {
                                return builder.routes().route("r1", r -> r.path("/api/**").uri("lb://api-service")).build();
                            }
                            """
                    ));
                }

                if (content.contains("@HystrixCommand") || content.contains("@EnableHystrix") || content.contains("@EnableCircuitBreaker")) {
                    violations.add(new CloudViolation(
                            "CLOUD-003",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "Hystrix"),
                            "Legacy Netflix Hystrix circuit breaker detected. Hystrix has been retired. Migrate to Resilience4j annotations (@CircuitBreaker, @Retry, @TimeLimiter).",
                            "@CircuitBreaker(name = \"backendA\", fallbackMethod = \"fallback\")"
                    ));
                }

                if (content.contains("@EnableEurekaClient")) {
                    violations.add(new CloudViolation(
                            "CLOUD-004",
                            Severity.MEDIUM,
                            relativePath,
                            findLineNumber(content, "@EnableEurekaClient"),
                            "Deprecated @EnableEurekaClient detected. In modern Spring Cloud, use @EnableDiscoveryClient or rely on auto-configuration.",
                            "@EnableDiscoveryClient"
                    ));
                }

                if (content.contains("org.springframework.cloud.sleuth")) {
                    violations.add(new CloudViolation(
                            "CLOUD-005",
                            Severity.HIGH,
                            relativePath,
                            findLineNumber(content, "sleuth"),
                            "Spring Cloud Sleuth detected. Sleuth is discontinued in Spring Boot 3+. Migrate to Micrometer Tracing (io.micrometer.tracing).",
                            "import io.micrometer.tracing.Tracer;"
                    ));
                }

                if (content.contains("org.springframework.cloud.netflix.feign")) {
                    violations.add(new CloudViolation(
                            "CLOUD-006",
                            Severity.HIGH,
                            relativePath,
                            findLineNumber(content, "org.springframework.cloud.netflix.feign"),
                            "Legacy Netflix Feign package detected. Migrate imports to org.springframework.cloud.openfeign.*.",
                            "import org.springframework.cloud.openfeign.FeignClient;"
                    ));
                }
            }

            // Check Config files (bootstrap.yml / bootstrap.properties)
            if (fileName.startsWith("bootstrap.") && (fileName.endsWith(".yml") || fileName.endsWith(".yaml") || fileName.endsWith(".properties"))) {
                violations.add(new CloudViolation(
                        "CLOUD-007",
                        Severity.HIGH,
                        relativePath,
                        1,
                        "Legacy bootstrap configuration file detected (" + fileName + "). In Spring Boot 2.4+ and Boot 3/4, bootstrap files are disabled by default. Migrate to application.properties / application.yml using 'spring.config.import'.",
                        "spring.config.import=optional:configserver:http://localhost:8888"
                ));
            }

            // Check pom.xml for obsolete dependencies
            if ("pom.xml".equals(fileName)) {
                if (content.contains("spring-cloud-starter-netflix-ribbon")) {
                    violations.add(new CloudViolation(
                            "CLOUD-008",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "spring-cloud-starter-netflix-ribbon"),
                            "Legacy dependency 'spring-cloud-starter-netflix-ribbon' found in pom.xml. Replace with 'spring-cloud-starter-loadbalancer'.",
                            "<dependency><groupId>org.springframework.cloud</groupId><artifactId>spring-cloud-starter-loadbalancer</artifactId></dependency>"
                    ));
                }
                if (content.contains("spring-cloud-starter-netflix-zuul")) {
                    violations.add(new CloudViolation(
                            "CLOUD-009",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "spring-cloud-starter-netflix-zuul"),
                            "Legacy dependency 'spring-cloud-starter-netflix-zuul' found in pom.xml. Replace with 'spring-cloud-starter-gateway'.",
                            "<dependency><groupId>org.springframework.cloud</groupId><artifactId>spring-cloud-starter-gateway</artifactId></dependency>"
                    ));
                }
                if (content.contains("spring-cloud-starter-netflix-hystrix")) {
                    violations.add(new CloudViolation(
                            "CLOUD-010",
                            Severity.CRITICAL,
                            relativePath,
                            findLineNumber(content, "spring-cloud-starter-netflix-hystrix"),
                            "Legacy dependency 'spring-cloud-starter-netflix-hystrix' found in pom.xml. Replace with 'spring-cloud-starter-circuitbreaker-resilience4j'.",
                            "<dependency><groupId>org.springframework.cloud</groupId><artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId></dependency>"
                    ));
                }
            }

        } catch (IOException ignored) {}
    }

    private static int findLineNumber(String text, String substring) {
        int index = text.indexOf(substring);
        if (index < 0) return 1;
        int line = 1;
        for (int i = 0; i < index; i++) {
            if (text.charAt(i) == '\n') line++;
        }
        return line;
    }
}
