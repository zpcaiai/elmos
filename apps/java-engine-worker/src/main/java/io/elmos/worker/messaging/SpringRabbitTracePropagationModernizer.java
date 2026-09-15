package io.elmos.worker.messaging;

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
 * Industrial-grade modernizer for RabbitMQ Distributed Tracing, TraceId propagation, and Micrometer Observation.
 *
 * <p>Key enterprise observability challenges in Spring Boot 3 messaging:
 * <ol>
 *   <li><b>Trace Context Severance Across MQ:</b> With Spring Cloud Sleuth removed, RabbitMQ message producers
 *       and consumers lose trace context unless {@code observationEnabled} is explicitly enabled on both
 *       {@code RabbitTemplate} and {@code SimpleRabbitListenerContainerFactory}.</li>
 *   <li><b>W3C Traceparent Header Missing:</b> Distributed tracing standards require {@code traceparent} and MDC
 *       propagation to maintain APM graph continuity in Grafana Tempo, Jaeger, and SkyWalking.</li>
 *   <li><b>Zero-Configuration Generator:</b> Automatically generates {@code RabbitMqObservationConfiguration.java}
 *       and injects observation-enabled flags into YAML configuration.</li>
 * </ol>
 */
public final class SpringRabbitTracePropagationModernizer {

    public record RabbitTraceModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static RabbitTraceModernizationResult empty() {
            return new RabbitTraceModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern RABBIT_DEP_PATTERN = Pattern.compile(
            "<artifactId>(?:spring-boot-starter-amqp|spring-rabbit)</artifactId>"
    );

    private SpringRabbitTracePropagationModernizer() {}

    public static RabbitTraceModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return RabbitTraceModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean rabbitDetected = false;

        // 1. Inspect pom.xml for AMQP / Rabbit dependencies
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                if (RABBIT_DEP_PATTERN.matcher(pomContent).find()) {
                    rabbitDetected = true;
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml for RabbitMQ: " + e.getMessage());
            }
        }

        // 2. Scan Java sources for Rabbit annotations
        Path srcDir = projectRoot.resolve("src");
        if (Files.isDirectory(srcDir)) {
            try (Stream<Path> stream = Files.walk(srcDir)) {
                List<Path> javaFiles = stream.filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".java")).toList();
                for (Path javaFile : javaFiles) {
                    try {
                        String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                        if (content.contains("@RabbitListener") || content.contains("RabbitTemplate")) {
                            rabbitDetected = true;
                            break;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to read Java file " + javaFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan src for RabbitMQ: " + e.getMessage());
            }
        }

        // 3. Scan and modernize application configuration for observation-enabled
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

                        if (content.contains("rabbitmq") || content.contains("spring.rabbitmq")) {
                            rabbitDetected = true;
                        }

                        if (rabbitDetected && !updated.contains("observation-enabled")) {
                            if (updated.contains("spring:")) {
                                if (updated.contains("rabbitmq:")) {
                                    updated = updated.replaceFirst("(?m)^(\\s*rabbitmq:\\s*)$",
                                            "$1\n$1  template:\n$1    observation-enabled: true\n$1  listener:\n$1    simple:\n$1      observation-enabled: true");
                                } else {
                                    updated = updated.replaceFirst("(?m)^(\\s*spring:\\s*)$",
                                            "$1\n$1  rabbitmq:\n$1    template:\n$1      observation-enabled: true\n$1    listener:\n$1      simple:\n$1        observation-enabled: true");
                                }
                            } else {
                                updated = updated + """
                                        \nspring:
                                          rabbitmq:
                                            template:
                                              observation-enabled: true
                                            listener:
                                              simple:
                                                observation-enabled: true
                                        """;
                            }
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                            rulesApplied.add("ENABLE_RABBITMQ_OBSERVATION_METRICS_AND_TRACING");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources for RabbitMQ: " + e.getMessage());
            }
        }

        // 4. Generate RabbitMqObservationConfiguration.java if RabbitMQ is detected
        if (rabbitDetected) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/messaging");
            try {
                Files.createDirectories(targetPackageDir);
                Path configFile = targetPackageDir.resolve("RabbitMqObservationConfiguration.java");
                if (!Files.exists(configFile)) {
                    String configSource = generateRabbitTraceConfigSource();
                    Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                    rulesApplied.add("GENERATE_RABBITMQ_OBSERVATION_CONFIGURATION");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate RabbitMqObservationConfiguration: " + e.getMessage());
            }
        }

        return new RabbitTraceModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateRabbitTraceConfigSource() {
        return """
                package io.elmos.generated.messaging;

                import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
                import org.springframework.amqp.rabbit.connection.ConnectionFactory;
                import org.springframework.amqp.rabbit.core.RabbitTemplate;
                import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                /**
                 * Enterprise RabbitMQ observation configuration for Spring Boot 3 Micrometer Observation.
                 *
                 * <p>Ensures W3C traceparent and Span propagation across asynchronous message queues.</p>
                 */
                @Configuration(proxyBeanMethods = false)
                @ConditionalOnClass({RabbitTemplate.class, ConnectionFactory.class})
                public class RabbitMqObservationConfiguration {

                    @Bean
                    @ConditionalOnMissingBean
                    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
                        RabbitTemplate template = new RabbitTemplate(connectionFactory);
                        template.setObservationEnabled(true);
                        return template;
                    }

                    @Bean
                    @ConditionalOnMissingBean(name = "rabbitListenerContainerFactory")
                    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
                            SimpleRabbitListenerContainerFactoryConfigurer configurer,
                            ConnectionFactory connectionFactory) {
                        SimpleRabbitListenerContainerFactory factory = new SimpleRabbitListenerContainerFactory();
                        configurer.configure(factory, connectionFactory);
                        factory.setObservationEnabled(true);
                        return factory;
                    }
                }
                """;
    }
}
