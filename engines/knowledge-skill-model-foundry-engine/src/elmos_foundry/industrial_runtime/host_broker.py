"""Local Host Broker that executes every HOST_ROUTE_BOUND Foundry skill.

Replaces the previous NOT_RUN / LLM-host dependency with a deterministic
kernel.  Tenant scope is recorded for provenance; no API key is consulted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..canonical import canonical_digest
from ..domain import TenantScope
from ..native_semantics import load_native_programs
from .families import classify_skill
from .kernels import KernelResult

INDUSTRIAL_BROKER_ID = "elmos.foundry.industrial-local-host-broker"
INDUSTRIAL_BROKER_VERSION = "1.0.0"
EXPECTED_BROKERED_SKILLS = 1244
EXPECTED_LOCAL_SEMANTIC_SKILLS = 66
EXPECTED_ATOMIC_SKILLS = 1310


@dataclass
class CatalogExecutionReport:
    executed: int
    succeeded: int
    failed: int
    families: dict[str, int]
    llm_required_count: int
    results: list[KernelResult] = field(default_factory=list)
    failed_skills: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.executed == EXPECTED_BROKERED_SKILLS and self.llm_required_count == 0


def execute_industrial_skill(
    skill_name: str,
    payload: Mapping[str, Any] | None,
    tenant_scope: TenantScope | None = None,
    invocation_id: str = "",
    pack: str = "",
) -> KernelResult:
    """Execute one skill through its exact compiled native-program handler."""
    scoped = dict(payload or {})
    if tenant_scope is not None:
        scoped.setdefault("_tenant", {
            "tenant_id": tenant_scope.tenant_id,
            "project_id": tenant_scope.project_id,
            "invocation_id": invocation_id or tenant_scope.invocation_id,
        })
    from ..exact_skills.compiler import ExactSkillError
    from ..exact_skills.registry import run_exact_skill

    try:
        result = run_exact_skill(skill_name, scoped, tenant_scope, invocation_id)
    except ExactSkillError as exc:
        return KernelResult(
            ok=False,
            family=classify_skill(skill_name, pack).value,
            skill_name=skill_name,
            algorithm="exact:missing",
            input_digest=canonical_digest({"skill": skill_name, "error": "missing"}),
            output_digest=canonical_digest({"error": str(exc)}),
            metrics={},
            artifacts={},
            error=str(exc),
            pack=pack,
        )
    return KernelResult(
        ok=result.get("status") == "SUCCEEDED",
        family=str(result.get("kernel_family") or ""),
        skill_name=skill_name,
        algorithm=str(result.get("algorithm") or f"exact:{skill_name}"),
        input_digest=str(result.get("input_digest") or ""),
        output_digest=str(result.get("output_digest") or ""),
        metrics=dict(result.get("metrics") or {}),
        artifacts=dict(result.get("artifacts") or {}),
        error=result.get("error"),
        execution_mode=str(result.get("execution_mode") or "EXACT_NATIVE_PROGRAM"),
        llm_required=bool(result.get("llm_required")),
        pack=str(result.get("pack") or pack),
    )


class IndustrialLocalHostBroker:
    """In-process broker covering the full 1,244 native-program catalog."""

    broker_id = INDUSTRIAL_BROKER_ID
    version = INDUSTRIAL_BROKER_VERSION

    def __init__(self) -> None:
        self._programs = load_native_programs()

    @property
    def skill_count(self) -> int:
        return len(self._programs)

    def execute(
        self,
        skill_name: str,
        payload: Mapping[str, Any] | None = None,
        tenant_scope: TenantScope | None = None,
        invocation_id: str = "",
    ) -> KernelResult:
        program = self._programs.get(skill_name)
        if program is None:
            return execute_industrial_skill(skill_name, payload, tenant_scope, invocation_id)
        pack = str(program.document.get("pack") or "")
        return execute_industrial_skill(skill_name, payload, tenant_scope, invocation_id, pack=pack)

    def execute_catalog(
        self,
        payload: Mapping[str, Any] | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> CatalogExecutionReport:
        results: list[KernelResult] = []
        failed: list[str] = []
        families: Counter[str] = Counter()
        for name in sorted(self._programs):
            result = self.execute(name, payload, tenant_scope, invocation_id=f"ind-{name[:24]}")
            results.append(result)
            families[result.family] += 1
            if not result.ok:
                failed.append(name)
        succeeded = sum(1 for row in results if row.ok)
        return CatalogExecutionReport(
            executed=len(results),
            succeeded=succeeded,
            failed=len(failed),
            families=dict(families),
            llm_required_count=sum(1 for row in results if row.llm_required),
            results=results,
            failed_skills=failed,
        )
