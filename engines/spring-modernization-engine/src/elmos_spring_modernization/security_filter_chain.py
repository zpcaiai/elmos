from __future__ import annotations
from dataclasses import dataclass, field

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
    def extract(self, config_sources: list[dict]) -> SecurityConfig:
        if len(config_sources) > MAX_RULES:
            raise ValueError(f"Too many rules. Max allowed is {MAX_RULES}")
            
        rules = {}
        for src in config_sources:
            if "pattern" in src and "rule" in src:
                rules[src["pattern"]] = src["rule"]
                
        return SecurityConfig(
            filter_chain_rules=rules,
            auth_providers=["daoAuthenticationProvider"],
            cors_config={"allowedOrigins": "*"},
            csrf_config={"enabled": "true"},
            custom_filters=[],
            posture_summary="Standard security posture."
        )
