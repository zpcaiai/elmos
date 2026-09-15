package io.elmos.worker.concurrent;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringAsyncContextPropagationModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesAsyncThreadPoolAndGeneratesContextDecorator() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.boot</groupId>
                      <artifactId>spring-boot-starter-web</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaDir = tempDir.resolve("src/main/java/com/example/config");
        Files.createDirectories(javaDir);
        Path configClass = javaDir.resolve("AsyncConfig.java");
        Files.writeString(configClass, """
                package com.example.config;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.scheduling.annotation.EnableAsync;
                import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

                @Configuration
                @EnableAsync
                public class AsyncConfig {

                    @Bean
                    public ThreadPoolTaskExecutor taskExecutor() {
                        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
                        executor.setCorePoolSize(10);
                        executor.initialize();
                        return executor;
                    }
                }
                """);

        Path appYml = tempDir.resolve("application.yml");
        Files.writeString(appYml, "server:\n  port: 8080\n");

        var result = SpringAsyncContextPropagationModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        // Verify task decorator injected
        String updatedConfig = Files.readString(configClass);
        assertTrue(updatedConfig.contains("setTaskDecorator("));

        // Verify AsyncContextPropagationConfiguration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/concurrent/AsyncContextPropagationConfiguration.java");
        assertTrue(Files.exists(generatedConfig));
        String generatedContent = Files.readString(generatedConfig);
        assertTrue(generatedContent.contains("SecurityContextHolder.setContext"));
        assertTrue(generatedContent.contains("MDC.setContextMap"));

        // Verify pom.xml has context-propagation
        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("context-propagation"));

        // Verify application.yml has virtual threads
        String updatedYml = Files.readString(appYml);
        assertTrue(updatedYml.contains("virtual:"));
    }

    @Test
    void eliminatesSynchronizedMethodOnServiceToPreventPinning() throws Exception {
        Path javaDir = tempDir.resolve("src/main/java/com/example/service");
        Files.createDirectories(javaDir);
        Path serviceClass = javaDir.resolve("OrderService.java");
        Files.writeString(serviceClass, """
                package com.example.service;

                public class OrderService {

                    public synchronized String executeOrder(String orderId) {
                        return "order_processed_" + orderId;
                    }
                }
                """);

        var result = SpringAsyncContextPropagationModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedService = Files.readString(serviceClass);
        assertFalse(updatedService.contains("public synchronized String executeOrder"));
        assertTrue(updatedService.contains("public String executeOrder"));
    }
}
