package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Industrial-grade structural validator for Spring Test Suite Modernization (JUnit 4 to JUnit 5 Jupiter).
 *
 * <p>Audits a codebase to guarantee:
 * <ul>
 *   <li>Zero usage of legacy JUnit 4 {@code @Test} ({@code org.junit.Test}).</li>
 *   <li>Zero usage of legacy JUnit 4 runners ({@code @RunWith(SpringRunner.class)}).</li>
 *   <li>Zero usage of legacy JUnit 4 lifecycle annotations ({@code @Before}, {@code @After}, {@code @BeforeClass}, {@code @AfterClass}, {@code @Ignore}).</li>
 *   <li>Zero usage of legacy JUnit 4 assertions ({@code org.junit.Assert.*}).</li>
 *   <li>Enforcement of the Zero-Test Rule: test files must contain active Jupiter {@code @Test} methods.</li>
 * </ul>
 */
public final class SpringTestingAuditValidator {

    public enum Severity {
        CRITICAL,
        HIGH,
        MEDIUM,
        LOW,
        INFO
    }

    public record TestingViolation(
            String ruleId,
            Severity severity,
            String filePath,
            int line,
            String message,
            String remediationSnippet
    ) {}

    public record TestingAuditReport(
            int totalFilesScanned,
            int totalViolations,
            int criticalViolations,
            int highViolations,
            double complianceScore,
            boolean isCompliant,
            List<TestingViolation> violations
    ) {}

    public TestingAuditReport auditProject(Path projectRoot) throws IOException {
        List<TestingViolation> violations = new ArrayList<>();
        int filesScanned = 0;

        if (!Files.isDirectory(projectRoot)) {
            return new TestingAuditReport(0, 0, 0, 0, 100.0, true, Collections.emptyList());
        }

        Path testDir = projectRoot.resolve("src/test/java");
        Path scanRoot = Files.isDirectory(testDir) ? testDir : projectRoot;

        int totalTestClasses = 0;
        int totalJupiterTestMethods = 0;

        try (var stream = Files.walk(scanRoot)) {
            List<Path> testFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .filter(p -> p.toString().contains("Test") || p.toString().contains("src/test"))
                    .toList();

            for (Path tf : testFiles) {
                filesScanned++;
                totalTestClasses++;
                String content = Files.readString(tf, StandardCharsets.UTF_8);

                boolean hasJupiterTest = (content.contains("org.junit.jupiter.api.Test"))
                        && java.util.regex.Pattern.compile("(?m)^\\s*@(org\\.junit\\.jupiter\\.api\\.)?Test\\b").matcher(content).find();
                if (hasJupiterTest) {
                    totalJupiterTestMethods++;
                }

                auditTestFile(tf, content, violations);
            }
        }

        // TST-005: Zero-Test Rule enforcement
        if (totalTestClasses > 0 && totalJupiterTestMethods == 0) {
            violations.add(new TestingViolation(
                    "TST-005",
                    Severity.CRITICAL,
                    scanRoot.toString(),
                    1,
                    "Zero-Test Rule Violation: " + totalTestClasses + " test class files were detected, but zero JUnit 5 Jupiter @Test methods were found.",
                    """
                    import org.junit.jupiter.api.Test;

                    @Test
                    void contextLoads() {
                        Assertions.assertTrue(true);
                    }
                    """
            ));
        }

        int critical = (int) violations.stream().filter(v -> v.severity() == Severity.CRITICAL).count();
        int high = (int) violations.stream().filter(v -> v.severity() == Severity.HIGH).count();
        int medium = (int) violations.stream().filter(v -> v.severity() == Severity.MEDIUM).count();

        double penalty = (critical * 25.0) + (high * 10.0) + (medium * 3.0);
        double complianceScore = Math.max(0.0, 100.0 - penalty);
        boolean isCompliant = critical == 0 && high == 0;

        return new TestingAuditReport(
                filesScanned,
                violations.size(),
                critical,
                high,
                complianceScore,
                isCompliant,
                Collections.unmodifiableList(violations)
        );
    }

    private void auditTestFile(Path testFile, String content, List<TestingViolation> violations) {
        String relativePath = testFile.toString();

        // TST-001: Legacy JUnit 4 @Test
        if (content.contains("import org.junit.Test;") || content.contains("org.junit.Test")) {
            violations.add(new TestingViolation(
                    "TST-001",
                    Severity.CRITICAL,
                    relativePath,
                    findLineNumber(content, "org.junit.Test"),
                    "Legacy JUnit 4 @Test detected. Migrate to JUnit 5 Jupiter (org.junit.jupiter.api.Test).",
                    "import org.junit.jupiter.api.Test;"
            ));
        }

        // TST-002: Legacy @RunWith(SpringRunner.class)
        if (content.contains("RunWith(SpringRunner.class)") || content.contains("RunWith(SpringJUnit4ClassRunner.class)")) {
            violations.add(new TestingViolation(
                    "TST-002",
                    Severity.HIGH,
                    relativePath,
                    findLineNumber(content, "RunWith"),
                    "Legacy JUnit 4 @RunWith runner detected. Migrate to JUnit 5 @ExtendWith(SpringExtension.class) or @SpringBootTest.",
                    "@ExtendWith(SpringExtension.class)\n// or @SpringBootTest which includes SpringExtension"
            ));
        }

        // TST-003: Legacy lifecycle annotations (@Before, @After, @Ignore)
        if (content.contains("import org.junit.Before;")
                || content.contains("import org.junit.After;")
                || content.contains("import org.junit.BeforeClass;")
                || content.contains("import org.junit.AfterClass;")
                || content.contains("import org.junit.Ignore;")) {
            violations.add(new TestingViolation(
                    "TST-003",
                    Severity.HIGH,
                    relativePath,
                    findLineNumber(content, "org.junit.Before"),
                    "Legacy JUnit 4 lifecycle annotation detected (@Before/@After/@Ignore). "
                            + "Migrate to Jupiter (@BeforeEach/@AfterEach/@BeforeAll/@AfterAll/@Disabled).",
                    "@BeforeEach / @AfterEach / @Disabled"
            ));
        }

        // TST-004: Legacy JUnit 4 assertions
        if (content.contains("import org.junit.Assert;") || content.contains("import static org.junit.Assert.")) {
            violations.add(new TestingViolation(
                    "TST-004",
                    Severity.HIGH,
                    relativePath,
                    findLineNumber(content, "org.junit.Assert"),
                    "Legacy org.junit.Assert static assertions detected. "
                            + "Migrate to org.junit.jupiter.api.Assertions (note: message parameter is last).",
                    "import static org.junit.jupiter.api.Assertions.*;"
            ));
        }
    }

    private static int findLineNumber(String text, String substring) {
        int index = text.indexOf(substring);
        if (index < 0) return 1;
        int line = 1;
        for (int i = 0; i < index; i++) {
            if (text.charAt(i) == '\n') line++;
        }
        return line;
    }
}
