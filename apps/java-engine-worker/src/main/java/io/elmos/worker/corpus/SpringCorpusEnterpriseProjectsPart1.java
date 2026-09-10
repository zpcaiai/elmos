package io.elmos.worker.corpus;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Rich enterprise scenario specifications for Benchmark Projects 01 through 10.
 * Provides authentic, high-complexity domain code across Security, JPA, Cloud, and XML.
 */
public final class SpringCorpusEnterpriseProjectsPart1 {

    private SpringCorpusEnterpriseProjectsPart1() {}

    public static Map<String, String> getFilesForProject(int index, String id, String bootVer, String javaVer) {
        Map<String, String> files = new LinkedHashMap<>();
        switch (index) {
            case 1 -> populateEcommerceMall(files, id, bootVer, javaVer);
            case 2 -> populateBankingPaymentGateway(files, id, bootVer, javaVer);
            case 3 -> populateEnterpriseErpCore(files, id, bootVer, javaVer);
            case 4 -> populateCloudMicroservicesGateway(files, id, bootVer, javaVer);
            case 5 -> populateCloudResilienceOrders(files, id, bootVer, javaVer);
            case 6 -> populateLegacyXmlCms(files, id, bootVer, javaVer);
            case 7 -> populateHybridXmlCrm(files, id, bootVer, javaVer);
            case 8 -> populateRbacMultiTenantAuth(files, id, bootVer, javaVer);
            case 9 -> populateJpaComplexReporting(files, id, bootVer, javaVer);
            case 10 -> populateCloudOpenFeignInventory(files, id, bootVer, javaVer);
            default -> {}
        }
        return files;
    }

    private static void populateEcommerceMall(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/ecommerce/domain/Product.java", """
                package io.elmos.benchmark.ecommerce.domain;

                import javax.persistence.*;
                import java.math.BigDecimal;
                import java.time.Instant;
                import org.hibernate.annotations.TypeDef;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "products")
                @TypeDef(name = "json", typeClass = String.class)
                public class Product {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false)
                    private String sku;

                    @Column(nullable = false)
                    private String title;

                    @Column(nullable = false, precision = 12, scale = 2)
                    private BigDecimal price;

                    private Integer stockQuantity;

                    @Type(type = "json")
                    @Column(columnDefinition = "json")
                    private String metadata;

                    private Instant createdAt;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getSku() { return sku; }
                    public void setSku(String sku) { this.sku = sku; }
                    public String getTitle() { return title; }
                    public void setTitle(String title) { this.title = title; }
                    public BigDecimal getPrice() { return price; }
                    public void setPrice(BigDecimal price) { this.price = price; }
                    public Integer getStockQuantity() { return stockQuantity; }
                    public void setStockQuantity(Integer stockQuantity) { this.stockQuantity = stockQuantity; }
                    public String getMetadata() { return metadata; }
                    public void setMetadata(String metadata) { this.metadata = metadata; }
                    public Instant getCreatedAt() { return createdAt; }
                    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/ecommerce/domain/CustomerOrder.java", """
                package io.elmos.benchmark.ecommerce.domain;

                import javax.persistence.*;
                import java.math.BigDecimal;
                import java.time.Instant;
                import java.util.ArrayList;
                import java.util.List;

                @Entity
                @Table(name = "customer_orders")
                public class CustomerOrder {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String orderNumber;

                    @Column(nullable = false)
                    private Long customerId;

                    @Column(nullable = false, precision = 14, scale = 2)
                    private BigDecimal totalAmount;

                    private String status;
                    private Instant placedAt;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getOrderNumber() { return orderNumber; }
                    public void setOrderNumber(String orderNumber) { this.orderNumber = orderNumber; }
                    public Long getCustomerId() { return customerId; }
                    public void setCustomerId(Long customerId) { this.customerId = customerId; }
                    public BigDecimal getTotalAmount() { return totalAmount; }
                    public void setTotalAmount(BigDecimal totalAmount) { this.totalAmount = totalAmount; }
                    public String getStatus() { return status; }
                    public void setStatus(String status) { this.status = status; }
                    public Instant getPlacedAt() { return placedAt; }
                    public void setPlacedAt(Instant placedAt) { this.placedAt = placedAt; }
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/ecommerce/repository/ProductRepository.java", """
                package io.elmos.benchmark.ecommerce.repository;

                import io.elmos.benchmark.ecommerce.domain.Product;
                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import org.springframework.data.repository.query.Param;
                import java.math.BigDecimal;
                import java.util.List;
                import java.util.Optional;

                public interface ProductRepository extends JpaRepository<Product, Long> {
                    Optional<Product> findBySku(String sku);

                    @Query("SELECT p FROM Product p WHERE p.price BETWEEN ? AND ?")
                    List<Product> findByPriceRange(BigDecimal min, BigDecimal max);
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/ecommerce/config/SecurityConfig.java", """
                package io.elmos.benchmark.ecommerce.config;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @Configuration
                @EnableGlobalMethodSecurity(prePostEnabled = true)
                public class SecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.csrf().disable()
                            .authorizeRequests()
                            .antMatchers("/api/public/**", "/actuator/health").permitAll()
                            .antMatchers("/api/admin/**").hasRole("ADMIN")
                            .anyRequest().authenticated()
                            .and()
                            .formLogin().disable();
                    }
                }
                """);
    }

    private static void populateBankingPaymentGateway(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/banking/domain/PaymentTransaction.java", """
                package io.elmos.benchmark.banking.domain;

                import javax.persistence.*;
                import java.math.BigDecimal;
                import java.time.Instant;
                import org.hibernate.annotations.TypeDef;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "payment_transactions")
                @TypeDef(name = "json", typeClass = String.class)
                public class PaymentTransaction {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String transactionReference;

                    @Column(nullable = false)
                    private String sourceAccount;

                    @Column(nullable = false)
                    private String destinationAccount;

                    @Column(nullable = false, precision = 18, scale = 4)
                    private BigDecimal amount;

                    private String currency;
                    private String status;

                    @Type(type = "json")
                    private String auditPayload;

                    private Instant initiatedAt;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getTransactionReference() { return transactionReference; }
                    public void setTransactionReference(String ref) { this.transactionReference = ref; }
                    public String getSourceAccount() { return sourceAccount; }
                    public void setSourceAccount(String acc) { this.sourceAccount = acc; }
                    public String getDestinationAccount() { return destinationAccount; }
                    public void setDestinationAccount(String acc) { this.destinationAccount = acc; }
                    public BigDecimal getAmount() { return amount; }
                    public void setAmount(BigDecimal amount) { this.amount = amount; }
                    public String getCurrency() { return currency; }
                    public void setCurrency(String c) { this.currency = c; }
                    public String getStatus() { return status; }
                    public void setStatus(String status) { this.status = status; }
                    public String getAuditPayload() { return auditPayload; }
                    public void setAuditPayload(String p) { this.auditPayload = p; }
                    public Instant getInitiatedAt() { return initiatedAt; }
                    public void setInitiatedAt(Instant t) { this.initiatedAt = t; }
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/banking/repository/PaymentTransactionRepository.java", """
                package io.elmos.benchmark.banking.repository;

                import io.elmos.benchmark.banking.domain.PaymentTransaction;
                import org.springframework.data.jpa.repository.JpaRepository;
                import org.springframework.data.jpa.repository.Query;
                import org.hibernate.Criteria;
                import java.util.List;
                import java.util.Optional;

                public interface PaymentTransactionRepository extends JpaRepository<PaymentTransaction, Long> {
                    Optional<PaymentTransaction> findByTransactionReference(String ref);

                    @Query("SELECT t FROM PaymentTransaction t WHERE t.sourceAccount = ? AND t.status = ?")
                    List<PaymentTransaction> findByAccountAndStatus(String acc, String status);
                }
                """);
    }

    private static void populateEnterpriseErpCore(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/erp/domain/InventoryItem.java", """
                package io.elmos.benchmark.erp.domain;

                import javax.persistence.*;
                import java.math.BigDecimal;
                import org.hibernate.annotations.Type;

                @Entity
                @Table(name = "inventory_items")
                public class InventoryItem {
                    @Id
                    @GeneratedValue(strategy = GenerationType.IDENTITY)
                    private Long id;

                    @Column(nullable = false, unique = true)
                    private String partNumber;

                    private String warehouseCode;
                    private Integer onHandQuantity;
                    private Integer reservedQuantity;

                    @Type(type = "json")
                    private String supplierSpecifications;

                    public Long getId() { return id; }
                    public void setId(Long id) { this.id = id; }
                    public String getPartNumber() { return partNumber; }
                    public void setPartNumber(String partNumber) { this.partNumber = partNumber; }
                    public String getWarehouseCode() { return warehouseCode; }
                    public void setWarehouseCode(String warehouseCode) { this.warehouseCode = warehouseCode; }
                    public Integer getOnHandQuantity() { return onHandQuantity; }
                    public void setOnHandQuantity(Integer onHandQuantity) { this.onHandQuantity = onHandQuantity; }
                    public Integer getReservedQuantity() { return reservedQuantity; }
                    public void setReservedQuantity(Integer reservedQuantity) { this.reservedQuantity = reservedQuantity; }
                    public String getSupplierSpecifications() { return supplierSpecifications; }
                    public void setSupplierSpecifications(String s) { this.supplierSpecifications = s; }
                }
                """);
    }

    private static void populateCloudMicroservicesGateway(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/gateway/ZuulGatewayConfig.java", """
                package io.elmos.benchmark.gateway;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.cloud.netflix.zuul.EnableZuulProxy;
                import com.netflix.zuul.ZuulFilter;

                @Configuration
                @EnableZuulProxy
                public class ZuulGatewayConfig extends ZuulFilter {
                    public String filterType() { return "pre"; }
                    public int filterOrder() { return 1; }
                    public boolean shouldFilter() { return true; }
                    public Object run() { return null; }
                }
                """);
    }

    private static void populateCloudResilienceOrders(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/orders/OrderResilienceService.java", """
                package io.elmos.benchmark.orders;

                import org.springframework.stereotype.Service;
                import com.netflix.hystrix.contrib.javanica.annotation.HystrixCommand;

                @Service
                public class OrderResilienceService {

                    @HystrixCommand(fallbackMethod = "processOrderFallback")
                    public String executeOrder(String orderId) {
                        return "OrderExecuted-" + orderId;
                    }

                    public String processOrderFallback(String orderId) {
                        return "OrderQueuedOffline-" + orderId;
                    }
                }
                """);
    }

    private static void populateLegacyXmlCms(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/resources/spring-cms-beans.xml", """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xmlns:tx="http://www.springframework.org/schema/tx"
                       xsi:schemaLocation="
                           http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd
                           http://www.springframework.org/schema/context http://www.springframework.org/schema/context/spring-context.xsd
                           http://www.springframework.org/schema/tx http://www.springframework.org/schema/tx/spring-tx.xsd">

                    <context:component-scan base-package="io.elmos.benchmark.cms" />
                    <tx:annotation-driven />

                    <bean id="cmsRenderer" class="io.elmos.benchmark.cms.CmsRenderer">
                        <property name="theme" value="enterprise-dark" />
                    </bean>

                    <bean id="contentFilter" class="io.elmos.benchmark.cms.CmsContentFilter">
                        <property name="filterActive" value="true" />
                    </bean>
                </beans>
                """);

        files.put("src/main/java/io/elmos/benchmark/cms/CmsRenderer.java", """
                package io.elmos.benchmark.cms;

                public class CmsRenderer {
                    private String theme;
                    public String getTheme() { return theme; }
                    public void setTheme(String theme) { this.theme = theme; }
                }
                """);

        files.put("src/main/java/io/elmos/benchmark/cms/CmsContentFilter.java", """
                package io.elmos.benchmark.cms;

                public class CmsContentFilter {
                    private String filterActive;
                    public String getFilterActive() { return filterActive; }
                    public void setFilterActive(String active) { this.filterActive = active; }
                }
                """);
    }

    private static void populateHybridXmlCrm(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/resources/applicationContext-crm.xml", """
                <?xml version="1.0" encoding="UTF-8"?>
                <beans xmlns="http://www.springframework.org/schema/beans"
                       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                       xmlns:context="http://www.springframework.org/schema/context"
                       xsi:schemaLocation="
                           http://www.springframework.org/schema/beans http://www.springframework.org/schema/beans/spring-beans.xsd
                           http://www.springframework.org/schema/context http://www.springframework.org/schema/context/spring-context.xsd">

                    <context:component-scan base-package="io.elmos.benchmark.crm" />

                    <bean id="crmPipelineManager" class="io.elmos.benchmark.crm.CrmPipelineManager">
                        <property name="pipelineName" value="EnterpriseSales" />
                    </bean>
                </beans>
                """);

        files.put("src/main/java/io/elmos/benchmark/crm/CrmPipelineManager.java", """
                package io.elmos.benchmark.crm;

                public class CrmPipelineManager {
                    private String pipelineName;
                    public String getPipelineName() { return pipelineName; }
                    public void setPipelineName(String name) { this.pipelineName = name; }
                }
                """);
    }

    private static void populateRbacMultiTenantAuth(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/rbac/RbacSecurityConfig.java", """
                package io.elmos.benchmark.rbac;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
                import org.springframework.security.config.annotation.web.builders.HttpSecurity;
                import org.springframework.security.config.annotation.method.configuration.EnableGlobalMethodSecurity;

                @Configuration
                @EnableGlobalMethodSecurity(prePostEnabled = true, securedEnabled = true)
                public class RbacSecurityConfig extends WebSecurityConfigurerAdapter {
                    @Override
                    protected void configure(HttpSecurity http) throws Exception {
                        http.csrf().disable()
                            .authorizeRequests()
                            .antMatchers("/api/auth/**").permitAll()
                            .antMatchers("/api/tenant/**").hasAuthority("TENANT_ADMIN")
                            .anyRequest().authenticated();
                    }
                }
                """);
    }

    private static void populateJpaComplexReporting(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/reporting/LegacyCriteriaReporter.java", """
                package io.elmos.benchmark.reporting;

                import org.hibernate.Criteria;

                public class LegacyCriteriaReporter {
                    public void runReport(Criteria criteria) {
                        // Legacy criteria reporting logic
                    }
                }
                """);
    }

    private static void populateCloudOpenFeignInventory(Map<String, String> files, String id, String bootVer, String javaVer) {
        files.put("src/main/java/io/elmos/benchmark/inventory/InventoryClientConfig.java", """
                package io.elmos.benchmark.inventory;

                import org.springframework.context.annotation.Configuration;
                import org.springframework.cloud.netflix.feign.EnableFeignClients;
                import org.springframework.cloud.netflix.ribbon.RibbonClient;

                @Configuration
                @EnableFeignClients
                @RibbonClient(name = "inventory-backend")
                public class InventoryClientConfig {
                }
                """);
    }
}
