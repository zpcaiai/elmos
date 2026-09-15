package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringNativeAndContainerModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesGracefulShutdownAndActuatorProbesYaml() throws Exception {
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path appYml = resDir.resolve("application.yml");
        Files.writeString(appYml, """
                spring:
                  application:
                    name: order-service
                """);

        var result = SpringNativeAndContainerModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        String updated = Files.readString(appYml);
        assertTrue(updated.contains("shutdown: graceful"));
        assertTrue(updated.contains("timeout-per-shutdown-phase: 30s"));
        assertTrue(updated.contains("livenessstate"));
        assertTrue(updated.contains("readinessstate"));
        assertTrue(updated.contains("exposure:"));
    }

    @Test
    void modernizesGracefulShutdownAndActuatorProbesProperties() throws Exception {
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path appProps = resDir.resolve("application.properties");
        Files.writeString(appProps, "spring.application.name=payment-service\n");

        var result = SpringNativeAndContainerModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updated = Files.readString(appProps);
        assertTrue(updated.contains("server.shutdown=graceful"));
        assertTrue(updated.contains("spring.lifecycle.timeout-per-shutdown-phase=30s"));
        assertTrue(updated.contains("management.health.livenessstate.enabled=true"));
        assertTrue(updated.contains("management.health.readinessstate.enabled=true"));
    }

    @Test
    void modernizesBuildFilesForActuatorAndNativePlugin() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.boot</groupId>
                      <artifactId>spring-boot-starter-web</artifactId>
                    </dependency>
                  </dependencies>
                  <build>
                    <plugins>
                      <plugin>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-maven-plugin</artifactId>
                      </plugin>
                    </plugins>
                  </build>
                </project>
                """);

        var result = SpringNativeAndContainerModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("spring-boot-starter-actuator"));
        assertTrue(updatedPom.contains("native-maven-plugin"));
    }

    @Test
    void deducesDynamicReflectionAndGeneratesAotHints() throws Exception {
        Path srcDir = tempDir.resolve("src/main/java/com/example/demo");
        Files.createDirectories(srcDir);

        Path mainApp = srcDir.resolve("DemoApplication.java");
        Files.writeString(mainApp, """
                package com.example.demo;

                import org.springframework.boot.autoconfigure.SpringBootApplication;

                @SpringBootApplication
                public class DemoApplication {
                }
                """);

        Path pluginService = srcDir.resolve("PluginService.java");
        Files.writeString(pluginService, """
                package com.example.demo;

                public class PluginService {
                    public void load() throws Exception {
                        Class<?> clazz = Class.forName("com.example.demo.plugin.CustomRuleEngine");
                    }
                }
                """);

        var result = SpringNativeAndContainerModernizer.modernize(tempDir);
        assertTrue(result.modified());

        // Verify generated AppRuntimeHintsRegistrar.java
        Path hintsFile = tempDir.resolve("src/main/java/com/example/demo/aot/AppRuntimeHintsRegistrar.java");
        assertTrue(Files.exists(hintsFile));
        String hintsContent = Files.readString(hintsFile);
        assertTrue(hintsContent.contains("AppRuntimeHintsRegistrar implements RuntimeHintsRegistrar"));
        assertTrue(hintsContent.contains("hints.resources().registerPattern(\"*.json\");"));
        assertTrue(hintsContent.contains("hints.resources().registerPattern(\"*.sql\");"));
        assertTrue(hintsContent.contains("com.example.demo.plugin.CustomRuleEngine"));
        assertTrue(hintsContent.contains("MemberCategory.INVOKE_DECLARED_CONSTRUCTORS"));

        // Verify aot.factories
        Path factoriesFile = tempDir.resolve("src/main/resources/META-INF/spring/aot.factories");
        assertTrue(Files.exists(factoriesFile));
        String factoriesContent = Files.readString(factoriesFile);
        assertTrue(factoriesContent.contains("org.springframework.aot.hint.RuntimeHintsRegistrar=com.example.demo.aot.AppRuntimeHintsRegistrar"));

        // Verify @ImportRuntimeHints annotated on DemoApplication
        String updatedMain = Files.readString(mainApp);
        assertTrue(updatedMain.contains("@ImportRuntimeHints(AppRuntimeHintsRegistrar.class)"));
        assertTrue(updatedMain.contains("import org.springframework.context.annotation.ImportRuntimeHints;"));
    }
}
