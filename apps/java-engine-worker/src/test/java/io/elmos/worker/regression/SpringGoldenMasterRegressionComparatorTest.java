package io.elmos.worker.regression;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SpringGoldenMasterRegressionComparatorTest {

    @Test
    @DisplayName("Verify certified equivalence when all routes and entities are preserved")
    void testEquivalenceOnPreservedRoutes() {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("src/main/java/com/example/OrderController.java", """
                package com.example;
                import org.springframework.web.bind.annotation.*;
                @RestController
                public class OrderController {
                    @GetMapping("/api/orders")
                    public List<Order> list() { return List.of(); }
                    @PostMapping("/api/orders")
                    public Order create(@RequestBody Order o) { return o; }
                }
                """);

        Map<String, String> target = new LinkedHashMap<>();
        target.put("src/main/java/com/example/OrderController.java", """
                package com.example;
                import org.springframework.web.bind.annotation.*;
                @RestController
                public class OrderController {
                    @GetMapping("/api/orders")
                    public List<Order> list() { return List.of(); }
                    @PostMapping("/api/orders")
                    public Order create(@RequestBody Order o) { return o; }
                }
                """);

        var result = SpringGoldenMasterRegressionComparator.compare(source, target);

        assertTrue(result.isEquivalenceCertified());
        assertEquals(100.0, result.overallEquivalenceScore());
        assertEquals(2, result.routeDivergences().size());
        for (var r : result.routeDivergences()) {
            assertEquals(SpringGoldenMasterRegressionComparator.DivergenceType.BENIGN_MODERNIZATION, r.divergenceType());
        }
    }

    @Test
    @DisplayName("Verify equivalence failure when endpoint is missing in target")
    void testMissingRouteFailsCertification() {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("src/main/java/com/example/ProductController.java", """
                package com.example;
                import org.springframework.web.bind.annotation.*;
                @RestController
                public class ProductController {
                    @GetMapping("/api/products")
                    public List<Product> list() { return List.of(); }
                    @DeleteMapping("/api/products/all")
                    public void deleteAll() {}
                }
                """);

        Map<String, String> target = new LinkedHashMap<>();
        target.put("src/main/java/com/example/ProductController.java", """
                package com.example;
                import org.springframework.web.bind.annotation.*;
                @RestController
                public class ProductController {
                    @GetMapping("/api/products")
                    public List<Product> list() { return List.of(); }
                }
                """);

        var result = SpringGoldenMasterRegressionComparator.compare(source, target);

        assertFalse(result.isEquivalenceCertified(), "Missing route must fail golden master equivalence");
        assertTrue(result.hasCriticalFailures());
        assertTrue(result.overallEquivalenceScore() < 100.0);
        assertTrue(result.routeDivergences().stream()
                .anyMatch(r -> r.divergenceType() == SpringGoldenMasterRegressionComparator.DivergenceType.MISSING_IN_TARGET));
    }

    @Test
    @DisplayName("Verify permission broadening is detected and fails certification")
    void testPermissionBroadeningDetected() {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("src/main/java/com/example/SecurityConfig.java", """
                package com.example;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                public class SecurityConfig {
                    void configure(HttpSecurity http) throws Exception {
                        http.authorizeRequests().antMatchers("/admin/**").hasRole("ADMIN");
                    }
                }
                """);

        Map<String, String> target = new LinkedHashMap<>();
        target.put("src/main/java/com/example/SecurityConfig.java", """
                package com.example;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                public class SecurityConfig {
                    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
                        return http.build();
                    }
                }
                """);

        var result = SpringGoldenMasterRegressionComparator.compare(source, target);

        assertFalse(result.isEquivalenceCertified());
        assertTrue(result.securityDivergences().stream().anyMatch(SpringGoldenMasterRegressionComparator.SecurityDivergence::isPermissionBroadened));
    }

    @Test
    @DisplayName("Verify Hibernate 5 @Type to Hibernate 6 @JdbcTypeCode modernization")
    void testDataModelTypeJsonModernization() {
        Map<String, String> source = new LinkedHashMap<>();
        source.put("src/main/java/com/example/UserEntity.java", """
                package com.example;
                import javax.persistence.*;
                import org.hibernate.annotations.Type;
                @Entity
                public class UserEntity {
                    @Id private Long id;
                    @Type(type = "json") private String preferences;
                }
                """);

        Map<String, String> target = new LinkedHashMap<>();
        target.put("src/main/java/com/example/UserEntity.java", """
                package com.example;
                import jakarta.persistence.*;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;
                @Entity
                public class UserEntity {
                    @Id private Long id;
                    @JdbcTypeCode(SqlTypes.JSON) private String preferences;
                }
                """);

        var result = SpringGoldenMasterRegressionComparator.compare(source, target);

        assertTrue(result.isEquivalenceCertified());
        assertTrue(result.dataModelDivergences().stream()
                .anyMatch(d -> d.divergenceType() == SpringGoldenMasterRegressionComparator.DivergenceType.BENIGN_MODERNIZATION));
    }

    @Test
    @DisplayName("Verify Markdown audit report formatting")
    void testMarkdownReportGeneration() {
        Map<String, String> source = Map.of("src/main/resources/bootstrap.yml", "spring.cloud.config.uri=http://localhost:8888");
        Map<String, String> target = Map.of("src/main/resources/application.yml", "spring.config.import=optional:configserver:http://localhost:8888");

        var result = SpringGoldenMasterRegressionComparator.compare(source, target);
        String report = SpringGoldenMasterRegressionComparator.generateMarkdownAuditReport(result);

        assertNotNull(report);
        assertTrue(report.contains("# Golden Master Modernization Equivalence Audit Report"));
        assertTrue(report.contains("CERTIFIED"));
        assertTrue(report.contains("spring.config.import"));
    }
}
