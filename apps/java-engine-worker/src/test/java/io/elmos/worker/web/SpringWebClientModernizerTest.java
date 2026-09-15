package io.elmos.worker.web;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringWebClientModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesAsyncRestTemplateToWebClientInJavaAndPom() throws Exception {
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

        Path javaFile = tempDir.resolve("src/main/java/com/example/ExternalHttpClientConfig.java");
        Files.createDirectories(javaFile.getParent());
        Files.writeString(javaFile, """
                package com.example;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.web.client.AsyncRestTemplate;

                @Configuration
                public class ExternalHttpClientConfig {

                    @Bean
                    public AsyncRestTemplate asyncRestTemplate() {
                        return new AsyncRestTemplate();
                    }

                    public void call(AsyncRestTemplate client) {
                    }
                }
                """);

        var result = SpringWebClientModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("spring-boot-starter-webflux"));

        String updatedJava = Files.readString(javaFile);
        assertFalse(updatedJava.contains("AsyncRestTemplate"));
        assertTrue(updatedJava.contains("WebClient"));
        assertTrue(updatedJava.contains("org.springframework.web.reactive.function.client.WebClient"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/webclient/WebClientConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
        String configCode = Files.readString(generatedConfig);
        assertTrue(configCode.contains("ConnectionProvider"));
        assertTrue(configCode.contains("maxConnections(500)"));
    }
}
