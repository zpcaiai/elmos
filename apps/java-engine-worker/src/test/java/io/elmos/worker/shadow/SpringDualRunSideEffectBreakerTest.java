package io.elmos.worker.shadow;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringDualRunSideEffectBreakerTest {

    @TempDir
    Path tempDir;

    @Test
    void generatesShadowInterceptorAndInjectsProperties() throws Exception {
        Path appYml = tempDir.resolve("application.yml");
        Files.writeString(appYml, "server:\n  port: 8080\n");

        var result = SpringDualRunSideEffectBreaker.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);

        // 1. Verify ShadowSideEffectInterceptorConfiguration generated
        Path generatedConfig = tempDir.resolve("src/main/java/io/elmos/generated/shadow/ShadowSideEffectInterceptorConfiguration.java");
        assertTrue(Files.exists(generatedConfig));
        String content = Files.readString(generatedConfig);
        assertTrue(content.contains("ShadowEgressBreakerInterceptor"));
        assertTrue(content.contains("X-Elmos-Shadow-Mode"));
        assertTrue(content.contains("SHADOW_MOCKED_SUCCESS"));

        // 2. Verify application.yml has shadow properties
        String updatedYml = Files.readString(appYml);
        assertTrue(updatedYml.contains("shadow:"));
        assertTrue(updatedYml.contains("topic-prefix: shadow."));
    }
}
