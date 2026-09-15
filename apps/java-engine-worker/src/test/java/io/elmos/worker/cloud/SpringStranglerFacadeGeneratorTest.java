package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringStranglerFacadeGeneratorTest {

    @TempDir
    Path tempDir;

    @Test
    void testStranglerFacadeGeneration() throws Exception {
        var artifacts = SpringStranglerFacadeGenerator.generate(
                tempDir,
                "http://legacy-app:8080",
                "http://modern-service:8081",
                List.of("/api/v2/orders", "/api/v2/payments")
        );

        assertTrue(artifacts.generatedFiles().contains("application-strangler.yml"));
        assertTrue(artifacts.generatedFiles().contains("StranglerFacadeGatewayConfiguration.java"));
        assertTrue(artifacts.generatedFiles().contains("strangler_proxy.conf"));

        // Check YAML
        String yamlContent = Files.readString(tempDir.resolve("application-strangler.yml"));
        assertTrue(yamlContent.contains("Path=/api/v2/orders/**"));
        assertTrue(yamlContent.contains("Path=/api/v2/payments/**"));
        assertTrue(yamlContent.contains("uri: http://modern-service:8081"));
        assertTrue(yamlContent.contains("Path=/**"));
        assertTrue(yamlContent.contains("uri: http://legacy-app:8080"));

        // Check Java DSL
        String javaContent = Files.readString(tempDir.resolve("StranglerFacadeGatewayConfiguration.java"));
        assertTrue(javaContent.contains("r.path(\"/api/v2/orders/**\")"));
        assertTrue(javaContent.contains("r.path(\"/**\")"));

        // Check Nginx conf
        String nginxContent = Files.readString(tempDir.resolve("strangler_proxy.conf"));
        assertTrue(nginxContent.contains("upstream legacy_backend"));
        assertTrue(nginxContent.contains("upstream modern_backend"));
        assertTrue(nginxContent.contains("location /api/v2/orders"));
        assertTrue(nginxContent.contains("proxy_pass http://modern_backend;"));
        assertTrue(nginxContent.contains("location /"));
        assertTrue(nginxContent.contains("proxy_pass http://legacy_backend;"));
    }
}
