package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringRegistryServiceDiscoveryModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesEurekaToNacosAndConfiguresGrpcTopology() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.cloud</groupId>
                      <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
                      <version>2.2.9.RELEASE</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path javaDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(javaDir);
        Path mainApp = javaDir.resolve("ServiceApp.java");
        Files.writeString(mainApp, """
                package com.example;

                import org.springframework.cloud.netflix.eureka.EnableEurekaClient;
                import org.springframework.boot.autoconfigure.SpringBootApplication;

                @SpringBootApplication
                @EnableEurekaClient
                public class ServiceApp {
                }
                """);

        Path appYml = tempDir.resolve("application.yml");
        Files.writeString(appYml, """
                server:
                  port: 8080
                eureka:
                  client:
                    serviceUrl:
                      defaultZone: http://localhost:8761/eureka/
                """);

        Path k8sDir = tempDir.resolve("k8s");
        Files.createDirectories(k8sDir);
        Path deploymentYaml = k8sDir.resolve("deployment.yaml");
        Files.writeString(deploymentYaml, """
                apiVersion: apps/v1
                kind: Deployment
                spec:
                  template:
                    spec:
                      containers:
                      - name: app
                        image: myapp:latest
                        ports:
                        - containerPort: 8080
                """);

        var result = SpringRegistryServiceDiscoveryModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 4);

        // 1. Verify POM has Nacos and no Eureka
        String updatedPom = Files.readString(pomFile);
        assertFalse(updatedPom.contains("eureka"));
        assertTrue(updatedPom.contains("spring-cloud-starter-alibaba-nacos-discovery"));

        // 2. Verify Java @EnableEurekaClient removed
        String updatedJava = Files.readString(mainApp);
        assertFalse(updatedJava.contains("@EnableEurekaClient"));
        assertFalse(updatedJava.contains("import org.springframework.cloud.netflix.eureka.EnableEurekaClient;"));

        // 3. Verify YAML purged Eureka and injected Nacos
        String updatedYml = Files.readString(appYml);
        assertFalse(updatedYml.contains("eureka:"));
        assertTrue(updatedYml.contains("nacos:"));
        assertTrue(updatedYml.contains("server-addr:"));

        // 4. Verify K8s deployment has 9848 nacos-grpc port
        String updatedK8s = Files.readString(deploymentYaml);
        assertTrue(updatedK8s.contains("9848"));
        assertTrue(updatedK8s.contains("nacos-grpc"));
    }
}
