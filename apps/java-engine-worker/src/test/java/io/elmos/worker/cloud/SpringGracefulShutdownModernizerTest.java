package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringGracefulShutdownModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesConfigAndK8sManifestWithPreStopAndGeneratesLogger() throws Exception {
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

        Path yamlConfig = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(yamlConfig.getParent());
        Files.writeString(yamlConfig, """
                spring:
                  application:
                    name: demo-service
                """);

        Path k8sDeploy = tempDir.resolve("deploy/k8s/deployment.yaml");
        Files.createDirectories(k8sDeploy.getParent());
        Files.writeString(k8sDeploy, """
                apiVersion: apps/v1
                kind: Deployment
                metadata:
                  name: demo-deployment
                spec:
                  template:
                    spec:
                      containers:
                      - name: app
                        image: demo:v1
                """);

        var result = SpringGracefulShutdownModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 3);

        String updatedConfig = Files.readString(yamlConfig);
        assertTrue(updatedConfig.contains("shutdown: graceful"));
        assertTrue(updatedConfig.contains("timeout-per-shutdown-phase: 30s"));
        assertTrue(updatedConfig.contains("probes:"));

        String updatedK8s = Files.readString(k8sDeploy);
        assertTrue(updatedK8s.contains("preStop"));
        assertTrue(updatedK8s.contains("sleep 15"));

        Path generatedLogger = tempDir.resolve("src/main/java/io/elmos/generated/cloud/GracefulShutdownLifecycleLogger.java");
        assertTrue(Files.isRegularFile(generatedLogger));
        String loggerCode = Files.readString(generatedLogger);
        assertTrue(loggerCode.contains("ContextClosedEvent"));
    }

    @Test
    void returnsEmptyWhenNoApplicableTargetFound() throws Exception {
        var result = SpringGracefulShutdownModernizer.modernize(tempDir);
        assertFalse(result.modified());
    }
}
