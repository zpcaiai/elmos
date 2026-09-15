package io.elmos.worker.jpa;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringHibernate6SqmQueryModernizerTest {

    @Test
    void testHibernate6SqmModernizationFlow(@TempDir Path tempDir) throws IOException {
        // 1. Setup entity with legacy @Type(type = "json")
        Path entityDir = tempDir.resolve("src/main/java/com/example/entity");
        Files.createDirectories(entityDir);
        Path entityPath = entityDir.resolve("OrderEntity.java");
        String legacyEntity = """
                package com.example.entity;

                import org.hibernate.annotations.Type;
                import jakarta.persistence.Entity;
                import jakarta.persistence.Id;
                import java.util.Map;

                @Entity
                public class OrderEntity {
                    @Id
                    private Long id;

                    @Type(type = "json")
                    private Map<String, Object> extraDetails;
                }
                """;
        Files.writeString(entityPath, legacyEntity);

        // 2. Setup repository with unindexed ? in @Query
        Path repoDir = tempDir.resolve("src/main/java/com/example/repo");
        Files.createDirectories(repoDir);
        Path repoPath = repoDir.resolve("OrderRepository.java");
        String legacyRepo = """
                package com.example.repo;

                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import com.example.entity.OrderEntity;

                public interface OrderRepository extends JpaRepository<OrderEntity, Long> {
                    @Query("SELECT o FROM OrderEntity o WHERE o.id = ?")
                    OrderEntity findByIdLegacy(Long id);

                    @Query("UPDATE OrderEntity o SET o.extraDetails = null WHERE o.id = :id")
                    int clearDetails(Long id);
                }
                """;
        Files.writeString(repoPath, legacyRepo);

        // 3. Setup application.yml
        Path resDir = tempDir.resolve("src/main/resources");
        Files.createDirectories(resDir);
        Path ymlPath = resDir.resolve("application.yml");
        Files.writeString(ymlPath, "spring:\n  datasource:\n    url: jdbc:h2:mem:testdb\n");

        // Execute modernization
        SpringHibernate6SqmQueryModernizer modernizer = new SpringHibernate6SqmQueryModernizer();
        SpringHibernate6SqmQueryModernizer.SqmModernizationResult result = modernizer.modernize(tempDir);

        assertTrue(result.modified(), "Workspace should be modified");
        assertTrue(result.changesCount() >= 3, "Should apply at least 3 changes");

        // Verify entity modernized with @JdbcTypeCode
        String updatedEntity = Files.readString(entityPath);
        assertTrue(updatedEntity.contains("@JdbcTypeCode(SqlTypes.JSON)"), "Should replace @Type with @JdbcTypeCode(SqlTypes.JSON)");
        assertTrue(updatedEntity.contains("import org.hibernate.annotations.JdbcTypeCode;"), "Should import JdbcTypeCode");
        assertTrue(updatedEntity.contains("import org.hibernate.type.SqlTypes;"), "Should import SqlTypes");
        assertFalse(updatedEntity.contains("@Type(type = \"json\")"), "Legacy @Type should be eliminated");

        // Verify repository @Query parameterized
        String updatedRepo = Files.readString(repoPath);
        assertTrue(updatedRepo.contains("WHERE o.id = ?1"), "Should convert unindexed ? to ?1");

        // Verify warning for DML without @Modifying
        assertFalse(result.warnings().isEmpty(), "Should warn about UPDATE query missing @Modifying");
        assertTrue(result.warnings().getFirst().contains("@Modifying"));

        // Verify application.yml has frozen naming strategy
        String updatedYml = Files.readString(ymlPath);
        assertTrue(updatedYml.contains("CamelCaseToUnderscoresNamingStrategy"), "Should freeze physical naming strategy");
        assertTrue(updatedYml.contains("SpringImplicitNamingStrategy"), "Should freeze implicit naming strategy");
    }
}
