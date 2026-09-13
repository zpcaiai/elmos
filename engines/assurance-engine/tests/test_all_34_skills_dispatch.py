"""Tests for allowlisted dispatch of all 34 skills and master orchestrator."""

import pytest

from elmos_assurance_engine.dispatcher import (
    AssuranceSkillDispatcher,
    dispatch_assurance_skill,
)
from elmos_assurance_engine.orchestrator import AssuranceOrchestrator

ALL_34_SKILLS = [
    "elmos-assurance-bootstrap",
    "elmos-assurance-scope",
    "elmos-assurance-requirement-oracles",
    "elmos-assurance-interface-discovery",
    "elmos-assurance-contract-ir",
    "elmos-assurance-state-effects",
    "elmos-assurance-coverage-planner",
    "elmos-assurance-test-generation",
    "elmos-assurance-fixtures-environments",
    "elmos-assurance-smoke-gate",
    "elmos-assurance-full-regression",
    "elmos-assurance-differential-runtime",
    "elmos-assurance-property-fuzz",
    "elmos-assurance-mutation-auditor",
    "elmos-assurance-lean",
    "elmos-assurance-model-checking",
    "elmos-assurance-verified-rules",
    "elmos-assurance-evidence-graph",
    "elmos-assurance-gate-engine",
    "elmos-assurance-ethen-audit",
    "elmos-assurance-signed-attestations",
    "elmos-assurance-bounded-repair",
    "elmos-assurance-generation-domain",
    "elmos-assurance-sql-domain",
    "elmos-assurance-spring-domain",
    "elmos-assurance-repository-domain",
    "elmos-assurance-durable-execution",
    "elmos-assurance-security-isolation",
    "elmos-assurance-router-budget",
    "elmos-assurance-commercial-control",
    "elmos-assurance-calibration-holdout",
    "elmos-assurance-release-recertification",
    "elmos-assurance-workbench-ui",
    "elmos-assurance-orchestrator",
]


def test_all_34_skills_registered():
    registered = set(AssuranceSkillDispatcher.HANDLERS.keys())
    expected = set(ALL_34_SKILLS)
    assert registered == expected
    assert len(registered) == 34


@pytest.mark.parametrize("skill_name", ALL_34_SKILLS)
def test_each_skill_dispatches_safely(skill_name):
    # Dispatching with empty or minimal payload must return a structured response, not crash with unhandled exception
    res = dispatch_assurance_skill(skill_name, {})
    assert isinstance(res, dict)
    assert "status" in res


def test_unregistered_skill_fails_closed():
    with pytest.raises(KeyError, match="UNKNOWN_OR_UNAUTHORIZED_ASSURANCE_SKILL"):
        dispatch_assurance_skill("arbitrary-unregistered-skill", {})


def test_orchestrator_vertical_slice_execution():
    orch = AssuranceOrchestrator()
    report = orch.run_vertical_slice({
        "tenant_id": "tenant-test",
        "project_id": "proj-test",
        "run_id": "run-test-01",
    })
    assert report["overall_status"] == "PASS"
    assert "B00" in report["batches"]
    assert "B01" in report["batches"]
    assert "B02" in report["batches"]
    assert "B03" in report["batches"]
    assert report["batches"]["B00"]["status"] == "PASS"
    assert report["batches"]["B01"]["status"] == "PASS"
    assert report["batches"]["B02"]["status"] == "PASS"
    assert report["batches"]["B03"]["status"] == "PASS"
    assert report["production_signing_allowed"] is False
