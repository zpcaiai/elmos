package io.elmos.worker.corpus;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Rich enterprise scenario specifications for Benchmark Projects 21 through 30.
 */
public final class SpringCorpusEnterpriseProjectsPart3 {

    private SpringCorpusEnterpriseProjectsPart3() {}

    public static Map<String, String> getFilesForProject(int index, String id, String bootVer, String javaVer) {
        Map<String, String> files = new LinkedHashMap<>();
        switch (index) {
            case 21 -> populateMultiModuleReactor(files, id, bootVer, javaVer);
            case 22 -> populateEventDrivenMessagingOrders(files, id, bootVer, javaVer);
            case 23 -> populateDataRestHalCatalog(files, id, bootVer, javaVer);
            case 24 -> populateGraphqlHybridService(files, id, bootVer, javaVer);
            case 25 -> populateSaasTenantProvisioner(files, id, bootVer, javaVer);
            case 26 -> populateLegacySecurityMethodGuard(files, id, bootVer, javaVer);
            case 27 -> populateDistributedRedisCacheResilience(files, id, bootVer, javaVer);
            case 28 -> populateAuditComplianceVault(files, id, bootVer, javaVer);
            case 29 -> populateLegacyHqlWarehouse(files, id, bootVer, javaVer);
            case 30 -> populateSpringCloudFullSuite(files, id, bootVer, javaVer);
            default -> {}
        }
        return files;
    }

    private static void populateMultiModuleReactor(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/reactor/domain/ReactorEntity.java", """
                package io.elmos.benchmark.reactor.domain;

                import javax.persistence.*;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "reactor_entities")
                public class ReactorEntity {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    private String moduleName;

                    @Type(type = "json")
                    private String moduleConfig;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getModuleName() { return moduleName; }
                    public void setModuleName(String m) { this.moduleName = m; }
                    public String getModuleConfig() { return moduleConfig; }
                    public void setModuleConfig(String c) { this.moduleConfig = c; }
                }
                """);
    }

    private static void populateEventDrivenMessagingOrders(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/events/OrderEventPublisher.java", """
                package io.elmos.benchmark.events;

                import org.springframework.stereotype.Component;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @Component
                public class OrderEventPublisher {

                    @HystrixCommand(fallbackMethod = "publishFallback")
                    public boolean publishEvent(String topic, String payload) {
                        return true;
                    }

                    public boolean publishFallback(String topic, String payload) {
                        return false;
                    }
                }
                """);
    }

    private static void populateDataRestHalCatalog(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/catalog/domain/CatalogItem.java", """
                package io.elmos.benchmark.catalog.domain;

                import javax.persistence.*;
                import org.hibernate.annotations.Type;

                @Entity
                public class CatalogItem {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    private String title;

                    @Type(type = "json")
                    private String attributes;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getTitle() { return title; }
                    public void setTitle(String t) { this.title = t; }
                    public String getAttributes() { return attributes; }
                    public void setAttributes(String a) { this.attributes = a; }
                }
                """);
    }

    private static void populateGraphqlHybridService(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/graphql/GraphqlSecurityConfig.java", """
                package io.elmos.benchmark.graphql;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;

                @Configuration
                public class GraphqlSecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.csrf().disable()
                            .authorizeRequests()
                            .antMatchers("/graphql").permitAll()
                            .anyRequest().authenticated();
                    }
                }
                """);
    }

    private static void populateSaasTenantProvisioner(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/tenant/domain/TenantProfile.java", """
                package io.elmos.benchmark.tenant.domain;

                import javax.persistence.*;
                import org.hibernate.annotations.Type;

                @Entity
                public class TenantProfile {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(unique = true, nullable = false)
                    private String tenantIdentifier;

                    @Type(type = "json")
                    private String isolationSettings;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getTenantIdentifier() { return tenantIdentifier; }
                    public void setTenantIdentifier(String id) { this.tenantIdentifier = id; }
                    public String getIsolationSettings() { return isolationSettings; }
                    public void setIsolationSettings(String s) { this.isolationSettings = s; }
                }
                """);
    }

    private static void populateLegacySecurityMethodGuard(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/guard/MethodGuardConfig.java", """
                package io.elmos.benchmark.guard;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @Configuration
                @EnableGlobalMethodSecurity(prePostEnabled = true, securedEnabled = true)
                public class MethodGuardConfig {
                }
                """);
    }

    private static void populateDistributedRedisCacheResilience(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/cache/CacheResilienceService.java", """
                package io.elmos.benchmark.cache;

                import org.springframework.stereotype.Service;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @Service
                public class CacheResilienceService {

                    @HystrixCommand(fallbackMethod = "getCachedFallback")
                    public String getWithFallback(String key) {
                        return "fromCache-" + key;
                    }

                    public String getCachedFallback(String key) {
                        return "offlineCache-" + key;
                    }
                }
                """);
    }

    private static void populateAuditComplianceVault(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/vault/domain/AuditVaultRecord.java", """
                package io.elmos.benchmark.vault.domain;

                import javax.persistence.*;
                import org.hibernate.annotations.Type;

                @Entity
                public class AuditVaultRecord {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    private String complianceHash;

                    @Type(type = "json")
                    private String tamperSealData;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getComplianceHash() { return complianceHash; }
                    public void setComplianceHash(String h) { this.complianceHash = h; }
                    public String getTamperSealData() { return tamperSealData; }
                    public void setTamperSealData(String d) { this.tamperSealData = d; }
                }
                """);
    }

    private static void populateLegacyHqlWarehouse(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/warehouse/domain/WarehouseFact.java", """
                package io.elmos.benchmark.warehouse.domain;

                import javax.persistence.*;
                import org.hibernate.Criteria;

                @Entity
                public class WarehouseFact {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    private String metricKey;
                    private Double metricValue;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getMetricKey() { return metricKey; }
                    public void setMetricKey(String k) { this.metricKey = k; }
                    public Double getMetricValue() { return metricValue; }
                    public void setMetricValue(Double v) { this.metricValue = v; }
                }
                """);
    }

    private static void populateSpringCloudFullSuite(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/suite/FullSuiteApplication.java", """
                package io.elmos.benchmark.suite;

                import org.springframework.boot.SpringApplication;
                import org.springframework.boot.autoconfigure.SpringBootApplication;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;
                import org.springframework.cloud.netflix.feign.EnableFeignClients;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @SpringBootApplication
                @EnableZuulProxy
                @EnableFeignClients
                @RibbonClient(name = "full-suite-service")
                public class FullSuiteApplication {

                    @HystrixCommand(fallbackMethod = "suiteFallback")
                    public String executeFullSuite() {
                        return "FullSuiteOK";
                    }

                    public String suiteFallback() {
                        return "FullSuiteFallback";
                    }

                    public static void main(String[] args) {
                        SpringApplication.run(FullSuiteApplication.class, args);
                    }
                }
                """);
        files.put("src/main/resources/bootstrap.yml", """
                spring:
                  application:
                    name: spring-cloud-full-suite
                  cloud:
                    config:
                      uri: http://config-server:8888
                """);
    }
}
