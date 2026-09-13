package io.elmos.worker.validation;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringTestingAuditValidatorTest {

    private final SpringTestingAuditValidator validator = new SpringTestingAuditValidator();

    @Test
    @DisplayName("Non-compliant project with JUnit 4 @Test, @RunWith(SpringRunner.class), and org.junit.Assert")
    void testNonCompliantTestingProject(@TempDir Path tempDir) throws IOException {
        Path testDir = tempDir.resolve("src/test/java/com/example");
        Files.createDirectories(testDir);

        String testCode = """
                package com.example;

                import org.junit.Test;
                import org.junit.Before;
                import org.junit.runner.RunWith;
                import org.springframework.test.context.junit4.SpringRunner;
                import org.junit.Assert;

                @RunWith(SpringRunner.class)
                public class LegacyOrderTest {
                    @Before
                    public void init() {}

                    @Test
                    public void testOrder() {
                        Assert.assertEquals(1, 1);
                    }
                }
                """;
        Files.writeString(testDir.resolve("LegacyOrderTest.java"), testCode, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertFalse(report.isCompliant(), "Must not be compliant with JUnit 4 legacy constructs");
        assertTrue(report.violations().stream().anyMatch(v -> "TST-001".equals(v.ruleId())), "Must report TST-001 (JUnit 4 @Test)");
        assertTrue(report.violations().stream().anyMatch(v -> "TST-002".equals(v.ruleId())), "Must report TST-002 (@RunWith)");
        assertTrue(report.violations().stream().anyMatch(v -> "TST-003".equals(v.ruleId())), "Must report TST-003 (@Before)");
        assertTrue(report.violations().stream().anyMatch(v -> "TST-004".equals(v.ruleId())), "Must report TST-004 (Assert)");
    }

    @Test
    @DisplayName("Zero-Test Rule Violation: test file exists but contains no active Jupiter @Test methods")
    void testZeroTestRuleViolation(@TempDir Path tempDir) throws IOException {
        Path testDir = tempDir.resolve("src/test/java/com/example");
        Files.createDirectories(testDir);

        String emptyTest = """
                package com.example;

                public class EmptyTest {
                    // Empty test class without any test annotations
                }
                """;
        Files.writeString(testDir.resolve("EmptyTest.java"), emptyTest, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertFalse(report.isCompliant(), "Zero-test rule violation must fail compliance");
        assertTrue(report.violations().stream().anyMatch(v -> "TST-005".equals(v.ruleId())), "Must report TST-005 (Zero-test rule)");
    }

    @Test
    @DisplayName("Compliant project with JUnit 5 Jupiter @Test, @ExtendWith, @BeforeEach, and Assertions")
    void testCompliantTestingProject(@TempDir Path tempDir) throws IOException {
        Path testDir = tempDir.resolve("src/test/java/com/example");
        Files.createDirectories(testDir);

        String testCode = """
                package com.example;

                import org.junit.jupiter.api.Test;
                import org.junit.jupiter.api.BeforeEach;
                import org.junit.jupiter.api.extension.ExtendWith;
                import org.springframework.test.context.junit.jupiter.SpringExtension;
                import org.junit.jupiter.api.Assertions;

                @ExtendWith(SpringExtension.class)
                public class JupiterOrderTest {
                    @BeforeEach
                    void init() {}

                    @Test
                    void testOrder() {
                        Assertions.assertEquals(1, 1);
                    }
                }
                """;
        Files.writeString(testDir.resolve("JupiterOrderTest.java"), testCode, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertTrue(report.isCompliant(), "Must be compliant with JUnit 5 Jupiter test suite");
        assertEquals(100.0, report.complianceScore(), 0.001);
        assertEquals(0, report.totalViolations());
    }
}
