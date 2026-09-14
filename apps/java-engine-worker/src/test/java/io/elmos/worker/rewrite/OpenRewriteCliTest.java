package io.elmos.worker.rewrite;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OpenRewriteCliTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Test
    @DisplayName("OpenRewriteCli: Successfully processes Spring Security modernization via JSON IPC")
    void testCliProcessesSecurityModernization() throws Exception {
        String legacyCode = """
                package com.example.security;

                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests().anyRequest().authenticated();
                    }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
                .put("action", "rewrite")
                .put("recipeFamily", "SPRING_SECURITY_6")
                .put("sourceCode", legacyCode)
                .toString();

        String outputJson = OpenRewriteCli.processJson(inputJson);
        assertNotNull(outputJson);

        JsonNode response = MAPPER.readTree(outputJson);
        assertEquals("SUCCESS", response.get("status").asText());
        assertTrue(response.get("modified").asBoolean());
        assertFalse(response.get("recipesApplied").isEmpty());

        String sourceCode = response.get("sourceCode").asText();
        assertFalse(sourceCode.contains("extends WebSecurityConfigurerAdapter"));
        assertTrue(sourceCode.contains("SecurityFilterChain filterChain(HttpSecurity http)"));
    }

    @Test
    @DisplayName("OpenRewriteCli: Successfully processes JUnit 5 modernization via JSON IPC")
    void testCliProcessesJunit5Modernization() throws Exception {
        String legacyTestCode = """
                package com.example.service;

                import org.junit.Test;
                import org.junit.Assert;

                public class OrderServiceTest {
                    @Test
                    public void testOrderTotal() {
                        Assert.assertEquals("Totals must match", 100, 100);
                        Assert.assertTrue("Must be valid", true);
                    }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
                .put("action", "rewrite")
                .put("recipeFamily", "JUNIT_5")
                .put("sourceCode", legacyTestCode)
                .toString();

        String outputJson = OpenRewriteCli.processJson(inputJson);
        JsonNode response = MAPPER.readTree(outputJson);

        assertEquals("SUCCESS", response.get("status").asText());
        assertTrue(response.get("modified").asBoolean());

        String sourceCode = response.get("sourceCode").asText();
        assertTrue(sourceCode.contains("import org.junit.jupiter.api.Test;"));
        assertTrue(sourceCode.contains("Assertions.assertEquals(100, 100, \"Totals must match\")"));
        assertTrue(sourceCode.contains("Assertions.assertTrue(true, \"Must be valid\")"));
    }

    @Test
    @DisplayName("OpenRewriteCli: Compiler-grade AST analysis for Transactional Self-Invocations (Zero False Positives)")
    void testCliAnalyzesTransactionalSelfInvocations() throws Exception {
        String code = """
                package com.example.service;

                import org.springframework.stereotype.Service;
                import org.springframework.transaction.annotation.Transactional;

                @Service
                public class PaymentService {

                    private ExternalGateway gateway;

                    public void processPayment(Long id) {
                        // External call on another bean: NOT a self-invocation
                        gateway.completeTx(id);

                        // Implicit this call: Self-invocation bypass!
                        completeTx(id);

                        // Explicit this call: Self-invocation bypass!
                        this.completeTx(id);
                    }

                    @Transactional
                    public void completeTx(Long id) {
                        // DB mutation
                    }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
                .put("action", "analyze")
                .put("analysisType", "TRANSACTIONAL_SELF_INVOCATION")
                .put("sourceCode", code)
                .toString();

        String outputJson = OpenRewriteCli.processJson(inputJson);
        JsonNode response = MAPPER.readTree(outputJson);

        assertEquals("SUCCESS", response.get("status").asText());
        assertEquals(2, response.get("findingsCount").asInt(), "Must detect exactly 2 self-invocations, zero false positives on gateway!");

        JsonNode findings = response.get("findings");
        assertEquals("SPRING_TX_SELF_INVOCATION", findings.get(0).get("ruleId").asText());
        assertEquals("CRITICAL", findings.get(0).get("severity").asText());
    }

    @Test
    @DisplayName("OpenRewriteCli: Compiler-grade AST analysis for Hibernate Lazy N+1 in loops")
    void testCliAnalyzesHibernateLazyNPlusOne() throws Exception {
        String code = """
                package com.example.service;

                import java.util.List;

                public class ReportService {
                    public void generateReport(List<Customer> customers) {
                        for (Customer c : customers) {
                            var orders = c.getOrders();
                        }
                    }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
                .put("action", "analyze")
                .put("analysisType", "HIBERNATE_LAZY_N_PLUS_ONE")
                .put("sourceCode", code)
                .toString();

        String outputJson = OpenRewriteCli.processJson(inputJson);
        JsonNode response = MAPPER.readTree(outputJson);

        assertEquals("SUCCESS", response.get("status").asText());
        assertEquals(1, response.get("findingsCount").asInt());
        assertEquals("HIBERNATE_LAZY_N_PLUS_ONE", response.get("findings").get(0).get("ruleId").asText());
    }

    @Test
    @DisplayName("OpenRewriteCli: Correctly handles irrelevant code without modification")
    void testCliUnmodifiedOnIrrelevantCode() throws Exception {
        String code = """
                package com.example.util;
                public class StringHelper {
                    public static String trim(String s) { return s != null ? s.trim() : null; }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
                .put("action", "rewrite")
                .put("recipeFamily", "SPRING_SECURITY_6")
                .put("sourceCode", code)
                .toString();

        String outputJson = OpenRewriteCli.processJson(inputJson);
        JsonNode response = MAPPER.readTree(outputJson);

        assertEquals("SUCCESS", response.get("status").asText());
        assertFalse(response.get("modified").asBoolean());
        assertTrue(response.get("recipesApplied").isEmpty());
    }
}
