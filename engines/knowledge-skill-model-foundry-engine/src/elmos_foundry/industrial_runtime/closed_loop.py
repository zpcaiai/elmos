"""Foundry → QA → Insight closed-loop industrial evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from ..local_semantics import LOCAL_SEMANTIC_SKILLS
from .families import KernelFamily
from .host_broker import (
    EXPECTED_ATOMIC_SKILLS,
    EXPECTED_BROKERED_SKILLS,
    EXPECTED_LOCAL_SEMANTIC_SKILLS,
    IndustrialLocalHostBroker,
)
from .kernels import execute_kernel


@dataclass
class InsightReport:
    foundry_executed: int
    foundry_succeeded: int
    local_semantic_skills: int
    atomic_executable: int
    input_dependent_checks: int
    input_dependent_passed: int
    qa_healed: int
    qa_integrity_ok: int
    qa_mutation_caught: int
    qa_loop_guard_ok: int
    families: dict[str, int]
    industrial_quality_percent: float
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.industrial_quality_percent >= 100.0


def _payload_pair(family: KernelFamily) -> tuple[dict[str, Any], dict[str, Any]]:
    if family == KernelFamily.SQL_DIALECT:
        return (
            {"sql": "SELECT IFNULL(a, 0) FROM `t` LIMIT 1, 2", "source_dialect": "mysql", "target_dialect": "postgresql"},
            {"sql": "SELECT NOW() FROM `u`", "source_dialect": "mysql", "target_dialect": "postgresql"},
        )
    if family == KernelFamily.CONCURRENCY_WFG:
        return ({"lock_acquisitions": [["A", "B"], ["B", "A"]]}, {"lock_acquisitions": [["A", "B"], ["A", "C"]]})
    if family == KernelFamily.RETRIEVAL_RANK:
        return ({"query": "deadlock lock order"}, {"query": "fencing token lease"})
    if family == KernelFamily.POLICY_EVAL:
        return (
            {"request": {"action": "ledger.post", "resource": "tenant-a/x", "rules": [{"effect": "ALLOW", "action": "ledger.post", "resource_prefix": "tenant-a/"}]}},
            {"request": {"action": "ledger.post", "resource": "tenant-b/x", "rules": [{"effect": "ALLOW", "action": "ledger.post", "resource_prefix": "tenant-a/"}]}},
        )
    if family == KernelFamily.AST_TRANSFORM:
        return (
            {"source_code": "def alpha(x: int) -> int:\n    return x + 1\n"},
            {"source_code": "def beta(y: int) -> int:\n    if y < 0:\n        return 0\n    return y\n"},
        )
    return ({"text": "alpha-corpus"}, {"text": "beta-corpus-distinct"})


def prove_input_dependence(sample_skills: Mapping[str, str]) -> tuple[int, int, list[str]]:
    passed = 0
    failures: list[str] = []
    for skill, pack in sample_skills.items():
        family = execute_kernel(skill, {}, pack=pack).family
        left_payload, right_payload = _payload_pair(KernelFamily(family))
        left = execute_kernel(skill, left_payload, pack=pack)
        right = execute_kernel(skill, right_payload, pack=pack)
        again = execute_kernel(skill, left_payload, pack=pack)
        ok = left.ok and right.ok and left.output_digest != right.output_digest and left.output_digest == again.output_digest
        if ok:
            passed += 1
        else:
            failures.append(skill)
    return len(sample_skills), passed, failures


def run_foundry_insight() -> dict[str, Any]:
    broker = IndustrialLocalHostBroker()
    catalog = broker.execute_catalog()
    sample: dict[str, str] = {}
    seen_packs: set[str] = set()
    for name, program in broker._programs.items():
        pack = str(program.document.get("pack") or "")
        if pack in seen_packs:
            continue
        seen_packs.add(pack)
        sample[name] = pack
        if len(sample) >= 18:
            break
    checks, passed, failures = prove_input_dependence(sample)
    return {
        "executed": catalog.executed,
        "succeeded": catalog.succeeded,
        "failed_skills": catalog.failed_skills,
        "families": catalog.families,
        "llm_required_count": catalog.llm_required_count,
        "input_dependence_checks": checks,
        "input_dependence_passed": passed,
        "input_dependence_failures": failures,
        "local_semantic_skills": len(LOCAL_SEMANTIC_SKILLS),
        "brokered_expected": EXPECTED_BROKERED_SKILLS,
        "atomic_expected": EXPECTED_ATOMIC_SKILLS,
        "ok": catalog.ok and passed == checks and len(LOCAL_SEMANTIC_SKILLS) == EXPECTED_LOCAL_SEMANTIC_SKILLS,
    }


def run_closed_loop(qa_results: list[Any] | None = None) -> InsightReport:
    foundry = run_foundry_insight()
    qa_healed = qa_integrity = qa_mutation = qa_loop = 0
    qa_details: list[dict[str, Any]] = []
    if qa_results:
        for row in qa_results:
            qa_healed += int(bool(getattr(row, "healed", False)))
            qa_integrity += int(bool(getattr(row, "integrity_ok", False)))
            qa_mutation += int(bool(getattr(row, "mutation_caught", False)))
            qa_loop += int(bool(getattr(row, "loop_guard_ok", False)))
            qa_details.append(
                {
                    "name": getattr(row, "name", ""),
                    "category": getattr(row, "category", ""),
                    "healed": getattr(row, "healed", False),
                    "integrity_ok": getattr(row, "integrity_ok", False),
                    "mutation_caught": getattr(row, "mutation_caught", False),
                }
            )
    qa_total = max(1, len(qa_results or []))
    foundry_ok = bool(foundry["ok"])
    qa_ok = (qa_healed == qa_total and qa_integrity == qa_total and qa_mutation == qa_total and qa_loop == qa_total) if qa_results else False
    percent = 100.0 if foundry_ok and qa_ok else (50.0 if foundry_ok or qa_ok else 0.0)
    if foundry_ok and qa_ok:
        percent = 100.0
    return InsightReport(
        foundry_executed=int(foundry["executed"]),
        foundry_succeeded=int(foundry["succeeded"]),
        local_semantic_skills=int(foundry["local_semantic_skills"]),
        atomic_executable=int(foundry["succeeded"]) + int(foundry["local_semantic_skills"]),
        input_dependent_checks=int(foundry["input_dependence_checks"]),
        input_dependent_passed=int(foundry["input_dependence_passed"]),
        qa_healed=qa_healed,
        qa_integrity_ok=qa_integrity,
        qa_mutation_caught=qa_mutation,
        qa_loop_guard_ok=qa_loop,
        families=dict(foundry["families"]),
        industrial_quality_percent=percent,
        details={
            "foundry": {k: v for k, v in foundry.items() if k != "failed_skills"},
            "foundry_failed_skills": foundry["failed_skills"],
            "qa": qa_details,
            "digest": hashlib.sha256(json.dumps(qa_details, sort_keys=True).encode()).hexdigest(),
        },
    )
