package io.elmos.worker.validation;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringWebRoutingAuditValidatorTest {

    private final SpringWebRoutingAuditValidator validator = new SpringWebRoutingAuditValidator();

    @Test
    @DisplayName("Non-compliant project with controllers missing trailing-slash config and using javax.servlet")
    void testNonCompliantWebRoutingProject(@TempDir Path tempDir) throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        String controller = """
                package com.example;

                import org.springframework.web.bind.annotation.RestController;
                import org.springframework.web.bind.annotation.GetMapping;

                @RestController
                public class OrderController {
                    @GetMapping("/api/orders")
                    public String getOrders() { return "[]"; }
                }
                """;
        Files.writeString(src.resolve("OrderController.java"), controller, StandardCharsets.UTF_8);

        String advice = """
                package com.example;

                import org.springframework.web.bind.annotation.ControllerAdvice;
                import org.springframework.web.bind.annotation.ExceptionHandler;
                import javax.servlet.http.HttpServletRequest;

                @ControllerAdvice
                public class GlobalAdvice {
                    @ExceptionHandler(Exception.class)
                    public void handle(Exception e, HttpServletRequest req) {}
                }
                """;
        Files.writeString(src.resolve("GlobalAdvice.java"), advice, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertFalse(report.isCompliant(), "Must not be compliant with missing trailing slash config and javax.servlet");
        assertTrue(report.violations().stream().anyMatch(v -> "WEB-001".equals(v.ruleId())), "Must report WEB-001 (Missing trailing slash)");
        assertTrue(report.violations().stream().anyMatch(v -> "WEB-002".equals(v.ruleId())), "Must report WEB-002 (javax.servlet)");
    }

    @Test
    @DisplayName("Compliant project with LegacyWebMvcTrailingSlashConfiguration and jakarta.servlet")
    void testCompliantWebRoutingProject(@TempDir Path tempDir) throws IOException {
        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);

        String controller = """
                package com.example;

                import org.springframework.web.bind.annotation.RestController;
                import org.springframework.web.bind.annotation.GetMapping;

                @RestController
                public class OrderController {
                    @GetMapping("/api/orders")
                    public String getOrders() { return "[]"; }
                }
                """;
        Files.writeString(src.resolve("OrderController.java"), controller, StandardCharsets.UTF_8);

        String config = """
                package com.example;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.web.servlet.config.annotation.PathMatchConfigurer;
                import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

                @Configuration
                public class LegacyWebMvcTrailingSlashConfiguration implements WebMvcConfigurer {
                    @Override
                    public void configurePathMatch(PathMatchConfigurer configurer) {
                        configurer.setUseTrailingSlashMatch(true);
                    }
                }
                """;
        Files.writeString(src.resolve("LegacyWebMvcTrailingSlashConfiguration.java"), config, StandardCharsets.UTF_8);

        String advice = """
                package com.example;

                import org.springframework.web.bind.annotation.ControllerAdvice;
                import org.springframework.web.bind.annotation.ExceptionHandler;
                import jakarta.servlet.http.HttpServletRequest;

                @ControllerAdvice
                public class GlobalAdvice {
                    @ExceptionHandler(Exception.class)
                    public void handle(Exception e, HttpServletRequest req) {}
                }
                """;
        Files.writeString(src.resolve("GlobalAdvice.java"), advice, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertTrue(report.isCompliant(), "Must be compliant with trailing slash config and jakarta.servlet");
        assertEquals(100.0, report.complianceScore(), 0.001);
        assertEquals(0, report.totalViolations());
    }
}
