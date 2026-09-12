package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SpringDiagnosticAutoRepairerTest {

    @TempDir
    Path tempDir;

    @Test
    void repairEmptyDirectoryProducesZeroChanges() {
        var result = SpringDiagnosticAutoRepairer.repair(tempDir, List.of());
        assertFalse(result.repaired());
        assertEquals(0, result.changesCount());
        assertTrue(result.modifiedFiles().isEmpty());
    }

    @Test
    void repairPomAddsJakartaDependenciesWhenDiagnosticsIndicateMissingPackages() throws IOException {
        Path pom = tempDir.resolve("pom.xml");
        Files.writeString(pom, """
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <groupId>com.example</groupId>
                  <artifactId>demo</artifactId>
                  <version>1.0.0</version>
                  <dependencies>
                    <dependency>
                      <groupId>org.springframework.boot</groupId>
                      <artifactId>spring-boot-starter-web</artifactId>
                    </dependency>
                  </dependencies>
                </project>
                """);

        List<String> diagnostics = List.of(
                "[ERROR] /src/main/java/UserDto.java:[5,26] package jakarta.validation.constraints does not exist",
                "[ERROR] /src/main/java/Config.java:[3,24] package jakarta.annotation does not exist"
        );

        var result = SpringDiagnosticAutoRepairer.repair(tempDir, diagnostics);
        assertTrue(result.repaired());
        assertTrue(result.changesCount() > 0);

        String updatedPom = Files.readString(pom);
        assertTrue(updatedPom.contains("jakarta.validation-api") || updatedPom.contains("spring-boot-starter-validation"));
        assertTrue(updatedPom.contains("jakarta.annotation-api"));
    }

    @Test
    void repairSpringSecurity6WebSecurityConfigurerAdapter() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);
        Path securityConfig = srcDir.resolve("SecurityConfig.java");
        Files.writeString(securityConfig, """
                package com.example;
                
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                
                @Configuration
                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests()
                            .antMatchers("/public/**").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """);

        var result = SpringDiagnosticAutoRepairer.repair(tempDir, List.of(
                "[ERROR] cannot find symbol: class WebSecurityConfigurerAdapter"
        ));

        assertTrue(result.repaired());
        String updated = Files.readString(securityConfig);
        assertFalse(updated.contains("extends WebSecurityConfigurerAdapter"));
        assertTrue(updated.contains("SecurityFilterChain"));
        assertTrue(updated.contains("@Bean"));
        assertTrue(updated.contains("authorizeHttpRequests"));
        assertTrue(updated.contains("requestMatchers"));
    }

    @Test
    void repairHibernate6TypeDefAndJsonAnnotations() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);
        Path entity = srcDir.resolve("CustomerEntity.java");
        Files.writeString(entity, """
                package com.example;
                
                import org.hibernate.annotations.Type;
                import org.hibernate.annotations.TypeDef;
                import com.vladmihalcea.hibernate.type.json.JsonStringType;
                import jakarta.persistence.Entity;
                import jakarta.persistence.Id;
                
                @Entity
                @TypeDef(name = "json", typeClass = JsonStringType.class)
                public class CustomerEntity {
                    @Id
                    private Long id;
                    
                    @Type(type = "json")
                    private String metadata;
                }
                """);

        var result = SpringDiagnosticAutoRepairer.repair(tempDir, List.of(
                "[ERROR] cannot find symbol: class TypeDef",
                "[ERROR] cannot find symbol: class Type"
        ));

        assertTrue(result.repaired());
        String updated = Files.readString(entity);
        assertFalse(updated.contains("@TypeDef("));
        assertTrue(updated.contains("@JdbcTypeCode(SqlTypes.JSON)"));
        assertTrue(updated.contains("org.hibernate.annotations.JdbcTypeCode"));
        assertTrue(updated.contains("org.hibernate.type.SqlTypes"));
    }

    @Test
    void repairActuatorAndWebMvcDeprecatedClasses() throws IOException {
        Path srcDir = tempDir.resolve("src/main/java/com/example");
        Files.createDirectories(srcDir);
        Path interceptor = srcDir.resolve("LoggingInterceptor.java");
        Files.writeString(interceptor, """
                package com.example;
                
                import org.springframework.web.servlet.handler.HandlerInterceptorAdapter;
                
                public class LoggingInterceptor extends HandlerInterceptorAdapter {
                }
                """);

        var result = SpringDiagnosticAutoRepairer.repair(tempDir, List.of(
                "[ERROR] cannot find symbol: class HandlerInterceptorAdapter"
        ));

        assertTrue(result.repaired());
        String updated = Files.readString(interceptor);
        assertFalse(updated.contains("extends HandlerInterceptorAdapter"));
        assertTrue(updated.contains("implements HandlerInterceptor") || updated.contains("HandlerInterceptor"));
    }
}
