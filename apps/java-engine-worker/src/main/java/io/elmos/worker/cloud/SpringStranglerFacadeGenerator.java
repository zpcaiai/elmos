package io.elmos.worker.cloud;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/**
 * Generates progressive Strangler Fig facade artifacts for phased enterprise coexistence:
 * <ul>
 *   <li>Spring Cloud Gateway application.yml / Java RouteLocator configuration</li>
 *   <li>Nginx reverse proxy upstream and location configuration</li>
 * </ul>
 * Enables zero-downtime routing of modernized endpoints to Boot 3 services while
 * preserving legacy monolith handling for unmigrated paths.
 */
public final class SpringStranglerFacadeGenerator {

    public record StranglerRouteSpec(
            String pathPattern,
            String targetService,
            boolean isModernized
    ) {}

    public record StranglerFacadeArtifacts(
            String gatewayYaml,
            String gatewayJavaConfig,
            String nginxConfig,
            Set<String> generatedFiles
    ) {}

    private SpringStranglerFacadeGenerator() {}

    public static StranglerFacadeArtifacts generate(
            Path outputDir,
            String legacyBaseUrl,
            String modernBaseUrl,
            List<String> modernizedPathPrefixes
    ) throws IOException {
        Objects.requireNonNull(outputDir, "outputDir must not be null");
        Objects.requireNonNull(legacyBaseUrl, "legacyBaseUrl must not be null");
        Objects.requireNonNull(modernBaseUrl, "modernBaseUrl must not be null");

        Files.createDirectories(outputDir);
        Set<String> createdFiles = new LinkedHashSet<>();

        // 1. Generate Spring Cloud Gateway YAML
        StringBuilder yaml = new StringBuilder("""
                spring:
                  cloud:
                    gateway:
                      routes:
                """);

        int routeIndex = 1;
        for (String prefix : modernizedPathPrefixes) {
            String cleanPrefix = prefix.startsWith("/") ? prefix : "/" + prefix;
            if (!cleanPrefix.endsWith("/**")) {
                cleanPrefix = cleanPrefix.endsWith("/") ? cleanPrefix + "**" : cleanPrefix + "/**";
            }
            yaml.append(String.format("""
                        - id: modern_route_%d
                          uri: %s
                          predicates:
                            - Path=%s
                          filters:
                            - AddRequestHeader=X-Strangler-Route, modern
                            - AddResponseHeader=X-Powered-By, SpringBoot3-Modernized
                    """, routeIndex++, modernBaseUrl, cleanPrefix));
        }

        // Fallback route to legacy monolith
        yaml.append(String.format("""
                    - id: legacy_fallback_route
                      uri: %s
                      predicates:
                        - Path=/**
                      filters:
                        - AddRequestHeader=X-Strangler-Route, legacy
                        - AddResponseHeader=X-Powered-By, SpringBoot2-Legacy
                """, legacyBaseUrl));

        Path gatewayYamlFile = outputDir.resolve("application-strangler.yml");
        Files.writeString(gatewayYamlFile, yaml.toString(), StandardCharsets.UTF_8);
        createdFiles.add(gatewayYamlFile.getFileName().toString());

        // 2. Generate Gateway Java RouteLocator Configuration
        StringBuilder javaBuilder = new StringBuilder("""
                package io.elmos.worker.cloud;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.cloud.gateway.route.RouteLocator;
                import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;

                @Configuration
                public class StranglerFacadeGatewayConfiguration {

                    @Bean
                    public RouteLocator customRouteLocator(RouteLocatorBuilder builder) {
                        return builder.routes()
                """);

        for (int i = 0; i < modernizedPathPrefixes.size(); i++) {
            String prefix = modernizedPathPrefixes.get(i);
            String cleanPrefix = prefix.startsWith("/") ? prefix : "/" + prefix;
            if (!cleanPrefix.endsWith("/**")) {
                cleanPrefix = cleanPrefix.endsWith("/") ? cleanPrefix + "**" : cleanPrefix + "/**";
            }
            javaBuilder.append(String.format("""
                                .route("modern_%d", r -> r.path("%s")
                                        .filters(f -> f.addRequestHeader("X-Strangler-Route", "modern")
                                                       .addResponseHeader("X-Powered-By", "SpringBoot3-Modernized"))
                                        .uri("%s"))
                    """, i + 1, cleanPrefix, modernBaseUrl));
        }

        javaBuilder.append(String.format("""
                                .route("legacy_fallback", r -> r.path("/**")
                                        .filters(f -> f.addRequestHeader("X-Strangler-Route", "legacy"))
                                        .uri("%s"))
                                .build();
                    }
                }
                """, legacyBaseUrl));

        Path javaFile = outputDir.resolve("StranglerFacadeGatewayConfiguration.java");
        Files.writeString(javaFile, javaBuilder.toString(), StandardCharsets.UTF_8);
        createdFiles.add(javaFile.getFileName().toString());

        // 3. Generate Nginx Proxy Configuration
        StringBuilder nginx = new StringBuilder(String.format("""
                # Elmos Strangler Fig Nginx Reverse Proxy Configuration
                upstream legacy_backend {
                    server %s;
                }

                upstream modern_backend {
                    server %s;
                }

                server {
                    listen 80;
                    server_name api.enterprise.corp;

                """, legacyBaseUrl.replace("http://", "").replace("https://", ""),
                modernBaseUrl.replace("http://", "").replace("https://", "")));

        for (String prefix : modernizedPathPrefixes) {
            String location = prefix.startsWith("/") ? prefix : "/" + prefix;
            location = location.replaceAll("/\\*\\*", "");
            nginx.append(String.format("""
                    location %s {
                        proxy_pass http://modern_backend;
                        proxy_set_header Host $host;
                        proxy_set_header X-Strangler-Route "modern";
                        add_header X-Powered-By "SpringBoot3-Modernized";
                    }

                """, location));
        }

        nginx.append("""
                    location / {
                        proxy_pass http://legacy_backend;
                        proxy_set_header Host $host;
                        proxy_set_header X-Strangler-Route "legacy";
                    }
                }
                """);

        Path nginxFile = outputDir.resolve("strangler_proxy.conf");
        Files.writeString(nginxFile, nginx.toString(), StandardCharsets.UTF_8);
        createdFiles.add(nginxFile.getFileName().toString());

        return new StranglerFacadeArtifacts(
                yaml.toString(),
                javaBuilder.toString(),
                nginx.toString(),
                createdFiles
        );
    }
}
