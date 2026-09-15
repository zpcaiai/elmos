package io.elmos.worker.messaging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringKafkaModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesSeekToCurrentErrorHandlerAndConfigAndGeneratesConfig() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.kafka</groupId>
                      <artifactId>spring-kafka</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaFile = tempDir.resolve("src/main/java/com/example/KafkaConsumerConfig.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.kafka.listener.SeekToCurrentErrorHandler;

                @Configuration
                public class KafkaConsumerConfig {

                    @Bean
                    public SeekToCurrentErrorHandler errorHandler() {
                        return new SeekToCurrentErrorHandler();
                    }
                }
                """);

        Path yamlConfig = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(yamlConfig.getParent());
        Files.writeString(yamlConfig, """
                spring:
                  kafka:
                    bootstrap-servers: localhost:9092
                """);

        var result = SpringKafkaModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        String updatedJava = Files.readString(javaFile);
        assertFalse(updatedJava.contains("SeekToCurrentErrorHandler"));
        assertTrue(updatedJava.contains("DefaultErrorHandler"));

        String updatedYaml = Files.readString(yamlConfig);
        assertTrue(updatedYaml.contains("ack-mode: RECORD"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/messaging/KafkaConsumerReliabilityConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
        String configSource = Files.readString(generatedConfig);
        assertTrue(configSource.contains("DeadLetterPublishingRecoverer"));
        assertTrue(configSource.contains("DefaultErrorHandler"));
    }

    @Test
    void returnsEmptyWhenNoKafkaDetected() throws Exception {
        var result = SpringKafkaModernizer.modernize(tempDir);
        assertFalse(result.modified());
    }
}
