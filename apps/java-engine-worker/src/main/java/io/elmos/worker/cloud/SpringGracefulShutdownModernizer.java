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
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for Spring Boot 3 Graceful Shutdown and Kubernetes Zero-Downtime lifecycle alignment.
 *
 * <p>Key production challenges in cloud-native rollouts:
 * <ol>
 *   <li><b>In-Flight Request Drop (502 / 504 Bad Gateway):</b> By default, Spring Boot server shutdown is {@code immediate},
 *       abruptly aborting ongoing HTTP requests and socket connections during deployment scaling or pod eviction.</li>
 *   <li><b>K8s Service Ingress Propagation Lag:</b> When a Pod enters terminating state, kube-proxy and Ingress controllers
 *       take 5-15 seconds to remove the Pod IP from routing endpoints. If the container stops listening immediately upon SIGTERM,
 *       in-flight and new ingress traffic is dropped. A container {@code preStop} hook with {@code sleep 15} is mandatory.</li>
 *   <li><b>Liveness & Readiness Actuator Probes:</b> Spring Boot provides dedicated {@code /actuator/health/liveness} and
 *       {@code /actuator/health/readiness} endpoints designed specifically for Kubernetes probe contracts.</li>
 * </ol>
 */
public final class SpringGracefulShutdownModernizer {

    public record GracefulShutdownModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static GracefulShutdownModernizationResult empty() {
            return new GracefulShutdownModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern WEB_DEP_PATTERN = Pattern.compile(
            "<artifactId>(?:spring-boot-starter-web|spring-boot-starter-webflux)</artifactId>"
    );

    private SpringGracefulShutdownModernizer() {}

    public static GracefulShutdownModernizationResult modernize(Path projectRoot) {
        return modernize(projectRoot, true);
    }

    public static GracefulShutdownModernizationResult modernize(Path projectRoot, boolean updatePom) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return GracefulShutdownModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean webDetected = false;

        // 1. Inspect pom.xml for web dependency
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                if (WEB_DEP_PATTERN.matcher(pomContent).find()) {
                    webDetected = true;
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml: " + e.getMessage());
            }
        }

        // 2. Scan and modernize application configuration (server.shutdown & timeout-per-shutdown-phase)
        Path srcDir = projectRoot.resolve("src");
        Path resourcesDir = srcDir.resolve("main/resources");
        if (Files.isDirectory(resourcesDir)) {
            try (Stream<Path> stream = Files.walk(resourcesDir)) {
                List<Path> configFiles = stream.filter(p -> Files.isRegularFile(p) &&
                        (p.toString().endsWith(".yml") || p.toString().endsWith(".yaml") || p.toString().endsWith(".properties"))
                ).toList();

                for (Path configFile : configFiles) {
                    try {
                        String content = Files.readString(configFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (configFile.toString().endsWith(".properties")) {
                            StringBuilder props = new StringBuilder(updated);
                            if (!updated.contains("server.shutdown")) {
                                props.append("\nserver.shutdown=graceful");
                            }
                            if (!updated.contains("spring.lifecycle.timeout-per-shutdown-phase")) {
                                props.append("\nspring.lifecycle.timeout-per-shutdown-phase=30s");
                            }
                            if (!updated.contains("management.endpoint.health.probes.enabled")) {
                                props.append("\nmanagement.endpoint.health.probes.enabled=true");
                            }
                            updated = props.toString();
                        } else {
                            // YAML configuration
                            if (!updated.contains("server.shutdown") && !updated.contains("shutdown: graceful")) {
                                if (updated.contains("server:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*server:\\s*)$",
                                            "$1\n$1  shutdown: graceful");
                                } else {
                                    updated = updated + "\nserver:\n  shutdown: graceful\n";
                                }
                            }

                            if (!updated.contains("timeout-per-shutdown-phase")) {
                                if (updated.contains("lifecycle:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*lifecycle:\\s*)$",
                                            "$1\n$1  timeout-per-shutdown-phase: 30s");
                                } else if (updated.contains("spring:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*spring:\\s*)$",
                                            "$1\n$1  lifecycle:\n$1    timeout-per-shutdown-phase: 30s");
                                } else {
                                    updated = updated + "\nspring:\n  lifecycle:\n    timeout-per-shutdown-phase: 30s\n";
                                }
                            }

                            if (!updated.contains("probes:")) {
                                if (updated.contains("management:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*management:\\s*)$",
                                            "$1\n$1  endpoint:\n$1    health:\n$1      probes:\n$1        enabled: true");
                                } else {
                                    updated = updated + "\nmanagement:\n  endpoint:\n    health:\n      probes:\n        enabled: true\n";
                                }
                            }
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                            rulesApplied.add("ENABLE_GRACEFUL_SHUTDOWN_AND_HEALTH_PROBES");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources: " + e.getMessage());
            }
        }

        // 3. Scan and modernize Kubernetes deployment manifests (deploy/, k8s/, etc.)
        List<Path> candidateK8sDirs = List.of(
                projectRoot.resolve("deploy"),
                projectRoot.resolve("k8s"),
                projectRoot.resolve("deployments"),
                projectRoot.resolve("helm")
        );

        for (Path k8sDir : candidateK8sDirs) {
            if (Files.isDirectory(k8sDir)) {
                try (Stream<Path> stream = Files.walk(k8sDir)) {
                    List<Path> yamlFiles = stream.filter(p -> Files.isRegularFile(p) &&
                            (p.toString().endsWith(".yml") || p.toString().endsWith(".yaml"))
                    ).toList();

                    for (Path yamlFile : yamlFiles) {
                        try {
                            String content = Files.readString(yamlFile, StandardCharsets.UTF_8);
                            if (content.contains("kind: Deployment") || content.contains("containers:")) {
                                String updated = content;

                                // Inject preStop hook if missing
                                if (!updated.contains("preStop")) {
                                    if (updated.contains("image:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*image:.*)$",
                                                "$1\n$1  lifecycle:\n$1    preStop:\n$1      exec:\n$1        command: [\"/bin/sh\", \"-c\", \"sleep 15\"]".replace("image:.*", "image:"));
                                        // Cleaner replacement: after image line
                                        int imageIdx = content.indexOf("image:");
                                        if (imageIdx != -1) {
                                            int lineEnd = content.indexOf('\n', imageIdx);
                                            String indent = "          ";
                                            String preStopBlock = "\n" + indent + "lifecycle:\n"
                                                    + indent + "  preStop:\n"
                                                    + indent + "    exec:\n"
                                                    + indent + "      command: [\"/bin/sh\", \"-c\", \"sleep 15\"]";
                                            updated = content.substring(0, lineEnd) + preStopBlock + content.substring(lineEnd);
                                        }
                                    }
                                }

                                if (!updated.equals(content)) {
                                    Files.writeString(yamlFile, updated, StandardCharsets.UTF_8);
                                    modifiedFiles.add(projectRoot.relativize(yamlFile).toString().replace('\\', '/'));
                                    rulesApplied.add("INJECT_K8S_PRESTOP_SLEEP_HOOK");
                                    changes++;
                                }
                            }
                        } catch (IOException e) {
                            warnings.add("Failed to process K8s file " + yamlFile + ": " + e.getMessage());
                        }
                    }
                } catch (IOException e) {
                    warnings.add("Failed to scan K8s dir " + k8sDir + ": " + e.getMessage());
                }
            }
        }

        // 4. Generate GracefulShutdownLifecycleLogger.java
        if (webDetected || !modifiedFiles.isEmpty()) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/cloud");
            try {
                Files.createDirectories(targetPackageDir);
                Path configFile = targetPackageDir.resolve("GracefulShutdownLifecycleLogger.java");
                if (!Files.exists(configFile)) {
                    String configSource = generateShutdownLoggerSource();
                    Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                    rulesApplied.add("GENERATE_GRACEFUL_SHUTDOWN_LOGGER");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate GracefulShutdownLifecycleLogger: " + e.getMessage());
            }
        }

        return new GracefulShutdownModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateShutdownLoggerSource() {
        return """
                package io.elmos.generated.cloud;

                import org.slf4j.Logger;
                import org.slf4j.LoggerFactory;
                import org.springframework.context.ApplicationListener;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.context.event.ContextClosedEvent;

                /**
                 * Enterprise SRE audit logger for Spring Boot Graceful Shutdown lifecycle events.
                 *
                 * <p>Logs application context termination timing and ensures clean drain observability.</p>
                 */
                @Configuration(proxyBeanMethods = false)
                public class GracefulShutdownLifecycleLogger implements ApplicationListener<ContextClosedEvent> {

                    private static final Logger log = LoggerFactory.getLogger(GracefulShutdownLifecycleLogger.class);

                    @Override
                    public void onApplicationEvent(ContextClosedEvent event) {
                        log.info("Spring ApplicationContext shutdown initiated. Active threads and web connections draining gracefully...");
                    }
                }
                """;
    }
}
