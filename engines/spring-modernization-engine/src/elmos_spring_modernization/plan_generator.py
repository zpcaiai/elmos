from __future__ import annotations
import uuid
from typing import List, Dict, Any, Optional
from .models import MigrationPlan, SpringProjectProfile, SpringVersion, MigrationRule, RiskLevel
from .migration_rules import RULE_CATALOG

class MigrationPlanGenerator:
    """
    Industrial-grade migration plan generator for Spring Boot modernizations.
    Evaluates project profile, framework dependencies, and deprecated APIs to
    construct an ordered, phased, risk-calibrated migration plan with blocking issue detection.
    """

    RULE_PRIORITY_ORDER = [
        # 1. Build and Core JDK baseline
        "RULE_POM_BOOT_PARENT_34",
        "RULE_JAVA_VERSION_17",
        # 2. Jakarta namespaces
        "RULE_JAKARTA_PERSISTENCE",
        "RULE_JAKARTA_SERVLET",
        "RULE_JAKARTA_VALIDATION",
        "RULE_JAKARTA_ANNOTATION",
        "RULE_JAKARTA_TRANSACTION",
        # 3. Security
        "RULE_SECURITY_MATCHER",
        "RULE_SECURITY_ANT_MATCHERS",
        # 4. Persistence & JPA
        "RULE_JPA_GET_ONE_TO_REFERENCE",
        # 5. Web & API Documentation
        "RULE_SWAGGER_API_TO_TAG",
        "RULE_SWAGGER_API_OPERATION",
        "RULE_SWAGGER_API_PARAM",
        "RULE_SWAGGER_API_MODEL_PROPERTY",
        "RULE_WEB_INTERCEPTOR_ADAPTER",
        # 6. Testing
        "RULE_JUNIT4_TO_JUNIT5_TEST",
        "RULE_JUNIT4_TO_JUNIT5_ASSERT",
        "RULE_JUNIT4_BEFORE_TO_BEFOREEACH",
        "RULE_JUNIT4_AFTER_TO_AFTEREACH",
    ]

    INCOMPATIBLE_BOOT3_DEPS = {
        "spring-cloud-starter-netflix-zuul": "Netflix Zuul is not supported in Spring Boot 3.x; migrate to Spring Cloud Gateway.",
        "spring-cloud-starter-netflix-hystrix": "Netflix Hystrix is deprecated; migrate to Resilience4j.",
        "spring-security-oauth2": "Legacy Spring Security OAuth2 is obsolete; migrate to Spring Security 6 OAuth2 client/resource-server.",
        "springfox-swagger2": "Springfox is unmaintained and incompatible with Spring Boot 3; migrate to SpringDoc OpenAPI."
    }

    def generate_plan(self, profile: SpringProjectProfile, target_version: SpringVersion) -> MigrationPlan:
        selected_rules: list[MigrationRule] = []
        dep_str = " ".join(profile.dependencies.keys()).lower()

        is_boot2_to_boot3 = (
            profile.version in (
                SpringVersion.BOOT_1_5, SpringVersion.BOOT_2_0, SpringVersion.BOOT_2_7
            )
            and target_version in (
                SpringVersion.BOOT_3_0, SpringVersion.BOOT_3_2, SpringVersion.BOOT_3_5,
                SpringVersion.BOOT_4_0
            )
        )

        for rule_id, rule in RULE_CATALOG.items():
            # Mandatory rules for Boot 2 -> Boot 3
            if is_boot2_to_boot3:
                # 1. Build and Jakarta namespaces are always mandatory for Boot 3
                if rule_id.startswith("RULE_JAKARTA_") or rule_id in ("RULE_POM_BOOT_PARENT_34", "RULE_JAVA_VERSION_17"):
                    selected_rules.append(rule)
                    continue

                # 2. Security rules
                if "security" in rule_id.lower():
                    if profile.security_mode == "WebSecurityConfigurerAdapter" or "security" in dep_str or not profile.dependencies:
                        selected_rules.append(rule)
                        continue

                # 3. JPA / Data rules
                if "jpa" in rule_id.lower():
                    if profile.data_access_type == "JPA" or "jpa" in dep_str or "hibernate" in dep_str or not profile.dependencies:
                        selected_rules.append(rule)
                        continue

                # 4. Swagger / OpenAPI rules
                if "swagger" in rule_id.lower():
                    if "swagger" in dep_str or "springfox" in dep_str or not profile.dependencies:
                        selected_rules.append(rule)
                        continue

                # 5. Web MVC rules
                if "web" in rule_id.lower() or "interceptor" in rule_id.lower():
                    if "web" in dep_str or not profile.dependencies:
                        selected_rules.append(rule)
                        continue

                # 6. Testing rules
                if "junit" in rule_id.lower():
                    if "test" in dep_str or not profile.dependencies:
                        selected_rules.append(rule)
                        continue
            else:
                selected_rules.append(rule)

        # Fallback if filtered list is empty: populate with core applicable rules
        if not selected_rules:
            selected_rules = list(RULE_CATALOG.values())[:8]

        # Deduplicate while preserving order
        seen_ids = set()
        unique_rules: list[MigrationRule] = []
        for r in selected_rules:
            if r.rule_id not in seen_ids:
                seen_ids.add(r.rule_id)
                unique_rules.append(r)

        # Sort rules in recommended topological migration order
        ordered_rules = self._order_rules(unique_rules)

        # Risk Summary
        risk_summary: Dict[RiskLevel, int] = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 0,
            RiskLevel.HIGH: 0
        }
        for r in ordered_rules:
            risk_summary[r.risk_level] = risk_summary.get(r.risk_level, 0) + 1

        # Estimated changes: sum of estimated file modifications per rule
        estimated_changes = sum(
            15 if r.risk_level == RiskLevel.HIGH else (5 if r.risk_level == RiskLevel.MEDIUM else 1)
            for r in ordered_rules
        )

        plan_id = f"plan_{profile.version.value.replace('.', '_')}_to_{target_version.value.replace('.', '_')}_{abs(hash(tuple(seen_ids))) % 10000:04d}"

        return MigrationPlan(
            plan_id=plan_id,
            source_version=profile.version,
            target_version=target_version,
            rules=ordered_rules,
            estimated_changes=estimated_changes,
            risk_summary=risk_summary
        )

    def _order_rules(self, rules: List[MigrationRule]) -> List[MigrationRule]:
        def sort_key(rule: MigrationRule) -> int:
            if rule.rule_id in self.RULE_PRIORITY_ORDER:
                return self.RULE_PRIORITY_ORDER.index(rule.rule_id)
            return len(self.RULE_PRIORITY_ORDER) + (10 if rule.risk_level == RiskLevel.HIGH else 0)

        return sorted(rules, key=sort_key)

    def estimate_effort(self, plan: MigrationPlan) -> float:
        """
        Estimates total engineering effort (in story points / hours).
        High risk = 2.5, Medium risk = 1.0, Low risk = 0.3.
        """
        effort = 0.0
        for rule in plan.rules:
            if rule.risk_level == RiskLevel.HIGH:
                effort += 2.5
            elif rule.risk_level == RiskLevel.MEDIUM:
                effort += 1.0
            else:
                effort += 0.3
        return round(effort, 1)

    def assess_risk(self, plan: MigrationPlan) -> Dict[RiskLevel, int]:
        return plan.risk_summary

    def suggest_migration_order(self, plan: MigrationPlan) -> List[MigrationRule]:
        return self._order_rules(plan.rules)

    def identify_blocking_issues(self, plan: MigrationPlan, profile: Optional[SpringProjectProfile] = None) -> List[str]:
        blockers: list[str] = []

        # 1. Target version requirements
        is_target_boot3 = plan.target_version in (
            SpringVersion.BOOT_3_0, SpringVersion.BOOT_3_2, SpringVersion.BOOT_3_5,
            SpringVersion.BOOT_4_0
        )

        # 2. Check dependencies for obsolete libraries
        if profile and profile.dependencies:
            for dep_name in profile.dependencies:
                dep_lower = dep_name.lower()
                for bad_dep, reason in self.INCOMPATIBLE_BOOT3_DEPS.items():
                    if bad_dep in dep_lower:
                        blockers.append(f"Incompatible dependency '{dep_name}': {reason}")

        # 3. WebSecurityConfigurerAdapter without SecurityFilterChain rule
        if profile and profile.security_mode == "WebSecurityConfigurerAdapter" and is_target_boot3:
            rule_ids = {r.rule_id for r in plan.rules}
            if "RULE_SECURITY_CONFIG_ADAPTER" not in rule_ids:
                blockers.append(
                    "WebSecurityConfigurerAdapter is removed in Spring Security 6 (Spring Boot 3.x). "
                    "Plan is missing RULE_SECURITY_CONFIG_ADAPTER."
                )

        return blockers

    def generate_migration_waves(self, plan: MigrationPlan, wave_size: int = 3) -> List[List[MigrationRule]]:
        ordered = self.suggest_migration_order(plan)
        if wave_size <= 0:
            wave_size = 3
        return [ordered[i:i + wave_size] for i in range(0, len(ordered), wave_size)]
