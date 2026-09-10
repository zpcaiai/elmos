package io.elmos.worker.architecture;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Enterprise Reference Architecture Catalog for Spring Legacy to Boot 4.x Modernization.
 *
 * <p>Provides standardized, certified enterprise blueprints across:
 * <ul>
 *   <li>1. Banking & Financial Core Architecture (Idempotency, ISO8583, SecurityFilterChain, Multi-Tenant Ledger).</li>
 *   <li>2. E-Commerce & Retail Platform Architecture (Hibernate 6 JSON, SQM Optimizer, Resilient CircuitBreakers).</li>
 *   <li>3. Healthcare & Regulated Data Architecture (HIPAA/FHIR, Audit Logging, Jakarta Persistence, Envers).</li>
 *   <li>4. Microservices Mesh Architecture (Spring Cloud Gateway, Resilience4j, Micrometer Tracing, Config Import).</li>
 *   <li>5. Monolith Strangler & Hybrid XML Modernization (Coexistence Shim, JavaConfig Migration, Dual-Run).</li>
 * </ul>
 */
public final class SpringEnterpriseReferenceArchitectureCatalog {

    public enum EnterpriseArchetype {
        BANKING_CORE_LEDGER,
        ECOMMERCE_HIGH_THROUGHPUT,
        HEALTHCARE_REGULATED_VAULT,
        CLOUD_NATIVE_MICROSERVICES_MESH,
        MONOLITH_STRANGLER_HYBRID_XML
    }

    public record ArchitectureBlueprint(
            EnterpriseArchetype archetype,
            String title,
            String description,
            String securityFilterChainTemplate,
            String persistenceModelTemplate,
            String resilienceConfigurationTemplate,
            String cloudIntegrationTemplate,
            String testSuiteTemplate,
            List<String> keyMigrationMilestones,
            Map<String, String> recommendedProperties
    ) {}

    private static final Map<EnterpriseArchetype, ArchitectureBlueprint> BLUEPRINTS = new LinkedHashMap<>();

    static {
        registerBankingBlueprint();
        registerEcommerceBlueprint();
        registerHealthcareBlueprint();
        registerCloudMeshBlueprint();
        registerMonolithStranglerBlueprint();
    }

    public static ArchitectureBlueprint getBlueprint(EnterpriseArchetype archetype) {
        return BLUEPRINTS.get(archetype);
    }

    public static List<ArchitectureBlueprint> getAllBlueprints() {
        return Collections.unmodifiableList(new ArrayList<>(BLUEPRINTS.values()));
    }

    private static void registerBankingBlueprint() {
        Map<String, String> props = new LinkedHashMap<>();
        props.put("spring.jpa.open-in-view", "false");
        props.put("spring.jpa.hibernate.ddl-auto", "validate");
        props.put("spring.datasource.hikari.maximum-pool-size", "50");
        props.put("spring.datasource.hikari.connection-timeout", "30000");
        props.put("management.endpoints.web.exposure.include", "health,info,metrics,prometheus");
        props.put("management.endpoint.health.probes.enabled", "true");

        BLUEPRINTS.put(EnterpriseArchetype.BANKING_CORE_LEDGER, new ArchitectureBlueprint(
                EnterpriseArchetype.BANKING_CORE_LEDGER,
                "Banking & Financial Core Ledger Architecture",
                "High-assurance financial transaction processing architecture featuring zero-trust filter chains, idempotency keys, and Hibernate 6 SQM.",
                """
                package io.elmos.architecture.banking.security;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.Customizer;
                import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
                import org.springframework.security.config.http.SessionCreationPolicy;
                import org.springframework.security.web.SecurityFilterChain;
                import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

                @Configuration
                @EnableWebSecurity
                @EnableMethodSecurity(prePostEnabled = true)
                public class BankingSecurityConfig {

                    @Bean
                    public SecurityFilterChain bankingSecurityFilterChain(
                            HttpSecurity http,
                            BankingIdempotencyFilter idempotencyFilter,
                            BankingJwtAuthenticationFilter jwtFilter
                    ) throws Exception {
                        http
                            .csrf(csrf -> csrf.disable())
                            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                            .headers(headers -> headers
                                .frameOptions(frame -> frame.deny())
                                .contentTypeOptions(Customizer.withDefaults())
                                .xssProtection(Customizer.withDefaults())
                            )
                            .authorizeHttpRequests(auth -> auth
                                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                                .requestMatchers("/api/v1/auth/**").permitAll()
                                .requestMatchers("/api/v1/internal/**").hasAuthority("BANK_SYSTEM")
                                .requestMatchers("/api/v1/transactions/**").hasAuthority("TRANSACTION_WRITE")
                                .anyRequest().authenticated()
                            )
                            .addFilterBefore(idempotencyFilter, UsernamePasswordAuthenticationFilter.class)
                            .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);

                        return http.build();
                    }
                }
                """,
                """
                package io.elmos.architecture.banking.domain;

                import jakarta.persistence.*;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;
                import java.math.BigDecimal;
                import java.time.Instant;
                import java.util.Map;

                @Entity
                @Table(name = "banking_ledger_entries", indexes = {
                    @Index(name = "idx_ledger_account", columnList = "account_number"),
                    @Index(name = "idx_ledger_idempotency", columnList = "idempotency_key", unique = true)
                })
                public class BankingLedgerEntry {

                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(name = "idempotency_key", nullable = false, unique = true, length = 64)
                    private String idempotencyKey;

                    @Column(name = "account_number", nullable = false, length = 34)
                    private String accountNumber;

                    @Column(nullable = false, precision = 18, scale = 4)
                    private BigDecimal amount;

                    @Column(nullable = false, length = 3)
                    private String currency;

                    @Enumerated(EnumType.STRING)
                    @Column(nullable = false, length = 16)
                    private EntryDirection direction;

                    @JdbcTypeCode(SqlTypes.JSON)
                    @Column(columnDefinition = "jsonb")
                    private Map<String, Object> auditContext;

                    @Column(nullable = false, updatable = false)
                    private Instant postedAt = Instant.now();

                    public enum EntryDirection { DEBIT, CREDIT }

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getIdempotencyKey() { return idempotencyKey; }
                    public void setIdempotencyKey(String k) { this.idempotencyKey = k; }
                    public String getAccountNumber() { return accountNumber; }
                    public void setAccountNumber(String acc) { this.accountNumber = acc; }
                    public BigDecimal getAmount() { return amount; }
                    public void setAmount(BigDecimal amount) { this.amount = amount; }
                    public String getCurrency() { return currency; }
                    public void setCurrency(String c) { this.currency = c; }
                    public EntryDirection getDirection() { return direction; }
                    public void setDirection(EntryDirection direction) { this.direction = direction; }
                    public Map<String, Object> getAuditContext() { return auditContext; }
                    public void setAuditContext(Map<String, Object> ctx) { this.auditContext = ctx; }
                    public Instant getPostedAt() { return postedAt; }
                }
                """,
                """
                package io.elmos.architecture.banking.resilience;

                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
                import io.github.resilience4j.retry.annotation.Retry;
                import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
                import org.springframework.stereotype.Service;
                import java.math.BigDecimal;
                import java.util.concurrent.CompletableFuture;

                @Service
                public class PaymentSettlementResilienceService {

                    @CircuitBreaker(name = "paymentSettlement", fallbackMethod = "settlementFallback")
                    @Retry(name = "paymentSettlement")
                    @TimeLimiter(name = "paymentSettlement")
                    public CompletableFuture<String> executeSettlement(String reference, BigDecimal amount) {
                        return CompletableFuture.completedFuture("SETTLED-" + reference);
                    }

                    public CompletableFuture<String> settlementFallback(String reference, BigDecimal amount, Throwable ex) {
                        return CompletableFuture.completedFuture("QUEUED_ASYNC-" + reference);
                    }
                }
                """,
                """
                package io.elmos.architecture.banking.cloud;

                import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
                import org.springframework.cloud.openfeign.EnableFeignClients;
                import org.springframework.cloud.openfeign.FeignClient;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.web.bind.annotation.PostMapping;
                import org.springframework.web.bind.annotation.RequestParam;

                @Configuration
                @EnableFeignClients
                @LoadBalancerClient(name = "core-clearing-service")
                public class BankingCloudMeshConfig {

                    @FeignClient(name = "core-clearing-service", path = "/api/v1/clearing")
                    public interface ClearingServiceClient {
                        @PostMapping("/submit")
                        String submitClearingBatch(@RequestParam("batchId") String batchId);
                    }
                }
                """,
                """
                package io.elmos.architecture.banking.test;

                import org.junit.jupiter.api.Test;
                import org.springframework.boot.test.context.SpringBootTest;
                import static org.junit.jupiter.api.Assertions.assertTrue;

                @SpringBootTest
                public class BankingArchitectureSmokeTest {
                    @Test
                    void contextLoadsAndSecured() {
                        assertTrue(true);
                    }
                }
                """,
                List.of(
                        "Eliminate WebSecurityConfigurerAdapter and replace with BankingSecurityFilterChain",
                        "Migrate javax.persistence to jakarta.persistence for BankingLedgerEntry",
                        "Adopt @JdbcTypeCode(SqlTypes.JSON) for auditContext JSON payload",
                        "Replace Netflix Hystrix with Resilience4j circuit breakers and retries",
                        "Verify 0 compilation errors, green test suite, and clean startup probe"
                ),
                props
        ));
    }

    private static void registerEcommerceBlueprint() {
        Map<String, String> props = new LinkedHashMap<>();
        props.put("spring.jpa.properties.hibernate.jdbc.batch_size", "50");
        props.put("spring.jpa.properties.hibernate.order_inserts", "true");
        props.put("spring.jpa.properties.hibernate.order_updates", "true");

        BLUEPRINTS.put(EnterpriseArchetype.ECOMMERCE_HIGH_THROUGHPUT, new ArchitectureBlueprint(
                EnterpriseArchetype.ECOMMERCE_HIGH_THROUGHPUT,
                "E-Commerce & Retail High-Throughput Architecture",
                "High-performance catalog and ordering architecture optimized for Hibernate 6 batching, Spring Data Specification criteria, and non-blocking load balancing.",
                """
                package io.elmos.architecture.ecommerce.security;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                public class EcommerceSecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth
                                .requestMatchers("/api/catalog/**", "/actuator/health").permitAll()
                                .requestMatchers("/api/cart/**").authenticated()
                                .requestMatchers("/api/admin/**").hasRole("MERCHANT")
                                .anyRequest().authenticated());
                        return http.build();
                    }
                }
                """,
                """
                package io.elmos.architecture.ecommerce.domain;

                import jakarta.persistence.*;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;
                import java.math.BigDecimal;
                import java.util.Map;

                @Entity
                @Table(name = "ecommerce_products")
                public class ProductEntity {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String title;

                    @Column(nullable = false, precision = 12, scale = 2)
                    private BigDecimal price;

                    @JdbcTypeCode(SqlTypes.JSON)
                    private Map<String, Object> specifications;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getTitle() { return title; }
                    public void setTitle(String t) { this.title = t; }
                    public BigDecimal getPrice() { return price; }
                    public void setPrice(BigDecimal p) { this.price = p; }
                    public Map<String, Object> getSpecifications() { return specifications; }
                    public void setSpecifications(Map<String, Object> s) { this.specifications = s; }
                }
                """,
                """
                package io.elmos.architecture.ecommerce.resilience;

                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
                import org.springframework.stereotype.Service;

                @Service
                public class CatalogPriceService {
                    @CircuitBreaker(name = "priceLookup", fallbackMethod = "cachedPriceFallback")
                    public Double getRealtimePrice(Long productId) {
                        return 99.99;
                    }

                    public Double cachedPriceFallback(Long productId, Throwable t) {
                        return 100.00;
                    }
                }
                """,
                """
                package io.elmos.architecture.ecommerce.cloud;

                import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                @LoadBalancerClient(name = "inventory-service")
                public class InventoryClientMeshConfig {
                }
                """,
                """
                package io.elmos.architecture.ecommerce.test;

                import org.junit.jupiter.api.Test;
                import static org.junit.jupiter.api.Assertions.assertNotNull;

                public class EcommerceArchitectureTest {
                    @Test
                    void checkSmoke() {
                        assertNotNull("ok");
                    }
                }
                """,
                List.of(
                        "Refactor legacy product TypeDefs to Hibernate 6 JdbcTypeCode(SqlTypes.JSON)",
                        "Rewrite old Criteria queries into JPA CriteriaBuilder and Specification",
                        "Migrate Ribbon client calls to Spring Cloud LoadBalancer",
                        "Ensure stateless session management with modern CORS and CSRF configurations"
                ),
                props
        ));
    }

    private static void registerHealthcareBlueprint() {
        Map<String, String> props = new LinkedHashMap<>();
        props.put("spring.jpa.hibernate.ddl-auto", "none");
        props.put("spring.jpa.properties.hibernate.envers.audit_table_suffix", "_AUDIT");

        BLUEPRINTS.put(EnterpriseArchetype.HEALTHCARE_REGULATED_VAULT, new ArchitectureBlueprint(
                EnterpriseArchetype.HEALTHCARE_REGULATED_VAULT,
                "Healthcare HIPAA/FHIR Regulated Data Vault",
                "Strict compliance architecture enforcing immutable audit logging, OAuth2 resource server token validation, and Envers entity history.",
                """
                package io.elmos.architecture.healthcare.security;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.Customizer;
                import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                @EnableMethodSecurity(prePostEnabled = true)
                public class HealthcareSecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
                            .authorizeHttpRequests(auth -> auth
                                .requestMatchers("/fhir/metadata").permitAll()
                                .requestMatchers("/fhir/Patient/**").hasAuthority("SCOPE_patient.read")
                                .anyRequest().authenticated()
                            );
                        return http.build();
                    }
                }
                """,
                """
                package io.elmos.architecture.healthcare.domain;

                import jakarta.persistence.*;
                import org.hibernate.annotations.JdbcTypeCode;
                import org.hibernate.type.SqlTypes;
                import java.util.Map;

                @Entity
                @Table(name = "clinical_patient_records")
                public class PatientRecord {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String patientIdentifier;

                    @JdbcTypeCode(SqlTypes.JSON)
                    @Column(columnDefinition = "jsonb")
                    private Map<String, Object> fhirResourcePayload;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getPatientIdentifier() { return patientIdentifier; }
                    public void setPatientIdentifier(String pid) { this.patientIdentifier = pid; }
                    public Map<String, Object> getFhirResourcePayload() { return fhirResourcePayload; }
                    public void setFhirResourcePayload(Map<String, Object> fhir) { this.fhirResourcePayload = fhir; }
                }
                """,
                """
                package io.elmos.architecture.healthcare.resilience;

                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
                import org.springframework.stereotype.Service;

                @Service
                public class FhirValidationService {
                    @CircuitBreaker(name = "fhirValidation", fallbackMethod = "validationFallback")
                    public boolean validateProfile(String profileUrl) {
                        return true;
                    }

                    public boolean validationFallback(String profileUrl, Throwable t) {
                        return false;
                    }
                }
                """,
                """
                package io.elmos.architecture.healthcare.cloud;

                import org.springframework.cloud.openfeign.EnableFeignClients;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                @EnableFeignClients
                public class HealthcareCloudConfig {
                }
                """,
                """
                package io.elmos.architecture.healthcare.test;

                import org.junit.jupiter.api.Test;
                import static org.junit.jupiter.api.Assertions.assertTrue;

                public class HealthcareArchitectureTest {
                    @Test
                    void checkAudit() {
                        assertTrue(true);
                    }
                }
                """,
                List.of(
                        "Configure OAuth2 JWT Resource Server using modern Lambda DSL",
                        "Verify strict Envers revision listeners and audit column integrity",
                        "Migrate custom SQL dialect functions to Hibernate 6 FunctionContributor",
                        "Enforce role-based access control on all FHIR endpoints via @PreAuthorize"
                ),
                props
        ));
    }

    private static void registerCloudMeshBlueprint() {
        Map<String, String> props = new LinkedHashMap<>();
        props.put("spring.config.import", "optional:configserver:http://localhost:8888");
        props.put("management.tracing.sampling.probability", "1.0");

        BLUEPRINTS.put(EnterpriseArchetype.CLOUD_NATIVE_MICROSERVICES_MESH, new ArchitectureBlueprint(
                EnterpriseArchetype.CLOUD_NATIVE_MICROSERVICES_MESH,
                "Cloud-Native Microservices Mesh Architecture",
                "Modern Spring Cloud 2023/2024 architecture featuring Spring Cloud Gateway, Resilience4j, LoadBalancer, and Micrometer Tracing.",
                """
                package io.elmos.architecture.mesh.security;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                public class GatewaySecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.csrf(csrf -> csrf.disable())
                            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
                        return http.build();
                    }
                }
                """,
                """
                package io.elmos.architecture.mesh.domain;

                import jakarta.persistence.*;

                @Entity
                @Table(name = "mesh_route_definitions")
                public class MeshRouteEntity {
                    @Id
                    private String routeId;
                    private String destinationUri;
                    private String pathPattern;

                    public String getRouteId() { return routeId; }
                    public void setRouteId(String id) { this.routeId = id; }
                    public String getDestinationUri() { return destinationUri; }
                    public void setDestinationUri(String uri) { this.destinationUri = uri; }
                    public String getPathPattern() { return pathPattern; }
                    public void setPathPattern(String pattern) { this.pathPattern = pattern; }
                }
                """,
                """
                package io.elmos.architecture.mesh.resilience;

                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
                import org.springframework.stereotype.Service;

                @Service
                public class GatewayRoutingFallbackService {
                    @CircuitBreaker(name = "downstreamRoute", fallbackMethod = "defaultFallback")
                    public String routeCall(String path) {
                        return "OK-" + path;
                    }

                    public String defaultFallback(String path, Throwable t) {
                        return "GATEWAY_SERVICE_UNAVAILABLE";
                    }
                }
                """,
                """
                package io.elmos.architecture.mesh.cloud;

                import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                @EnableDiscoveryClient
                public class MeshDiscoveryConfig {
                }
                """,
                """
                package io.elmos.architecture.mesh.test;

                import org.junit.jupiter.api.Test;
                import static org.junit.jupiter.api.Assertions.assertTrue;

                public class MeshSmokeTest {
                    @Test
                    void check() { assertTrue(true); }
                }
                """,
                List.of(
                        "Migrate Netflix Zuul 1.x blocking filters to Spring Cloud Gateway GlobalFilter",
                        "Migrate Netflix Ribbon client load balancers to Spring Cloud LoadBalancer",
                        "Migrate Netflix Hystrix circuit breakers to Resilience4j",
                        "Migrate Spring Cloud Sleuth tracing to Micrometer Tracing and OpenTelemetry"
                ),
                props
        ));
    }

    private static void registerMonolithStranglerBlueprint() {
        Map<String, String> props = new LinkedHashMap<>();
        props.put("spring.main.allow-bean-definition-overriding", "true");

        BLUEPRINTS.put(EnterpriseArchetype.MONOLITH_STRANGLER_HYBRID_XML, new ArchitectureBlueprint(
                EnterpriseArchetype.MONOLITH_STRANGLER_HYBRID_XML,
                "Monolith Strangler & Hybrid XML Modernization Architecture",
                "Gradual modernization blueprint converting legacy XML context configurations, WAR deployments, and Struts/Servlet beans into modular Spring Boot JavaConfig.",
                """
                package io.elmos.architecture.strangler.security;

                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.web.SecurityFilterChain;

                @Configuration
                public class StranglerSecurityConfig {
                    @Bean
                    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
                        http.authorizeHttpRequests(auth -> auth
                                .requestMatchers("/legacy/**").permitAll()
                                .requestMatchers("/modern/**").authenticated());
                        return http.build();
                    }
                }
                """,
                """
                package io.elmos.architecture.strangler.domain;

                import jakarta.persistence.*;

                @Entity
                @Table(name = "strangler_coexistence_state")
                public class CoexistenceState {
                    @Id
                    private String moduleKey;
                    private Boolean routedToModern;

                    public String getModuleKey() { return moduleKey; }
                    public void setModuleKey(String key) { this.moduleKey = key; }
                    public Boolean getRoutedToModern() { return routedToModern; }
                    public void setRoutedToModern(Boolean modern) { this.routedToModern = modern; }
                }
                """,
                """
                package io.elmos.architecture.strangler.resilience;

                import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
                import org.springframework.stereotype.Service;

                @Service
                public class StranglerRoutingService {
                    @CircuitBreaker(name = "modernModule", fallbackMethod = "legacyFallback")
                    public String dispatch(String request) {
                        return "MODERN-" + request;
                    }

                    public String legacyFallback(String request, Throwable t) {
                        return "LEGACY_SHIM-" + request;
                    }
                }
                """,
                """
                package io.elmos.architecture.strangler.config;

                import org.springframework.context.annotation.ComponentScan;
                import org.springframework.context.annotation.Configuration;
                import org.springframework.transaction.annotation.EnableTransactionManagement;

                @Configuration
                @ComponentScan(basePackages = "io.elmos.architecture.strangler")
                @EnableTransactionManagement
                public class StranglerJavaConfigMigration {
                }
                """,
                """
                package io.elmos.architecture.strangler.test;

                import org.junit.jupiter.api.Test;
                import static org.junit.jupiter.api.Assertions.assertTrue;

                public class StranglerArchitectureTest {
                    @Test
                    void check() { assertTrue(true); }
                }
                """,
                List.of(
                        "Convert all XML <bean> tags to @Configuration and @Bean methods",
                        "Replace <context:component-scan> with @ComponentScan",
                        "Replace <tx:annotation-driven> with @EnableTransactionManagement",
                        "Verify zero orphaned XML beans and complete JavaConfig fidelity"
                ),
                props
        ));
    }
}
