package io.elmos.worker.security;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringSecurityCorsCsrfAdvancedModernizerTest {

    @Test
    @DisplayName("Modernize CSRF token repository with BREACH defense XorCsrfTokenRequestAttributeHandler")
    void testCsrfBreachDefenseModernization() {
        String source = "package com.example;\n"
                + "import org.springframework.security.config.annotation.web.builders.HttpSecurity;\n"
                + "import org.springframework.security.web.csrf.CookieCsrfTokenRepository;\n"
                + "public class SecConfig {\n"
                + "    public void config(HttpSecurity http) throws Exception {\n"
                + "        http.csrf().csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse());\n"
                + "    }\n"
                + "}";

        var result = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(source);

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertTrue(modernized.contains("XorCsrfTokenRequestAttributeHandler"));
        assertTrue(modernized.contains("csrfTokenRequestHandler(new XorCsrfTokenRequestAttributeHandler())"));
        assertTrue(modernized.contains("import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;"));
    }

    @Test
    @DisplayName("Modernize fluent .cors().and() to .cors(Customizer.withDefaults())")
    void testCorsCustomizerModernization() {
        String source = "package com.example;\n"
                + "import org.springframework.security.config.annotation.web.builders.HttpSecurity;\n"
                + "public class SecConfig {\n"
                + "    public void config(HttpSecurity http) throws Exception {\n"
                + "        http.cors().and().authorizeHttpRequests();\n"
                + "    }\n"
                + "}";

        var result = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(source);

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains(".cors().and()"));
        assertTrue(modernized.contains(".cors(Customizer.withDefaults())"));
        assertTrue(modernized.contains("import org.springframework.security.config.Customizer;"));
    }

    @Test
    @DisplayName("Harden CORS wildcard origin when credentials are enabled")
    void testCorsCredentialSafety() {
        String source = "package com.example;\n"
                + "import org.springframework.web.cors.CorsConfiguration;\n"
                + "import java.util.List;\n"
                + "public class CorsConfig {\n"
                + "    public CorsConfiguration config() {\n"
                + "        CorsConfiguration c = new CorsConfiguration();\n"
                + "        c.setAllowCredentials(true);\n"
                + "        c.setAllowedOrigins(List.of(\"*\"));\n"
                + "        return c;\n"
                + "    }\n"
                + "}";

        var result = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(source);

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains("setAllowedOrigins(List.of(\"*\"))"));
        assertTrue(modernized.contains("setAllowedOriginPatterns(List.of(\"*\"))"));
    }

    @Test
    @DisplayName("Modernize frameOptions sameOrigin to lambda HeadersConfigurer")
    void testHeadersLambdaModernization() {
        String source = "package com.example;\n"
                + "import org.springframework.security.config.annotation.web.builders.HttpSecurity;\n"
                + "public class SecConfig {\n"
                + "    public void config(HttpSecurity http) throws Exception {\n"
                + "        http.headers().frameOptions().sameOrigin();\n"
                + "    }\n"
                + "}";

        var result = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(source);

        assertTrue(result.modified());
        String modernized = result.rulesApplied().get(0);
        assertFalse(modernized.contains(".headers().frameOptions().sameOrigin()"));
        assertTrue(modernized.contains("HeadersConfigurer.FrameOptionsConfig::sameOrigin"));
    }

    @Test
    @DisplayName("Modernize CORS and CSRF across workspace on disk")
    void testWorkspaceCorsCsrfModernization(@TempDir Path tempDir) throws IOException {
        Path javaDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(javaDir);
        Files.writeString(javaDir.resolve("Sec.java"),
                "package com.example;\nimport org.springframework.security.config.annotation.web.builders.HttpSecurity;\npublic class Sec { void c(HttpSecurity h) throws Exception { h.cors().and(); } }");

        var result = SpringSecurityCorsCsrfAdvancedModernizer.modernize(tempDir);

        assertTrue(result.modified());
        String updated = Files.readString(javaDir.resolve("Sec.java"));
        assertTrue(updated.contains("cors(Customizer.withDefaults())"));
    }
}
