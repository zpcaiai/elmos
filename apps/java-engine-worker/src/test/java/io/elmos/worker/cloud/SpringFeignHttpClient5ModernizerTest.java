package io.elmos.worker.cloud;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringFeignHttpClient5ModernizerTest {

    @Test
    void testFeignHttpClient5ModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup pom.xml with legacy feign-httpclient
        Path pomPath = tempDir.resolve("pom.xml");
        String pomContent = """
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>io.github.openfeign</groupId>
                            <artifactId>feign-httpclient</artifactId>
                            <version>11.8</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(pomPath, pomContent);

        // 2. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  application:\n    name: order-consumer\n");

        // Execute modernization
        SpringFeignHttpClient5Modernizer modernizer = new SpringFeignHttpClient5Modernizer();
        SpringFeignHttpClient5Modernizer.FeignModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Project should have been modified");
        assertTrue(result.changesCount() >= 4, "Should have applied at least 4 modifications");

        // Verify pom.xml upgraded to feign-hc5
        String updatedPom = Files.readString(pomPath);
        assertTrue(updatedPom.contains("feign-hc5"), "Should contain feign-hc5 dependency");
        assertFalse(updatedPom.contains("feign-httpclient"), "Legacy feign-httpclient should be eliminated");

        // Verify FeignHttpClient5Configuration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/config/FeignHttpClient5Configuration.java");
        assertTrue(Files.exists(generatedConfig), "FeignHttpClient5Configuration should be generated");
        String configSource = Files.readString(generatedConfig);
        assertTrue(configSource.contains("PoolingHttpClientConnectionManager"), "Should configure PoolingHttpClientConnectionManager");
        assertTrue(configSource.contains("setMaxTotal(500)"), "Should set max connections to 500");

        // Verify FeignHeaderPropagationRequestInterceptor generated
        Path generatedInterceptor = tempDir.resolve("src/main/java/io/elmos/generated/config/FeignHeaderPropagationRequestInterceptor.java");
        assertTrue(Files.exists(generatedInterceptor), "FeignHeaderPropagationRequestInterceptor should be generated");
        String interceptorSource = Files.readString(generatedInterceptor);
        assertTrue(interceptorSource.contains("PROPAGATED_HEADERS"), "Should contain propagated header definitions");

        // Verify application.yml updated
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("hc5:"), "Should configure HC5 in application.yml");
        assertTrue(updatedYml.contains("enabled: true"), "Should enable HC5 client");
    }
}
