package io.elmos.worker.benchmark;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringEnterpriseFullCorpusBenchmarkValidatorTest {

    @Test
    @DisplayName("Execute full 30-project corpus benchmark and verify 100% green rate")
    void testFullCorpusBenchmarkExecution() {
        var report = SpringEnterpriseFullCorpusBenchmarkValidator.executeFullCorpusBenchmark();

        assertNotNull(report);
        assertEquals(30, report.totalProjectsEvaluated(), "Must evaluate all 30 projects");
        assertEquals(30, report.totalGreenProjects(), "All 30 projects must achieve green status");
        assertEquals(100.0, report.overallGreenRatePercentage(), 0.001, "Green rate must be 100.0%");
        assertEquals(100.0, report.averageAuditScore(), 0.01, "Average audit score must be 100.0%");
        assertTrue(report.totalRulesAppliedAcrossCorpus() >= 30, "Rules applied across corpus must be non-zero");
        assertTrue(report.totalTargetLoc() > 0, "Target LOC must be positive");
        assertTrue(report.allProjectsFullyCertified(), "All projects must be fully certified");
        assertTrue(report.isProductionGrade(), "Benchmark suite must be production grade");

        // Verify Domain summaries
        assertNotNull(report.domainSummaries());
        assertEquals(5, report.domainSummaries().size(), "Must cover all 5 domain categories");
        for (var ds : report.domainSummaries().values()) {
            assertEquals(6, ds.totalProjects(), "Each domain must have 6 projects");
            assertEquals(6, ds.greenProjects(), "Each domain must have 6 green projects");
            assertEquals(100.0, ds.greenRatePercentage(), 0.001);
            assertEquals(100.0, ds.averageAuditScore(), 0.01);
        }

        // Verify Markdown scorecard generation
        String scorecard = SpringEnterpriseFullCorpusBenchmarkValidator.generateMarkdownScorecard(report);
        assertNotNull(scorecard);
        assertTrue(scorecard.contains("# 30 Open Source Complex Projects Modernization Benchmark Scorecard"));
        assertTrue(scorecard.contains("100% GREEN (ALL 30 CERTIFIED)"));
        assertTrue(scorecard.contains("project-01-ecommerce-mall"));
        assertTrue(scorecard.contains("project-30-spring-cloud-full-suite"));
    }
}
