package io.elmos.worker.testing;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringPowerMockEliminatorTest {

    @Test
    void testPowerMockRunnerAndStaticMockElimination(@TempDir Path tempDir) throws IOException {
        String testContent = """
                package com.example.service;

                import org.junit.Test;
                import org.junit.runner.RunWith;
                import org.powermock.api.mockito.PowerMockito;
                import org.powermock.core.classloader.annotations.PrepareForTest;
                import org.powermock.modules.junit4.PowerMockRunner;
                import static org.junit.Assert.assertEquals;

                @RunWith(PowerMockRunner.class)
                @PrepareForTest({DateTimeUtils.class})
                public class OrderServiceTest {

                    @Test
                    public void testGenerateOrder() {
                        PowerMockito.mockStatic(DateTimeUtils.class);
                        PowerMockito.when(DateTimeUtils.getCurrentDateString()).thenReturn("2026-09-15");

                        String date = DateTimeUtils.getCurrentDateString();
                        assertEquals("2026-09-15", date);
                    }
                }
                """;
        Path testDir = tempDir.resolve("src/test/java/com/example/service");
        Files.createDirectories(testDir);
        Path testFile = testDir.resolve("OrderServiceTest.java");
        Files.writeString(testFile, testContent);

        String pomContent = """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example</groupId>
                  <artifactId>demo-service</artifactId>
                  <version>1.0.0</version>
                  <dependencies>
                    <dependency>
                      <groupId>org.powermock</groupId>
                      <artifactId>powermock-module-junit4</artifactId>
                      <version>2.0.9</version>
                      <scope>test</scope>
                    </dependency>
                    <dependency>
                      <groupId>org.powermock</groupId>
                      <artifactId>powermock-api-mockito2</artifactId>
                      <version>2.0.9</version>
                      <scope>test</scope>
                    </dependency>
                  </dependencies>
                </project>
                """;
        Path pomFile = tempDir.resolve("pom.xml");
        Files.writeString(pomFile, pomContent);

        var result = SpringPowerMockEliminator.eliminate(tempDir);

        assertTrue(result.modified());
        assertTrue(result.rulesApplied().contains("POWERMOCK_RUNNER_TO_MOCKITO_EXTENSION"));
        assertTrue(result.rulesApplied().contains("POWERMOCK_PREPARE_FOR_TEST_REMOVED"));
        assertTrue(result.rulesApplied().contains("POWERMOCK_MOCK_STATIC_TO_MOCKED_STATIC"));
        assertTrue(result.rulesApplied().contains("POWERMOCK_POM_DEPENDENCIES_REMOVED"));
        assertTrue(result.rulesApplied().contains("MOCKITO_5_JUPITER_DEPENDENCIES_ADDED"));

        String updatedTest = Files.readString(testFile);
        assertFalse(updatedTest.contains("PowerMockRunner"));
        assertFalse(updatedTest.contains("PrepareForTest"));
        assertFalse(updatedTest.contains("PowerMockito.mockStatic"));
        assertTrue(updatedTest.contains("@ExtendWith(MockitoExtension.class)"));
        assertTrue(updatedTest.contains("MockedStatic<DateTimeUtils> mockedDateTimeUtils = mockStatic(DateTimeUtils.class)"));
        assertTrue(updatedTest.contains("mockedDateTimeUtils.when(() -> DateTimeUtils.getCurrentDateString()).thenReturn(\"2026-09-15\");"));

        String updatedPom = Files.readString(pomFile);
        assertFalse(updatedPom.contains("powermock-module-junit4"));
        assertFalse(updatedPom.contains("powermock-api-mockito2"));
        assertTrue(updatedPom.contains("mockito-junit-jupiter"));
        assertTrue(updatedPom.contains("5.11.0"));
    }

    @Test
    void testFullSuiteModernizeWithPowerMock(@TempDir Path tempDir) throws IOException {
        String testContent = """
                package com.example.service;

                import org.junit.Test;
                import org.junit.runner.RunWith;
                import org.powermock.api.mockito.PowerMockito;
                import org.powermock.core.classloader.annotations.PrepareForTest;
                import org.powermock.modules.junit4.PowerMockRunner;
                import static org.junit.Assert.assertTrue;

                @RunWith(PowerMockRunner.class)
                @PrepareForTest({SystemUtil.class})
                public class SimpleTest {

                    @Test
                    public void testActive() {
                        PowerMockito.mockStatic(SystemUtil.class);
                        PowerMockito.when(SystemUtil.isActive()).thenReturn(true);
                        assertTrue(SystemUtil.isActive());
                    }
                }
                """;
        Path testDir = tempDir.resolve("src/test/java/com/example/service");
        Files.createDirectories(testDir);
        Path testFile = testDir.resolve("SimpleTest.java");
        Files.writeString(testFile, testContent);

        // Run full SpringJUnitModernizer
        var res = SpringJUnitModernizer.modernize(tempDir);
        assertTrue(res.modified());

        String updated = Files.readString(testFile);
        assertFalse(updated.contains("org.junit.Test"));
        assertTrue(updated.contains("org.junit.jupiter.api.Test"));
        assertTrue(updated.contains("@ExtendWith(MockitoExtension.class)"));
        assertFalse(updated.contains("PrepareForTest"));
    }
}
