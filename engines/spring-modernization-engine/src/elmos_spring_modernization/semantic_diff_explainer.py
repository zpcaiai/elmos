from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class SemanticCategory(str, Enum):
    TOOLCHAIN_BUILD = "TOOLCHAIN_BUILD"
    ECOSYSTEM_DEPENDENCY = "ECOSYSTEM_DEPENDENCY"
    JAKARTA_NAMESPACE = "JAKARTA_NAMESPACE"
    FRAMEWORK_CONFIGURATION = "FRAMEWORK_CONFIGURATION"
    MICROSERVICE_NETFLIX = "MICROSERVICE_NETFLIX"
    SECURITY_AUTH = "SECURITY_AUTH"
    TEST_MOCKING = "TEST_MOCKING"
    PERSISTENCE_TRANSACTION = "PERSISTENCE_TRANSACTION"
    GENERAL_REFACTOR = "GENERAL_REFACTOR"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class SemanticChange:
    file_path: str
    category: SemanticCategory
    risk: RiskLevel
    title: str
    rationale: str
    reviewer_guidance: str
    before_snippet: Optional[str] = None
    after_snippet: Optional[str] = None


@dataclass
class SemanticDiffReport:
    total_files_changed: int
    changes_by_category: Dict[str, int]
    highest_risk: RiskLevel
    changes: List[SemanticChange] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Spring Modernization Semantic Diff Report",
            "",
            f"- **Total Files Modified**: {self.total_files_changed}",
            f"- **Overall Risk Level**: `{self.highest_risk.value}`",
            "",
            "## Distribution by Semantic Category",
            "",
            "| Category | File Count |",
            "| :--- | :--- |",
        ]
        for cat, count in sorted(self.changes_by_category.items()):
            lines.append(f"| `{cat}` | {count} |")
        lines.append("")
        lines.append("## Detailed Change Explanations")
        lines.append("")

        for idx, change in enumerate(self.changes, 1):
            lines.extend([
                f"### {idx}. [{change.risk.value}] {change.title} (`{change.file_path}`)",
                f"- **Category**: `{change.category.value}`",
                f"- **Rationale**: {change.rationale}",
                f"- **Reviewer Guidance**: {change.reviewer_guidance}",
            ])
            if change.before_snippet and change.after_snippet:
                lines.extend([
                    "```diff",
                    f"- {change.before_snippet.strip()}",
                    f"+ {change.after_snippet.strip()}",
                    "```",
                ])
            lines.append("")

        return "\n".join(lines)


class SemanticDiffExplainer:
    """
    Analyzes modernized file content vs original content to explain
    WHY changes were made and how to review them safely.
    """

    @classmethod
    def explain_file_change(cls, file_path: str, original: str, modernized: str) -> List[SemanticChange]:
        changes: List[SemanticChange] = []
        if original == modernized:
            return changes

        # 1. Build / Toolchain
        if file_path.endswith("pom.xml") or file_path.endswith(".gradle") or file_path.endswith(".properties"):
            if "spring-boot-starter-parent" in modernized or "org.springframework.boot" in modernized:
                changes.append(SemanticChange(
                    file_path=file_path,
                    category=SemanticCategory.TOOLCHAIN_BUILD,
                    risk=RiskLevel.MEDIUM,
                    title="Toolchain baseline upgrade to Spring Boot 3.5.3 & Java 21",
                    rationale="Spring Boot 3 requires Java 17+ baseline and new compiler/build plugins.",
                    reviewer_guidance="Verify compiler source/target settings and parent artifact versions.",
                ))
            if "pagehelper" in modernized.lower() or "mybatis" in modernized.lower():
                changes.append(SemanticChange(
                    file_path=file_path,
                    category=SemanticCategory.ECOSYSTEM_DEPENDENCY,
                    risk=RiskLevel.MEDIUM,
                    title="Ecosystem dependency upgrade (MyBatis / PageHelper)",
                    rationale="MyBatis and PageHelper 1.x rely on javax.servlet; upgraded to 2.1.0+ / 6.1.0+ for Jakarta EE compatibility.",
                    reviewer_guidance="Check pagination interceptor beans and database dialect configuration.",
                ))

        # 2. Jakarta namespace
        if "javax.servlet" in original and "jakarta.servlet" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.JAKARTA_NAMESPACE,
                risk=RiskLevel.MEDIUM,
                title="Namespace migration from javax.servlet to jakarta.servlet",
                rationale="Jakarta EE 9/10 renamed javax.* namespaces to jakarta.*. Spring Boot 3 no longer supports javax.servlet.",
                reviewer_guidance="Ensure custom filters, listeners, and servlets implement jakarta.servlet interfaces.",
                before_snippet="import javax.servlet.http.HttpServletRequest;",
                after_snippet="import jakarta.servlet.http.HttpServletRequest;",
            ))

        if "javax.persistence" in original and "jakarta.persistence" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.JAKARTA_NAMESPACE,
                risk=RiskLevel.MEDIUM,
                title="Namespace migration from javax.persistence to jakarta.persistence",
                rationale="Hibernate 6 / JPA 3.1 adopts the jakarta.persistence namespace.",
                reviewer_guidance="Inspect JPA entity annotations and entityManager operations.",
                before_snippet="import javax.persistence.Entity;",
                after_snippet="import jakarta.persistence.Entity;",
            ))

        # 3. Security
        if "WebSecurityConfigurerAdapter" in original:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.SECURITY_AUTH,
                risk=RiskLevel.HIGH,
                title="Spring Security: WebSecurityConfigurerAdapter to SecurityFilterChain Bean",
                rationale="WebSecurityConfigurerAdapter was removed in Spring Security 6. Component-based SecurityFilterChain is required.",
                reviewer_guidance="Carefully review authorizeHttpRequests endpoint rules and CSRF/CORS policies.",
                before_snippet="public class SecurityConfig extends WebSecurityConfigurerAdapter",
                after_snippet="@Bean public SecurityFilterChain filterChain(HttpSecurity http)",
            ))

        if "EnableResourceServer" in original or "oauth2ResourceServer" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.SECURITY_AUTH,
                risk=RiskLevel.HIGH,
                title="Legacy Spring Security OAuth2 to modern Nimbus Resource Server",
                rationale="spring-security-oauth2 is completely deprecated and removed in favor of Spring Security 6 OAuth2 Resource Server.",
                reviewer_guidance="Verify JWT / opaque token decoder bean and claims extraction logic.",
            ))

        # 4. Microservices / Netflix OSS
        if ("netflix.zuul" in original or "@EnableZuulProxy" in original) and "RouteLocator" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.MICROSERVICE_NETFLIX,
                risk=RiskLevel.HIGH,
                title="Netflix Zuul to Spring Cloud Gateway reactive routing",
                rationale="Zuul 1.x is dead and blocking; Spring Cloud Gateway provides non-blocking, modern routing and filter filters.",
                reviewer_guidance="Inspect URI route predicates and custom gateway filter factories.",
            ))

        if "netflix.ribbon" in original and "LoadBalancerClient" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.MICROSERVICE_NETFLIX,
                risk=RiskLevel.MEDIUM,
                title="Netflix Ribbon to Spring Cloud LoadBalancer",
                rationale="Ribbon is deprecated and superseded by non-blocking Spring Cloud LoadBalancer.",
                reviewer_guidance="Verify client load balancer configuration and health checks.",
            ))

        if "netflix.hystrix" in original and "io.github.resilience4j" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.MICROSERVICE_NETFLIX,
                risk=RiskLevel.MEDIUM,
                title="Netflix Hystrix to Resilience4j circuit breaker",
                rationale="Hystrix is unmaintained; Resilience4j offers functional fault tolerance with lightweight thread management.",
                reviewer_guidance="Check circuit breaker failure rates, wait duration, and fallback methods.",
            ))

        # 5. Testing & Mocking
        if "PowerMockRunner" in original or "PowerMockito" in original:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.TEST_MOCKING,
                risk=RiskLevel.LOW,
                title="Elimination of PowerMock in favor of Mockito 5 MockedStatic",
                rationale="PowerMock fails on Java 17+ due to JVM module encapsulation. Mockito 5 provides native try-with-resources static mocking.",
                reviewer_guidance="Ensure static mocks are properly scoped within try-with-resources blocks to prevent thread leak.",
                before_snippet="@RunWith(PowerMockRunner.class)\nPowerMockito.mockStatic(X.class);",
                after_snippet="try (MockedStatic<X> mocked = mockStatic(X.class)) { ... }",
            ))

        if "org.junit.Test" in original and "org.junit.jupiter.api.Test" in modernized:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.TEST_MOCKING,
                risk=RiskLevel.LOW,
                title="JUnit 4 to JUnit 5 Jupiter migration",
                rationale="Modernize testing annotations (@Before -> @BeforeEach, assertThrows, @ExtendWith).",
                reviewer_guidance="Verify test lifecycle callbacks and assertion exceptions.",
            ))

        # Default fallback if changes detected but no specific signature matched
        if not changes:
            changes.append(SemanticChange(
                file_path=file_path,
                category=SemanticCategory.GENERAL_REFACTOR,
                risk=RiskLevel.LOW,
                title=f"Refactored {Path(file_path).name} for Spring Boot 3 compatibility",
                rationale="Code modifications applied during automated modernization pass.",
                reviewer_guidance="Review standard syntax and logic equivalence.",
            ))

        return changes

    @classmethod
    def generate_report(cls, file_pairs: List[Tuple[str, str, str]]) -> SemanticDiffReport:
        """
        Takes list of (file_path, original_content, modernized_content)
        and builds an aggregated SemanticDiffReport.
        """
        all_changes: List[SemanticChange] = []
        counts: Dict[str, int] = {}
        highest_risk = RiskLevel.LOW
        risk_weights = {
            RiskLevel.LOW: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.HIGH: 3,
            RiskLevel.CRITICAL: 4,
        }

        total_files = len(file_pairs)

        for file_path, original, modernized in file_pairs:
            changes = cls.explain_file_change(file_path, original, modernized)
            for c in changes:
                all_changes.append(c)
                counts[c.category.value] = counts.get(c.category.value, 0) + 1
                if risk_weights[c.risk] > risk_weights[highest_risk]:
                    highest_risk = c.risk

        return SemanticDiffReport(
            total_files_changed=total_files,
            changes_by_category=counts,
            highest_risk=highest_risk,
            changes=all_changes,
        )
