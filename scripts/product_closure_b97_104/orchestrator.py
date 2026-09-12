#!/usr/bin/env python3
"""Product Closure Orchestrator for Batches 97-104.

Executes product closure batches or individual skills, assembling
content-addressed execution evidence and receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from scripts.product_closure_b97_104.canonical import (
    digest,
    format_instant,
)
from scripts.product_closure_b97_104.engine import ClosureDeterministicEngine
from scripts.product_closure_b97_104.errors import ProductClosureError
from scripts.product_closure_b97_104.registry import (
    ProductClosureRegistry,
    get_closure_registry,
)


@dataclass(frozen=True)
class ClosureBatchReceipt:
    batch: int
    package: str
    status: str
    certification: str
    skills_executed: int
    receipt_digest: str
    journal_digest: str
    timestamp: str
    skill_results: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch": self.batch,
            "package": self.package,
            "status": self.status,
            "certification": self.certification,
            "skills_executed": self.skills_executed,
            "receipt_digest": self.receipt_digest,
            "journal_digest": self.journal_digest,
            "timestamp": self.timestamp,
            "skill_results": self.skill_results,
        }


class ProductClosureOrchestrator:
    """Orchestrates execution of Batch 97-104 Product Closure skills."""

    def __init__(
        self,
        registry: Optional[ProductClosureRegistry] = None,
        engine: Optional[ClosureDeterministicEngine] = None,
    ) -> None:
        self.registry = registry or get_closure_registry()
        self.engine = engine or ClosureDeterministicEngine()

    def run_skill(
        self,
        skill_identifier: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if skill_identifier.startswith("B"):
            skill = self.registry.get_by_id(skill_identifier)
        else:
            skill = self.registry.get_by_name(skill_identifier)

        res = self.engine.execute_skill(
            skill.source_id, skill.archetype_name, payload
        )
        return {
            "skill_id": skill.source_id,
            "installed_name": skill.installed_name,
            "batch": skill.batch,
            "archetype": skill.archetype_name,
            "status": "LOCAL_EXECUTED",
            "certification": "NOT_CERTIFIED",
            "output_digest": res.output_digest,
            "journal_digest": res.journal_digest,
            "data": res.output_data["data"],
        }

    def run_batch(
        self,
        batch_number: int,
        custom_fixtures: Optional[dict[str, dict[str, Any]]] = None,
    ) -> ClosureBatchReceipt:
        skills = self.registry.get_batch(batch_number)
        if not skills:
            raise ProductClosureError(f"No skills found for closure batch {batch_number}")

        fixtures = custom_fixtures or {}
        step_results: list[dict[str, Any]] = []

        default_payloads: dict[str, dict[str, Any]] = {
            "estate-inventory-closure": {
                "skills": [f"skill-{i:02d}" for i in range(16)],
                "aliases": {f"skill-{i:02d}": f"alias-{i:02d}" for i in range(16)},
            },
            "contract-certification-closure": {
                "contract_id": f"B{batch_number}_CONTRACT",
                "inputs_schema": {"type": "object", "required": ["tenant_id"]},
                "outputs_schema": {"type": "object", "required": ["status"]},
                "preconditions": ["authenticated", "lease_active"],
            },
            "effect-messaging-closure": {
                "workflow_id": f"WF_CLOSURE_B{batch_number}",
                "steps": ["intake", "transform", "verify", "commit"],
                "lease_seconds": 120,
            },
            "sandbox-profile-closure": {
                "runner_id": f"runner-b{batch_number}",
                "isolation_level": "MICROVM",
                "egress_policy": "ALLOWLISTED_REGISTRY",
            },
            "route-discovery-closure": {
                "source_language": "LegacyJava",
                "target_language": "ModernJava21",
                "recipes": ["recipes.java.modernize"],
            },
            "verification-testing-closure": {
                "oracles": ["state-oracle", "api-oracle"],
                "test_count": 20,
                "mutations_killed": 20,
            },
            "independent-verifier-closure": {
                "artifact_id": f"ART_B{batch_number}",
                "executor_id": "executor-worker-01",
                "verifier_id": "independent-verifier-agent",
            },
            "release-environment-closure": {
                "environments": ["clean-room-ci", "staging-vpc"],
                "gate_checks": ["contract", "security", "matrix", "dr_replay"],
            },
        }

        for s in skills:
            payload = fixtures.get(s.source_id, default_payloads.get(s.archetype_name, {}))
            res = self.engine.execute_skill(s.source_id, s.archetype_name, payload)
            step_results.append({
                "source_id": s.source_id,
                "installed_name": s.installed_name,
                "archetype": s.archetype_name,
                "output_digest": res.output_digest,
                "input_digest": res.input_digest,
            })

        timestamp = format_instant()
        raw_receipt = {
            "batch": batch_number,
            "skills_count": len(step_results),
            "step_results": step_results,
            "timestamp": timestamp,
        }
        receipt_digest = digest(raw_receipt)

        return ClosureBatchReceipt(
            batch=batch_number,
            package=self.registry.package_name,
            status="LOCAL_EXECUTED",
            certification="NOT_CERTIFIED",
            skills_executed=len(step_results),
            receipt_digest=receipt_digest,
            journal_digest=self.engine._journal.journal_digest,
            timestamp=timestamp,
            skill_results=step_results,
        )
