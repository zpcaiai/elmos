package io.elmos.worker.validation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.*;

class SpringJpaHibernateQueryValidatorTest {

    @TempDir
    Path tempDir;

    private final SpringJpaHibernateQueryValidator validator = new SpringJpaHibernateQueryValidator();

    @Test
    void testDetectsLegacyJpaAndHibernateConstructs() throws IOException {
        Path javaFile = tempDir.resolve("LegacyEntity.java");
        Files.writeString(javaFile, """
                package com.example;
                import javax.persistence.Entity;
                import javax.persistence.Id;
                import org.hibernate.annotations.TypeDef;
                import org.hibernate.annotations.Type;
                import org.hibernate.Criteria;

                @Entity
                @TypeDef(name = "json", typeClass = String.class)
                public class LegacyEntity {
                    @Id
                    private Long id;
                    @Type(type = "json")
                    private String data;
                }
                """);

        SpringJpaHibernateQueryValidator.JpaHibernateAuditReport report = validator.auditProject(tempDir);
        assertFalse(report.isCompliant());
        assertTrue(report.criticalViolations() >= 2);
        assertTrue(report.violations().stream().anyMatch(v -> "JPA-001".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "JPA-002".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "JPA-003".equals(v.ruleId())));
        assertTrue(report.violations().stream().anyMatch(v -> "JPA-004".equals(v.ruleId())));
    }

    @Test
    void testDetectsLegacyPositionalQueryParameter() throws IOException {
        Path repoFile = tempDir.resolve("UserRepo.java");
        Files.writeString(repoFile, """
                package com.example;
                import org.springframework.data.jpa.repository.Query;
                import org.springframework.data.repository.Repository;

                public interface UserRepo extends Repository<Object, Long> {
                    @Query("SELECT u FROM User u WHERE u.email = ?")
                    Object findByEmail(String email);
                }
                """);

        SpringJpaHibernateQueryValidator.JpaHibernateAuditReport report = validator.auditProject(tempDir);
        assertTrue(report.violations().stream().anyMatch(v -> "JPA-005".equals(v.ruleId())));
    }

    @Test
    void testCompliantJakartaEntity() throws IOException {
        Path javaFile = tempDir.resolve("ModernEntity.java");
        Files.writeString(javaFile, """
                package com.example;
                import jakarta.persistence.Entity;
                import jakarta.persistence.Id;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;
                import java.util.Map;

                @Entity
                public class ModernEntity {
                    @Id
                    private Long id;
                    @JdbcTypeCode(SqlTypes.JSON)
                    private Map<String, Object> data;
                }
                """);

        SpringJpaHibernateQueryValidator.JpaHibernateAuditReport report = validator.auditProject(tempDir);
        assertTrue(report.isCompliant());
        assertEquals(0, report.criticalViolations());
        assertEquals(0, report.highViolations());
    }
}
