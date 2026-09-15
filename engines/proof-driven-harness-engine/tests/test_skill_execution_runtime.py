"""Unit tests for universal SkillExecutionRuntime and catalog dispatching."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from elmos_proof_harness.skill_execution_runtime import (
    ExecutionMode,
    ExecutionStatus,
    ImplementationStatus,
    SkillCatalog,
    SkillExecutionReceipt,
    SkillExecutionRuntime,
)


@pytest.fixture
def repo_root() -> Path:
    current = Path(__file__).resolve()
    while current.parent != current:
        if (current / ".agents").is_dir() or (current / "Makefile").is_file():
            return current
        current = current.parent
    return Path.cwd()


@pytest.fixture
def runtime(repo_root: Path) -> SkillExecutionRuntime:
    return SkillExecutionRuntime(repo_root)


def test_catalog_loads_skills(runtime: SkillExecutionRuntime):
    catalog = runtime.catalog
    catalog.load()
    assert catalog.total_count > 100, f"Expected > 100 skills, got {catalog.total_count}"
    
    # Check that a known skill can be retrieved
    skill = catalog.get_skill("conv-product-convergence-orchestrator")
    assert skill is not None
    assert skill.bound_engine == "composite-engine"
    assert skill.implementation_status == ImplementationStatus.LOCAL


def test_composite_engine_dispatch(runtime: SkillExecutionRuntime):
    payload = {
        "operation": "topology",
        "nodes": [
            {"id": "service-a", "kind": "service", "status": "active"},
            {"id": "service-b", "kind": "service", "status": "active"},
            {"id": "db-shared", "kind": "database", "status": "active"},
        ],
        "edges": [
            {"source": "service-a", "target": "service-b", "kind": "sync_rpc"},
            {"source": "service-a", "target": "db-shared", "kind": "database_write"},
            {"source": "service-b", "target": "db-shared", "kind": "database_write"},
        ],
    }
    receipt = runtime.execute(
        "conv-product-convergence-orchestrator",
        payload=payload,
        mode=ExecutionMode.EXECUTE,
    )
    assert receipt.status == ExecutionStatus.SUCCESS
    assert receipt.bound_engine == "composite-engine"
    assert receipt.evidence_grade == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert receipt.external_evidence == "NOT_RUN"
    assert receipt.certification_status == "NOT_CERTIFIED"
    assert receipt.outputs["node_count"] == 3
    assert "db-shared" in receipt.outputs["shared_database_writers"]


def test_mature_platform_dr_dispatch(runtime: SkillExecutionRuntime):
    payload = {
        "type": "dr_drill",
        "region_a": "dc-east",
        "region_b": "dc-west",
        "records": [
            {"id": "tx-1", "amount": 100.5},
            {"id": "tx-2", "amount": 250.0},
        ],
    }
    receipt = runtime.execute(
        "tst-chaos-dr-recovery",
        payload=payload,
        mode=ExecutionMode.EXECUTE,
    )
    assert receipt.status == ExecutionStatus.SUCCESS
    assert receipt.bound_engine == "mature-platform-engine"
    assert receipt.evidence_grade == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert receipt.external_evidence == "NOT_RUN"
    assert receipt.certification_status == "NOT_CERTIFIED"
    assert receipt.outputs["primary_region"] == "dc-east"
    assert receipt.outputs["data_divergence_records"] == 0


def test_dry_run_mode(runtime: SkillExecutionRuntime):
    receipt = runtime.execute(
        "b31-canonical-database-ir",
        payload={"sample_key": "val"},
        mode=ExecutionMode.DRY_RUN,
    )
    assert receipt.status == ExecutionStatus.SUCCESS
    assert receipt.execution_mode == ExecutionMode.DRY_RUN
    assert receipt.outputs["check_passed"] is True
    assert "payload_keys_provided" in receipt.outputs


def test_unregistered_skill_fails_closed(runtime: SkillExecutionRuntime):
    receipt = runtime.execute(
        "non-existent-random-skill-name-xyz",
        payload={},
        mode=ExecutionMode.EXECUTE,
    )
    assert receipt.status == ExecutionStatus.UNSUPPORTED
    assert "not found" in receipt.diagnostics[0]
    assert receipt.certification_status == "NOT_CERTIFIED"


def test_strict_non_self_certification_invariants(runtime: SkillExecutionRuntime):
    receipt = runtime.execute("conv-product-convergence-orchestrator", payload={})
    data = receipt.to_dict()
    assert data["evidence_grade"] == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert data["external_evidence"] == "NOT_RUN"
    assert data["certification_status"] == "NOT_CERTIFIED"
