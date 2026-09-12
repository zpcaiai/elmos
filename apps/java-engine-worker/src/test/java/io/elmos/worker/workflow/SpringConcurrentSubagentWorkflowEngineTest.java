package io.elmos.worker.workflow;

import io.elmos.worker.workflow.SpringConcurrentSubagentWorkflowEngine.SubagentDomain;
import io.elmos.worker.workflow.SpringModernizationEndToEndWorkflowEngine.WorkflowRequest;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SpringConcurrentSubagentWorkflowEngineTest {

    @Test
    @DisplayName("Concurrent 7-Subagent Full Industrial Modernization (100% complete enterprise pipeline)")
    void testConcurrentExecutionOfSevenSubagentsOnEnterpriseProject() {
        Map<String, String> sourceFiles = new LinkedHashMap<>();

        // 1. Maven POM baseline (includes legacy Springfox, MyBatis 2.x, missing -parameters)
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
                        <dependency>
                            <groupId>io.springfox</groupId>
                            <artifactId>springfox-swagger2</artifactId>
                            <version>2.9.2</version>
                        </dependency>
                        <dependency>
                            <groupId>io.springfox</groupId>
                            <artifactId>springfox-swagger-ui</artifactId>
                            <version>2.9.2</version>
                        </dependency>
                        <dependency>
                            <groupId>org.mybatis.spring.boot</groupId>
                            <artifactId>mybatis-spring-boot-starter</artifactId>
                            <version>2.2.0</version>
                        </dependency>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-test</artifactId>
                            <scope>test</scope>
                        </dependency>
                    </dependencies>
                    <build>
                        <plugins>
                            <plugin>
                                <groupId>org.apache.maven.plugins</groupId>
                                <artifactId>maven-compiler-plugin</artifactId>
                                <configuration>
                                    <source>1.8</source>
                                    <target>1.8</target>
                                </configuration>
                            </plugin>
                        </plugins>
                    </build>
                </project>
                """);

        // 2. Subagent-A Target: Legacy Security Config
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

        // 3. Subagent-B Target: Legacy JPA Entity
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

        // 4. Subagent-C Target: Legacy XML Configuration
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

        // 5. Subagent-D Target: Legacy Cloud Service with Ribbon and Hystrix
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

        sourceFiles.put("src/main/resources/bootstrap.yml", """
                spring:
                  cloud:
                    config:
                      uri: http://config-server:8888
                """);

        // 6. Subagent-E Target: Controller with Swagger 2 annotations
        sourceFiles.put("src/main/java/com/enterprise/legacy/UserController.java", """
                package com.enterprise.legacy;

                import io.swagger.annotations.Api;
                import io.swagger.annotations.ApiOperation;
                import org.springframework.web.bind.annotation.GetMapping;
                import org.springframework.web.bind.annotation.PathVariable;
                import org.springframework.web.bind.annotation.RequestMapping;
                import org.springframework.web.bind.annotation.RestController;

                @Api(tags = "User Management")
                @RestController
                @RequestMapping("/api/users")
                public class UserController {

                    @ApiOperation(value = "Get User by ID", notes = "Retrieves user details")
                    @GetMapping("/{id}")
                    public String getUser(@PathVariable Long id) {
                        return "USER_" + id;
                    }
                }
                """);

        // 7. Subagent-F Target: Global Exception Handler with javax.servlet
        sourceFiles.put("src/main/java/com/enterprise/legacy/GlobalExceptionHandler.java", """
                package com.enterprise.legacy;

                import org.springframework.web.bind.annotation.ControllerAdvice;
                import org.springframework.web.bind.annotation.ExceptionHandler;
                import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
                import javax.servlet.http.HttpServletRequest;
                import org.springframework.http.ResponseEntity;

                @ControllerAdvice
                public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

                    @ExceptionHandler(Exception.class)
                    public ResponseEntity<String> handleGeneric(Exception ex, HttpServletRequest req) {
                        return ResponseEntity.internalServerError().body("An internal error occurred");
                    }
                }
                """);

        // 8. Subagent-G Target: Legacy JUnit 4 Test Suite
        sourceFiles.put("src/test/java/com/enterprise/legacy/OrderServiceTest.java", """
                package com.enterprise.legacy;

                import org.junit.Test;
                import org.junit.Before;
                import org.junit.runner.RunWith;
                import org.springframework.test.context.junit4.SpringRunner;
                import org.junit.Assert;

                @RunWith(SpringRunner.class)
                public class OrderServiceTest {

                    @Before
                    public void setUp() {
                        // test init
                    }

                    @Test
                    public void testOrderProcessing() {
                        Assert.assertEquals("OK", "OK");
                        Assert.assertTrue(true);
                    }
                }
                """);

        WorkflowRequest request = new WorkflowRequest(
                "proj-concurrent-01",
                "Concurrent Enterprise Project",
                "2.3.12.RELEASE",
                "8",
                "4.1.0",
                "21",
                sourceFiles
        );

        var result = SpringConcurrentSubagentWorkflowEngine.execute(request);

        assertNotNull(result);
        assertTrue(result.isSuccessful(), "Concurrent workflow must succeed");
        assertTrue(result.isProductionReady(), "Must reach E5 production ready status");
        assertEquals("E5_CERTIFIED_PRODUCTION_READY", result.certificationLevel());
        assertTrue(result.zeroCollisionInvariantHeld(), "Zero collision invariant must hold across all 7 subagents");
        assertTrue(result.collisionsDetected().isEmpty(), "No colliding file paths should be reported");

        // Validate each of the 7 subagent outcomes
        var outcomes = result.subagentOutcomes();
        assertEquals(7, outcomes.size(), "All 7 subagents must report outcomes");

        // Subagent-A (Security - 25%)
        var outcomeA = outcomes.get(SubagentDomain.SECURITY);
        assertNotNull(outcomeA);
        assertTrue(outcomeA.successful(), "Subagent-A must succeed");
        assertTrue(outcomeA.domainCompliant(), "Security domain must be compliant");
        assertTrue(outcomeA.modifiedFiles().contains("src/main/java/com/enterprise/legacy/SecurityConfig.java"));

        // Subagent-B (JPA - 20%)
        var outcomeB = outcomes.get(SubagentDomain.PERSISTENCE);
        assertNotNull(outcomeB);
        assertTrue(outcomeB.successful(), "Subagent-B must succeed");
        assertTrue(outcomeB.domainCompliant(), "JPA domain must be compliant");
        assertTrue(outcomeB.modifiedFiles().contains("src/main/java/com/enterprise/legacy/OrderEntity.java"));

        // Subagent-C (Configuration / XML - 15%)
        var outcomeC = outcomes.get(SubagentDomain.CONFIGURATION);
        assertNotNull(outcomeC);
        assertTrue(outcomeC.successful(), "Subagent-C must succeed");
        assertTrue(outcomeC.domainCompliant(), "XML configuration must be fully migrated");
        assertFalse(outcomeC.modifiedFiles().isEmpty(), "Subagent-C must produce JavaConfig files");

        // Subagent-D (Microservices / Cloud - 15%)
        var outcomeD = outcomes.get(SubagentDomain.MICROSERVICES);
        assertNotNull(outcomeD);
        assertTrue(outcomeD.successful(), "Subagent-D must succeed");
        assertTrue(outcomeD.domainCompliant(), "Cloud microservices domain must be compliant");
        assertTrue(outcomeD.modifiedFiles().contains("src/main/java/com/enterprise/legacy/PaymentService.java"));

        // Subagent-E (Ecosystem Dependencies - 10%)
        var outcomeE = outcomes.get(SubagentDomain.ECOSYSTEM);
        assertNotNull(outcomeE);
        assertTrue(outcomeE.successful(), "Subagent-E must succeed");
        assertTrue(outcomeE.domainCompliant(), "Ecosystem domain must be compliant");
        assertTrue(outcomeE.modifiedFiles().contains("pom.xml"));
        assertTrue(outcomeE.modifiedFiles().contains("src/main/java/com/enterprise/legacy/UserController.java"));
        assertTrue(outcomeE.rulesApplied().contains("RULE-SPRINGFOX-TO-SPRINGDOC-OPENAPI3"));
        assertTrue(outcomeE.rulesApplied().contains("RULE-MYBATIS-BOOT-3-JAKARTA-UPGRADE"));
        assertTrue(outcomeE.rulesApplied().contains("RULE-INJECT-COMPILER-PARAMETERS-FLAG"));

        // Subagent-F (Web Routing / MVC - 8%)
        var outcomeF = outcomes.get(SubagentDomain.WEB_ROUTING);
        assertNotNull(outcomeF);
        assertTrue(outcomeF.successful(), "Subagent-F must succeed");
        assertTrue(outcomeF.domainCompliant(), "Web routing domain must be compliant");
        assertTrue(outcomeF.modifiedFiles().contains("src/main/java/io/elmos/benchmark/config/LegacyWebMvcTrailingSlashConfiguration.java"));
        assertTrue(outcomeF.rulesApplied().contains("RULE-SPRING-MVC-TRAILING-SLASH-COMPATIBILITY"));

        // Subagent-G (Test Suite Modernization - 7%)
        var outcomeG = outcomes.get(SubagentDomain.TESTING);
        assertNotNull(outcomeG);
        assertTrue(outcomeG.successful(), "Subagent-G must succeed");
        assertTrue(outcomeG.domainCompliant(), "Test suite domain must be compliant");
        assertTrue(outcomeG.modifiedFiles().contains("src/test/java/com/enterprise/legacy/OrderServiceTest.java"));
        assertTrue(outcomeG.rulesApplied().contains("RULE-JUNIT4-TEST-TO-JUPITER"));
        assertTrue(outcomeG.rulesApplied().contains("RULE-SPRINGRUNNER-TO-SPRINGEXTENSION"));

        // Validate merged results in master workspace
        Map<String, String> merged = result.modernizedFiles();

        // 1. Security merged verification
        String secCode = merged.get("src/main/java/com/enterprise/legacy/SecurityConfig.java");
        assertNotNull(secCode);
        assertFalse(secCode.contains("WebSecurityConfigurerAdapter"));
        assertTrue(secCode.contains("SecurityFilterChain"));
        assertTrue(secCode.contains("authorizeHttpRequests"));

        // 2. JPA merged verification
        String jpaCode = merged.get("src/main/java/com/enterprise/legacy/OrderEntity.java");
        assertNotNull(jpaCode);
        assertFalse(jpaCode.contains("javax.persistence"));
        assertTrue(jpaCode.contains("jakarta.persistence"));
        assertTrue(jpaCode.contains("@JdbcTypeCode(SqlTypes.JSON)"));

        // 3. Cloud merged verification
        String cloudCode = merged.get("src/main/java/com/enterprise/legacy/PaymentService.java");
        assertNotNull(cloudCode);
        assertFalse(cloudCode.contains("@RibbonClient"));
        assertFalse(cloudCode.contains("@HystrixCommand"));
        assertTrue(cloudCode.contains("@LoadBalancerClient"));
        assertTrue(cloudCode.contains("@CircuitBreaker"));

        // 4. Ecosystem merged verification (Swagger 2 -> OpenAPI 3)
        String userCtrlCode = merged.get("src/main/java/com/enterprise/legacy/UserController.java");
        assertNotNull(userCtrlCode);
        assertFalse(userCtrlCode.contains("@Api("));
        assertFalse(userCtrlCode.contains("@ApiOperation("));
        assertTrue(userCtrlCode.contains("@Tag(name = \"User Management\")"));
        assertTrue(userCtrlCode.contains("@Operation(summary = \"Get User by ID\", description = \"Retrieves user details\")"));

        // 5. Web routing merged verification (Trailing slash configuration)
        String trailingSlashConfig = merged.get("src/main/java/io/elmos/benchmark/config/LegacyWebMvcTrailingSlashConfiguration.java");
        assertNotNull(trailingSlashConfig);
        assertTrue(trailingSlashConfig.contains("setUseTrailingSlashMatch(true)"));

        // 6. Test suite merged verification (JUnit 4 -> JUnit 5 Jupiter)
        String testCode = merged.get("src/test/java/com/enterprise/legacy/OrderServiceTest.java");
        assertNotNull(testCode);
        assertFalse(testCode.contains("org.junit.Test;"));
        assertFalse(testCode.contains("@RunWith(SpringRunner.class)"));
        assertTrue(testCode.contains("@ExtendWith(SpringExtension.class)"));
        assertTrue(testCode.contains("import org.junit.jupiter.api.Test;"));
        assertTrue(testCode.contains("Assertions.assertEquals"));

        // 7. POM merged verification
        String pomCode = merged.get("pom.xml");
        assertNotNull(pomCode);
        assertTrue(pomCode.contains("<version>4.1.0</version>"));
        assertTrue(pomCode.contains("<java.version>21</java.version>"));
        assertTrue(pomCode.contains("springdoc-openapi-starter-webmvc-ui"));
        assertFalse(pomCode.contains("springfox-swagger2"));
        assertTrue(pomCode.contains("-parameters"));
        assertTrue(pomCode.contains("3.0.3"));
    }
}
