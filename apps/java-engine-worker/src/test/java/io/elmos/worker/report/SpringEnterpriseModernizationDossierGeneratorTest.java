package io.elmos.worker.report;

import io.elmos.worker.rulebook.SpringModernizationArchitectureRulebookEnforcer;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SpringEnterpriseModernizationDossierGeneratorTest {

    @Test
    @DisplayName("Generate, sign, and verify tamper-evident enterprise modernization dossier")
    void testDossierGenerationAndVerification() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/SecurityConfig.java", """
                package com.example;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;
                import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

                @Configuration
                @EnableMethodSecurity
                public class SecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth
                                .requestMatchers("/public/**").permitAll()
                                .anyRequest().authenticated()
                        );
                        return http.build();
                    }
                }
                """);
        files.put("src/main/java/com/example/OrderEntity.java", """
                package com.example;
                import jakarta.persistence.Entity;
                import jakarta.persistence.Id;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;

                @Entity
                public class OrderEntity {
                    @Id
                    private Long id;
                    @JdbcTypeCode(SqlTypes.JSON)
                    private String payload;
                }
                """);

        var req = new SpringModernizationEndToEndWorkflowEngine.WorkflowRequest(
                "project-01-ecommerce-mall",
                "E-Commerce Mall",
                "2.7.18",
                "11",
                "4.1.0",
                "21",
                files
        );

        var workflowResult = SpringModernizationEndToEndWorkflowEngine.execute(req);
        var enforcementReport = SpringModernizationArchitectureRulebookEnforcer.enforce(req.projectId(), workflowResult.modernizedFiles());

        var dossier = SpringEnterpriseModernizationDossierGenerator.generate(
                workflowResult,
                enforcementReport,
                "Global Financial Services Ltd."
        );

        assertNotNull(dossier);
        assertNotNull(dossier.metadata().dossierId());
        assertEquals("project-01-ecommerce-mall", dossier.metadata().projectId());
        assertEquals("Global Financial Services Ltd.", dossier.metadata().organization());
        assertTrue(dossier.qualitySection().isPassed());
        assertTrue(dossier.qualitySection().isProductionReady());
        assertEquals("APPROVED_FOR_PRODUCTION_CUTOVER", dossier.qualitySection().gateDecision());

        // Verify tamper evidence
        assertTrue(SpringEnterpriseModernizationDossierGenerator.verifyTamperEvidence(dossier),
                "Dossier must pass cryptographic tamper evidence validation");

        // Verify Markdown rendering
        String md = SpringEnterpriseModernizationDossierGenerator.toMarkdown(dossier);
        assertNotNull(md);
        assertTrue(md.contains("Enterprise Modernization & Cryptographic Certification Dossier"));
        assertTrue(md.contains("CERTIFIED PRODUCTION READY (100% GREEN)"));
        assertTrue(md.contains("Global Financial Services Ltd."));
        assertTrue(md.contains("SecurityConfig.java"));

        // Verify JSON rendering
        String json = SpringEnterpriseModernizationDossierGenerator.toJson(dossier);
        assertNotNull(json);
        assertTrue(json.contains("\"dossierId\""));
        assertTrue(json.contains("\"digitalSignatureDigest\""));
        assertTrue(json.contains("\"auditMaturityScore\": 100.0"));
        assertTrue(json.contains("\"isProductionReady\": true"));
    }

    @Test
    @DisplayName("Detect tampering when quality metrics or payload are forged")
    void testTamperDetection() {
        Map<String, String> files = Map.of("src/main/java/Dummy.java", "public class Dummy {}");
        var req = new SpringModernizationEndToEndWorkflowEngine.WorkflowRequest(
                "tamper-test", "Tamper Test", "2.7.18", "11", "4.1.0", "21", files
        );
        var wr = SpringModernizationEndToEndWorkflowEngine.execute(req);
        var enf = SpringModernizationArchitectureRulebookEnforcer.enforce("tamper-test", wr.modernizedFiles());
        var dossier = SpringEnterpriseModernizationDossierGenerator.generate(wr, enf, "Org");

        // Forge quality section with different audit score
        var forgedQuality = new SpringEnterpriseModernizationDossierGenerator.QualityVerificationSection(
                50.0, false, 5, false, 10, false, "E0", "REJECTED"
        );
        var forgedDossier = new SpringEnterpriseModernizationDossierGenerator.EnterpriseModernizationDossier(
                dossier.metadata(),
                dossier.artifactLedger(),
                dossier.metrics(),
                forgedQuality,
                dossier.digitalSignatureDigest() // Kept original signature
        );

        assertFalse(SpringEnterpriseModernizationDossierGenerator.verifyTamperEvidence(forgedDossier),
                "Tampered dossier must be rejected by tamper evidence verification");
    }
}
