package io.elmos.worker.validation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringCloudArchitectureValidatorTest {

    @TempDir
    Path tempDir;

    private final SpringCloudArchitectureValidator validator = new SpringCloudArchitectureValidator();

    @Test
    void testDetectsLegacyNetflixComponents() throws IOException {
        Path javaFile = tempDir.resolve("LegacyService.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @EnableZuulProxy
                @RibbonClient(name = "svc")
                public class LegacyService {
                    @HystrixCommand(fallbackMethod = "fallback")
                    public String call() { return "ok"; }
                }
                """);

        Path bootstrapFile = tempDir.resolve("bootstrap.yml");
        Files.writeString(bootstrapFile, "spring.cloud.config.uri: http://localhost:8888\n");

        SpringCloudArchitectureValidator.SpringCloudAuditReport report = validator.auditProject(tempDir);
        assertFalse(report.isCompliant());
        assertTrue(report.criticalViolations() >= 3);
        assertTrue(report.violations().stream().anyMatch(v -> "CLOUD-001".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "CLOUD-002".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "CLOUD-003".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "CLOUD-007".equals(v.ruleId())));
    }

    @Test
    void testCompliantModernSpringCloudService() throws IOException {
        Path javaFile = tempDir.resolve("ModernService.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;

                @LoadBalancerClient(name = "svc")
                public class ModernService {
                    @CircuitBreaker(name = "svc", fallbackMethod = "fallback")
                    public String call() { return "ok"; }
                }
                """);

        SpringCloudArchitectureValidator.SpringCloudAuditReport report = validator.auditProject(tempDir);
        assertTrue(report.isCompliant());
        assertEquals(0, report.criticalViolations());
    }
}
