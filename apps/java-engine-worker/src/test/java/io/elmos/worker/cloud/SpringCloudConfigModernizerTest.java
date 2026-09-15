package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringCloudConfigModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void injectsSpringCloudBusDependencyWhenConfigClientDetected() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.cloud</groupId>
                      <artifactId>spring-cloud-starter-config</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        var result = SpringCloudConfigModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 1);

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("spring-cloud-starter-bus-amqp"));

        Path fallbackListener = tempDir.resolve("src/main/java/io/elmos/generated/config/LocalConfigSnapshotFallbackListener.java");
        assertTrue(Files.isRegularFile(fallbackListener));
    }

    @Test
    void enablesActuatorRefreshAndBusEndpointsInYaml() throws Exception {
        Path ymlFile = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(ymlFile.getParent());
        Files.writeString(ymlFile, """
                spring:
                  config:
                    import: "optional:configserver:http://localhost:8888"
                management:
                  endpoints:
                    web:
                      exposure:
                        include: "health,info"
                """);

        var result = SpringCloudConfigModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String updatedYaml = Files.readString(ymlFile);
        assertTrue(updatedYaml.contains("busrefresh"));
        assertTrue(updatedYaml.contains("bus:"));
        assertTrue(updatedYaml.contains("refresh:"));
    }
}
