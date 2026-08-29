"""Unit and integration tests for Elmos Semantic Assurance Engine and modules."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/semantic-assurance-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_semantic_assurance.models import (
    BatchType,
    ObligationStatus,
    SemanticRisk,
    VerdictStatus,
)
from elmos_semantic_assurance.service import SemanticAssuranceService
from elmos_semantic_assurance.modules import (
    FrontendSemanticsModule,
    TypeSemanticsModule,
    ControlDataflowSemanticsModule,
    RuntimeMemorySemanticsModule,
    BehaviorOracleModule,
    CorpusGovernanceModule,
    NativeRuntimeLabModule,
    FormalAssuranceModule,
    SemanticFuzzingModule,
)


@pytest.fixture
def manifest_data():
    manifest_path = ROOT / "skills/elmos-semantic-assurance-expansion-skills-v1.0.0/manifest.json"
    if manifest_path.is_file():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"skills": []}


def test_batch_j_frontend_semantics():
    j = FrontendSemanticsModule()
    det = j.detect_dialect_version("python", "async def get_value() -> int: return 1")
    assert det["detected_version"] == "python3"

    sec = j.validate_parse_error_recovery("python", "def foo(): pass", {"functions": ["foo"]})
    assert sec["is_recovery_safe"] is True

    obl = j.create_frontend_obligation("BNF_JAVA", "ANTLR_JAVA", "SYNTAX_PARSER_ISOMORPHISM")
    assert obl.batch == BatchType.BATCH_J
    assert obl.risk == SemanticRisk.CRITICAL


def test_batch_k_type_semantics():
    k = TypeSemanticsModule()
    ver = k.verify_type_preservation("java.lang.String", "string", "java_to_csharp")
    assert ver["is_type_safe"] is True
    assert ver["status"] == "PASS"

    obl = k.create_type_obligation("java.lang.String", "string", "STRING_TYPE_PRESERVATION")
    assert obl.batch == BatchType.BATCH_K


def test_batch_l_control_dataflow_semantics():
    l = ControlDataflowSemanticsModule()
    cfg = l.build_cfg_summary("compute", [
        {"block_id": "b0", "is_entry": True, "is_exit": False},
        {"block_id": "b1", "is_entry": False, "is_exit": True},
    ])
    assert cfg["has_valid_entry_exit"] is True
    assert cfg["status"] == "VALID_CFG"

    ex = l.verify_exception_equivalence(["IOException", "SQLException"], ["ioexception", "sqlexception"])
    assert ex["is_exception_safe"] is True


def test_batch_m_runtime_memory_semantics():
    m = RuntimeMemorySemanticsModule()
    layout = m.compute_struct_layout("Header", [("id", 4, 4), ("flag", 1, 1), ("data", 8, 8)])
    assert layout["total_size_bytes"] >= 16
    assert layout["alignment"] == 8

    ord_res = m.verify_memory_order_safety("acquire", "seq_cst")
    assert ord_res["is_memory_order_safe"] is True


def test_batch_n_behavior_oracle():
    n = BehaviorOracleModule()
    oracle = n.create_behavior_oracle("calc", ["result"], [{"range": [0, 100]}])
    assert oracle.oracle_id.startswith("oracle-calc-")

    diff = n.evaluate_differential_execution("cpp", "rust", "tc-math", 3.14159, 3.14159, epsilon=1e-5)
    assert diff.verdict == VerdictStatus.EQUIVALENT


def test_batch_o_corpus_governance():
    o = CorpusGovernanceModule()
    fix = o.register_fixture("fix-01", "csharp", "generics", "class Box<T> { T val; }")
    assert fix["status"] == "ACTIVE"

    cov = o.calculate_corpus_coverage(20, [f"feat_{i}" for i in range(18)])
    assert cov["is_ready_for_certification"] is True


def test_batch_p_native_runtime_lab():
    p = NativeRuntimeLabModule()
    prof = p.get_lab_profile("jvm_standard")
    assert "OpenJDK" in prof["runtime"]

    att = p.create_lab_evidence_attestation("jvm_standard", "BUILD SUCCESS", 0)
    assert att["status"] == "ATTESTED"


def test_batch_q_formal_assurance():
    q = FormalAssuranceModule()
    proof = q.create_proof_obligation("x > 0 => x + 1 > 1")
    solved = q.solve_obligation(proof.proof_id, simulated_pass=True)
    assert solved.status == ObligationStatus.PROVED
    assert solved.proof_witness is not None


def test_batch_r_semantic_fuzzing():
    r = SemanticFuzzingModule()
    meta = r.run_metamorphic_test("sort_identity", [3, 1, 2], "INVARIANT", sorted, sorted)
    assert meta["is_relation_satisfied"] is True

    fuzz = r.run_differential_fuzz_campaign("transpiler_route", iterations=50)
    assert fuzz["status"] == "COMPLETED"


def test_semantic_assurance_service_full_campaign(manifest_data):
    svc = SemanticAssuranceService(manifest_data)
    assert len(svc.skills_registry) == 132

    cert_run = svc.run_route_assurance_campaign(
        source_lang="java",
        target_lang="csharp",
        source_code="class Foo { int add(int a, int b) { return a + b; } }",
        target_code="class Foo { int Add(int a, int b) => a + b; }",
    )
    assert cert_run.overall_verdict == VerdictStatus.EQUIVALENT
    assert cert_run.proved_obligations == 132
    assert cert_run.total_obligations == 132
    assert len(cert_run.receipt_digest) == 64
