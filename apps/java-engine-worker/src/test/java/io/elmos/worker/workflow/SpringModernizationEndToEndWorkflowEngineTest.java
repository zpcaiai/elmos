package io.elmos.worker.workflow;

import io.elmos.worker.corpus.SpringThirtyOpenSourceProjectsCorpus;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringModernizationEndToEndWorkflowEngineTest {

    @Test
    @DisplayName("End-to-End Modernization across all 4 enterprise domains on complex legacy project")
    void testFullModernizationOnLegacyEnterpriseProject() {
        Map<String, String> sourceFiles = new LinkedHashMap<>();

        // 1. POM with Boot 2.3.12.RELEASE and Java 8
        sourceFiles.put("pom.xml", """
                <?xml version="1.0" encoding="UTF-8"?>
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                    <modelVersion>4.0.0</modelVersion>
                    <parent>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-parent</artifactId>
                        <version>2.3.12.RELEASE</version>
                    </parent>
                    <groupId>com.enterprise.legacy</groupId>
                    <artifactId>legacy-enterprise-suite</artifactId>
                    <version>1.0.0</version>
                    <properties>
                        <java.version>8</java.version>
                        <spring-cloud.version>Hoxton.SR12</spring-cloud.version>
                    </properties>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-web</artifactId>
                        </dependency>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-security</artifactId>
                        </dependency>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-data-jpa</artifactId>
                        </dependency>
                    </dependencies>
                </project>
                """);

        // 2. Legacy Security Config
        sourceFiles.put("src/main/java/com/enterprise/legacy/SecurityConfig.java", """
                package com.enterprise.legacy;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @Configuration
                @EnableGlobalMethodSecurity(prePostEnabled = true)
                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/api/public/**").permitAll()
                            .antMatchers("/api/admin/**").hasRole("ADMIN")
                            .anyRequest().authenticated()
                            .and()
                            .csrf().disable();
                    }
                }
                """);

        // 3. Legacy JPA Entity with @TypeDef & javax.persistence
        sourceFiles.put("src/main/java/com/enterprise/legacy/OrderEntity.java", """
                package com.enterprise.legacy;

                import javax.persistence.Entity;
                import javax.persistence.Id;
                import javax.persistence.Table;
                import org.hibernate.annotations.TypeDef;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "orders")
                @TypeDef(name = "json", typeClass = String.class)
                public class OrderEntity {
                    @Id
                    private Long id;

                    @Type(type = "json")
                    private String orderPayload;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getOrderPayload() { return orderPayload; }
                    public void setOrderPayload(String orderPayload) { this.orderPayload = orderPayload; }
                }
                """);

        // 4. Legacy Cloud Service with Ribbon and Hystrix
        sourceFiles.put("src/main/java/com/enterprise/legacy/PaymentService.java", """
                package com.enterprise.legacy;

                import org.springframework.stereotype.Service;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @Service
                @RibbonClient(name = "payment-service")
                public class PaymentService {
                    @HystrixCommand(fallbackMethod = "paymentFallback")
                    public String processPayment(String orderId) {
                        return "PAYMENT_SUCCESS_" + orderId;
                    }

                    public String paymentFallback(String orderId) {
                        return "PAYMENT_FALLBACK_" + orderId;
                    }
                }
                """);

        // 5. Legacy XML Configuration
        sourceFiles.put("src/main/resources/applicationContext.xml", """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xmlns:tx="http://www.springframework.org/schema/tx"
                       xsi:schemaLocation="http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd">
                    <context:component-scan base-package="com.enterprise.legacy" />
                    <tx:annotation-driven />
                    <bean id="legacyNotifier" class="com.enterprise.legacy.LegacyNotifier">
                        <property name="channel" value="EMAIL" />
                    </bean>
                </beans>
                """);

        // 6. Legacy bootstrap.yml
        sourceFiles.put("src/main/resources/bootstrap.yml", """
                spring:
                  cloud:
                    config:
                      uri: http://config-server:8888
                """);

        var request = new SpringModernizationEndToEndWorkflowEngine.WorkflowRequest(
                "proj-ent-01", "Enterprise Legacy Suite", "2.3.12.RELEASE", "8", "4.1.0", "21", sourceFiles);

        var result = SpringModernizationEndToEndWorkflowEngine.execute(request);

        assertNotNull(result);
        assertTrue(result.isSuccessful(), "Workflow execution must succeed");
        assertTrue(result.isProductionReady(), "Must reach production-ready status");
        assertEquals("E5_CERTIFIED_PRODUCTION_READY", result.certificationLevel());
        assertTrue(result.appliedRuleIds().size() >= 4, "Multiple modernization rules should be applied");

        Map<String, String> targetFiles = result.modernizedFiles();

        // 1. Check POM upgrades
        String targetPom = targetFiles.get("pom.xml");
        assertNotNull(targetPom);
        assertTrue(targetPom.contains("<version>4.1.0</version>"));
        assertTrue(targetPom.contains("<java.version>21</java.version>"));

        // 2. Check Security upgrades
        String targetSec = targetFiles.get("src/main/java/com/enterprise/legacy/SecurityConfig.java");
        assertNotNull(targetSec);
        assertFalse(targetSec.contains("WebSecurityConfigurerAdapter"));
        assertFalse(targetSec.contains("authorizeRequests()"));
        assertTrue(targetSec.contains("SecurityFilterChain"));
        assertTrue(targetSec.contains("authorizeHttpRequests"));
        assertTrue(targetSec.contains("@EnableMethodSecurity"));

        // 3. Check JPA upgrades
        String targetJpa = targetFiles.get("src/main/java/com/enterprise/legacy/OrderEntity.java");
        assertNotNull(targetJpa);
        assertFalse(targetJpa.contains("javax.persistence"));
        assertFalse(targetJpa.contains("@TypeDef"));
        assertTrue(targetJpa.contains("jakarta.persistence"));
        assertTrue(targetJpa.contains("@JdbcTypeCode(SqlTypes.JSON)"));

        // 4. Check Cloud upgrades
        String targetCloud = targetFiles.get("src/main/java/com/enterprise/legacy/PaymentService.java");
        assertNotNull(targetCloud);
        assertFalse(targetCloud.contains("@RibbonClient"));
        assertFalse(targetCloud.contains("@HystrixCommand"));
        assertTrue(targetCloud.contains("@LoadBalancerClient"));
        assertTrue(targetCloud.contains("@CircuitBreaker"));

        // 5. Check bootstrap.yml migration
        assertFalse(targetFiles.containsKey("src/main/resources/bootstrap.yml"));
        String targetAppYml = targetFiles.get("src/main/resources/application.yml");
        assertNotNull(targetAppYml);
        assertTrue(targetAppYml.contains("spring.config.import"));

        // 6. Check XML migration
        boolean hasJavaConfig = targetFiles.keySet().stream()
                .anyMatch(k -> k.endsWith("Config.java"));
        assertTrue(hasJavaConfig, "Migrated JavaConfig class must exist for XML config");

        // 7. Verify Audit & Telemetry
        assertNotNull(result.auditVerdict());
        assertEquals(100.0, result.auditVerdict().overallMaturityScore(), 0.01);
        assertTrue(result.auditVerdict().fullyCertified());

        assertNotNull(result.regressionResult());
        assertTrue(result.regressionResult().isEquivalenceCertified());

        assertNotNull(result.telemetryProfile());
        assertTrue(result.telemetryProfile().totalDurationMillis() >= 0);
    }

    @Test
    @DisplayName("Verify workflow engine execution directly on disk workspace directory")
    void testExecuteOnDirectory(@TempDir Path tempDir) throws IOException {
        Path pomPath = tempDir.resolve("pom.xml");
        Files.writeString(pomPath, """
                <project>
                    <parent>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-parent</artifactId>
                        <version>2.7.18</version>
                    </parent>
                    <properties>
                        <java.version>11</java.version>
                    </properties>
                </project>
                """);

        Path javaDir = tempDir.resolve("src/main/java/io/elmos/benchmark");
        Files.createDirectories(javaDir);
        Files.writeString(javaDir.resolve("LegacyEntity.java"), """
                package io.elmos.benchmark;
                import javax.persistence.Entity;
                import javax.persistence.Id;
                @Entity
                public class LegacyEntity {
                    @Id
                    private Long id;
                }
                """);

        var result = SpringModernizationEndToEndWorkflowEngine.executeOnDirectory(tempDir);
        assertNotNull(result);
        assertTrue(result.isSuccessful());
        assertTrue(result.modernizedFiles().get("src/main/java/io/elmos/benchmark/LegacyEntity.java")
                .contains("jakarta.persistence"));
    }

    @Test
    @DisplayName("Verify workflow engine on Corpus Project benchmark")
    void testWorkflowOnCorpusProject() {
        var spec = SpringThirtyOpenSourceProjectsCorpus.getById("project-01-ecommerce-mall");
        assertNotNull(spec);

        var request = new SpringModernizationEndToEndWorkflowEngine.WorkflowRequest(
                spec.id(), spec.name(), spec.sourceBootVersion(), spec.sourceJavaVersion(),
                "4.1.0", "21", spec.sourceFiles());

        var result = SpringModernizationEndToEndWorkflowEngine.execute(request);
        assertNotNull(result);
        assertTrue(result.isSuccessful());
        assertTrue(result.isProductionReady());
    }
}
