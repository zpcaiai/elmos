package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringAdminClientModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesAdminClientDependencyInPom() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>de.codecentric</groupId>
                      <artifactId>spring-boot-admin-starter-client</artifactId>
                      <version>2.7.4</version>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringAdminClientModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updated = Files.readString(pomFile);
        assertFalse(updated.contains("2.7.4"));
        assertTrue(updated.contains("3.2.3"));

        Path securityConfig = tempDir.resolve("src/main/java/io/elmos/generated/admin/AdminClientHeartbeatSecurityConfiguration.java");
        assertTrue(Files.isRegularFile(securityConfig));
    }

    @Test
    void configuresActuatorEndpointsForAdminClientInYaml() throws Exception {
        Path ymlFile = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(ymlFile.getParent());
        Files.writeString(ymlFile, """
                spring:
                  boot:
                    admin:
                      client:
                        url: "http://localhost:8080"
                management:
                  endpoints:
                    web:
                      exposure:
                        include: "health,info"
                """);

        var result = SpringAdminClientModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedYaml = Files.readString(ymlFile);
        assertTrue(updatedYaml.contains("loggers"));
        assertTrue(updatedYaml.contains("metrics"));
    }
}
