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
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for Spring Boot Admin (SBA) Client 3.x integration.
 *
 * <p>Key enterprise operational challenges in Spring Boot 3 migration:
 * <ol>
 *   <li><b>Client Dependency Incompatibility:</b> Older {@code de.codecentric:spring-boot-admin-starter-client} 2.x
 *       fails to serialize registration metadata against Spring Boot 3 Actuator endpoints.
 *       Upgrades to {@code 3.2.3+}.</li>
 *   <li><b>Actuator Endpoint Exposure for Operations:</b> Configures {@code management.endpoints.web.exposure.include}
 *       to expose essential diagnostic endpoints ({@code health,info,metrics,env,loggers,threaddump}) for the Admin console.</li>
 *   <li><b>Security & Heartbeat Probe Exemption:</b> Generates {@code AdminClientHeartbeatSecurityConfiguration.java}
 *       to ensure registration credentials and Actuator health probes are correctly authenticated or exempted.</li>
 * </ol>
 */
public final class SpringAdminClientModernizer {

    public record AdminClientModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static AdminClientModernizationResult empty() {
            return new AdminClientModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern OLD_ADMIN_CLIENT_DEP_PATTERN = Pattern.compile(
            "(?s)<dependency>\\s*<groupId>de\\.codecentric</groupId>\\s*<artifactId>spring-boot-admin-starter-client</artifactId>\\s*(?:<version>[^<]+</version>\\s*)?</dependency>"
    );

    private static final String MODERN_ADMIN_CLIENT_DEP = """
            <dependency>
                <groupId>de.codecentric</groupId>
                <artifactId>spring-boot-admin-starter-client</artifactId>
                <version>3.2.3</version>
            </dependency>""";

    private SpringAdminClientModernizer() {}

    public static AdminClientModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return AdminClientModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean adminClientDetected = false;

        // 1. Scan and modernize pom.xml dependencies
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                Matcher matcher = OLD_ADMIN_CLIENT_DEP_PATTERN.matcher(pomContent);
                if (matcher.find()) {
                    adminClientDetected = true;
                    String updated = matcher.replaceAll(Matcher.quoteReplacement(MODERN_ADMIN_CLIENT_DEP));
                    Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add("pom.xml");
                    rulesApplied.add("UPGRADE_SPRING_BOOT_ADMIN_CLIENT_DEPENDENCY_3_2_3");
                    changes++;
                } else if (pomContent.contains("spring-boot-admin-starter-client")) {
                    adminClientDetected = true;
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml for Spring Boot Admin: " + e.getMessage());
            }
        }

        // 2. Scan and modernize application configuration for admin client url and actuator exposure
        Path resourcesDir = projectRoot.resolve("src/main/resources");
        if (Files.isDirectory(resourcesDir)) {
            try (Stream<Path> stream = Files.walk(resourcesDir)) {
                List<Path> configFiles = stream.filter(p -> Files.isRegularFile(p) &&
                        (p.toString().endsWith(".yml") || p.toString().endsWith(".yaml") || p.toString().endsWith(".properties"))
                ).toList();

                for (Path configFile : configFiles) {
                    try {
                        String content = Files.readString(configFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (content.contains("boot.admin.client") || content.contains("admin.client.url")
                                || (content.contains("admin:") && content.contains("client:"))
                                || content.contains("spring-boot-admin")) {
                            adminClientDetected = true;
                        }

                        // Ensure comprehensive monitoring endpoints are exposed
                        if (adminClientDetected && !updated.contains("loggers")) {
                            Pattern quotedInclude = Pattern.compile("(?m)^(\\s*include:\\s*[\"'])([^\"']+)([\"']\\s*)$");
                            Matcher qm = quotedInclude.matcher(updated);
                            if (qm.find()) {
                                updated = qm.replaceAll("$1$2,metrics,env,loggers$3");
                            } else {
                                Pattern unquoted = Pattern.compile("(?m)^(\\s*include:\\s*)([^\"'\\r\\n]+)$");
                                if (unquoted.matcher(updated).find()) {
                                    updated = unquoted.matcher(updated).replaceAll("$1$2,metrics,env,loggers");
                                } else if (content.contains("management:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*management:\\s*)$",
                                            "$1\n$1  endpoints:\n$1    web:\n$1      exposure:\n$1        include: \"health,info,metrics,env,loggers\"");
                                }
                            }
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString());
                            rulesApplied.add("EXPOSE_ACTUATOR_ENDPOINTS_FOR_ADMIN_CLIENT");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources for Spring Boot Admin: " + e.getMessage());
            }
        }

        // 3. Generate AdminClientHeartbeatSecurityConfiguration.java if admin client detected
        if (adminClientDetected) {
            Path targetPackageDir = projectRoot.resolve("src/main/java/io/elmos/generated/admin");
            try {
                Files.createDirectories(targetPackageDir);
                Path securityFile = targetPackageDir.resolve("AdminClientHeartbeatSecurityConfiguration.java");
                if (!Files.exists(securityFile)) {
                    String securitySource = generateAdminSecuritySource();
                    Files.writeString(securityFile, securitySource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(securityFile).toString());
                    rulesApplied.add("GENERATE_ADMIN_CLIENT_HEARTBEAT_SECURITY_CONFIGURATION");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate AdminClientHeartbeatSecurityConfiguration: " + e.getMessage());
            }
        }

        return new AdminClientModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateAdminSecuritySource() {
        return """
                package io.elmos.generated.admin;

                import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                /**
                 * Security filter configuration for Spring Boot Admin heartbeat and diagnostic probes.
                 *
                 * <p>Permits health and info endpoints for operational dashboards while safeguarding sensitive operations.</p>
                 */
                @Configuration(proxyBeanMethods = false)
                @ConditionalOnClass({HttpSecurity.class, EndpointRequest.class})
                @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
                public class AdminClientHeartbeatSecurityConfiguration {

                    @Bean
                    public SecurityFilterChain adminHeartbeatSecurityFilterChain(HttpSecurity http) throws Exception {
                        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                            .authorizeHttpRequests(authorize -> authorize
                                .requestMatchers(EndpointRequest.to("health", "info")).permitAll()
                                .anyRequest().authenticated()
                            )
                            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
                            .csrf(csrf -> csrf.disable());
                        return http.build();
                    }
                }
                """;
    }
}
