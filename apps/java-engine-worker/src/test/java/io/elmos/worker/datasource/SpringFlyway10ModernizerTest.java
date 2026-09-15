package io.elmos.worker.datasource;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringFlyway10ModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesFlyway10PomAndConfigAndGeneratesSafetyCustomizer() throws Exception {
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, """
                <project>
                  <dependencies>
                    <dependency>
                      <groupId>org.flywaydb</groupId>
                      <artifactId>flyway-core</artifactId>
                    </dependency>
                    <dependency>
                      <groupId>com.mysql</groupId>
                      <artifactId>mysql-connector-j</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        Path yamlConfig = tempDir.resolve("src/main/resources/application.yml");
        Files.createDirectories(yamlConfig.getParent());
        Files.writeString(yamlConfig, """
                spring:
                  flyway:
                    locations: classpath:db/migration
                """);

        var result = SpringFlyway10Modernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 3);

        String updatedPom = Files.readString(pomFile);
        assertTrue(updatedPom.contains("flyway-mysql"));

        String updatedYaml = Files.readString(yamlConfig);
        assertTrue(updatedYaml.contains("clean-disabled: true"));
        assertTrue(updatedYaml.contains("baseline-on-migrate: true"));

        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/flyway/FlywayMigrationSafetyConfiguration.java");
        assertTrue(Files.isRegularFile(generatedConfig));
        String configCode = Files.readString(generatedConfig);
        assertTrue(configCode.contains("cleanDisabled(true)"));
        assertTrue(configCode.contains("baselineOnMigrate(true)"));
    }

    @Test
    void returnsEmptyWhenNoFlywayDetected() throws Exception {
        var result = SpringFlyway10Modernizer.modernize(tempDir);
        assertFalse(result.modified());
    }
}
