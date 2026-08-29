"""Tests for Elmos Commercial Capability Expansion Engine service and kernels."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/commercial-capability-expansion-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_commercial_expansion.models import (
    GateLevel,
    KernelType,
    Priority,
    RiskLevel,
    SkillDefinition,
    TaskContext,
)
from elmos_commercial_expansion.service import CommercialCapabilityExpansionService
from elmos_commercial_expansion.kernels import (
    SkillRuntimeKernel,
    RepositoryIntelligenceKernel,
    TransformationKernel,
    BuildExecutionKernel,
    VerificationKernel,
    SecurityGovernanceKernel,
    DatabaseDataKernel,
    ObservabilityEvolutionKernel,
)


@pytest.fixture
def manifest_data():
    manifest_path = ROOT / "skills/elmos-commercial-capability-expansion-skills-v2.0.0/manifest.json"
    if manifest_path.is_file():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"skills": []}


@pytest.fixture
def sample_context():
    return TaskContext(
        tenant_id="tenant-acme-prod",
        repository_id="repo-order-service",
        objective="Modernize legacy database queries and apply security policies",
        budget_tokens=50_000,
        budget_usd=3.5,
    )


def test_k1_skill_runtime(sample_context):
    k1 = SkillRuntimeKernel()
    skill = SkillDefinition(
        id="universal-agent-skill-runtime",
        name="universal-agent-skill-runtime",
        kernel=KernelType.K1_SKILL_RUNTIME,
        priority=Priority.P0,
        objective="Universal skill execution runtime",
        path="skills/K1/universal-agent-skill-runtime/SKILL.md",
    )
    k1.register_skill(skill)
    discovered = k1.discover_skills(sample_context, max_results=5)
    assert len(discovered) == 1
    assert discovered[0].id == "universal-agent-skill-runtime"

    cp = k1.create_checkpoint(
        task_id="t-001",
        step_number=1,
        state_snapshot={"stage": "INIT"},
        completed_steps=["INIT"],
        next_step="PARSE",
    )
    assert cp.checkpoint_id.startswith("cp-t-001")
    restored = k1.restore_checkpoint("t-001", cp.checkpoint_id)
    assert restored is not None
    assert restored.step_number == 1

    route = k1.route_execution(sample_context, skill)
    assert route["status"] == "ROUTED"
    assert route["routed_model_tier"] == "advanced-reasoning"


def test_k2_repository_intelligence(sample_context):
    k2 = RepositoryIntelligenceKernel()
    risk = k2.evaluate_change_risk(
        context=sample_context,
        modified_files=["src/auth/service.py", "src/payment/gateway.py"],
    )
    assert risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert "SANDBOX_HERMETIC_ISOLATION" in risk.mandatory_obligations

    selected_tests = k2.select_affected_tests(
        modified_files=["src/auth/service.py"],
        all_tests=["tests/test_auth.py", "tests/test_user.py", "tests/test_order.py"],
    )
    assert "tests/test_auth.py" in selected_tests


def test_k3_transformation():
    k3 = TransformationKernel()
    strat = k3.route_rewrite_strategy("src/App.java", "rename method getOldName")
    assert strat["selected_engine"] == "AST_COMPILER_API"
    assert strat["is_deterministic"] is True

    edit = k3.record_transformation_edit(
        task_id="t-002",
        file_path="src/App.java",
        before_content="void getOldName() {}",
        after_content="void getNewName() {}",
        rule_applied="RENAME_RULE",
        engine_used="AST_COMPILER_API",
        rationale="Modernize method name",
    )
    assert edit["edit_id"].startswith("edit-")
    rb = k3.get_rollback_snapshot("t-002")
    assert rb["src/App.java"] == "void getOldName() {}"


def test_k4_build_execution(sample_context):
    k4 = BuildExecutionKernel()
    key = k4.compute_action_key(["python3", "-c", "print(1)"], {"main.py": "abc"}, {"ENV": "PROD"})
    assert len(key) == 64

    res = k4.run_sandboxed_command(sample_context, ["echo", "sandbox_test"], cwd=str(ROOT))
    assert res["status"] == "SUCCESS"
    assert "sandbox_test" in res["stdout"]

    rep = k4.verify_reproducible_build(b"binary_v1", b"binary_v1")
    assert rep["is_reproducible"] is True
    assert rep["status"] == "VERIFIED"


def test_k5_verification():
    k5 = VerificationKernel()
    diff = k5.run_differential_oracle({"count": 10}, {"count": 10})
    assert diff["is_equivalent"] is True
    assert diff["status"] == "PASS"

    k5.record_evidence("t-003", "INGESTION", "K2", {"ok": True})
    k5.record_evidence("t-003", "FINGERPRINT", "K2", {"ok": True})
    gate_dec = k5.evaluate_e0_e5_gate("t-003", GateLevel.E0_INGESTION)
    assert gate_dec.passed is True
    assert gate_dec.status.value == "APPROVED"


def test_k6_security_governance(sample_context):
    k6 = SecurityGovernanceKernel()
    dec = k6.evaluate_policy("user-1", "EXEC_UNRESTRICTED_SHELL", "shell", sample_context)
    assert dec.allowed is False
    assert len(dec.violations) > 0

    sanitized, cnt = k6.sanitize_secrets("api_key = 'sk-1234567890abcdef1234567890'")
    assert "[REDACTED_SECRET]" in sanitized
    assert cnt > 0

    prov = k6.generate_slsa_provenance("artifact-bin", "deadbeef", [{"uri": "git+repo", "digest": "HEAD"}], {})
    assert prov.signature != ""
    assert prov.slsa_level == "SLSA_BUILD_LEVEL_3"

    sbom = k6.generate_cyclonedx_sbom("elmos-app", "2.0.0", [{"name": "requests", "version": "2.31.0"}])
    assert sbom["bomFormat"] == "CycloneDX"


def test_k7_database_data():
    k7 = DatabaseDataKernel()
    transpiled = k7.transpile_sql_dialect(
        sql_query="SELECT NVL(name, 'default'), SYSDATE FROM users",
        source_dialect="oracle",
        target_dialect="postgres",
    )
    assert "COALESCE" in transpiled["transpiled_sql"]
    assert "CURRENT_TIMESTAMP" in transpiled["transpiled_sql"]

    recon = k7.reconcile_data_migration(
        source_records=[{"id": 1, "val": "A"}, {"id": 2, "val": "B"}],
        target_records=[{"id": 1, "val": "A"}, {"id": 2, "val": "B"}],
        key_fields=["id"],
    )
    assert recon["is_reconciled"] is True
    assert recon["status"] == "PASS"


def test_k8_observability_evolution():
    k8 = ObservabilityEvolutionKernel()
    span_id = k8.start_trace_span("t-004", "test_span", "K8")
    assert span_id.startswith("span-")
    k8.end_trace_span(span_id, status="OK")

    traj = k8.record_trajectory("t-004", 5, 2, "SUCCESS", 1200, 450)
    assert traj.trajectory_id.startswith("traj-t-004")

    attr = k8.attribute_failure(traj, "SyntaxError: invalid syntax at line 42", "COMPILE")
    assert attr["attributed_cause"] == "SYNTAX_PARSER_MISMATCH"

    canary = k8.stage_canary_promotion("sql-dialect-transpiler", "2.1.0", 0.15)
    assert canary["stage"] == "CANARY_EVALUATION"


def test_commercial_expansion_service_end_to_end(manifest_data, sample_context):
    svc = CommercialCapabilityExpansionService(manifest_data)
    assert len(svc.k1.registry) == 85

    res = svc.run_commercial_workflow(
        context=sample_context,
        target_files=["src/database/query.py", "src/auth/token.py"],
        change_intent="Migrate to async database pool and enable RLS policies",
        target_gate=GateLevel.E3_SECURITY_ISOLATION,
    )
    assert res["status"] == "APPROVED"
    assert res["task_id"].startswith("task-")
    assert res["gate_decision"]["passed"] is True
    assert res["provenance"]["slsa_level"] == "SLSA_BUILD_LEVEL_3"
    assert res["trajectory"]["outcome"] == "SUCCESS"
