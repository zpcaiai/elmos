#!/usr/bin/env python3
"""Language Pack Orchestrator for Batches 81-95.

Executes complete language migration pipelines or individual skills,
assembling content-addressed execution evidence and lineage graphs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from scripts.language_packs_b81_95.canonical import (
    digest,
    format_instant,
    idempotency_key,
)
from scripts.language_packs_b81_95.engine import DeterministicEngine
from scripts.language_packs_b81_95.errors import LanguagePackError
from scripts.language_packs_b81_95.registry import (
    LanguagePackRegistry,
    LanguageSkill,
    get_registry,
)


@dataclass(frozen=True)
class BatchRunReceipt:
    """Receipt of one complete batch run."""

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


class LanguagePackOrchestrator:
    """Orchestrates execution of Batch 81-95 Language Packs."""

    def __init__(
        self,
        registry: Optional[LanguagePackRegistry] = None,
        engine: Optional[DeterministicEngine] = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.engine = engine or DeterministicEngine()

    def run_skill(
        self,
        skill_identifier: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single skill by source ID (e.g. PG223) or installed name."""
        if skill_identifier.startswith("PG"):
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
    ) -> BatchRunReceipt:
        """Run all 12 skills of a language batch in dependency order."""
        skills = self.registry.get_batch(batch_number)
        if not skills:
            raise LanguagePackError(f"No skills found for batch {batch_number}")

        fixtures = custom_fixtures or {}
        step_results: list[dict[str, Any]] = []

        # Standard baseline fixture
        default_payloads: dict[str, dict[str, Any]] = {
            "discovery-inventory": {
                "sources": [
                    {"path": f"src/batch_{batch_number}/main.src", "content": "PROGRAM main\nBEGIN\n  DISPLAY 'Hello'\nEND", "dialect": "native"}
                ]
            },
            "parser-semantic-model": {
                "source_code": "PROGRAM test\nDATA:\n  var x = 10\nBEGIN\n  IF x > 5 THEN PERFORM sub\nEND",
                "language": f"Batch{batch_number}"
            },
            "schema-data-compiler": {
                "schema_name": f"B{batch_number}_SCHEMA",
                "fields": [
                    {"name": "ID", "type": "INT", "length": 4},
                    {"name": "AMOUNT", "type": "COMP-3", "length": 8},
                    {"name": "NAME", "type": "CHAR", "length": 32},
                ]
            },
            "batch-workflow-modeler": {
                "workflow_id": f"WF_B{batch_number}",
                "steps": [
                    {"id": "STEP1", "program": "INIT_PGM", "depends_on": []},
                    {"id": "STEP2", "program": "PROCESS_PGM", "depends_on": ["STEP1"]},
                ]
            },
            "transaction-modernizer": {
                "transaction_name": f"TX_B{batch_number}",
                "isolation_level": "SERIALIZABLE",
                "has_commit": True,
                "has_rollback": True,
                "resources": ["DB", "QUEUE"],
            },
            "data-storage-adapter": {
                "storage_type": "LEGACY_INDEXED",
                "primary_key": "PK_ID",
                "entities": ["Customer", "Account"],
                "target_storage": "POSTGRESQL",
            },
            "business-rule-recovery": {
                "raw_rules": [
                    {"id": "R1", "condition": "amount > 1000", "action": "REQUIRE_APPROVAL"},
                    {"id": "R2", "condition": "status == 'ACTIVE'", "action": "ALLOW_LOGIN"},
                ]
            },
            "api-event-extractor": {
                "service_name": f"ModernService_B{batch_number}",
                "endpoints": [
                    {"name": "query_status", "method": "GET", "path": "/status"},
                    {"name": "submit_order", "method": "POST", "path": "/order"},
                ]
            },
            "target-generator": {
                "target_language": "Java",
                "component_name": f"ServiceHandlerB{batch_number}",
                "methods": ["handleEvent", "validatePayload"],
            },
            "parallel-run-verifier": {
                "test_cases": [
                    {"id": "TC-01", "legacy_output": {"val": 42}, "target_output": {"val": 42}},
                    {"id": "TC-02", "legacy_output": {"status": "OK"}, "target_output": {"status": "OK"}},
                ]
            },
            "security-operations-mapper": {
                "legacy_roles": [
                    {"role": "OPERATOR", "privileges": ["EXECUTE", "READ"]},
                    {"role": "ADMIN", "privileges": ["ALL"]},
                ]
            },
            "cutover-decommission-planner": {
                "strategy": "CANARY_DUAL_RUN",
                "waves": ["canary_10", "wave_50", "final_100"],
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

        return BatchRunReceipt(
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
