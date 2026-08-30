"""Application service for the semantic-assurance runtime.

This layer prepares campaigns and dispatches exact Skills. It cannot execute
native toolchains by itself and cannot certify a route.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import AdapterSet
from .canonical import digest_bytes, validate_identifier
from .contracts import TrustedIdentity
from .registry import EXPECTED_BATCH_COUNTS, SkillRegistry
from .runtime import SemanticAssuranceRuntime
from .store import SemanticAssuranceStore


class SemanticAssuranceService:
    """Stable service boundary for catalog, planning and exact dispatch."""

    def __init__(
        self,
        *,
        registry: SkillRegistry | None = None,
        store: SemanticAssuranceStore | None = None,
        adapters: AdapterSet | None = None,
    ) -> None:
        self.runtime = SemanticAssuranceRuntime(
            registry=registry,
            store=store,
            adapters=adapters,
        )
        self.skills_registry = {
            item["sourceName"]: item for item in self.runtime.registry.list()
        }

    def status(self) -> dict[str, Any]:
        return self.runtime.status().to_dict()

    def catalog(self, *, batch: str | None = None) -> list[dict[str, Any]]:
        if batch is not None and batch not in EXPECTED_BATCH_COUNTS:
            raise ValueError(f"unsupported batch: {batch}")
        return self.runtime.registry.list(batch)

    def dispatch(
        self,
        skill_name: str,
        request: Mapping[str, Any],
        identity: TrustedIdentity,
    ) -> dict[str, Any]:
        return self.runtime.dispatch(skill_name, request, identity)

    def prepare_route_assurance_campaign(
        self,
        *,
        source_technology: str,
        target_technology: str,
        source_bytes: bytes,
        target_bytes: bytes,
        route_id: str | None = None,
    ) -> dict[str, Any]:
        """Prepare a digest-bound nine-batch plan without claiming execution."""

        source = validate_identifier(source_technology, "sourceTechnology")
        target = validate_identifier(target_technology, "targetTechnology")
        route = validate_identifier(
            route_id or f"{source}-to-{target}",
            "routeId",
        )
        return {
            "schemaVersion": "elmos.semantic-assurance.campaign-plan/v1",
            "routeId": route,
            "sourceTechnology": source,
            "targetTechnology": target,
            "sourceDigest": digest_bytes(source_bytes),
            "targetDigest": digest_bytes(target_bytes),
            "batchPlan": [
                {"batch": batch, "skillCount": count, "executionStatus": "NOT_RUN"}
                for batch, count in EXPECTED_BATCH_COUNTS.items()
            ],
            "plannedSkills": self.runtime.registry.count,
            "executionStatus": "NOT_RUN",
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
            "nextAction": "invoke exact Skills with trusted scope and configured adapters",
        }

    def run_route_assurance_campaign(
        self,
        source_lang: str,
        target_lang: str,
        source_code: str,
        target_code: str,
        route_id: str | None = None,
    ) -> dict[str, Any]:
        """Compatibility API that now fails closed as a plan-only operation."""

        plan = self.prepare_route_assurance_campaign(
            source_technology=source_lang,
            target_technology=target_lang,
            source_bytes=source_code.encode("utf-8"),
            target_bytes=target_code.encode("utf-8"),
            route_id=route_id,
        )
        return {
            **plan,
            "readiness": "BLOCKED",
            "blockers": [
                "EXACT_SCOPE_REQUIRED",
                "NATIVE_FORMAL_FUZZ_ADAPTERS_NOT_EXECUTED",
                "INDEPENDENT_EVIDENCE_NOT_RUN",
                "CERTIFICATION_GATE_NOT_RUN",
            ],
        }


def get_assurance_status() -> dict[str, Any]:
    """Return honest package status for the unified CLI gateway."""

    return SemanticAssuranceService().status()


__all__ = ["SemanticAssuranceService", "get_assurance_status"]
