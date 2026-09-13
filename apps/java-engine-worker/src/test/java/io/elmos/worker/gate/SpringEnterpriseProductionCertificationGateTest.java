package io.elmos.worker.gate;

import io.elmos.worker.benchmark.SpringEnterpriseFullCorpusBenchmarkValidator;
import io.elmos.worker.rulebook.SpringModernizationArchitectureRulebookEnforcer;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SpringEnterpriseProductionCertificationGateTest {

    @Test
    @DisplayName("Evaluate full 30-project corpus and grant E5 production certification")
    void testFullCorpusCertificationGateEvaluation() {
        var benchmarkReport = SpringEnterpriseFullCorpusBenchmarkValidator.executeFullCorpusBenchmark();
        assertNotNull(benchmarkReport);

        var gateVerdict = SpringEnterpriseProductionCertificationGate.evaluate(benchmarkReport);
        assertNotNull(gateVerdict);
        assertEquals(SpringEnterpriseProductionCertificationGate.GateStatus.PASSED, gateVerdict.overallStatus());
        assertTrue(gateVerdict.isCertifiedForProduction());
        assertEquals("E5_CERTIFIED_PRODUCTION_READY", gateVerdict.certificationTier());
        assertEquals(10, gateVerdict.totalCriteriaEvaluated(), "Must evaluate all 10 industrial gate criteria");
        assertEquals(10, gateVerdict.criteriaPassedCount(), "All 10 criteria must pass");
        assertEquals(100.0, gateVerdict.criteriaPassRatePercentage(), 0.001);
        assertTrue(gateVerdict.isAllMandatoryCriteriaMet());
        assertNotNull(gateVerdict.cryptographicVerificationSeal());
        assertTrue(gateVerdict.cryptographicVerificationSeal().startsWith("SEAL-SHA256-"));
        assertEquals(12 + 64, gateVerdict.cryptographicVerificationSeal().length(), "Seal must contain full 64-hex SHA-256 digest");

        // Verify Markdown certificate output
        String cert = SpringEnterpriseProductionCertificationGate.toMarkdownCertificate(gateVerdict);
        assertNotNull(cert);
        assertTrue(cert.contains("Official Industrial Production Certification Certificate"));
        assertTrue(cert.contains("100% PRODUCTION READY (PASSED)"));
        assertTrue(cert.contains("E5_CERTIFIED_PRODUCTION_READY"));
        assertTrue(cert.contains("CRIT-01"));
        assertTrue(cert.contains("CRIT-10"));
    }

    @Test
    @DisplayName("Evaluate single project and ensure production certification criteria checks")
    void testSingleProjectCertificationGateEvaluation() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/SecurityConfig.java", """
                package com.example;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                public class SecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
                        return http.build();
                    }
                }
                """);

        var req = new SpringModernizationEndToEndWorkflowEngine.WorkflowRequest(
                "project-single-cert", "Single Cert Project", "2.7.18", "11", "4.1.0", "21", files
        );
        var wr = SpringModernizationEndToEndWorkflowEngine.execute(req);
        var enf = SpringModernizationArchitectureRulebookEnforcer.enforce(req.projectId(), wr.modernizedFiles());

        var verdict = SpringEnterpriseProductionCertificationGate.evaluateSingleProject(wr, enf);
        assertNotNull(verdict);
        assertTrue(verdict.isCertifiedForProduction());
        assertEquals(SpringEnterpriseProductionCertificationGate.GateStatus.PASSED, verdict.overallStatus());
        assertEquals("E5_CERTIFIED_PRODUCTION_READY", verdict.certificationTier());
        assertTrue(verdict.blockers().isEmpty());
    }
}
