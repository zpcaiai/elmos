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
    @DisplayName("OpenRewriteCli: Correctly handles irrelevant code without modification")
    void testCliUnmodifiedOnIrrelevantCode() throws Exception {
        String code = """
                package com.example.util;
                public class StringHelper {
                    public static String trim(String s) { return s != null ? s.trim() : null; }
                }
                """;

        String inputJson = MAPPER.createObjectNode()
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
