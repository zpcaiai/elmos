"""Unit and integration tests for ELMOS Polyglot Repository Semantic Compiler Engine and 18 layers."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
import sys

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/polyglot-semantic-compiler-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_polyglot_compiler.models import (
    BatchType,
    ObligationStatus,
    SemanticRisk,
    VerdictStatus,
)
from elmos_polyglot_compiler.service import PolyglotSemanticCompilerService
from elmos_polyglot_compiler.modules import (
    DiscoveryIngestionModule,
    IrNormalizationModule,
    AdaptersFrontendsModule,
    CoreTransformationModule,
    SystemsUiTransformationModule,
    DatabaseDataTransformationModule,
    IntegrationSpecializedTransformationModule,
    VerificationTestingModule,
    DeliveryOrchestrationModule,
    FrontendSyntaxSemanticsModule,
    TypeContractSemanticsModule,
    ControlDataflowSemanticsModule,
    RuntimeMemoryConcurrencyModule,
    ObservableBehaviorOracleModule,
    CorpusGovernanceModule,
    NativeRuntimeLabModule,
    FormalAssuranceModule,
    SemanticFuzzingModule,
)


@pytest.fixture
def manifest_data():
    manifest_path = ROOT / "skills/elmos-polyglot-skills-v3.0.0-semantic-assurance/manifest.json"
    if manifest_path.is_file():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"skills": [], "technologies": [], "repository_surfaces": []}


def test_batch_a_discovery_ingestion():
    a = DiscoveryIngestionModule()
    snap = a.scan_repository_surface("/path/to/repo", ["java", "csharp"])
    assert snap["status"] == "DISCOVERED"
    obl = a.create_discovery_obligation("java_csharp_surface", "INVENTORY_COMPLETENESS")
    assert obl.batch == BatchType.BATCH_A


def test_batch_b_ir_normalization():
    b = IrNormalizationModule()
    uir = b.lift_to_uir("python", [{"kind": "FunctionDef", "name": "foo"}])
    assert uir["status"] == "NORMALIZED"
    assert uir["schema_version"] == "3.0.0"


def test_batch_c_adapters_frontends():
    c = AdaptersFrontendsModule()
    prof = c.get_adapter_profile("csharp")
    assert prof["parser"] == "Roslyn"
    assert "Nominal" in prof["type_system"]


def test_batch_d_core_transformation():
    d = CoreTransformationModule()
    tx = d.transform_snippet("java", "csharp", "public static void main(String[] args) {}")
    assert "public static void Main" in tx["target_code"]


def test_batch_e_systems_ui_transformation():
    e = SystemsUiTransformationModule()
    ui = e.transform_ui_component("react", "vue3", {"name": "Header", "state": ["title"]})
    assert ui["status"] == "CONVERTED"


def test_batch_f_database_transformation():
    f = DatabaseDataTransformationModule()
    db = f.transform_schema_ddl("oracle", "postgres", ["CREATE TABLE USERS (ID NUMBER)"])
    assert db["status"] == "DDL_CONVERTED"


def test_batch_g_legacy_integration():
    g = IntegrationSpecializedTransformationModule()
    strat = g.get_legacy_migration_strategy("cobol")
    assert strat["target"] == "java"


def test_batch_h_verification_testing():
    h = VerificationTestingModule()
    res = h.execute_dual_run_comparison("test-42", "PASS", "PASS")
    assert res["verdict"] == VerdictStatus.EQUIVALENT.value


def test_batch_i_delivery_orchestration():
    i = DeliveryOrchestrationModule()
    pkg = i.assemble_project_manifest("OrderService", "csharp", ["Program.cs"])
    assert pkg["status"] == "ASSEMBLED"
    assert "dotnet" in pkg["build_command"]


def test_batch_j_frontend_syntax():
    j = FrontendSyntaxSemanticsModule()
    det = j.detect_syntax_dialect("python", "async def run(): pass")
    assert det["detected_version"] == "python3"


def test_batch_k_type_contracts():
    k = TypeContractSemanticsModule()
    pres = k.verify_algebraic_preservation("java.lang.String", "string", "java_to_csharp")
    assert pres["is_type_safe"] is True


def test_batch_l_control_dataflow():
    l = ControlDataflowSemanticsModule()
    cfg = l.analyze_cfg_bisimulation("process", 4)
    assert cfg["bisimulation_preserved"] is True


def test_batch_m_runtime_memory():
    m = RuntimeMemoryConcurrencyModule()
    layout = m.calculate_memory_layout("Header", [("id", 4, 4), ("data", 8, 8)])
    assert layout["total_size"] >= 16


def test_batch_n_observable_behavior_oracle():
    n = ObservableBehaviorOracleModule()
    diff = n.compare_differential_output("java", "csharp", "tc-01", 100, 100)
    assert diff.verdict == VerdictStatus.EQUIVALENT


def test_batch_o_corpus_governance():
    o = CorpusGovernanceModule()
    fix = o.register_fixture("fix-01", "java", "math", "class Math {}")
    assert fix["status"] == "REGISTERED"


def test_batch_p_native_runtime_lab():
    p = NativeRuntimeLabModule()
    att = p.attest_lab_execution("openjdk21", "mvn test", 0)
    assert att["status"] == "ATTESTED"


def test_batch_q_formal_assurance():
    q = FormalAssuranceModule()
    proof = q.create_proof_obligation("x + 0 == x")
    solved = q.solve_proof(proof.proof_id, simulated_pass=True)
    assert solved.status == ObligationStatus.PROVED


def test_batch_r_semantic_fuzzing():
    r = SemanticFuzzingModule()
    fuzz = r.execute_differential_fuzz_campaign("java_to_csharp", iterations=50)
    assert fuzz["status"] == "PASSED"


def test_compiler_service_full_certification(manifest_data):
    svc = PolyglotSemanticCompilerService(manifest_data)
    assert len(svc.skills_registry) == 300
    assert len(svc.technology_surfaces) == 28
    assert len(svc.repository_surfaces) == 8

    cert = svc.certify_route(
        source_lang="java",
        target_lang="csharp",
        source_code="class Foo { static int Add(int a, int b) { return a + b; } }",
        target_code="class Foo { static int Add(int a, int b) => a + b; }",
    )
    assert cert.overall_verdict == VerdictStatus.EQUIVALENT
    assert cert.total_obligations == 300
    assert cert.proved_obligations == 300
    assert len(cert.batch_coverage) == 18
    assert len(cert.receipt_digest) == 64
