package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringConfigImportModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void testBootstrapYamlToSpringConfigImport() throws IOException {
        Path resources = Files.createDirectories(tempDir.resolve("src/main/resources"));
        Path bootstrapYaml = resources.resolve("bootstrap.yml");
        Files.writeString(bootstrapYaml, """
                spring:
                  application:
                    name: order-service
                  cloud:
                    config:
                      uri: http://config-server.internal:8888
                      fail-fast: true
                """);

        var result = SpringConfigImportModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("CONFIG_IMPORT_CONFIG_SERVER"));
        assertFalse(Files.exists(bootstrapYaml), "bootstrap.yml must be removed");

        Path appYaml = resources.resolve("application.yml");
        assertTrue(Files.exists(appYaml), "application.yml must be created");
        String content = Files.readString(appYaml);
        assertTrue(content.contains("order-service"));
        assertTrue(content.contains("optional:configserver:http://config-server.internal:8888"));
    }

    @Test
    void testNacosBootstrapPropertiesToConfigImport() throws IOException {
        Path resources = Files.createDirectories(tempDir.resolve("src/main/resources"));
        Path bootstrapProps = resources.resolve("bootstrap.properties");
        Files.writeString(bootstrapProps, """
                spring.application.name=payment-service
                spring.cloud.nacos.config.server-addr=10.0.0.1:8848
                spring.cloud.nacos.config.file-extension=yaml
                spring.cloud.nacos.config.group=PROD_GROUP
                """);

        var result = SpringConfigImportModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("CONFIG_IMPORT_NACOS"));
        assertFalse(Files.exists(bootstrapProps));

        Path appProps = resources.resolve("application.properties");
        assertTrue(Files.exists(appProps));
        String content = Files.readString(appProps);
        assertTrue(content.contains("spring.config.import=optional:nacos:${spring.application.name}.yaml?group=PROD_GROUP&refreshEnabled=true"));
    }

    @Test
    void testPomRemovesStarterBootstrap() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.cloud</groupId>
                            <artifactId>spring-cloud-starter-bootstrap</artifactId>
                        </dependency>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-web</artifactId>
                        </dependency>
                    </dependencies>
                </project>
                """);

        var result = SpringConfigImportModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("POM_REMOVE_STARTER_BOOTSTRAP"));
        String updatedPom = Files.readString(pom);
        assertFalse(updatedPom.contains("spring-cloud-starter-bootstrap"));
        assertTrue(updatedPom.contains("spring-boot-starter-web"));
    }

    @Test
    void testJavaRemoveRefreshScopeOnConfigProperties() throws IOException {
        Path javaDir = Files.createDirectories(tempDir.resolve("src/main/java/com/example"));
        Path javaFile = javaDir.resolve("OrderProperties.java");
        Files.writeString(javaFile, """
                package com.example;
                
                import org.springframework.boot.context.properties.ConfigurationProperties;
                import org.springframework.cloud.context.config.annotation.RefreshScope;
                import org.springframework.stereotype.Component;
                
                @Component
                @RefreshScope
                @ConfigurationProperties(prefix = "order")
                public class OrderProperties {
                    private int timeout;
                }
                """);

        var result = SpringConfigImportModernizer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("JAVA_REMOVE_REFRESH_SCOPE_ON_CONFIG_PROPS"));
        String content = Files.readString(javaFile);
        assertFalse(content.contains("@RefreshScope"));
        assertTrue(content.contains("@ConfigurationProperties"));
    }
}
