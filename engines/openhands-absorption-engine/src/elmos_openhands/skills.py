"""Progressive Skill disclosure with permission-aware routing."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import ContractViolation, TenantIsolationError


@dataclass(frozen=True, slots=True)
class SkillMetadata:
    name: str
    version: str
    description: str
    keywords: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    tenant_allowlist: frozenset[str] = frozenset()
    content: Mapping[str, Any] = field(default_factory=dict)
    triggers: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    frameworks: frozenset[str] = frozenset()
    risk_capabilities: frozenset[str] = frozenset()
    token_estimate: int = 0
    package_name: str | None = None
    trust_level: str = "untrusted"

    def __post_init__(self) -> None:
        if not self.name or not self.version or not self.description or self.token_estimate < 0:
            raise ContractViolation("skill metadata is incomplete")
        if self.trust_level not in {"untrusted", "trusted", "verified"}:
            raise ContractViolation("skill trust level is invalid")


@dataclass(frozen=True, slots=True)
class SkillRoute:
    skill: SkillMetadata
    score: float
    stages: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class ProgressiveSkillRouter:
    STAGES = ("L0_catalog", "L1_contract", "L2_instructions", "L3_examples")

    def __init__(self, skills: Iterable[SkillMetadata]) -> None:
        self._skills = {skill.name: skill for skill in skills}

    def route(self, tenant_id: str, query: str, *, required_permissions: Iterable[str] = (), top_k: int = 5) -> tuple[SkillRoute, ...]:
        if not tenant_id or not query.strip() or top_k < 1:
            raise ContractViolation("tenant, query and positive top_k are required")
        required = set(required_permissions)
        tokens = {token.lower() for token in query.split() if token}
        routes: list[SkillRoute] = []
        for skill in self._skills.values():
            if skill.tenant_allowlist and tenant_id not in skill.tenant_allowlist:
                continue
            missing = required - set(skill.permissions)
            if missing:
                continue
            score = len(tokens & {keyword.lower() for keyword in skill.keywords}) / max(1, len(tokens))
            if any(token in skill.description.lower() for token in tokens):
                score += 0.1
            warnings = ("INCOMPATIBLE_PERMISSION_SCOPE",) if missing else ()
            routes.append(SkillRoute(skill, score, ("L0_catalog",), warnings))
        routes.sort(key=lambda route: (-route.score, route.skill.name))
        return tuple(routes[:top_k])

    def disclose(self, tenant_id: str, skill_name: str, stage: str) -> dict[str, object]:
        skill = self._skills.get(skill_name)
        if skill is None:
            raise KeyError(skill_name)
        if skill.tenant_allowlist and tenant_id not in skill.tenant_allowlist:
            raise TenantIsolationError("skill is not enabled for tenant")
        if stage not in self.STAGES:
            raise ContractViolation("invalid Skill disclosure stage")
        result: dict[str, object] = {"name": skill.name, "version": skill.version, "stage": stage, "description": skill.description, "permissions": sorted(skill.permissions), "package_name": skill.package_name, "trust_level": skill.trust_level, "token_estimate": skill.token_estimate}
        if stage in self.STAGES[1:]:
            contract = (skill.content or {}).get("contract", "")
            result["contract"] = dict(contract) if isinstance(contract, dict) else contract
        if stage in self.STAGES[2:]:
            result["instructions"] = (skill.content or {}).get("instructions", "")
        if stage == "L3_examples":
            result["examples"] = (skill.content or {}).get("examples", "")
            result["schemas"] = (skill.content or {}).get("schemas", "")
            result["scripts"] = (skill.content or {}).get("scripts", "")
            result["references"] = (skill.content or {}).get("references", "")
        return result
