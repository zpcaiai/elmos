"""Comprehensive tests for AST-driven migrators without regex heuristics.

Tests Spring Security AST transformation, JPA Criteria AST modernization,
Transaction Boundary AST isolation, and Spring XML Bean AST compilation.
"""

from __future__ import annotations

import unittest

from elmos_legacy_web_modernization.java_ast_toolkit import JavaAstParser
from elmos_legacy_web_modernization.jpa_persistence_migrator import JpaPersistenceMigrator
from elmos_legacy_web_modernization.security_migrator import SpringSecurityMigrator
from elmos_legacy_web_modernization.transaction_boundary_migrator import TransactionBoundaryMigrator
from elmos_legacy_web_modernization.xml_bean_compiler import SpringXmlSemanticAstCompiler


class AstMigratorsComprehensiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.security_migrator = SpringSecurityMigrator()
        self.jpa_migrator = JpaPersistenceMigrator()
        self.tx_migrator = TransactionBoundaryMigrator()
        self.xml_compiler = SpringXmlSemanticAstCompiler()

    def test_spring_security_ast_migration_complex(self) -> None:
        legacy_code = """
package com.example.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

@Configuration
public class WebSecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .csrf().disable()
            .authorizeRequests()
                .antMatchers("/public/**", "/health").permitAll()
                .antMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .cors().and();
    }
}
"""
        result = self.security_migrator.migrate(legacy_code)
        self.assertTrue(result.has_security_config)
        self.assertIn("WebSecurityConfigurerAdapter", result.deprecated_features_removed)
        self.assertNotIn("extends WebSecurityConfigurerAdapter", result.migrated_code)
        self.assertIn("public SecurityFilterChain filterChain(HttpSecurity http)", result.migrated_code)
        self.assertIn("@Bean", result.migrated_code)
        self.assertIn("authorizeHttpRequests()", result.migrated_code)
        self.assertIn("requestMatchers", result.migrated_code)
        self.assertNotIn("antMatchers", result.migrated_code)
        self.assertIn(".csrf(csrf -> csrf.disable())", result.migrated_code)
        self.assertIn("return http.build();", result.migrated_code)
        self.assertIn("import org.springframework.security.web.SecurityFilterChain;", result.migrated_code)

    def test_jpa_typedef_and_type_ast_migration(self) -> None:
        legacy_entity = """
package com.example.entity;

import javax.persistence.Entity;
import javax.persistence.Id;
import org.hibernate.annotations.Type;
import org.hibernate.annotations.TypeDef;
import com.vladmihalcea.hibernate.type.json.JsonBinaryType;

@TypeDef(name = "jsonb", typeClass = JsonBinaryType.class)
@Entity
public class OrderEntity {
    @Id
    private Long id;

    @Type(type = "jsonb")
    private Map<String, Object> metadata;

    @Type(type = "org.hibernate.type.TextType")
    private String description;
}
"""
        res = self.jpa_migrator.migrate_entity_source(legacy_entity)
        self.assertTrue(res.has_jpa_config)
        self.assertIn("@TypeDef", res.deprecated_annotations_removed)
        self.assertIn("@Type", res.deprecated_annotations_removed)
        self.assertNotIn("@TypeDef", res.migrated_content)
        self.assertNotIn("@Type(type", res.migrated_content)
        self.assertIn("@JdbcTypeCode(SqlTypes.JSON)", res.migrated_content)
        self.assertIn('@Column(columnDefinition = "text")', res.migrated_content)
        self.assertIn("import org.hibernate.annotations.JdbcTypeCode;", res.migrated_content)
        self.assertIn("import org.hibernate.type.SqlTypes;", res.migrated_content)

    def test_jpa_criteria_to_criteriabuilder_ast_migration(self) -> None:
        legacy_criteria_code = """
package com.example.dao;

import org.hibernate.Criteria;
import org.hibernate.Session;
import org.hibernate.criterion.Restrictions;
import org.hibernate.criterion.Order;

public class EmployeeDao {
    public List<Employee> findActive(Session session, String dept) {
        Criteria cr = session.createCriteria(Employee.class);
        cr.add(Restrictions.eq("department", dept));
        cr.add(Restrictions.gt("salary", 50000));
        cr.addOrder(Order.asc("lastName"));
        return cr.list();
    }
}
"""
        res = self.jpa_migrator.migrate_criteria_query_source(legacy_criteria_code)
        self.assertTrue(res.has_jpa_config)
        self.assertNotIn("import org.hibernate.Criteria;", res.migrated_content)
        self.assertIn("import jakarta.persistence.criteria.CriteriaBuilder;", res.migrated_content)
        self.assertIn("import jakarta.persistence.criteria.CriteriaQuery;", res.migrated_content)
        self.assertIn("CriteriaQuery<?> cr", res.migrated_content)
        self.assertIn("cb.eq", res.migrated_content)

    def test_transaction_boundary_disambiguation_ast(self) -> None:
        legacy_config = """
package com.example.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class DataSourceConfig {

    @Bean
    public PlatformTransactionManager primaryTxManager() {
        return new DataSourceTransactionManager();
    }

    @Bean
    public PlatformTransactionManager secondaryTxManager() {
        return new JpaTransactionManager();
    }
}
"""
        res = self.tx_migrator.migrate_configuration(legacy_config, default_primary_bean="primaryTxManager")
        self.assertTrue(res.has_transaction_config)
        self.assertIn("primaryTxManager", res.disambiguated_managers)
        self.assertIn("@Primary\n    @Bean\n    public PlatformTransactionManager primaryTxManager()", res.migrated_code)
        self.assertNotIn("@Primary\n    @Bean\n    public PlatformTransactionManager secondaryTxManager()", res.migrated_code)

    def test_transaction_service_qualification_ast(self) -> None:
        service_code = """
package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @Transactional
    public void processOrder(Long orderId) {
        // ...
    }

    @Transactional()
    public void cancelOrder(Long orderId) {
        // ...
    }
}
"""
        res = self.tx_migrator.qualify_service_transactions(service_code, "primaryTxManager")
        self.assertTrue(res.has_transaction_config)
        self.assertIn('@Transactional("primaryTxManager")', res.migrated_code)
        self.assertNotIn("@Transactional\n", res.migrated_code)

    def test_spring_xml_to_javaconfig_ast_compilation(self) -> None:
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:tx="http://www.springframework.org/schema/tx">

    <context:component-scan base-package="com.example.app"/>
    <tx:annotation-driven/>

    <bean id="orderRepository" class="com.example.repo.OrderRepositoryImpl">
        <property name="timeoutSeconds" value="30"/>
    </bean>

    <bean id="orderService" class="com.example.service.OrderServiceImpl" init-method="init" destroy-method="cleanup">
        <constructor-arg ref="orderRepository"/>
        <property name="serviceName" value="OrderProcessingService"/>
    </bean>
</beans>
"""
        res = self.xml_compiler.compile_to_javaconfig(
            xml_content,
            config_class_name="AppConfig",
            package_name="com.example.config",
        )
        self.assertEqual(res.config_class_name, "AppConfig")
        self.assertIn("orderRepository", res.beans_converted)
        self.assertIn("orderService", res.beans_converted)
        self.assertIn("@Configuration", res.java_code)
        self.assertIn('@ComponentScan("com.example.app")', res.java_code)
        self.assertIn("@EnableTransactionManagement", res.java_code)
        self.assertIn("public OrderRepositoryImpl orderRepository()", res.java_code)
        self.assertIn('@Bean(initMethod = "init", destroyMethod = "cleanup")', res.java_code)
        self.assertIn("public OrderServiceImpl orderService(OrderRepositoryImpl orderRepository)", res.java_code)
        self.assertIn("new OrderServiceImpl(orderRepository);", res.java_code)


if __name__ == "__main__":
    unittest.main()
