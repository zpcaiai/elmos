package io.elmos.worker.rulebook;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SpringModernizationArchitectureRulebookEnforcerTest {

    @Test
    @DisplayName("Detect legacy security violations and enforce compliance rules")
    void testSecurityRuleEnforcement() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/SecurityConfig.java", """
                package com.example;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/api/admin/**").hasRole("ADMIN")
                            .anyRequest().authenticated();
                    }
                }
                """);

        var report = SpringModernizationArchitectureRulebookEnforcer.enforce("test-sec-proj", files);
        assertNotNull(report);
        assertEquals(1, report.totalFilesScanned());
        assertTrue(report.totalViolations() >= 3);
        assertTrue(report.hasBlockers() || report.hasCriticals());
        assertFalse(report.isCompliant());

        // Check specific rule IDs
        var ruleIds = report.violations().stream().map(SpringModernizationArchitectureRulebookEnforcer.RuleViolation::ruleId).toList();
        assertTrue(ruleIds.contains("SEC-001"), "Must detect WebSecurityConfigurerAdapter");
        assertTrue(ruleIds.contains("SEC-002"), "Must detect authorizeRequests");
        assertTrue(ruleIds.contains("SEC-003"), "Must detect antMatchers");
    }

    @Test
    @DisplayName("Detect JPA/Hibernate 6 and Spring Cloud violations")
    void testJpaAndCloudRuleEnforcement() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/OrderEntity.java", """
                package com.example;
                import javax.persistence.Entity;
                import javax.persistence.Id;
                import org.hibernate.annotations.TypeDef;
                import org.hibernate.annotations.Type;

                @Entity
                @TypeDef(name = "json", typeClass = String.class)
                public class OrderEntity {
                    @Id
                    private Long id;
                    @Type(type = "json")
                    private String payload;
                }
                """);
        files.put("src/main/java/com/example/OrderService.java", """
                package com.example;
                import org.springframework.cloud.netflix.hystrix.EnableCircuitBreaker;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @EnableCircuitBreaker
                public class OrderService {
                    @HystrixCommand(fallbackMethod = "fallback")
                    public String execute() { return "ok"; }
                }
                """);
        files.put("src/main/resources/bootstrap.yml", """
                spring:
                  cloud:
                    config:
                      uri: http://localhost:8888
                """);

        var report = SpringModernizationArchitectureRulebookEnforcer.enforce("test-jpa-cloud-proj", files);
        assertNotNull(report);
        assertEquals(3, report.totalFilesScanned());
        assertTrue(report.totalViolations() >= 5);

        var ruleIds = report.violations().stream().map(SpringModernizationArchitectureRulebookEnforcer.RuleViolation::ruleId).toList();
        assertTrue(ruleIds.contains("JPA-001"), "Must detect javax.persistence");
        assertTrue(ruleIds.contains("JPA-002"), "Must detect @TypeDef");
        assertTrue(ruleIds.contains("JPA-003"), "Must detect @Type(type = 'json')");
        assertTrue(ruleIds.contains("CLD-001"), "Must detect @EnableCircuitBreaker");
        assertTrue(ruleIds.contains("CLD-002"), "Must detect @HystrixCommand");
        assertTrue(ruleIds.contains("CLD-006"), "Must detect bootstrap.yml");
    }

    @Test
    @DisplayName("Detect architectural layering violations and transactional antipatterns")
    void testArchitecturalLayeringEnforcement() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/controller/UserController.java", """
                package com.example.controller;
                import org.springframework.web.bind.annotation.RestController;
                import org.springframework.transaction.annotation.Transactional;
                import org.springframework.beans.factory.annotation.Autowired;
                import com.example.repository.UserRepository;

                @RestController
                @Transactional
                public class UserController {
                    @Autowired
                    private UserRepository userRepository;
                }
                """);

        var report = SpringModernizationArchitectureRulebookEnforcer.enforce("test-arch-proj", files);
        assertNotNull(report);

        var ruleIds = report.violations().stream().map(SpringModernizationArchitectureRulebookEnforcer.RuleViolation::ruleId).toList();
        assertTrue(ruleIds.contains("COR-010"), "Must detect Controller bypassing Service to directly inject Repository");
        assertTrue(ruleIds.contains("COR-011"), "Must detect @Transactional placed on Controller");
    }

    @Test
    @DisplayName("Verify clean modernized project achieves 100% compliance with zero violations")
    void testCleanModernizedProjectEnforcement() {
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
        files.put("src/main/resources/application.yml", """
                spring:
                  config:
                    import: "optional:configserver:http://localhost:8888"
                  application:
                    name: clean-modern-service
                """);

        var report = SpringModernizationArchitectureRulebookEnforcer.enforce("clean-modern-proj", files);
        assertNotNull(report);
        assertEquals(3, report.totalFilesScanned());
        assertEquals(0, report.totalViolations());
        assertEquals(0, report.blockerCount());
        assertEquals(0, report.criticalCount());
        assertEquals(100.0, report.complianceScore(), 0.01);
        assertTrue(report.isCompliant());

        // Validate SARIF generation
        String sarif = SpringModernizationArchitectureRulebookEnforcer.toSarifJson(report);
        assertNotNull(sarif);
        assertTrue(sarif.contains("\"version\": \"2.1.0\""));
        assertTrue(sarif.contains("\"Elmos Spring Modernization Rulebook Enforcer\""));

        // Validate Markdown report generation
        String md = SpringModernizationArchitectureRulebookEnforcer.toMarkdownReport(report);
        assertNotNull(md);
        assertTrue(md.contains("Clean Architecture Confirmed: Zero rulebook violations detected!"));
        assertTrue(md.contains("✅ **COMPLIANT**"));
    }

    @Test
    @DisplayName("Verify SARIF 2.1.0 output formatting with detected violations")
    void testSarifOutputWithViolations() {
        Map<String, String> files = new HashMap<>();
        files.put("src/main/java/com/example/LegacyServlet.java", """
                package com.example;
                import javax.servlet.http.HttpServletRequest;

                public class LegacyServlet {
                    public void handle(HttpServletRequest req) {}
                }
                """);

        var report = SpringModernizationArchitectureRulebookEnforcer.enforce("sarif-test-proj", files);
        String sarif = SpringModernizationArchitectureRulebookEnforcer.toSarifJson(report);

        assertNotNull(sarif);
        assertTrue(sarif.contains("\"ruleId\": \"COR-001\""));
        assertTrue(sarif.contains("\"level\": \"warning\""));
        assertTrue(sarif.contains("\"artifactLocation\""));
        assertTrue(sarif.contains("LegacyServlet.java"));
        assertTrue(sarif.contains("\"remediation\""));
    }
}
