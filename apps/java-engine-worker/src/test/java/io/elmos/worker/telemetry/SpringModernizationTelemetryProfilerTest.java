package io.elmos.worker.telemetry;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SpringModernizationTelemetryProfilerTest {

    @Test
    @DisplayName("Verify end-to-end profiler execution lifecycle and metrics capture")
    void testFullPipelineProfilerLifecycle() {
        var profiler = SpringModernizationTelemetryProfiler.start(
                "enterprise-banking-core",
                "2.7.18",
                "4.1.0",
                "1.8"
        );

        // Simulate Phase 1: Discovery
        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.DISCOVERY);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.DISCOVERY);

        // Simulate Phase 2: Recipe Execution with rules
        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.RECIPE_EXECUTION);
        profiler.recordRuleApplication("SEC-001", 15_000_000L, true, 4, 120, 85);
        profiler.recordRuleApplication("JPA-001", 8_000_000L, true, 12, 45, 45);
        profiler.recordRuleApplication("CLD-001", 12_000_000L, true, 2, 30, 20);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.RECIPE_EXECUTION);

        // Simulate Phase 3: Automated Repair
        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.AUTOMATED_REPAIR);
        profiler.recordRuleApplication("XML-001", 20_000_000L, true, 1, 95, 110);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.AUTOMATED_REPAIR);

        // Simulate Phase 4: Target Build
        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.TARGET_BUILD);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.TARGET_BUILD);

        // Simulate Phase 5: Test Execution
        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.TEST_EXECUTION);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.TEST_EXECUTION);

        // Finish profile
        var profile = profiler.finish(250, 19, 15000, 15800);

        assertNotNull(profile.runId());
        assertEquals("enterprise-banking-core", profile.repositoryName());
        assertEquals("2.7.18", profile.sourceBootVersion());
        assertEquals("4.1.0", profile.targetBootVersion());
        assertEquals("1.8", profile.javaVersion());
        assertEquals(250, profile.totalFilesScanned());
        assertEquals(19, profile.totalFilesModified());
        assertEquals(15000, profile.totalSourceLoc());
        assertEquals(15800, profile.totalTargetLoc());
        assertTrue(profile.totalDurationMillis() >= 0);
        assertTrue(profile.throughputLocPerSecond() > 0);
        assertEquals(5, profile.phases().size());
        assertEquals(4, profile.ruleMetrics().size());
        assertTrue(profile.errors().isEmpty());
        assertTrue(profile.peakMemoryUsageBytes() > 0);

        // Check specific rule
        var sec01 = profile.ruleMetrics().get("SEC-001");
        assertNotNull(sec01);
        assertEquals(1, sec01.applicationCount());
        assertEquals(4, sec01.filesModifiedCount());
        assertEquals(120, sec01.linesAddedCount());
        assertEquals(85, sec01.linesDeletedCount());
    }

    @Test
    @DisplayName("Verify JSON and Prometheus export formatting")
    void testExporters() {
        var profiler = SpringModernizationTelemetryProfiler.start(
                "cloud-gateway-service",
                "2.6.4",
                "4.1.0",
                "11"
        );

        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.TARGET_BUILD);
        profiler.recordRuleApplication("CLD-002", 50_000_000L, true, 3, 200, 180);
        profiler.endPhaseSuccess(SpringModernizationTelemetryProfiler.TelemetryPhase.TARGET_BUILD);

        var profile = profiler.finish(80, 5, 4500, 4700);

        String json = profiler.exportToJson(profile);
        assertNotNull(json);
        assertTrue(json.contains("\"repositoryName\": \"cloud-gateway-service\""));
        assertTrue(json.contains("\"targetBootVersion\": \"4.1.0\""));
        assertTrue(json.contains("\"totalFilesScanned\": 80"));

        String prometheus = profiler.exportToPrometheusMetrics(profile);
        assertNotNull(prometheus);
        assertTrue(prometheus.contains("spring_modernization_duration_seconds"));
        assertTrue(prometheus.contains("spring_modernization_throughput_loc_per_sec"));
        assertTrue(prometheus.contains("spring_modernization_rules_applied_total"));
        assertTrue(prometheus.contains("rule=\"CLD-002\""));

        String summary = profiler.generateExecutiveSummaryMarkdown(profile);
        assertNotNull(summary);
        assertTrue(summary.contains("# Modernization Run Executive Telemetry Summary"));
        assertTrue(summary.contains("✅ **VERIFIED 100% PRODUCTION READY & GREEN**"));
    }

    @Test
    @DisplayName("Verify error recording and failed status propagation")
    void testErrorRecording() {
        var profiler = SpringModernizationTelemetryProfiler.start(
                "legacy-cms-app",
                "2.2.0.RELEASE",
                "4.1.0",
                "1.8"
        );

        profiler.startPhase(SpringModernizationTelemetryProfiler.TelemetryPhase.TEST_EXECUTION);
        profiler.endPhaseFailure(SpringModernizationTelemetryProfiler.TelemetryPhase.TEST_EXECUTION, "Flaky integration timeout");

        var profile = profiler.finish(50, 2, 2000, 2050);

        assertEquals(1, profile.errors().size());
        assertTrue(profile.errors().get(0).contains("Flaky integration timeout"));

        String summary = profiler.generateExecutiveSummaryMarkdown(profile);
        assertTrue(summary.contains("⚠️ **COMPLETED WITH REVIEW ADVISORIES**"));
        assertTrue(summary.contains("Flaky integration timeout"));
    }
}
