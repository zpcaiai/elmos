package io.elmos.worker.messaging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringMessagingReliabilityModernizerTest {

    @Test
    void testMessagingReliabilityModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  application:\n    name: payment-events\n");

        // Execute modernization
        SpringMessagingReliabilityModernizer modernizer = new SpringMessagingReliabilityModernizer();
        SpringMessagingReliabilityModernizer.MessagingModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should be modified");
        assertTrue(result.changesCount() >= 3, "Should have applied at least 3 modifications");

        // Verify RabbitMqReliabilityConfiguration generated
        Path generatedAmqp = tempDir.resolve("src/main/java/io/elmos/generated/config/RabbitMqReliabilityConfiguration.java");
        assertTrue(Files.exists(generatedAmqp), "RabbitMqReliabilityConfiguration should be generated");
        String amqpSource = Files.readString(generatedAmqp);
        assertTrue(amqpSource.contains("setTrustedPackages(\"*\")"), "Should trust all packages for JSON deserialization");

        // Verify MessageIdempotentConsumerTemplate generated
        Path generatedIdempotent = tempDir.resolve("src/main/java/io/elmos/generated/messaging/MessageIdempotentConsumerTemplate.java");
        assertTrue(Files.exists(generatedIdempotent), "MessageIdempotentConsumerTemplate should be generated");
        String idempotentSource = Files.readString(generatedIdempotent);
        assertTrue(idempotentSource.contains("opsForValue().setIfAbsent"), "Should use atomic setIfAbsent");
        assertTrue(idempotentSource.contains("redisTemplate.delete(key)"), "Should clean up key on exception to permit retry");

        // Verify application.yml updated
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("default-requeue-rejected: false"), "Should reject requeue to route to DLQ");
        assertTrue(updatedYml.contains("max-attempts: 3"), "Should configure bounded retries");
    }
}
