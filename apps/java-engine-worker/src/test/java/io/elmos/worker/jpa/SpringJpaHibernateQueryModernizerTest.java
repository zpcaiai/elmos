package io.elmos.worker.jpa;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringJpaHibernateQueryModernizerTest {

    @TempDir
    Path tempDir;

    @Test
    void modernizesJakartaPersistenceAndHibernate6TypesAndSqm() throws Exception {
        Path entityFile = tempDir.resolve("OrderEntity.java");
        Files.writeString(entityFile, """
                package com.example.domain;

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
                    private String metadata;
                }
                """);

        Path repoFile = tempDir.resolve("OrderRepository.java");
        Files.writeString(repoFile, """
                package com.example.domain;

                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import org.hibernate.Criteria;

                public interface OrderRepository extends JpaRepository<OrderEntity, Long> {
                    @Query("SELECT o FROM OrderEntity o WHERE o.id = ? AND o.metadata = ?")
                    OrderEntity findLegacy(Long id, String metadata);
                }
                """);

        var result = SpringJpaHibernateQueryModernizer.modernize(tempDir);
        assertTrue(result.modified());
        assertTrue(result.changesCount() > 0);

        String entityContent = Files.readString(entityFile);
        assertTrue(entityContent.contains("jakarta.persistence.Entity"));
        assertFalse(entityContent.contains("javax.persistence.Entity"));
        assertFalse(entityContent.contains("@TypeDef"));
        assertTrue(entityContent.contains("@JdbcTypeCode(SqlTypes.JSON)"));

        String repoContent = Files.readString(repoFile);
        assertTrue(repoContent.contains("WHERE o.id = ?1 AND o.metadata = ?2"));
    }

    @Test
    void modernizesMultipleQueriesWithPositionalParameters() throws Exception {
        Path repoFile = tempDir.resolve("MultiQueryRepository.java");
        Files.writeString(repoFile, """
                package com.example.domain;

                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import java.util.List;

                public interface MultiQueryRepository extends JpaRepository<OrderEntity, Long> {
                    @Query("SELECT o FROM OrderEntity o WHERE o.status = ?")
                    List<OrderEntity> findByStatus(String status);

                    @Query("SELECT o FROM OrderEntity o WHERE o.status = ? AND o.price > ?")
                    List<OrderEntity> findByStatusAndMinPrice(String status, Double minPrice);
                }
                """);

        var result = SpringJpaHibernateQueryModernizer.modernize(tempDir);
        assertTrue(result.modified());

        String repoContent = Files.readString(repoFile);
        assertTrue(repoContent.contains("WHERE o.status = ?1"));
        assertTrue(repoContent.contains("WHERE o.status = ?1 AND o.price > ?2"));
    }
}
