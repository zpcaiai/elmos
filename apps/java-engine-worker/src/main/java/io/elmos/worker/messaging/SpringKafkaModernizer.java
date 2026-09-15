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
 * Industrial-grade modernizer for Spring Kafka 3.x in Spring Boot 3.
 *
 * <p>Key enterprise messaging challenges in Spring Boot 3 Kafka:
 * <ol>
 *   <li><b>Deprecated ErrorHandler Elimination:</b> {@code SeekToCurrentErrorHandler} and old {@code ErrorHandler}
 *       hierarchy are completely removed in Spring Kafka 3.x. Must be modernized to {@code DefaultErrorHandler}.</li>
 *   <li><b>Dead Letter Topic (DLT) & Exponential Backoff:</b> Unhandled consumer exceptions cause partition head-of-line
 *       blocking unless backed by a non-blocking retry mechanism or dead-letter topic ({@code DeadLetterPublishingRecoverer}).</li>
 *   <li><b>Consumer AckMode & Concurrency:</b> Spring Boot 3 defaults require explicit container factory configuration
 *       to prevent message loss on ungraceful worker termination.</li>
 * </ol>
 */
public final class SpringKafkaModernizer {

    public record KafkaModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static KafkaModernizationResult empty() {
            return new KafkaModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern KAFKA_DEP_PATTERN = Pattern.compile(
            "<artifactId>(?:spring-kafka|spring-boot-starter-kafka)</artifactId>"
    );

    private static final Pattern SEEK_TO_CURRENT_ERROR_HANDLER_PATTERN = Pattern.compile(
            "SeekToCurrentErrorHandler"
    );

    private static final Pattern OLD_ERROR_HANDLER_IMPORT_PATTERN = Pattern.compile(
            "import\\s+org\\.springframework\\.kafka\\.listener\\.SeekToCurrentErrorHandler;"
    );

    private SpringKafkaModernizer() {}

    public static KafkaModernizationResult modernize(Path projectRoot) {
        return modernize(projectRoot, true);
    }

    public static KafkaModernizationResult modernize(Path projectRoot, boolean updatePom) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return KafkaModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;
        boolean kafkaDetected = false;

        // 1. Inspect pom.xml for Kafka
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pomContent = Files.readString(pomFile, StandardCharsets.UTF_8);
                if (KAFKA_DEP_PATTERN.matcher(pomContent).find() || pomContent.contains("spring-kafka")) {
                    kafkaDetected = true;
                }
            } catch (IOException e) {
                warnings.add("Failed to inspect pom.xml for Kafka: " + e.getMessage());
            }
        }

        // 2. Scan Java source files for Kafka annotations and obsolete ErrorHandler
        Path srcDir = projectRoot.resolve("src");
        if (Files.isDirectory(srcDir)) {
            try (Stream<Path> stream = Files.walk(srcDir)) {
                List<Path> javaFiles = stream.filter(p -> Files.isRegularFile(p) && p.toString().endsWith(".java")).toList();
                for (Path javaFile : javaFiles) {
                    try {
                        String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                        String updated = content;

                        if (content.contains("@KafkaListener") || content.contains("KafkaTemplate") || content.contains("ConsumerRecord")) {
                            kafkaDetected = true;
                        }

                        if (SEEK_TO_CURRENT_ERROR_HANDLER_PATTERN.matcher(updated).find()) {
                            kafkaDetected = true;
                            updated = OLD_ERROR_HANDLER_IMPORT_PATTERN.matcher(updated)
                                    .replaceAll("import org.springframework.kafka.listener.DefaultErrorHandler;\nimport org.springframework.util.backoff.FixedBackOff;");
                            updated = updated.replaceAll("new\\s+SeekToCurrentErrorHandler\\(\\)",
                                    "new DefaultErrorHandler(new FixedBackOff(1000L, 3L))");
                            updated = updated.replaceAll("SeekToCurrentErrorHandler", "DefaultErrorHandler");
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(javaFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(javaFile).toString().replace('\\', '/'));
                            rulesApplied.add("MIGRATE_SEEK_TO_CURRENT_TO_DEFAULT_ERROR_HANDLER");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process Java file " + javaFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan src for Kafka: " + e.getMessage());
            }
        }

        // 3. Scan resources for application configuration
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

                        if (content.contains("kafka:") || content.contains("spring.kafka")) {
                            kafkaDetected = true;
                        }

                        if (kafkaDetected) {
                            if (configFile.toString().endsWith(".properties")) {
                                StringBuilder props = new StringBuilder(updated);
                                if (!updated.contains("spring.kafka.listener.ack-mode")) {
                                    props.append("\nspring.kafka.listener.ack-mode=RECORD");
                                }
                                if (!updated.contains("spring.kafka.consumer.auto-offset-reset")) {
                                    props.append("\nspring.kafka.consumer.auto-offset-reset=earliest");
                                }
                                updated = props.toString();
                            } else {
                                // YAML
                                if (!updated.contains("ack-mode")) {
                                    if (updated.contains("listener:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*listener:\\s*)$",
                                                "$1\n$1  ack-mode: RECORD");
                                    } else if (updated.contains("kafka:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*kafka:\\s*)$",
                                                "$1\n$1  listener:\n$1    ack-mode: RECORD");
                                    } else if (updated.contains("spring:")) {
                                        updated = updated.replaceFirst("(?m)^(\\s*spring:\\s*)$",
                                                "$1\n$1  kafka:\n$1    listener:\n$1      ack-mode: RECORD");
                                    } else {
                                        updated = updated + """
                                                \nspring:
                                                  kafka:
                                                    listener:
                                                      ack-mode: RECORD
                                                    consumer:
                                                      auto-offset-reset: earliest
                                                """;
                                    }
                                }
                            }
                        }

                        if (!updated.equals(content)) {
                            Files.writeString(configFile, updated, StandardCharsets.UTF_8);
                            modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                            rulesApplied.add("NORMALIZE_KAFKA_CONSUMER_ACK_MODE_CONFIGURATION");
                            changes++;
                        }
                    } catch (IOException e) {
                        warnings.add("Failed to process config file " + configFile + ": " + e.getMessage());
                    }
                }
            } catch (IOException e) {
                warnings.add("Failed to scan resources for Kafka: " + e.getMessage());
            }
        }

        // 4. Generate KafkaConsumerReliabilityConfiguration.java
        if (kafkaDetected) {
            Path targetPackageDir = srcDir.resolve("main/java/io/elmos/generated/messaging");
            try {
                Files.createDirectories(targetPackageDir);
                Path configFile = targetPackageDir.resolve("KafkaConsumerReliabilityConfiguration.java");
                if (!Files.exists(configFile)) {
                    String configSource = generateKafkaReliabilityConfigSource();
                    Files.writeString(configFile, configSource, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(configFile).toString().replace('\\', '/'));
                    rulesApplied.add("GENERATE_KAFKA_RELIABILITY_CONFIGURATION");
                    changes++;
                }
            } catch (IOException e) {
                warnings.add("Failed to generate KafkaConsumerReliabilityConfiguration: " + e.getMessage());
            }
        }

        return new KafkaModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static String generateKafkaReliabilityConfigSource() {
        return """
                package io.elmos.generated.messaging;

                import org.apache.kafka.common.TopicPartition;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
                import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.kafka.core.KafkaOperations;
                import org.springframework.kafka.listener.CommonErrorHandler;
                import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
                import org.springframework.kafka.listener.DefaultErrorHandler;
                import org.springframework.util.backoff.ExponentialBackOff;

                /**
                 * Enterprise Spring Kafka 3.x consumer error handling and dead letter queue configuration.
                 *
                 * <p>Prevents partition head-of-line blocking by routing poisoned records to dead letter topic (topic.DLT)
                 * after 3 exponential retries.</p>
                 */
                @Configuration(proxyBeanMethods = false)
                @ConditionalOnClass(KafkaOperations.class)
                public class KafkaConsumerReliabilityConfiguration {

                    @Bean
                    @ConditionalOnMissingBean(CommonErrorHandler.class)
                    public DefaultErrorHandler kafkaDefaultErrorHandler(KafkaOperations<Object, Object> kafkaOperations) {
                        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(kafkaOperations,
                                (record, ex) -> new TopicPartition(record.topic() + ".DLT", record.partition()));

                        ExponentialBackOff backOff = new ExponentialBackOff(1000L, 2.0);
                        backOff.setMaxElapsedTime(10000L);

                        DefaultErrorHandler errorHandler = new DefaultErrorHandler(recoverer, backOff);
                        errorHandler.addNotRetryableExceptions(IllegalArgumentException.class);
                        return errorHandler;
                    }
                }
                """;
    }
}
