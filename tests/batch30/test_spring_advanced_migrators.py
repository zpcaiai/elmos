"""Unit tests for Spring Security, JPA persistence, transaction boundary migrators, and coexistence proxy."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/legacy-web-modernization-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_legacy_web_modernization import (
    SpringSecurityMigrator,
    JpaPersistenceMigrator,
    TransactionBoundaryMigrator,
    CoexistenceStranglerProxy,
    OutboxDualWriteAuditor,
    RouteDestination,
)


class TestSpringSecurityMigrator(unittest.TestCase):
    def setUp(self) -> None:
        self.migrator = SpringSecurityMigrator()

    def test_migrates_web_security_configurer_adapter(self) -> None:
        legacy_code = """package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

@Configuration
public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .csrf().disable()
            .cors().and();
    }
}
"""
        result = self.migrator.migrate(legacy_code)
        self.assertTrue(result.has_security_config)
        self.assertIn("SecurityFilterChain", result.migrated_code)
        self.assertIn("@Bean", result.migrated_code)
        self.assertNotIn("WebSecurityConfigurerAdapter", result.migrated_code)
        self.assertIn("authorizeHttpRequests()", result.migrated_code)
        self.assertIn("requestMatchers(\"/public/**\")", result.migrated_code)
        self.assertIn(".csrf(csrf -> csrf.disable())", result.migrated_code)
        self.assertIn("return http.build();", result.migrated_code)
        self.assertIn("authentication-success-and-failure", result.invariants_preserved)


class TestJpaPersistenceMigrator(unittest.TestCase):
    def setUp(self) -> None:
        self.migrator = JpaPersistenceMigrator()

    def test_migrates_hibernate_dialects_and_custom_types(self) -> None:
        legacy_code = """package com.example.domain;

import org.hibernate.annotations.Type;
import org.hibernate.annotations.TypeDef;
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
@TypeDef(name = "jsonb", typeClass = JsonBinaryType.class)
public class Account {
    @Id
    private Long id;

    @Type(type = "jsonb")
    private Map<String, Object> metadata;
}
"""
        result = self.migrator.migrate_entity_source(legacy_code)
        self.assertTrue(result.has_jpa_config)
        self.assertNotIn("@TypeDef", result.migrated_content)
        self.assertNotIn("@Type(type = \"jsonb\")", result.migrated_content)
        self.assertIn("@JdbcTypeCode(SqlTypes.JSON)", result.migrated_content)
        self.assertIn("import org.hibernate.annotations.JdbcTypeCode;", result.migrated_content)
        self.assertIn("schema-mapping-and-generated-identifiers", result.invariants_preserved)

    def test_migrates_properties_dialect(self) -> None:
        props = """spring.datasource.url=jdbc:postgresql://localhost:5432/mydb
spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.PostgreSQL10Dialect
spring.jpa.show-sql=true
"""
        result = self.migrator.migrate_properties_config(props)
        self.assertIn("org.hibernate.dialect.PostgreSQLDialect", result.migrated_content)
        self.assertNotIn("PostgreSQL10Dialect", result.migrated_content)


class TestTransactionBoundaryMigrator(unittest.TestCase):
    def setUp(self) -> None:
        self.migrator = TransactionBoundaryMigrator()

    def test_disambiguates_multiple_transaction_managers(self) -> None:
        config_code = """package com.example.config;

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
        return new DataSourceTransactionManager();
    }
}
"""
        result = self.migrator.migrate_configuration(config_code)
        self.assertTrue(result.has_transaction_config)
        self.assertIn("@Primary", result.migrated_code)
        self.assertIn("primaryTxManager", result.disambiguated_managers)

    def test_qualifies_unqualified_service_transactions(self) -> None:
        service_code = """package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @Transactional
    public void processOrder() {
        // do work
    }

    @Transactional(readOnly = true)
    public void queryOrder() {
        // query work
    }
}
"""
        result = self.migrator.qualify_service_transactions(service_code, "primaryTxManager")
        self.assertTrue(result.has_transaction_config)
        self.assertIn("@Transactional(\"primaryTxManager\")", result.migrated_code)


class TestCoexistenceStranglerProxy(unittest.TestCase):
    def setUp(self) -> None:
        self.proxy = CoexistenceStranglerProxy(
            legacy_base_url="http://legacy-host:8080",
            modern_base_url="http://modern-host:8081",
        )
        self.proxy.register_migrated_route("/api/v2/orders")
        self.proxy.add_header_rule("X-Force-Target", "modern-preview")
        self.auditor = OutboxDualWriteAuditor()

    def test_route_dispatch(self) -> None:
        # Default unmigrated route goes to legacy
        dec1 = self.proxy.route_request("/api/v1/users")
        self.assertEqual(dec1.destination, RouteDestination.LEGACY)
        self.assertEqual(dec1.target_url, "http://legacy-host:8080/api/v1/users")

        # Migrated route goes to modern
        dec2 = self.proxy.route_request("/api/v2/orders/123")
        self.assertEqual(dec2.destination, RouteDestination.MODERN)
        self.assertEqual(dec2.target_url, "http://modern-host:8081/api/v2/orders/123")

        # Header override takes precedence
        dec3 = self.proxy.route_request("/api/v1/users", headers={"X-Force-Target": "modern-preview"})
        self.assertEqual(dec3.destination, RouteDestination.MODERN)
        self.assertEqual(dec3.target_url, "http://modern-host:8081/api/v1/users")

    def test_outbox_dual_write_audit(self) -> None:
        leg_event = {
            "id": "evt-1",
            "aggregate_type": "Order",
            "topic": "orders.created",
            "payload": {"order_id": "ord-99", "amount": 120.50, "status": "CONFIRMED"},
            "created_at": "2026-06-01T10:00:00Z",
        }
        mod_event = {
            "id": "evt-2",
            "aggregate_type": "Order",
            "topic": "orders.created",
            "payload": {"order_id": "ord-99", "amount": 120.50, "status": "CONFIRMED"},
            "created_at": "2026-06-01T10:00:01Z",
        }
        audit = self.auditor.compare_events(leg_event, mod_event)
        self.assertTrue(audit.is_equivalent)
        self.assertFalse(audit.semantic_drift_detected)
        self.assertEqual(audit.mismatched_fields, [])


if __name__ == "__main__":
    unittest.main()
