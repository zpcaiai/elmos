package io.elmos.worker.validation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringSecurityAuditValidatorTest {

    @TempDir
    Path tempDir;

    private final SpringSecurityAuditValidator validator = new SpringSecurityAuditValidator();

    @Test
    void testDetectsLegacyWebSecurityConfigurerAdapter() throws IOException {
        Path javaFile = tempDir.resolve("LegacySecurity.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class LegacySecurity extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests().antMatchers("/admin/**").hasRole("ADMIN");
                    }
                }
                """);

        SpringSecurityAuditValidator.SecurityAuditReport report = validator.auditProject(tempDir);
        assertFalse(report.isCompliant());
        assertTrue(report.criticalViolations() >= 1);
        assertTrue(report.violations().stream().anyMatch(v -> "SEC-001".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "SEC-002".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "SEC-003".equals(v.ruleId())));
    }

    @Test
    void testCompliantModernSecurityConfig() throws IOException {
        Path javaFile = tempDir.resolve("ModernSecurity.java");
        Files.writeString(javaFile, """
                package com.example;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                @EnableMethodSecurity
                public class ModernSecurity {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth
                                .requestMatchers("/public/**").permitAll()
                                .anyRequest().authenticated());
                        return http.build();
                    }
                }
                """);

        SpringSecurityAuditValidator.SecurityAuditReport report = validator.auditProject(tempDir);
        assertTrue(report.isCompliant());
        assertEquals(0, report.criticalViolations());
        assertEquals(0, report.highViolations());
        assertEquals(100.0, report.complianceScore());
    }
}
