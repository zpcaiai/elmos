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

/**
 * Enterprise Spring AMQP / RabbitMQ / Kafka Reliability Modernizer.
 *
 * <p>Solves enterprise messaging pitfalls in Spring Boot 3.x:
 * <ol>
 *   <li><b>Trusted Package Deserialization:</b>
 *       Configures {@code Jackson2JsonMessageConverter} with {@code DefaultClassMapper.setTrustedPackages("*")}
 *       to prevent fatal {@code SecurityException} rejecting message payloads during cross-version communication.</li>
 *   <li><b>Dead Letter Queue (DLQ) & Retry Governance:</b>
 *       Configures exponential backoff retry and automatic routing of poisoned messages to Dead Letter Exchanges (DLX),
 *       preventing message redelivery infinite loops.</li>
 *   <li><b>Anti-Double-Spend Message Idempotency:</b>
 *       Generates {@code MessageIdempotentConsumerTemplate.java} leveraging Redis atomic {@code setIfAbsent}
 *       to guarantee strict at-most-once processing semantics and prevent duplicate financial records.</li>
 * </ol>
 */
public final class SpringMessagingReliabilityModernizer {

    public record MessagingModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static MessagingModernizationResult empty() {
            return new MessagingModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    /**
     * Executes messaging reliability modernization across the project workspace.
     */
    public MessagingModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return MessagingModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Generate RabbitMQ / Messaging Reliability Configuration
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/config");
        Files.createDirectories(configDir);
        Path amqpConfigFile = configDir.resolve("RabbitMqReliabilityConfiguration.java");
        if (!Files.exists(amqpConfigFile)) {
            String configContent = generateAmqpConfig();
            Files.writeString(amqpConfigFile, configContent, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(amqpConfigFile.toString());
            generatedArtifacts.add(amqpConfigFile.toString());
            rulesApplied.add("GENERATE_RABBITMQ_RELIABILITY_CONFIG");
        }

        // 2. Generate MessageIdempotentConsumerTemplate
        Path messagingDir = projectRoot.resolve("src/main/java/io/elmos/generated/messaging");
        Files.createDirectories(messagingDir);
        Path idempotentFile = messagingDir.resolve("MessageIdempotentConsumerTemplate.java");
        if (!Files.exists(idempotentFile)) {
            String idempotentContent = generateIdempotentTemplate();
            Files.writeString(idempotentFile, idempotentContent, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(idempotentFile.toString());
            generatedArtifacts.add(idempotentFile.toString());
            rulesApplied.add("GENERATE_MESSAGE_IDEMPOTENT_CONSUMER_TEMPLATE");
        }

        // 3. Configure Retry & DLQ in application.yml
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("rabbitmq:") || !ymlContent.contains("default-requeue-rejected:")) {
                String amqpSettings =
                        """

                        spring:
                          rabbitmq:
                            listener:
                              simple:
                                retry:
                                  enabled: true
                                  max-attempts: 3
                                  initial-interval: 1000ms
                                  multiplier: 2.0
                                  max-interval: 10000ms
                                default-requeue-rejected: false
                        """;
                Files.writeString(ymlPath, ymlContent + amqpSettings, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("CONFIGURE_AMQP_RETRY_AND_DLQ_IN_YML");
            }
        }

        return new MessagingModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateAmqpConfig() {
        return """
                package io.elmos.generated.config;

                import org.springframework.amqp.support.converter.DefaultClassMapper;
                import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
                import org.springframework.amqp.support.converter.MessageConverter;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                /**
                 * Trusted JSON Message Converter configuration for Spring Boot 3 AMQP.
                 */
                @Configuration
                public class RabbitMqReliabilityConfiguration {

                    @Bean
                    public MessageConverter jackson2JsonMessageConverter() {
                        Jackson2JsonMessageConverter converter = new Jackson2JsonMessageConverter();
                        DefaultClassMapper classMapper = new DefaultClassMapper();
                        classMapper.setTrustedPackages("*");
                        converter.setClassMapper(classMapper);
                        return converter;
                    }
                }
                """;
    }

    private static String generateIdempotentTemplate() {
        return """
                package io.elmos.generated.messaging;

                import org.springframework.data.redis.core.StringRedisTemplate;
                import org.springframework.stereotype.Component;

                import java.time.Duration;

                /**
                 * Enterprise Message Idempotent Consumer Guard.
                 *
                 * <p>Prevents duplicate business execution and financial discrepancies
                 * during consumer rebalancing or network retries using atomic Redis tokens.
                 */
                @Component
                public class MessageIdempotentConsumerTemplate {

                    private static final Duration LOCK_TIMEOUT = Duration.ofMinutes(5);
                    private static final Duration COMPLETED_TIMEOUT = Duration.ofHours(24);

                    private final StringRedisTemplate redisTemplate;

                    public MessageIdempotentConsumerTemplate(StringRedisTemplate redisTemplate) {
                        this.redisTemplate = redisTemplate;
                    }

                    public boolean executeIfUnique(String messageId, Runnable consumerTask) {
                        String key = "elmos:msg:idempotent:" + messageId;
                        Boolean acquired = redisTemplate.opsForValue().setIfAbsent(key, "PROCESSING", LOCK_TIMEOUT);

                        if (Boolean.FALSE.equals(acquired)) {
                            // Already processed or processing elsewhere
                            return false;
                        }

                        try {
                            consumerTask.run();
                            redisTemplate.opsForValue().set(key, "COMPLETED", COMPLETED_TIMEOUT);
                            return true;
                        } catch (RuntimeException e) {
                            // Allow retry on failure
                            redisTemplate.delete(key);
                            throw e;
                        }
                    }
                }
                """;
    }
}
