package io.elmos.worker.testing;

import io.elmos.worker.validation.SpringTestingAuditValidator;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SpringJUnitModernizerTest {

    private final SpringTestingAuditValidator validator = new SpringTestingAuditValidator();

    @Test
    @DisplayName("Modernize basic JUnit 4 imports and lifecycle annotations")
    void testBasicImportsAndLifecycleAnnotations() {
        String legacyCode = """
                package com.example;

                import org.junit.Test;
                import org.junit.Before;
                import org.junit.After;
                import org.junit.BeforeClass;
                import org.junit.AfterClass;
                import org.junit.Ignore;
                import org.junit.Assert;

                public class SampleTest {
                    @BeforeClass
                    public static void setUpClass() {}

                    @AfterClass
                    public static void tearDownClass() {}

                    @Before
                    public void setUp() {}

                    @After
                    public void tearDown() {}

                    @Test
                    public void testBasic() {
                        Assert.assertEquals(1, 1);
                    }

                    @Ignore("legacy disabled")
                    @Test
                    public void testDisabled() {}
                }
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacyCode, rules);

        assertNotNull(modernized);
        assertFalse(modernized.contains("import org.junit.Test;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.Test;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.BeforeAll;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.AfterAll;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.BeforeEach;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.AfterEach;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.Disabled;"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.Assertions;"));

        assertTrue(modernized.contains("@BeforeAll"));
        assertTrue(modernized.contains("@AfterAll"));
        assertTrue(modernized.contains("@BeforeEach"));
        assertTrue(modernized.contains("@AfterEach"));
        assertTrue(modernized.contains("@Disabled(\"legacy disabled\")"));
        assertTrue(modernized.contains("Assertions.assertEquals(1, 1);"));
    }

    @Test
    @DisplayName("Invert 2-arg assertions: assertTrue(message, condition) -> assertTrue(condition, message)")
    void testAssertionTwoArgParameterSwap() {
        String legacy = """
                Assert.assertTrue("user must be active", user.isActive());
                Assert.assertFalse("must not be locked", user.isLocked());
                Assert.assertNotNull("order cannot be null", order);
                Assert.assertNull("error must be null", error);
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertTrue(modernized.contains("Assertions.assertTrue(user.isActive(), \"user must be active\");"));
        assertTrue(modernized.contains("Assertions.assertFalse(user.isLocked(), \"must not be locked\");"));
        assertTrue(modernized.contains("Assertions.assertNotNull(order, \"order cannot be null\");"));
        assertTrue(modernized.contains("Assertions.assertNull(error, \"error must be null\");"));
        assertTrue(rules.contains("RULE-JUNIT4-SWAP-ASSERT-MESSAGE-ORDER"));
    }

    @Test
    @DisplayName("Invert 3-arg assertions with complex nested calls and commas: assertEquals(msg, exp, act)")
    void testAssertionThreeArgParameterSwapWithCommasAndMethods() {
        String legacy = """
                Assert.assertEquals("ID mismatch", 100L, user.getId());
                Assert.assertNotEquals("Should not equal default", -1, user.getStatus());
                Assert.assertSame("Must be exact instance", expectedObj, actualObj);
                Assert.assertEquals("nested call, with, commas (and brackets)", service.compute(1, 2), result);
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertTrue(modernized.contains("Assertions.assertEquals(100L, user.getId(), \"ID mismatch\");"));
        assertTrue(modernized.contains("Assertions.assertNotEquals(-1, user.getStatus(), \"Should not equal default\");"));
        assertTrue(modernized.contains("Assertions.assertSame(expectedObj, actualObj, \"Must be exact instance\");"));
        assertTrue(modernized.contains("Assertions.assertEquals(service.compute(1, 2), result, \"nested call, with, commas (and brackets)\");"));
    }

    @Test
    @DisplayName("Invert 4-arg floating point assertion with delta: assertEquals(msg, exp, act, delta)")
    void testFloatingPointDeltaAssertion() {
        String legacy = """
                Assert.assertEquals("Pi tolerance", 3.1415, Math.PI, 0.001);
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertTrue(modernized.contains("Assertions.assertEquals(3.1415, Math.PI, 0.001, \"Pi tolerance\");"));
    }

    @Test
    @DisplayName("Static import assertions without Assert. prefix are also correctly reordered")
    void testStaticImportAssertionSwap() {
        String legacy = """
                import static org.junit.Assert.assertEquals;
                import static org.junit.Assert.assertTrue;

                public class StaticTest {
                    public void test() {
                        assertEquals("count mismatch", 10, count);
                        assertTrue("flag is true", flag);
                    }
                }
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertTrue(modernized.contains("import static org.junit.jupiter.api.Assertions.assertEquals;"));
        assertTrue(modernized.contains("import static org.junit.jupiter.api.Assertions.assertTrue;"));
        assertTrue(modernized.contains("assertEquals(10, count, \"count mismatch\");"));
        assertTrue(modernized.contains("assertTrue(flag, \"flag is true\");"));
    }

    @Test
    @DisplayName("Modernize @Test(expected = Foo.class) to assertThrows(...)")
    void testExpectedExceptionTransformation() {
        String legacy = """
                @Test(expected = IllegalArgumentException.class)
                public void testInvalidInput() {
                    service.process(null);
                }
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertFalse(modernized.contains("@Test(expected"));
        assertTrue(modernized.contains("@Test"));
        assertTrue(modernized.contains("Assertions.assertThrows(IllegalArgumentException.class, () -> {"));
        assertTrue(modernized.contains("service.process(null);"));
        assertTrue(rules.contains("RULE-JUNIT4-EXPECTED-EXCEPTION-TO-ASSERT-THROWS"));
    }

    @Test
    @DisplayName("Modernize @Test(timeout = 5000L) to @Timeout(5)")
    void testTimeoutAnnotationTransformation() {
        String legacy = """
                @Test(timeout = 5000L)
                public void testSlowCall() {
                    service.doSlowWork();
                }
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertFalse(modernized.contains("@Test(timeout"));
        assertTrue(modernized.contains("@Test"));
        assertTrue(modernized.contains("@Timeout(5)"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.Timeout;"));
        assertTrue(rules.contains("RULE-JUNIT4-TIMEOUT-TO-JUPITER-TIMEOUT"));
    }

    @Test
    @DisplayName("Modernize Mockito and Spring runners to Jupiter @ExtendWith")
    void testRunnerTransformations() {
        String legacy = """
                import org.junit.runner.RunWith;
                import org.springframework.test.context.junit4.SpringRunner;
                import org.mockito.junit.MockitoJUnitRunner;

                @RunWith(SpringRunner.class)
                public class SpringTest {}

                @RunWith(MockitoJUnitRunner.class)
                public class MockitoTest {}
                """;

        List<String> rules = new ArrayList<>();
        String modernized = SpringJUnitModernizer.modernizeTestContent(legacy, rules);

        assertFalse(modernized.contains("@RunWith"));
        assertTrue(modernized.contains("@ExtendWith(SpringExtension.class)"));
        assertTrue(modernized.contains("@ExtendWith(MockitoExtension.class)"));
        assertTrue(modernized.contains("import org.junit.jupiter.api.extension.ExtendWith;"));
        assertTrue(modernized.contains("import org.springframework.test.context.junit.jupiter.SpringExtension;"));
        assertTrue(modernized.contains("import org.mockito.junit.jupiter.MockitoExtension;"));
    }

    @Test
    @DisplayName("End-to-end modernization in project directory and compliance audit pass")
    void testEndToEndProjectModernizationAndCompliance(@TempDir Path tempDir) throws IOException {
        Path testDir = tempDir.resolve("src/test/java/com/example");
        Files.createDirectories(testDir);

        String legacyClass = """
                package com.example;

                import org.junit.Test;
                import org.junit.Before;
                import org.junit.runner.RunWith;
                import org.springframework.test.context.junit4.SpringRunner;
                import org.junit.Assert;

                @RunWith(SpringRunner.class)
                public class FullOrderTest {
                    @Before
                    public void init() {}

                    @Test
                    public void testOrder() {
                        Assert.assertEquals("ID mismatch", 100L, 100L);
                    }
                }
                """;
        Files.writeString(testDir.resolve("FullOrderTest.java"), legacyClass, StandardCharsets.UTF_8);

        // Run modernization
        var result = SpringJUnitModernizer.modernize(tempDir);
        assertTrue(result.modified(), "Project must be marked modified");
        assertEquals(1, result.changesCount());

        // Verify with SpringTestingAuditValidator
        var auditReport = validator.auditProject(tempDir);
        assertNotNull(auditReport);
        assertTrue(auditReport.isCompliant(), "Modernized project must be 100% compliant with JUnit 5 Jupiter rules");
        assertEquals(100.0, auditReport.complianceScore(), 0.001);
        assertEquals(0, auditReport.totalViolations());
    }

    @Test
    @DisplayName("Idempotency: Re-running modernizer on already modernized code produces zero modifications")
    void testIdempotency() {
        String legacy = """
                package com.example;

                import org.junit.Test;
                import org.junit.Assert;

                public class IdempotentTest {
                    @Test
                    public void testOne() {
                        Assert.assertEquals("must match", 1, 1);
                    }
                }
                """;

        String firstPass = SpringJUnitModernizer.modernizeTestContent(legacy, new ArrayList<>());
        String secondPass = SpringJUnitModernizer.modernizeTestContent(firstPass, new ArrayList<>());

        assertEquals(firstPass, secondPass, "Modernizer must be strictly idempotent");
    }
}
