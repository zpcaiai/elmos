package io.elmos.worker.messaging;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringRabbitTracePropagationModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesRabbitMqTraceObservationInConfigAndGeneratesBean() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.boot</groupId>
                      <artifactId>spring-boot-starter-amqp</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaFile = tempDir.resolve("src/main/java/com/example/OrderEventConsumer.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.springframework.amqp.rabbit.annotation.RabbitListener;
                import org.springframework.stereotype.Component;

                @Component
                public class OrderEventConsumer {

                    @RabbitListener(queues = "order.created")
                    public void onMessage(String payload) {
                    }
                }
                """);

        Path yamlConfig = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(yamlConfig.getParent());
        Files.writeString(yamlConfig, """
                spring:
                  rabbitmq:
                    host: localhost
                    port: 5672
                """);

        var result = SpringRabbitTracePropagationModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        String updatedYaml = Files.readString(yamlConfig);
        assertTrue(updatedYaml.contains("observation-enabled: true"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/messaging/RabbitMqObservationConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
        String configSource = Files.readString(generatedConfig);
        assertTrue(configSource.contains("template.setObservationEnabled(true);"));
        assertTrue(configSource.contains("factory.setObservationEnabled(true);"));
    }

    @Test
    void returnsEmptyWhenNoRabbitMqDetected() throws Exception {
        var result = SpringRabbitTracePropagationModernizer.modernize(tempDir);
        assertFalse(result.modified());
    }
}
