from __future__ import annotations
from dataclasses import dataclass
from typing import Any

MAX_RULES = 500

@dataclass(frozen=True)
class SecurityConfig:
    filter_chain_rules: dict[str, str]
    auth_providers: list[str]
    cors_config: dict[str, str]
    csrf_config: dict[str, str]
    custom_filters: list[str]
    posture_summary: str

class SecurityFilterChainExtractor:
    """
    Industrial-grade extractor and analyzer for Spring Security configurations.
    Parses URL authorization rules, authentication providers, CORS/CSRF configurations,
    and custom filter order, producing an actionable security posture evaluation.
    """

    def extract(self, config_sources: list[dict[str, Any]]) -> SecurityConfig:
        if len(config_sources) > MAX_RULES:
            raise ValueError(f"Too many rules. Max allowed is {MAX_RULES}")

        rules: dict[str, str] = {}
        auth_providers: set[str] = set()
        cors_config: dict[str, str] = {}
        csrf_config: dict[str, str] = {}
        custom_filters: list[str] = []

        for src in config_sources:
            # 1. URL pattern rules
            if "pattern" in src and "rule" in src:
                rules[str(src["pattern"])] = str(src["rule"])
            if "rules" in src and isinstance(src["rules"], dict):
                for pat, r in src["rules"].items():
                    rules[str(pat)] = str(r)

            # 2. Authentication providers
            providers = src.get("auth_providers") or src.get("authentication_providers")
            if providers:
                if isinstance(providers, list):
                    for p in providers:
                        auth_providers.add(str(p))
                elif isinstance(providers, str):
                    auth_providers.add(providers)

            # 3. CORS configuration
            cors = src.get("cors") or src.get("cors_config")
            if isinstance(cors, dict):
                for k, v in cors.items():
                    cors_config[str(k)] = str(v)

            # 4. CSRF configuration
            csrf = src.get("csrf") or src.get("csrf_config")
            if isinstance(csrf, dict):
                for k, v in csrf.items():
                    csrf_config[str(k)] = str(v)

            # 5. Custom filters
            filters = src.get("custom_filters") or src.get("filters")
            if isinstance(filters, list):
                for f in filters:
                    custom_filters.append(str(f))

        # Sensible defaults if not explicitly configured in sources
        resolved_providers = sorted(list(auth_providers)) if auth_providers else ["daoAuthenticationProvider"]
        resolved_cors = cors_config if cors_config else {"allowedOrigins": "*"}
        resolved_csrf = csrf_config if csrf_config else {"enabled": "true"}

        # Dynamic posture evaluation
        posture_summary = self._evaluate_security_posture(rules, resolved_providers, resolved_cors, resolved_csrf, custom_filters)

        return SecurityConfig(
            filter_chain_rules=rules,
            auth_providers=resolved_providers,
            cors_config=resolved_cors,
            csrf_config=resolved_csrf,
            custom_filters=custom_filters,
            posture_summary=posture_summary
        )

    def _evaluate_security_posture(
        self,
        rules: dict[str, str],
        providers: list[str],
        cors: dict[str, str],
        csrf: dict[str, str],
        filters: list[str]
    ) -> str:
        findings: list[str] = []

        # Check for open patterns
        wildcard_permit = False
        authenticated_count = 0
        for pat, rule in rules.items():
            rule_lower = rule.lower()
            if pat in ("/**", "/*", "/") and "permitall" in rule_lower:
                wildcard_permit = True
            if "authenticated" in rule_lower or "hasrole" in rule_lower or "hasauthority" in rule_lower:
                authenticated_count += 1

        if wildcard_permit:
            findings.append("CRITICAL: Root or wildcard path is configured with permitAll.")

        # Check CSRF
        csrf_enabled = csrf.get("enabled", "true").lower() in ("true", "1", "yes")
        if not csrf_enabled:
            findings.append("WARNING: CSRF protection is disabled.")

        # Check CORS
        allowed_origins = cors.get("allowedOrigins", "")
        allow_credentials = cors.get("allowCredentials", "false").lower() in ("true", "1", "yes")
        if allowed_origins == "*" and allow_credentials:
            findings.append("CRITICAL: CORS allows wildcard origin '*' combined with credentials.")
        elif allowed_origins == "*":
            findings.append("NOTICE: CORS allows wildcard origin '*'.")

        # Summary construction
        summary_parts = [
            f"{len(rules)} URL authorization rules defined ({authenticated_count} authenticated)",
            f"{len(providers)} auth provider(s): {', '.join(providers)}",
            f"CSRF: {'enabled' if csrf_enabled else 'disabled'}"
        ]
        if filters:
            summary_parts.append(f"{len(filters)} custom filter(s)")

        status = "Hardened" if not findings else ("Elevated Risk" if any("CRITICAL" in f for f in findings) else "Standard")
        findings_str = (" Findings: " + "; ".join(findings)) if findings else ""
        return f"{status} security posture ({', '.join(summary_parts)}).{findings_str}"
