package io.elmos.worker.observability;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringEnterpriseObservabilityAndMicrometerTracerTest {

    @Test
    @DisplayName("Modernize Sleuth Java imports to Micrometer Tracing")
    void testJavaSleuthMigration() {
        String legacyCode = "package com.example.service;\n"
                + "import org.springframework.cloud.sleuth.Tracer;\n"
                + "import org.springframework.cloud.sleuth.Span;\n"
                + "import org.springframework.cloud.sleuth.CurrentTraceContext;\n"
                + "import org.springframework.cloud.sleuth.annotation.NewSpan;\n"
                + "public class PaymentTracerService {\n"
                + "    private Tracer tracer;\n"
                + "}";

        var result = SpringEnterpriseObservabilityAndMicrometerTracer.modernizeContent(legacyCode, "PaymentTracerService.java");

        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 4);
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains("org.springframework.cloud.sleuth.Tracer"));
        assertTrue(modernized.contains("io.micrometer.tracing.Tracer"));
        assertTrue(modernized.contains("io.micrometer.tracing.Span"));
        assertTrue(modernized.contains("io.micrometer.tracing.CurrentTraceContext"));
        assertTrue(modernized.contains("io.micrometer.tracing.annotation.NewSpan"));
    }

    @Test
    @DisplayName("Modernize Sleuth properties and YAML configuration")
    void testConfigPropertiesMigration() {
        String legacyProps = "server.port=8080\n"
                + "spring.sleuth.sampler.probability=1.0\n"
                + "spring.zipkin.base-url=http://zipkin:9411\n"
                + "spring.sleuth.enabled=true\n";

        var result = SpringEnterpriseObservabilityAndMicrometerTracer.modernizeContent(legacyProps, "application.properties");

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains("spring.sleuth.sampler.probability"));
        assertTrue(modernized.contains("management.tracing.sampling.probability=1.0"));
        assertTrue(modernized.contains("management.zipkin.tracing.endpoint=http://zipkin:9411"));
        assertTrue(modernized.contains("management.tracing.enabled=true"));
    }

    @Test
    @DisplayName("Modernize Sleuth Maven dependencies in POM")
    void testPomDependenciesMigration() {
        String legacyPom = "<dependencies>\n"
                + "    <dependency>\n"
                + "        <groupId>org.springframework.cloud</groupId>\n"
                + "        <artifactId>spring-cloud-starter-sleuth</artifactId>\n"
                + "    </dependency>\n"
                + "    <dependency>\n"
                + "        <groupId>org.springframework.cloud</groupId>\n"
                + "        <artifactId>spring-cloud-sleuth-zipkin</artifactId>\n"
                + "    </dependency>\n"
                + "</dependencies>\n";

        var result = SpringEnterpriseObservabilityAndMicrometerTracer.modernizeContent(legacyPom, "pom.xml");

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains("spring-cloud-starter-sleuth"));
        assertTrue(modernized.contains("micrometer-tracing-bridge-brave"));
        assertTrue(modernized.contains("zipkin-reporter-brave"));
    }

    @Test
    @DisplayName("Modernize observability files across workspace directory on disk")
    void testWorkspaceObservabilityModernization(@TempDir Path tempDir) throws IOException {
        Path javaDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(javaDir);
        Files.writeString(javaDir.resolve("TraceService.java"),
                "package com.example;\nimport org.springframework.cloud.sleuth.Tracer;\npublic class TraceService { private Tracer tracer; }");

        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Files.writeString(resDir.resolve("application.properties"), "spring.sleuth.sampler.probability=0.5\n");

        var result = SpringEnterpriseObservabilityAndMicrometerTracer.modernize(tempDir);

        assertTrue(result.modified());
        assertTrue(result.changesCount() >= 2);
        assertTrue(Files.readString(javaDir.resolve("TraceService.java")).contains("io.micrometer.tracing.Tracer"));
        assertTrue(Files.readString(resDir.resolve("application.properties")).contains("management.tracing.sampling.probability=0.5"));
    }
}
