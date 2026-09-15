"""Tests for Delta v3.2 Skill Registry and Unified Dispatcher."""

from __future__ import annotations

from typing import Any
import pytest

from elmos_proof_harness.delta_v32 import (
    DELTA_V32_SKILL_REGISTRY,
    execute_v32_skill,
)


def test_delta_v32_registry_completeness() -> None:
    """Verify that all 20 v3.2 skills are registered with proper metadata."""
    assert len(DELTA_V32_SKILL_REGISTRY) == 20
    for name, desc in DELTA_V32_SKILL_REGISTRY.items():
        assert desc.skill_name == name
        assert desc.batch.startswith("B")
        assert desc.kernel.startswith("K")
        assert len(desc.description) > 0


@pytest.mark.parametrize("skill_name", list(DELTA_V32_SKILL_REGISTRY.keys()))
def test_execute_v32_skill_smoke(skill_name: str) -> None:
    """Test invocation of each v3.2 skill with default/smoke payload."""
    payload: dict[str, Any] = {
        "execution_id": f"exec-{skill_name}",
        "action": "default",
    }
    result = execute_v32_skill(skill_name, payload)
    assert result["status"] == "SUCCESS"
    assert result["skill"] == skill_name


def test_durable_execution_ownership_actions() -> None:
    res_quiesce = execute_v32_skill(
        "durable-execution-ownership",
        {"execution_id": "exec-1", "owner_id": "owner-1", "epoch": 1, "action": "quiesce"},
    )
    assert res_quiesce["ownership"]["state"] == "QUIESCING"

    res_release = execute_v32_skill(
        "durable-execution-ownership",
        {"execution_id": "exec-2", "owner_id": "owner-2", "epoch": 1, "action": "release"},
    )
    assert res_release["ownership"]["state"] == "RELEASED"


def test_effective_policy_authority_intersection() -> None:
    res = execute_v32_skill(
        "effective-policy-authority",
        {
            "policies": [
                {"allows": ["read", "write"], "denies": []},
                {"allows": ["read", "execute"], "denies": ["write"]},
            ]
        },
    )
    assert res["effective_policy"]["allows"] == ["read"]
    assert res["effective_policy"]["denies"] == ["write"]


def test_release_evidence_exact_artifact_gate() -> None:
    res_pass = execute_v32_skill(
        "release-evidence-exact-artifact",
        {
            "release_id": "rel-01",
            "checks": [{"status": "PASS", "evidence_id": "ev-1"}],
            "exact_artifact_verified": True,
        },
    )
    assert res_pass["gate_decision"] == "PASS"

    res_fail = execute_v32_skill(
        "release-evidence-exact-artifact",
        {
            "release_id": "rel-02",
            "checks": [{"status": "FAIL", "evidence_id": "ev-2"}],
            "exact_artifact_verified": True,
        },
    )
    assert res_fail["gate_decision"] == "FAIL"


def test_unknown_skill_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown Delta v3.2 skill"):
        execute_v32_skill("non-existent-skill", {})
