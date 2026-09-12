#!/usr/bin/env python3
"""Pytest suite for ElmosCoreRuntime (all 26 core skills)."""

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/elmos-core"))

from elmos_core_runtime import ElmosCoreRuntime, CoreExecutionResult


@pytest.fixture
def runtime():
    return ElmosCoreRuntime(ROOT)


def test_core_skills_enumeration(runtime):
    assert len(runtime.SKILLS) == 26
    expected_skills = [
        "elmos-infrastructure-program-orchestrator",
        "elmos-architecture-contract-governance",
        "elmos-identity-tenant-security",
        "elmos-temporal-task-reliability",
        "elmos-repository-snapshot-workspace",
        "elmos-content-addressed-cache",
        "elmos-reproducible-toolchain",
        "elmos-staging-snapshot-promotion",
        "elmos-incremental-semantic-index",
        "elmos-runner-scheduler-execution",
        "elmos-semantic-ir-compiler-platform",
        "elmos-secure-sandbox-runtime",
        "elmos-model-gateway-agent-runtime",
        "elmos-policy-supply-chain-signing",
        "elmos-verification-fabric",
        "elmos-evidence-pack-offline-verification",
        "elmos-java-migration-production-loop",
        "elmos-observability-finops",
        "elmos-backup-recovery-replay",
        "elmos-progressive-delivery",
        "elmos-scale-benchmark-certification",
        "elmos-auto-skill-router",
        "elmos-proof-driven-certification",
        "elmos-live-workbench",
        "elmos-project-synthesis",
        "elmos-ai-optimization",
    ]
    for sk in expected_skills:
        assert sk in runtime.SKILLS, f"Missing {sk} in runtime"


@pytest.mark.parametrize("skill_name", [
    "elmos-infrastructure-program-orchestrator",
    "elmos-architecture-contract-governance",
    "elmos-identity-tenant-security",
    "elmos-temporal-task-reliability",
    "elmos-repository-snapshot-workspace",
    "elmos-content-addressed-cache",
    "elmos-reproducible-toolchain",
    "elmos-staging-snapshot-promotion",
    "elmos-incremental-semantic-index",
    "elmos-runner-scheduler-execution",
    "elmos-semantic-ir-compiler-platform",
    "elmos-secure-sandbox-runtime",
    "elmos-model-gateway-agent-runtime",
    "elmos-policy-supply-chain-signing",
    "elmos-verification-fabric",
    "elmos-evidence-pack-offline-verification",
    "elmos-java-migration-production-loop",
    "elmos-observability-finops",
    "elmos-backup-recovery-replay",
    "elmos-progressive-delivery",
    "elmos-scale-benchmark-certification",
    "elmos-auto-skill-router",
    "elmos-proof-driven-certification",
    "elmos-live-workbench",
    "elmos-project-synthesis",
    "elmos-ai-optimization",
])
def test_each_skill_execution(runtime, skill_name):
    result = runtime.execute(skill_name, {"test_mode": True})
    assert isinstance(result, CoreExecutionResult)
    assert result.skill == skill_name
    assert result.status == "SUCCESS"
    assert result.local_handler_status == "PASSED"
    assert result.external_evidence_status == "LOCAL_EXECUTED"
    assert result.certification_status == "NOT_CERTIFIED"
    assert len(result.evidence) > 0


def test_custom_payload_program_orchestrator(runtime):
    res = runtime.execute("elmos-infrastructure-program-orchestrator", {"slice": "production-slice-01"})
    assert res.details["selected_slice"] == "production-slice-01"
    assert res.details["wall_clock_eta_seconds"] > 0


def test_custom_payload_identity_security(runtime):
    res = runtime.execute("elmos-identity-tenant-security", {"tenant_id": "tenant-custom-corp"})
    assert res.details["tenant_id"] == "tenant-custom-corp"
    assert res.details["rls_enforced"] is True


def test_custom_payload_temporal_reliability(runtime):
    res = runtime.execute("elmos-temporal-task-reliability", {"workflow_id": "wf-custom-009"})
    assert res.details["workflow_id"] == "wf-custom-009"
    assert res.details["cancellable"] is True


def test_custom_payload_proof_driven_certification(runtime):
    res = runtime.execute("elmos-proof-driven-certification")
    assert res.details["non_self_certification_enforced"] is True
    assert res.details["zero_tests_rejected"] is True


def test_custom_payload_auto_skill_router(runtime):
    res = runtime.execute("elmos-auto-skill-router", {"task": "migrate spring boot to aspnet"})
    assert res.details["mandatory_trust_rule_applied"] is True
    assert "elmos-proof-driven-certification" in res.details["matched_skills"]


def test_unknown_skill_raises(runtime):
    with pytest.raises(ValueError, match="Unknown core skill"):
        runtime.execute("elmos-nonexistent-skill")
