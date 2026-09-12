package io.elmos.worker.rulebook;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class SpringModernizationRulebookCatalogTest {

    @Test
    @DisplayName("Verify exactly 150 enterprise modernization rules are registered")
    void testTotalRulesCount() {
        List<SpringModernizationRulebookCatalog.ModernizationRule> rules =
                SpringModernizationRulebookCatalog.getAllRules();

        assertEquals(150, rules.size(), "Catalog must contain exactly 150 registered rules");
    }

    @Test
    @DisplayName("Verify all 6 enterprise modernization categories have expected counts")
    void testCategoryDistribution() {
        var stats = SpringModernizationRulebookCatalog.getSummaryStatistics();

        assertEquals(150, stats.totalRules());
        assertTrue(stats.totalEffortHours() > 300, "Total effort hours must reflect realistic enterprise scope");

        assertEquals(30, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.SECURITY));
        assertEquals(30, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.JPA_HIBERNATE));
        assertEquals(30, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.SPRING_CLOUD));
        assertEquals(25, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.XML_JAVACONFIG));
        assertEquals(20, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.CORE_FRAMEWORK));
        assertEquals(15, stats.countByCategory().get(SpringModernizationRulebookCatalog.RuleCategory.ACTUATOR_OBSERVABILITY));
    }

    @Test
    @DisplayName("Verify rule lookup by identifier across all domains")
    void testLookupById() {
        Optional<SpringModernizationRulebookCatalog.ModernizationRule> sec01 =
                SpringModernizationRulebookCatalog.getRule("SEC-001");
        assertTrue(sec01.isPresent());
        assertEquals("WebSecurityConfigurerAdapter Deprecation Removal", sec01.get().name());
        assertEquals(SpringModernizationRulebookCatalog.RuleSeverity.BLOCKER, sec01.get().severity());

        Optional<SpringModernizationRulebookCatalog.ModernizationRule> jpa01 =
                SpringModernizationRulebookCatalog.getRule("JPA-001");
        assertTrue(jpa01.isPresent());
        assertEquals("javax.persistence to jakarta.persistence Namespace Migration", jpa01.get().name());

        Optional<SpringModernizationRulebookCatalog.ModernizationRule> cld01 =
                SpringModernizationRulebookCatalog.getRule("CLD-001");
        assertTrue(cld01.isPresent());
        assertEquals("Netflix Ribbon to Spring Cloud LoadBalancer Migration", cld01.get().name());

        Optional<SpringModernizationRulebookCatalog.ModernizationRule> xml01 =
                SpringModernizationRulebookCatalog.getRule("XML-001");
        assertTrue(xml01.isPresent());
        assertEquals("Legacy <beans> Root to @Configuration Class Migration", xml01.get().name());

        Optional<SpringModernizationRulebookCatalog.ModernizationRule> cor01 =
                SpringModernizationRulebookCatalog.getRule("COR-001");
        assertTrue(cor01.isPresent());

        Optional<SpringModernizationRulebookCatalog.ModernizationRule> act01 =
                SpringModernizationRulebookCatalog.getRule("ACT-001");
        assertTrue(act01.isPresent());
    }

    @Test
    @DisplayName("Verify rule severity filtering")
    void testSeverityFiltering() {
        List<SpringModernizationRulebookCatalog.ModernizationRule> blockers =
                SpringModernizationRulebookCatalog.findBySeverity(SpringModernizationRulebookCatalog.RuleSeverity.BLOCKER);
        assertFalse(blockers.isEmpty(), "Blocker rules must exist");
        for (var b : blockers) {
            assertEquals(SpringModernizationRulebookCatalog.RuleSeverity.BLOCKER, b.severity());
        }

        List<SpringModernizationRulebookCatalog.ModernizationRule> criticals =
                SpringModernizationRulebookCatalog.findBySeverity(SpringModernizationRulebookCatalog.RuleSeverity.CRITICAL);
        assertFalse(criticals.isEmpty(), "Critical rules must exist");
    }

    @Test
    @DisplayName("Verify source code pattern analysis against legacy enterprise code")
    void testAnalyzeSourceCode() {
        String legacyCode = """
                package com.legacy.app;

                import javax.persistence.*;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;

                @RibbonClient(name = "order-service")
                public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {
                    @Type(type = "json")
                    private String payload;
                }
                """;

        List<SpringModernizationRulebookCatalog.ModernizationRule> matched =
                SpringModernizationRulebookCatalog.analyzeSourceCode(legacyCode);

        assertFalse(matched.isEmpty(), "Should match legacy patterns");
        List<String> ids = matched.stream().map(SpringModernizationRulebookCatalog.ModernizationRule::ruleId).toList();
        assertTrue(ids.contains("SEC-001"), "Must match SEC-001 extends WebSecurityConfigurerAdapter");
        assertTrue(ids.contains("JPA-001"), "Must match JPA-001 import javax.persistence.*");
        assertTrue(ids.contains("JPA-002"), "Must match JPA-002 @Type(type = \"json\")");
        assertTrue(ids.contains("CLD-001"), "Must match CLD-001 @RibbonClient");
    }

    @Test
    @DisplayName("Verify keyword search functionality")
    void testKeywordSearch() {
        List<SpringModernizationRulebookCatalog.ModernizationRule> gatewayRules =
                SpringModernizationRulebookCatalog.search("gateway");
        assertFalse(gatewayRules.isEmpty(), "Should find gateway related rules");

        List<SpringModernizationRulebookCatalog.ModernizationRule> lambdaRules =
                SpringModernizationRulebookCatalog.search("lambda");
        assertFalse(lambdaRules.isEmpty(), "Should find lambda DSL rules");
    }

    @Test
    @DisplayName("Verify markdown documentation export")
    void testGenerateMarkdownCatalog() {
        String markdown = SpringModernizationRulebookCatalog.generateMarkdownCatalog();
        assertNotNull(markdown);
        assertTrue(markdown.contains("Total Rules: **150**"));
        assertTrue(markdown.contains("## Category Breakdown"));
        assertTrue(markdown.contains("### [SEC-001]"));
        assertTrue(markdown.contains("### [JPA-001]"));
        assertTrue(markdown.contains("### [CLD-001]"));
        assertTrue(markdown.contains("### [XML-001]"));
        assertTrue(markdown.contains("### [COR-001]"));
        assertTrue(markdown.contains("### [ACT-001]"));
    }
}
