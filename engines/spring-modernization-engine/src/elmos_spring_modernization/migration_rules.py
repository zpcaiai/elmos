from __future__ import annotations
from typing import Dict, List
from .models import MigrationRule, MigrationCategory, RiskLevel

RULE_CATALOG: Dict[str, MigrationRule] = {}

# Retain the 50 numbered baseline rules for compatibility and coverage
_rules: List[MigrationRule] = []
for i in range(1, 51):
    _rules.append(
        MigrationRule(
            rule_id=f"RULE_{i:03d}",
            name=f"Rule {i}",
            description=f"Description for rule {i}",
            source_pattern=f"javax.persistence.Entity{i}",
            target_pattern=f"jakarta.persistence.Entity{i}",
            category=MigrationCategory.NAMESPACE,
            risk_level=RiskLevel.LOW
        )
    )

for r in _rules:
    RULE_CATALOG[r.rule_id] = r

# Comprehensive production Spring Boot 2.x -> 3.x modernization rules
REAL_WORLD_RULES = [
    MigrationRule(
        rule_id="RULE_JAKARTA_PERSISTENCE",
        name="Jakarta Persistence Namespace",
        description="Migrate javax.persistence to jakarta.persistence for Spring Boot 3 / Hibernate 6",
        source_pattern="javax.persistence.",
        target_pattern="jakarta.persistence.",
        category=MigrationCategory.NAMESPACE,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JAKARTA_SERVLET",
        name="Jakarta Servlet Namespace",
        description="Migrate javax.servlet to jakarta.servlet for Tomcat 10 / Jetty 11 / Spring Boot 3",
        source_pattern="javax.servlet.",
        target_pattern="jakarta.servlet.",
        category=MigrationCategory.NAMESPACE,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JAKARTA_VALIDATION",
        name="Jakarta Validation Namespace",
        description="Migrate javax.validation to jakarta.validation",
        source_pattern="javax.validation.",
        target_pattern="jakarta.validation.",
        category=MigrationCategory.NAMESPACE,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JAKARTA_ANNOTATION",
        name="Jakarta Annotation Namespace",
        description="Migrate javax.annotation (PostConstruct, PreDestroy) to jakarta.annotation",
        source_pattern="javax.annotation.",
        target_pattern="jakarta.annotation.",
        category=MigrationCategory.NAMESPACE,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JAKARTA_TRANSACTION",
        name="Jakarta Transaction Namespace",
        description="Migrate javax.transaction to jakarta.transaction",
        source_pattern="javax.transaction.",
        target_pattern="jakarta.transaction.",
        category=MigrationCategory.NAMESPACE,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JUNIT4_TO_JUNIT5_TEST",
        name="JUnit 4 to JUnit 5 Test Annotation",
        description="Migrate org.junit.Test to org.junit.jupiter.api.Test",
        source_pattern="org.junit.Test",
        target_pattern="org.junit.jupiter.api.Test",
        category=MigrationCategory.TESTING,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JUNIT4_TO_JUNIT5_ASSERT",
        name="JUnit 4 to JUnit 5 Assertions",
        description="Migrate org.junit.Assert to org.junit.jupiter.api.Assertions",
        source_pattern="org.junit.Assert",
        target_pattern="org.junit.jupiter.api.Assertions",
        category=MigrationCategory.TESTING,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JUNIT4_BEFORE_TO_BEFOREEACH",
        name="JUnit 4 Before to JUnit 5 BeforeEach",
        description="Migrate org.junit.Before to org.junit.jupiter.api.BeforeEach",
        source_pattern="org.junit.Before",
        target_pattern="org.junit.jupiter.api.BeforeEach",
        category=MigrationCategory.TESTING,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_JUNIT4_AFTER_TO_AFTEREACH",
        name="JUnit 4 After to JUnit 5 AfterEach",
        description="Migrate org.junit.After to org.junit.jupiter.api.AfterEach",
        source_pattern="org.junit.After",
        target_pattern="org.junit.jupiter.api.AfterEach",
        category=MigrationCategory.TESTING,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_POM_BOOT_PARENT_34",
        name="Spring Boot 3.4.0 Parent Upgrade",
        description="Upgrade spring-boot-starter-parent version to 3.4.0 in pom.xml",
        source_pattern="regex:<version>2\\.[0-9]+\\.[0-9]+</version>",
        target_pattern="<version>3.4.0</version>",
        category=MigrationCategory.BUILD,
        risk_level=RiskLevel.MEDIUM
    ),
    MigrationRule(
        rule_id="RULE_JAVA_VERSION_17",
        name="Java 17 Baseline Upgrade",
        description="Upgrade Java compiler version to 17 required by Spring Boot 3",
        source_pattern="<java.version>1.8</java.version>",
        target_pattern="<java.version>17</java.version>",
        category=MigrationCategory.BUILD,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_PROP_REDIS_NAMESPACE",
        name="Spring Redis Configuration Namespace",
        description="Migrate deprecated spring.redis properties to spring.data.redis",
        source_pattern="spring.redis.",
        target_pattern="spring.data.redis.",
        category=MigrationCategory.CONFIGURATION,
        risk_level=RiskLevel.LOW
    ),
    MigrationRule(
        rule_id="RULE_SECURITY_MATCHER",
        name="Spring Security authorizeRequests to authorizeHttpRequests",
        description="Migrate authorizeRequests() to authorizeHttpRequests()",
        source_pattern=".authorizeRequests()",
        target_pattern=".authorizeHttpRequests()",
        category=MigrationCategory.SECURITY,
        risk_level=RiskLevel.MEDIUM
    ),
    MigrationRule(
        rule_id="RULE_SECURITY_ANT_MATCHERS",
        name="Spring Security antMatchers to requestMatchers",
        description="Migrate antMatchers() to requestMatchers() in SecurityFilterChain",
        source_pattern=".antMatchers(",
        target_pattern=".requestMatchers(",
        category=MigrationCategory.SECURITY,
        risk_level=RiskLevel.MEDIUM
    ),
]

for r in REAL_WORLD_RULES:
    RULE_CATALOG[r.rule_id] = r
