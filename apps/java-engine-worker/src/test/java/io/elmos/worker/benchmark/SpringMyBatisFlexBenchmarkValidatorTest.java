package io.elmos.worker.benchmark;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringMyBatisFlexBenchmarkValidatorTest {

    @Test
    @DisplayName("Evaluate real-world MyBatis-Flex repository across Links 2 to 7")
    void testMyBatisFlexModernizationEvaluation() {
        Path repoPath = findMyBatisFlexRoot();
        org.junit.jupiter.api.Assumptions.assumeTrue(repoPath != null && Files.isDirectory(repoPath),
                "fixtures/real-world/mybatis-flex fixture not present; skipping benchmark evaluation");
        assertNotNull(repoPath, "Must locate fixtures/real-world/mybatis-flex");
        assertTrue(Files.isDirectory(repoPath), "MyBatis-Flex fixture directory must exist");

        var report = SpringMyBatisFlexBenchmarkValidator.evaluate(repoPath);
        assertNotNull(report);

        System.out.println("=== MyBatis-Flex Real-World Benchmark Logs ===");
        for (String log : report.validationLogs()) {
            System.out.println(log);
        }

        assertTrue(report.allLinksPassed(), "All 6 links (2 to 7) must pass verification");

        // Link 2 assertions: Multi-module reactor
        assertTrue(report.totalModulesDiscovered() >= 10, "Must discover at least 10 modules in reactor DAG");
        assertTrue(report.moduleArtifactIds().contains("mybatis-flex-spring-boot-starter"));
        assertTrue(report.moduleArtifactIds().contains("mybatis-flex-core"));
        assertTrue(report.link2ReactorVerdict().isMultiModule());
        assertTrue(report.link2ReactorVerdict().allSubmodulesExist());

        // Link 3 assertions: AST & Ecosystem
        assertTrue(report.link3AutoConfigurationImportsSynthesized(), "AutoConfiguration.imports must be present");

        // Link 4 assertions: Private Artifact Mock Shims
        assertTrue(report.link4ShimsGeneratedCount() >= 2, "Must generate mock shims for unresolvable dependencies");
        assertTrue(report.link4ShimHygieneVerdict().isCompliant(), "Shim hygiene must be 100% compliant with @ConditionalOnMissingBean");

        // Link 5 assertions: Runtime readiness
        assertTrue(report.link5RuntimeReadinessPassed(), "Runtime test harness readiness must pass");

        // Link 6 assertions: Async messaging differential comparison
        assertTrue(report.link6MessagingVerdict().isEquivalent(), "RocketMQ/Kafka shadow dual-write events must be equivalent");
        assertEquals(100.0, report.link6MessagingVerdict().equivalenceScore(), 0.01);
        assertEquals(0, report.link6MessagingVerdict().mismatchedCount());

        // Link 7 assertions: Enterprise Audit Suite
        assertTrue(report.overallMaturityScore() >= 95.0, "Overall maturity score must exceed 95.0%");

        // Print sample logs
        System.out.println("=== MyBatis-Flex Real-World Benchmark Logs ===");
        for (String log : report.validationLogs()) {
            System.out.println(log);
        }
    }

    private static Path findMyBatisFlexRoot() {
        Path direct = Path.of("fixtures/real-world/mybatis-flex");
        if (Files.isDirectory(direct)) return direct.toAbsolutePath().normalize();

        Path parent = Path.of("../../fixtures/real-world/mybatis-flex");
        if (Files.isDirectory(parent)) return parent.toAbsolutePath().normalize();

        Path workspace = Path.of("/Users/stephen/DevProjects/AIProjects/elmos/fixtures/real-world/mybatis-flex");
        if (Files.isDirectory(workspace)) return workspace.toAbsolutePath().normalize();

        return null;
    }
}
