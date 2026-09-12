package io.elmos.worker.validation;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringEcosystemAuditValidatorTest {

    private final SpringEcosystemAuditValidator validator = new SpringEcosystemAuditValidator();

    @Test
    @DisplayName("Non-compliant project with Springfox, MyBatis 2.x, missing -parameters, and Swagger 2 annotations")
    void testNonCompliantEcosystemProject(@TempDir Path tempDir) throws IOException {
        String pom = """
                <project>
                    <parent>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-parent</artifactId>
                        <version>3.4.0</version>
                    </parent>
                    <dependencies>
                        <dependency>
                            <groupId>io.springfox</groupId>
                            <artifactId>springfox-swagger2</artifactId>
                            <version>2.9.2</version>
                        </dependency>
                        <dependency>
                            <groupId>org.mybatis.spring.boot</groupId>
                            <artifactId>mybatis-spring-boot-starter</artifactId>
                            <version>2.2.0</version>
                        </dependency>
                    </dependencies>
                </project>
                """;
        Files.writeString(tempDir.resolve("pom.xml"), pom, StandardCharsets.UTF_8);

        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);
        String controller = """
                package com.example;

                import io.swagger.annotations.Api;
                import io.swagger.annotations.ApiOperation;

                @Api(tags = "Test")
                public class TestController {
                    @ApiOperation("get")
                    public String get() { return "ok"; }
                }
                """;
        Files.writeString(src.resolve("TestController.java"), controller, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertFalse(report.isCompliant(), "Project with Springfox and MyBatis 2.x must NOT be compliant");
        assertTrue(report.complianceScore() < 70.0, "Score should reflect multiple severe penalties");
        assertTrue(report.violations().stream().anyMatch(v -> "ECO-001".equals(v.ruleId())), "Must report ECO-001 (Springfox)");
        assertTrue(report.violations().stream().anyMatch(v -> "ECO-002".equals(v.ruleId())), "Must report ECO-002 (Swagger 2 annotations)");
        assertTrue(report.violations().stream().anyMatch(v -> "ECO-003".equals(v.ruleId())), "Must report ECO-003 (MyBatis 2.x)");
        assertTrue(report.violations().stream().anyMatch(v -> "ECO-004".equals(v.ruleId())), "Must report ECO-004 (Missing -parameters)");
    }

    @Test
    @DisplayName("Compliant project with Springdoc OpenAPI 3, MyBatis 3.0.3, and -parameters compiler flag")
    void testCompliantEcosystemProject(@TempDir Path tempDir) throws IOException {
        String pom = """
                <project>
                    <parent>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-starter-parent</artifactId>
                        <version>3.4.0</version>
                    </parent>
                    <dependencies>
                        <dependency>
                            <groupId>org.springdoc</groupId>
                            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
                            <version>2.5.0</version>
                        </dependency>
                        <dependency>
                            <groupId>org.mybatis.spring.boot</groupId>
                            <artifactId>mybatis-spring-boot-starter</artifactId>
                            <version>3.0.3</version>
                        </dependency>
                    </dependencies>
                    <build>
                        <plugins>
                            <plugin>
                                <groupId>org.apache.maven.plugins</groupId>
                                <artifactId>maven-compiler-plugin</artifactId>
                                <configuration>
                                    <compilerArgs>
                                        <arg>-parameters</arg>
                                    </compilerArgs>
                                </configuration>
                            </plugin>
                        </plugins>
                    </build>
                </project>
                """;
        Files.writeString(tempDir.resolve("pom.xml"), pom, StandardCharsets.UTF_8);

        Path src = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(src);
        String controller = """
                package com.example;

                import io.swagger.v3.oas.annotations.tags.Tag;
                import io.swagger.v3.oas.annotations.Operation;

                @Tag(name = "Test")
                public class TestController {
                    @Operation(summary = "get")
                    public String get() { return "ok"; }
                }
                """;
        Files.writeString(src.resolve("TestController.java"), controller, StandardCharsets.UTF_8);

        var report = validator.auditProject(tempDir);
        assertNotNull(report);
        assertTrue(report.isCompliant(), "Fully modernized ecosystem project must be compliant");
        assertEquals(100.0, report.complianceScore(), 0.001);
        assertEquals(0, report.totalViolations());
    }
}
