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
 * Industrial-grade modernizer for Microservice Service Registry and Discovery.
 *
 * <p>Key challenges in Spring Boot 2 to 3 Cloud-Native Migration:
 * <ol>
 *   <li><b>Eureka Deprecation:</b> Legacy {@code spring-cloud-starter-netflix-eureka-client} is retired.
 *       This modernizer transitions applications to Nacos 2.x / Spring Cloud Consul.</li>
 *   <li><b>Nacos 2.x/3.x gRPC Dual-Port Topology:</b> Nacos 2.x uses gRPC long-connections on offset port
 *       {@code 9848} (client gRPC) and {@code 9849}. If container network mappings or Kubernetes services
 *       fail to expose and forward port 9848, heartbeats timeout and services silently deregister.
 *       This modernizer auto-configures K8s deployment/service and Dockerfile port topologies.</li>
 *   <li><b>Configuration Normalization:</b> Purges obsolete Eureka configs and injects clean
 *       {@code spring.cloud.nacos.discovery} settings.</li>
 * </ol>
 */
public final class SpringRegistryServiceDiscoveryModernizer {

    public record RegistryModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static RegistryModernizationResult empty() {
            return new RegistryModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern EUREKA_DEP_PATTERN = Pattern.compile("(?s)<dependency>\\s*<groupId>org\\.springframework\\.cloud</groupId>\\s*<artifactId>spring-cloud-starter(?:-netflix)?-eureka-client</artifactId>\\s*(?:<version>[^<]+</version>\\s*)?</dependency>");
    private static final Pattern EUREKA_ANNOTATION_PATTERN = Pattern.compile("(?m)^\\s*@EnableEurekaClient\\s*");
    private static final Pattern EUREKA_IMPORT_PATTERN = Pattern.compile("(?m)^\\s*import\\s+org\\.springframework\\.cloud\\.netflix\\.eureka\\.EnableEurekaClient;\\s*");

    private SpringRegistryServiceDiscoveryModernizer() {}

    public static RegistryModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return RegistryModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        boolean hasEureka = false;
        boolean hasNacos = false;

        // 1. Scan and modernize Java files
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                try {
                    String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                    if (content.contains("EnableEurekaClient")) {
                        hasEureka = true;
                        String updated = EUREKA_IMPORT_PATTERN.matcher(content).replaceAll("");
                        updated = EUREKA_ANNOTATION_PATTERN.matcher(updated).replaceAll("");
                        if (!updated.equals(content)) {
                            Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(javaFile).toString());
                            rulesApplied.add("ENABLE_EUREKA_CLIENT_ANNOTATION_REMOVED");
                            changes++;
                        }
                    }
                } catch (IOException ignored) {}
            }
        } catch (IOException ignored) {}

        // 2. Modernize pom.xml dependencies
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                String updated = pomContent;

                if (EUREKA_DEP_PATTERN.matcher(updated).find()) {
                    hasEureka = true;
                    hasNacos = true;
                    String nacosDep = """
                                <dependency>
                                  <groupId>com.alibaba.cloud</groupId>
                                  <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
                                  <version>2023.0.1.0</version>
                                </dependency>""";
                    updated = EUREKA_DEP_PATTERN.matcher(updated).replaceAll(Matcher.quoteReplacement(nacosDep));
                    rulesApplied.add("EUREKA_CLIENT_REPLACED_WITH_NACOS_DISCOVERY");
                    changes++;
                } else if (updated.contains("spring-cloud-starter-alibaba-nacos-discovery")) {
                    hasNacos = true;
                }

                if (!updated.equals(pomContent)) {
                    Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString());
                }
            } catch (IOException e) {
                warnings.add("Failed to modernize pom.xml: " + e.getMessage());
            }
        }

        // 3. Modernize Configuration files (Purge Eureka and inject Nacos if needed)
        ConfigResult cfgRes = modernizeConfiguration(projectRoot, hasEureka || hasNacos);
        if (cfgRes.modified()) {
            modifiedFiles.addAll(cfgRes.files());
            rulesApplied.addAll(cfgRes.rules());
            changes += cfgRes.changes();
        }

        // 4. Kubernetes and Dockerfile Topology Governance for Nacos 2.x gRPC (Port 9848)
        if (hasEureka || hasNacos) {
            K8sTopologyResult topoRes = governNacosNetworkTopology(projectRoot);
            if (topoRes.modified()) {
                modifiedFiles.addAll(topoRes.files());
                rulesApplied.addAll(topoRes.rules());
                changes += topoRes.changes();
            }
        }

        return new RegistryModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private record ConfigResult(boolean modified, int changes, Set<String> files, List<String> rules) {}

    private static ConfigResult modernizeConfiguration(Path projectRoot, boolean targetNacos) {
        Set<String> files = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        int changes = 0;

        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> configs = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.startsWith("application.") || name.startsWith("application-")) &&
                                (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"));
                    })
                    .toList();

            for (Path config : configs) {
                try {
                    String content = Files.readString(config, StandardCharsets.UTF_8);
                    String updated = content;

                    // Remove obsolete Eureka configs
                    if (updated.contains("eureka:")) {
                        updated = updated.replaceAll("(?m)^\\s*eureka:[\\s\\S]*?(?=^[a-zA-Z0-9_#]|$)", "");
                        rules.add("EUREKA_CONFIGURATION_PURGED");
                        changes++;
                    }
                    if (updated.contains("eureka.")) {
                        updated = updated.replaceAll("(?m)^\\s*eureka\\.[a-zA-Z0-9_\\-.]+=.*$\n?", "");
                        rules.add("EUREKA_CONFIGURATION_PURGED");
                        changes++;
                    }

                    // Inject Nacos config if absent and target is Nacos
                    if (targetNacos && !updated.contains("nacos:")) {
                        if (config.getFileName().toString().endsWith(".yml") || config.getFileName().toString().endsWith(".yaml")) {
                            updated += """

                                    spring:
                                      cloud:
                                        nacos:
                                          discovery:
                                            server-addr: ${NACOS_SERVER_ADDR:127.0.0.1:8848}
                                            ephemeral: true
                                    """;
                            rules.add("NACOS_DISCOVERY_CONFIGURATION_INJECTED");
                            changes++;
                        }
                    }

                    if (!updated.equals(content)) {
                        Files.writeString(config, updated, StandardCharsets.UTF_8);
                        files.add(projectRoot.relativize(config).toString());
                    }
                } catch (IOException ignored) {}
            }
        } catch (IOException ignored) {}

        return new ConfigResult(!files.isEmpty(), changes, files, rules);
    }

    private record K8sTopologyResult(boolean modified, int changes, Set<String> files, List<String> rules) {}

    private static K8sTopologyResult governNacosNetworkTopology(Path projectRoot) {
        Set<String> files = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        int changes = 0;

        // Check k8s directory or root files
        List<String> candidatePaths = List.of(
                "k8s/deployment.yaml",
                "k8s/deployment.yml",
                "deployment.yaml",
                "deployment.yml"
        );

        for (String candidate : candidatePaths) {
            Path path = projectRoot.resolve(candidate);
            if (Files.isRegularFile(path)) {
                try {
                    String content = Files.readString(path, StandardCharsets.UTF_8);
                    if (content.contains("containerPort:") && !content.contains("9848")) {
                        // Inject 9848 port
                        String portSnippet = """
                                - containerPort: 9848
                                  name: nacos-grpc
                                """;
                        String updated = content.replaceFirst("(?m)^(\\s*-\\s*containerPort:\\s*\\d+.*)$", "$1\n            " + portSnippet.trim());
                        if (!updated.equals(content)) {
                            Files.writeString(path, updated, StandardCharsets.UTF_8);
                            files.add(projectRoot.relativize(path).toString());
                            rules.add("NACOS_GRPC_PORT_9848_EXPOSED_IN_K8S");
                            changes++;
                        }
                    }
                } catch (IOException ignored) {}
            }
        }

        // Check Dockerfile
        Path dockerfile = projectRoot.resolve("Dockerfile");
        if (Files.isRegularFile(dockerfile)) {
            try {
                String content = Files.readString(dockerfile, StandardCharsets.UTF_8);
                if (content.contains("EXPOSE") && !content.contains("9848")) {
                    String updated = content.replaceFirst("(?m)^EXPOSE\\s+.*$", "$0 9848");
                    if (!updated.equals(content)) {
                        Files.writeString(dockerfile, updated, StandardCharsets.UTF_8);
                        files.add(projectRoot.relativize(dockerfile).toString());
                        rules.add("NACOS_GRPC_PORT_9848_EXPOSED_IN_DOCKERFILE");
                        changes++;
                    }
                }
            } catch (IOException ignored) {}
        }

        return new K8sTopologyResult(!files.isEmpty(), changes, files, rules);
    }
}
