"""Test suite verifying all 20 Batch 29 Route skills in B29SkillRuntime."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from scripts.batch29.b29_skill_runtime import B29SkillRuntime


@pytest.fixture
def runtime():
    return B29SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 20
    for s in runtime.SKILLS:
        assert s.startswith("b29-")


def test_b29_route_factory(runtime):
    res = runtime.dispatch("b29-route-factory", "init", {
        "source_language": "csharp",
        "target_language": "java",
    })
    assert res["route_key"] == "csharp-to-java"
    assert res["status"] == "INITIALIZED"
    assert "certification_gate" in res["pipeline_stages"]


def test_b29_route_prioritizer(runtime):
    res = runtime.dispatch("b29-route-prioritizer", "rank", {
        "candidates": [
            {"route": "java-to-csharp", "demand": 95, "feasibility": 90},
            {"route": "python-to-typescript", "demand": 80, "feasibility": 85},
        ]
    })
    assert res["total_evaluated"] == 2
    assert res["top_priority"] == "java-to-csharp"


def test_b29_language_support_matrix(runtime):
    res = runtime.dispatch("b29-language-support-matrix", "query", {
        "route": "java-to-csharp"
    })
    assert res["tier"] == "CERTIFIED"
    assert "version_contract" in res


def test_b29_adapter_emitter_conformance(runtime):
    res = runtime.dispatch("b29-adapter-emitter-conformance", "check", {
        "adapter": "JavaAdapter",
        "emitter": "CSharpEmitter",
    })
    assert res["conformance_status"] == "CONFORMANT"
    assert res["lossless_ast_preservation"] is True


def test_b29_compatibility_runtime_governor(runtime):
    res = runtime.dispatch("b29-compatibility-runtime-governor", "audit", {
        "route": "java-to-csharp",
        "shim_packages": ["Compat.JavaCollections"],
        "max_size_kb": 256,
    })
    assert res["within_budget"] is True
    assert res["memory_overhead"] == "ZERO_ALLOC_BRIDGES"


def test_b29_route_corpus_certifier(runtime):
    res = runtime.dispatch("b29-route-corpus-certifier", "eval_corpus", {
        "results": {
            "smoke": {"total": 10, "passed": 10},
            "semantic": {"total": 20, "passed": 20},
        }
    })
    assert res["corpus_status"] == "PASSED"
    assert res["all_tests_passed"] is True


def test_b29_route_economics_certifier(runtime):
    res = runtime.dispatch("b29-route-economics-certifier", "certify", {
        "build_green_rate": 0.98,
        "cost_per_workload_usd": 3.50,
        "manual_effort_hours": 0.4,
    })
    assert res["economics_certified"] is True
    assert res["status"] == "CERTIFIED"


def test_b29_route_certification_gate(runtime):
    res_pass = runtime.dispatch("b29-route-certification-gate", "evaluate", {
        "evidence": {
            "critical_unknowns": 0,
            "corpus_passed": True,
            "economics_passed": True,
            "conformance_passed": True,
        }
    })
    assert res_pass["gate_decision"] == "PASSED"
    assert res_pass["certification_status"] == "CERTIFIED"

    res_fail = runtime.dispatch("b29-route-certification-gate", "evaluate", {
        "evidence": {
            "critical_unknowns": 1,
            "corpus_passed": False,
        }
    })
    assert res_fail["gate_decision"] == "REJECTED"


@pytest.mark.parametrize("route_skill,src,tgt", [
    ("b29-certify-csharp-to-java", "csharp", "java"),
    ("b29-certify-csharp-to-python", "csharp", "python"),
    ("b29-certify-csharp-to-typescript", "csharp", "typescript"),
    ("b29-certify-java-to-csharp", "java", "csharp"),
    ("b29-certify-java-to-python", "java", "python"),
    ("b29-certify-java-to-typescript", "java", "typescript"),
    ("b29-certify-python-to-csharp", "python", "csharp"),
    ("b29-certify-python-to-java", "python", "java"),
    ("b29-certify-python-to-typescript", "python", "typescript"),
    ("b29-certify-typescript-to-csharp", "typescript", "csharp"),
    ("b29-certify-typescript-to-java", "typescript", "java"),
    ("b29-certify-typescript-to-python", "typescript", "python"),
])
def test_directed_language_routes(runtime, route_skill, src, tgt):
    res = runtime.dispatch(route_skill, "certify_route", {
        "source_symbols": ["UserService", "login", "logout"]
    })
    assert res["route"] == f"{src}-to-{tgt}"
    assert res["source_language"] == src
    assert res["target_language"] == tgt
    assert res["symbols_translated"] == 3
    assert res["verification_status"] == "VERIFIED"
    assert "idioms" in res


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b29-nonexistent-route", "certify")
