package io.elmos.worker.security;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringConfigurationCipherModernizerTest {

    @Test
    void testConfigurationCipherModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml with legacy jasypt
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>com.github.ulisesbocchio</groupId>
                            <artifactId>jasypt-spring-boot-starter</artifactId>
                            <version>3.0.3</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  datasource:\n    password: ENC(xyz123==)\n");

        // Execute modernization
        SpringConfigurationCipherModernizer modernizer = new SpringConfigurationCipherModernizer();
        SpringConfigurationCipherModernizer.CipherModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should be modified");
        assertTrue(result.changesCount() >= 3, "Should have applied at least 3 modifications");

        // Verify pom.xml upgraded to 3.0.5
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("<version>3.0.5</version>"), "Should upgrade Jasypt to 3.0.5");
        assertFalse(updatedPom.contains("3.0.3"), "Legacy version 3.0.3 should be replaced");

        // Verify EnvironmentSecretBootstrapCheck generated
        Path generatedCheck = tempDir.resolve("src/main/java/io/elmos/generated/security/EnvironmentSecretBootstrapCheck.java");
        assertTrue(Files.exists(generatedCheck), "EnvironmentSecretBootstrapCheck should be generated");
        String checkSource = Files.readString(generatedCheck);
        assertTrue(checkSource.contains("str.startsWith(\"ENC(\")"), "Should inspect ENC token");
        assertTrue(checkSource.contains("Fatal Secret Startup Failure"), "Should format diagnostic message");

        // Verify application.yml updated
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("PBEWITHHMACSHA512ANDAES_256"), "Should configure AES-256 algorithm");
        assertTrue(updatedYml.contains("RandomIvGenerator"), "Should configure RandomIvGenerator");
    }
}
