from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .contracts import SkillOutcome


PACKAGE_ID = "elmos-formal-assurance-kernel-v1.0.0"
SOURCE_ARCHIVE_SHA256 = (
    "sha256:7d397f9379e15023208d3fb49b3928af07b7b6134e6a91fe70ebaf7048f9e73e"
)


@dataclass(frozen=True)
class SkillBinding:
    skill_id: str
    priority: str
    domain: str
    handler_id: str
    capability_state: str


_SKILL_META = (
    ("elmos-api-contract-verifier", "P0", "project-generation"),
    ("elmos-architecture-constraint-checker", "P0", "project-generation"),
    ("elmos-assumption-ledger", "P0", "core"),
    ("elmos-counterexample-to-test", "P0", "platform"),
    ("elmos-credit-billing-invariant-model", "P0", "platform"),
    ("elmos-cross-language-product-program", "P0", "cross-language"),
    ("elmos-data-invariant-verifier", "P0", "project-generation"),
    ("elmos-ddl-constraint-preservation", "P0", "sql-conversion"),
    ("elmos-dml-state-equivalence", "P0", "sql-conversion"),
    ("elmos-dynamic-sql-proof-boundary", "P0", "sql-conversion"),
    ("elmos-effect-exception-trace-refinement", "P0", "cross-language"),
    ("elmos-formal-assurance-orchestrator", "P0", "core"),
    ("elmos-formal-assurance-report", "P0", "platform"),
    ("elmos-formal-release-gate", "P0", "platform"),
    ("elmos-formal-spec-ir", "P0", "core"),
    ("elmos-generated-workflow-model-checker", "P0", "project-generation"),
    ("elmos-java-jml-contract-verifier", "P0", "spring-modernization"),
    ("elmos-language-semantic-profile", "P0", "cross-language"),
    ("elmos-lease-fencing-verifier", "P0", "platform"),
    ("elmos-legacy-modernization-trace-validator", "P0", "spring-modernization"),
    ("elmos-observable-behavior-contract", "P0", "core"),
    ("elmos-proof-artifact-store", "P0", "platform"),
    ("elmos-proof-cache-invalidation", "P0", "core"),
    ("elmos-proof-obligation-planner", "P0", "core"),
    ("elmos-proof-status-policy", "P0", "core"),
    ("elmos-repository-refinement-composer", "P0", "cross-language"),
    ("elmos-requirement-to-formal-spec", "P0", "project-generation"),
    ("elmos-resource-termination-verifier", "P0", "project-generation"),
    ("elmos-routine-contract-verifier", "P0", "sql-conversion"),
    ("elmos-rule-preservation-prover", "P0", "cross-language"),
    ("elmos-schema-losslessness-proof", "P0", "sql-conversion"),
    ("elmos-semantic-gap-obligation-generator", "P0", "cross-language"),
    ("elmos-semantic-ir-formal-semantics", "P0", "cross-language"),
    ("elmos-spring-exception-mapping-refinement", "P0", "spring-modernization"),
    ("elmos-spring-filter-interceptor-order-proof", "P0", "spring-modernization"),
    ("elmos-spring-route-binding-proof", "P0", "spring-modernization"),
    ("elmos-spring-security-chain-model", "P0", "spring-modernization"),
    ("elmos-spring-session-state-refinement", "P0", "spring-modernization"),
    ("elmos-spring-transaction-refinement", "P0", "spring-modernization"),
    ("elmos-sql-query-equivalence", "P0", "sql-conversion"),
    ("elmos-sql-semantic-ir", "P0", "sql-conversion"),
    ("elmos-sql-type-precision-verifier", "P0", "sql-conversion"),
    ("elmos-tenant-noninterference-verifier", "P0", "project-generation"),
    ("elmos-tla-task-runtime-model", "P0", "platform"),
    ("elmos-trigger-trace-verifier", "P0", "sql-conversion"),
    ("elmos-trusted-computing-base-registry", "P0", "core"),
    ("elmos-verifier-portfolio-router", "P0", "core"),
    ("elmos-waiver-governance", "P0", "platform"),
    ("elmos-concurrency-async-refinement", "P1", "cross-language"),
    ("elmos-formal-model-versioning", "P1", "core"),
    ("elmos-liveness-fairness-verifier", "P1", "project-generation"),
    ("elmos-proof-carrying-conversion", "P1", "cross-language"),
    ("elmos-proof-drift-monitor", "P1", "platform"),
    ("elmos-proof-evidence-bundle", "P1", "platform"),
    ("elmos-spring-data-migration-refinement", "P1", "spring-modernization"),
    ("elmos-spring-proxy-aop-semantic-checker", "P1", "spring-modernization"),
    ("elmos-sql-transaction-exception-refinement", "P1", "sql-conversion"),
    ("elmos-verified-core-generator", "P1", "project-generation"),
    ("elmos-formal-observability-slo", "P2", "platform"),
    ("elmos-reflection-ffi-boundary-verifier", "P2", "cross-language"),
)


def _handler_id(skill_id: str) -> str:
    return "execute_" + skill_id.replace("-", "_")


def _capability_state(priority: str, domain: str) -> str:
    if priority == "P2":
        return "PARTIAL_EXTERNAL_OBSERVABILITY_OR_BOUNDARY_EVIDENCE_REQUIRED"
    if domain in {"core", "platform"}:
        return "LOCAL_BOUNDED"
    return "PARTIAL_NATIVE_TOOLCHAIN_OR_RUNTIME_REQUIRED"


def _load_handlers() -> dict[str, Callable[..., SkillOutcome]]:
    from . import handlers

    result: dict[str, Callable[..., SkillOutcome]] = {}
    for skill_id, _, _ in _SKILL_META:
        handler = getattr(handlers, _handler_id(skill_id), None)
        if handler is None or not callable(handler):
            raise RuntimeError(f"missing exact handler for {skill_id}")
        result[skill_id] = handler
    return result


class SkillRegistry:
    """Exact allowlisted source identity to callable binding."""

    def __init__(self, metadata_path: str | Path | None = None) -> None:
        handlers = _load_handlers()
        self._bindings = {
            skill_id: SkillBinding(
                skill_id=skill_id,
                priority=priority,
                domain=domain,
                handler_id=_handler_id(skill_id),
                capability_state=_capability_state(priority, domain),
            )
            for skill_id, priority, domain in _SKILL_META
        }
        self._handlers = handlers
        if metadata_path is not None:
            self._verify_metadata(Path(metadata_path))

    @property
    def count(self) -> int:
        return len(self._bindings)

    def get(self, skill_id: str) -> SkillBinding:
        try:
            return self._bindings[skill_id]
        except KeyError as exc:
            raise KeyError(f"unknown formal assurance Skill: {skill_id}") from exc

    def handler(self, skill_id: str) -> Callable[..., SkillOutcome]:
        self.get(skill_id)
        return self._handlers[skill_id]

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "skillId": binding.skill_id,
                "priority": binding.priority,
                "domain": binding.domain,
                "handlerId": binding.handler_id,
                "capabilityState": binding.capability_state,
                "implementationState": "BOUND_LOCAL_EXACT",
                "externalEvidenceStatus": "NOT_RUN",
                "certificationStatus": "NOT_CERTIFIED",
            }
            for binding in self._bindings.values()
        ]

    def _verify_metadata(self, path: Path) -> None:
        if not path.is_file() or path.is_symlink():
            raise ValueError(
                f"formal assurance registry metadata is missing or unsafe: {path}"
            )
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("packageId") != PACKAGE_ID:
            raise ValueError("formal assurance registry package identity mismatch")
        if document.get("sourceArchiveSha256") != SOURCE_ARCHIVE_SHA256:
            raise ValueError("formal assurance registry source digest mismatch")
        records = document.get("skills")
        if not isinstance(records, list) or len(records) != len(_SKILL_META):
            raise ValueError("formal assurance registry must contain exactly 60 Skills")
        actual = {
            record.get("skillId"): record
            for record in records
            if isinstance(record, dict)
        }
        expected = {
            skill_id: (priority, domain) for skill_id, priority, domain in _SKILL_META
        }
        if set(actual) != set(expected):
            raise ValueError("formal assurance registry Skill identity drift")
        for skill_id, (priority, domain) in expected.items():
            record = actual[skill_id]
            if (
                record.get("priority") != priority
                or record.get("domain") != domain
                or record.get("handlerId") != _handler_id(skill_id)
            ):
                raise ValueError(f"formal assurance registry binding drift: {skill_id}")


__all__ = ["PACKAGE_ID", "SOURCE_ARCHIVE_SHA256", "SkillBinding", "SkillRegistry"]
