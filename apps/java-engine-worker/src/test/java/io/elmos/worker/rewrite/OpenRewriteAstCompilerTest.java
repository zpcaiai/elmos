package io.elmos.worker.rewrite;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Validates compiler-grade OpenRewrite AST transformations across Spring Security,
 * JPA/Hibernate 6, and Spring Cloud Netflix OSS modernizations.
 */
class OpenRewriteAstCompilerTest {

    @Test
    @DisplayName("OpenRewrite AST: Modernizes WebSecurityConfigurerAdapter and authorizeRequests to Spring Security 6")
    void testOpenRewriteSecurityModernization() {
        String legacyCode = """
                package com.example.security;

                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @EnableGlobalMethodSecurity(prePostEnabled = true)
                public class SecurityConfig extends WebSecurityConfigurerAdapter {

                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/public/**").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """;

        var result = OpenRewriteAstCompiler.modernizeSecurity(legacyCode);
        assertNotNull(result);
        assertTrue(result.modified(), "Source must be modified by OpenRewrite AST recipe pipeline");
        assertFalse(result.recipesApplied().isEmpty(), "Applied recipes list must not be empty");

        String updated = result.source();
        // Extends clause removed via typed AST ClassDeclaration transformation
        assertFalse(updated.contains("extends WebSecurityConfigurerAdapter"));
        // Annotation modernized via typed AST Annotation transformation
        assertTrue(updated.contains("@EnableMethodSecurity"));
        assertFalse(updated.contains("@EnableGlobalMethodSecurity"));
        // Method modernized to filterChain bean
        assertTrue(updated.contains("SecurityFilterChain filterChain(HttpSecurity http)"));
        // Invocations modernized via typed AST MethodInvocation transformation
        assertTrue(updated.contains("authorizeHttpRequests"));
        assertTrue(updated.contains("requestMatchers"));
    }

    @Test
    @DisplayName("OpenRewrite AST: Modernizes Hibernate legacy Criteria to Jakarta Persistence CriteriaBuilder")
    void testOpenRewriteJpaHibernateModernization() {
        String legacyCode = """
                package com.example.dao;

                import org.hibernate.Criteria;
                import org.hibernate.criterion.Restrictions;

                public class UserDao {
                    public void query() {
                        Criteria criteria = null;
                    }
                }
                """;

        var result = OpenRewriteAstCompiler.modernizeJpaHibernate(legacyCode);
        assertNotNull(result);
        assertTrue(result.modified());
        assertFalse(result.recipesApplied().isEmpty());

        String updated = result.source();
        assertFalse(updated.contains("import org.hibernate.Criteria;"));
        assertTrue(updated.contains("CriteriaQuery"));
    }

    @Test
    @DisplayName("OpenRewrite AST: Returns unmodified result cleanly if no applicable recipes match")
    void testUnmodifiedOnIrrelevantSource() {
        String code = """
                package com.example.util;

                public class MathUtils {
                    public static int add(int a, int b) {
                        return a + b;
                    }
                }
                """;

        var result = OpenRewriteAstCompiler.modernizeSecurity(code);
        assertFalse(result.modified());
        assertTrue(result.recipesApplied().isEmpty());
        assertTrue(result.source().contains("MathUtils"));
    }
}
