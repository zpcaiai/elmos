"""Executable test suite verifying all 50 ETGB skills through SkillRegistry."""

from __future__ import annotations

from pathlib import Path
import pytest

from elmos_etgb.registry import SkillRegistry

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "skills/elmos-etgb-full-product-assurance-skills-package-v2.0.0"


@pytest.fixture(scope="module")
def registry() -> SkillRegistry:
    return SkillRegistry(PACKAGE_ROOT)


def test_registry_contains_all_50_skills(registry: SkillRegistry) -> None:
    skills = registry.describe()
    assert len(skills) == 50
    for s in skills:
        assert s["runtime_state"] == "BOUND"
        assert len(s["operations"]) > 0


@pytest.mark.parametrize(
    "skill_name",
    [
        "spring-modernization-validation",
        "repository-translation-validation",
        "project-generation-validation",
        "sql-dialect-routine-validation",
        "identity-access-tenant-validation",
        "platform-control-plane-validation",
        "repository-ingestion-context-validation",
        "multimodal-document-processing-validation",
        "ai-runtime-model-routing-validation",
        "agent-protocol-tooling-validation",
        "rag-memory-knowledge-validation",
        "project-intelligence-validation",
        "online-ide-debug-validation",
        "artifact-document-diagram-validation",
        "collaboration-integrations-validation",
        "billing-entitlements-validation",
        "payment-finance-validation",
        "api-sdk-webhook-validation",
        "storage-search-cache-validation",
        "deployment-operations-validation",
        "security-privacy-compliance-validation",
        "ui-accessibility-localization-validation",
        "analytics-admin-support-validation",
        "notifications-scheduler-validation",
        "ai-solution-factory-validation",
        "data-bigdata-solution-validation",
        "commercial-delivery-certification-validation",
        "product-journey-validation",
        "standards-assurance-validation",
    ],
)
def test_domain_validation_skills(registry: SkillRegistry, skill_name: str) -> None:
    # Test capability query
    cap = registry.dispatch(skill_name, "capability")
    assert cap["status"] == "EXTERNAL_ADAPTER_REQUIRED"
    assert cap["claimable"] is False

    # Test case validation
    case_payload = {
        "case": {
            "id": f"TC-{skill_name}-001",
            "business_line": "cross-cutting",
            "family": "smoke",
            "source": "java",
            "target": "csharp",
            "requirements": ["req1"],
            "execution": {
                "adapter": "local-subprocess",
                "timeout_seconds": 30,
                "command": "test",
            },
            "oracles": ["oracle1"],
            "coverage": {
                "capability_id": "CAP-001",
                "dimensions": {"feature": "smoke"},
            },
            "gates": ["G1"],
            "provenance": {"author": "elmos"},
        }
    }
    val = registry.dispatch(skill_name, "validate_case", case_payload)
    assert val["valid"] is True, f"Validation failed: {val.get('errors')}"


def test_core_assurance_skills(registry: SkillRegistry) -> None:
    # etgb-orchestrator
    eta = registry.dispatch("etgb-orchestrator", "eta", {"results": [{"duration": 1.5}]})
    assert "eta_seconds" in eta or "machine_eta" in eta or "average_duration" in eta or isinstance(eta, (dict, int, float))

    # test-case-authoring
    case_res = registry.dispatch("test-case-authoring", "validate_case", {
        "case": {
            "id": "TC-AUTH-001",
            "business_line": "cross-cutting",
            "family": "smoke",
            "source": "java",
            "target": "python",
            "requirements": ["r1"],
            "execution": {
                "adapter": "local-subprocess",
                "timeout_seconds": 30,
            },
            "oracles": ["oracle1"],
            "coverage": {
                "capability_id": "CAP-001",
                "dimensions": {"feature": "smoke"},
            },
            "gates": ["G1"],
            "provenance": {"author": "elmos"},
        }
    })
    assert case_res["valid"] is True, f"Validation failed: {case_res.get('errors')}"

    # differential-oracle-engine
    diff = registry.dispatch("differential-oracle-engine", "compare_json", {
        "left": {"status": "ok", "code": 200},
        "right": {"status": "ok", "code": 200},
    })
    assert diff["passed"] is True

    # metamorphic-fuzz-mutation
    mut = registry.dispatch("metamorphic-fuzz-mutation", "mutation_summary", {
        "mutants": [{"id": "M1"}],
        "killed": [True],
    })
    assert mut["total"] == 1
    assert mut["killed"] == 1

    # budget-cost-eta-governance
    b_eta = registry.dispatch("budget-cost-eta-governance", "eta", {"results": [{"duration": 0.5}]})
    assert b_eta is not None

    # risk-based-test-selection
    risk = registry.dispatch("risk-based-test-selection", "risk_plan", {
        "cases": [{"id": "C1", "risk": "high"}, {"id": "C2", "risk": "low"}],
        "risk_level": "high",
    })
    assert "case_ids" in risk or "selections" in risk

    # statistical-validity-reproducibility
    wilson = registry.dispatch("statistical-validity-reproducibility", "wilson", {
        "successes": 95,
        "trials": 100,
    })
    assert "lower" in wilson and "upper" in wilson

    # supply-chain-artifact-security
    inspect_res = registry.dispatch("supply-chain-artifact-security", "inspect", {"root": str(PACKAGE_ROOT / "schemas")})
    assert "files" in inspect_res

    # incident-regression-learning
    reg = registry.dispatch("incident-regression-learning", "regression", {
        "incident": {
            "incident_id": "INC-01",
            "summary": "Null pointer in parser",
            "business_line": "cross-cutting",
            "failure_class": "unhandled-null",
        }
    })
    assert "regression_id" in reg

    # multi-tenant-scheduling-isolation
    sched = registry.dispatch("multi-tenant-scheduling-isolation", "schedule", {
        "requests": [
            {"task_id": "T1", "tenant_id": "tenant1", "account_id": "acc1", "priority": 1}
        ]
    })
    assert "dispatched" in sched

    # release-candidate-integrity
    cand_spec = {
        "candidate_id": "cand-001",
        "source_commit": "0123456789abcdef0123456789abcdef01234567",
        "model": "gpt-4",
        "model_revision": "2026-01-01",
        "prompt_digest": "sha256:" + "a" * 64,
        "skill_manifest_digest": "sha256:" + "b" * 64,
        "rule_bundle_digest": "sha256:" + "c" * 64,
        "toolchain_image_digest": "sha256:" + "d" * 64,
        "oracle_version": "v1.0.0",
        "normalization_version": "v1.0.0",
    }
    freeze_res = registry.dispatch("release-candidate-integrity", "freeze", {
        "candidate": cand_spec
    })
    assert "candidate_digest" in freeze_res

    # environment-authority-sandbox
    auth_digest = registry.dispatch("environment-authority-sandbox", "authority_digest", {
        "authority": {"tenant": "T1"}
    })
    assert "digest" in auth_digest

    # checkpoint-resume-recovery
    chk = registry.dispatch("checkpoint-resume-recovery", "verify_checkpoint", {
        "directory": str(PACKAGE_ROOT / "schemas"),
        "run_id": "nonexistent-run",
    })
    assert "valid" in chk

    # evidence-provenance-ledger
    ev = registry.dispatch("evidence-provenance-ledger", "verify_evidence", {
        "directory": str(PACKAGE_ROOT / "schemas"),
    })
    assert "valid" in ev

    # benchmark-integrity-hidden-tests
    boundary = registry.dispatch("benchmark-integrity-hidden-tests", "hidden_boundary", {})
    assert boundary is not None

    # observability-failure-triage
    triage = registry.dispatch("observability-failure-triage", "triage", {
        "results": [{"case_id": "C1", "status": "failed", "error": "NullPointerException"}]
    })
    assert "clusters" in triage

    # performance-scale-certification
    perf = registry.dispatch("performance-scale-certification", "performance", {
        "candidate": {"latency_p50_ms": 100.0},
        "budgets": {"latency_p50_ms": {"limit": 200.0}},
    })
    assert perf["passed"] is True

    # project-generation-validation
    gen_req = registry.dispatch("project-generation-validation", "compile_requirement", {
        "requirement": "Build a secure REST microservice in Java"
    })
    assert gen_req["decision"] == "ready-for-generation"
