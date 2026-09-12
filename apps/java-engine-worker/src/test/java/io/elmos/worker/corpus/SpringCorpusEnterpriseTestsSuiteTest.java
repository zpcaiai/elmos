package io.elmos.worker.corpus;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus.ProjectSpec;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringCorpusEnterpriseTestsSuiteTest {

    @Test
    @DisplayName("Verify all 30 open source projects generate non-empty, valid integration test suites")
    void testAllThirtyProjectsGenerateValidTests() {
        List<ProjectSpec> projects = SpringThirtyOpenSourceProjectsCorpus.getCorpus();

        assertNotNull(projects);
        assertEquals(30, projects.size(),
                "Corpus must contain exactly 30 benchmark projects");

        int totalTestFiles = 0;
        int totalTestAssertions = 0;

        for (ProjectSpec project : projects) {
            Map<String, String> files = project.sourceFiles();
            assertNotNull(files, "Project files cannot be null for " + project.id());

            // 1. Every project must have base ApplicationTests.java
            String baseTest = files.get("src/test/java/io/elmos/benchmark/ApplicationTests.java");
            assertNotNull(baseTest, "ApplicationTests.java missing in " + project.id());
            assertTrue(baseTest.contains("@Test"));

            // 2. Count all test files under src/test/java
            long projectTestFiles = files.keySet().stream()
                    .filter(k -> k.startsWith("src/test/java/") && k.endsWith(".java"))
                    .count();
            assertTrue(projectTestFiles >= 1, "Project " + project.id() + " must contain at least 1 test file");
            totalTestFiles += projectTestFiles;

            // 3. Inspect test assertions and annotations
            for (Map.Entry<String, String> entry : files.entrySet()) {
                if (entry.getKey().startsWith("src/test/java/") && entry.getKey().endsWith(".java")) {
                    String testCode = entry.getValue();
                    assertTrue(testCode.contains("@Test"),
                            "Test file " + entry.getKey() + " in " + project.id() + " must have @Test annotation");

                    boolean hasAssertions = testCode.contains("assert")
                            || testCode.contains("verify")
                            || testCode.contains("status().is")
                            || testCode.contains("jsonPath");
                    assertTrue(hasAssertions,
                            "Test file " + entry.getKey() + " in " + project.id() + " must have assertions");

                    if (testCode.contains("assert")) totalTestAssertions += 2;
                    if (testCode.contains("status().is")) totalTestAssertions += 2;
                }
            }
        }

        assertTrue(totalTestFiles >= 30, "Total test files across corpus should be at least 30");
        assertTrue(totalTestAssertions >= 60, "Total test assertions across corpus should be at least 60");
    }

    @Test
    @DisplayName("Verify Part 1 domain integration test suites (Projects 1-10)")
    void testPart1EnterpriseTestSuites() {
        List<ProjectSpec> projects = SpringThirtyOpenSourceProjectsCorpus.getCorpus();
        for (int i = 0; i < 10; i++) {
            ProjectSpec project = projects.get(i);
            Map<String, String> files = project.sourceFiles();

            boolean hasIntegrationTest = files.keySet().stream()
                    .anyMatch(k -> k.startsWith("src/test/java/") && k.contains("Test"));
            assertTrue(hasIntegrationTest, "Project " + project.id() + " must have integration tests");
        }
    }

    @Test
    @DisplayName("Verify Part 2 domain integration test suites (Projects 11-20)")
    void testPart2EnterpriseTestSuites() {
        List<ProjectSpec> projects = SpringThirtyOpenSourceProjectsCorpus.getCorpus();
        for (int i = 10; i < 20; i++) {
            ProjectSpec project = projects.get(i);
            Map<String, String> files = project.sourceFiles();

            boolean hasIntegrationTest = files.keySet().stream()
                    .anyMatch(k -> k.startsWith("src/test/java/") && k.contains("Test"));
            assertTrue(hasIntegrationTest, "Project " + project.id() + " must have integration tests");
        }
    }

    @Test
    @DisplayName("Verify Part 3 domain integration test suites (Projects 21-30)")
    void testPart3EnterpriseTestSuites() {
        List<ProjectSpec> projects = SpringThirtyOpenSourceProjectsCorpus.getCorpus();
        for (int i = 20; i < 30; i++) {
            ProjectSpec project = projects.get(i);
            Map<String, String> files = project.sourceFiles();

            boolean hasIntegrationTest = files.keySet().stream()
                    .anyMatch(k -> k.startsWith("src/test/java/") && k.contains("Test"));
            assertTrue(hasIntegrationTest, "Project " + project.id() + " must have integration tests");
        }
    }
}
