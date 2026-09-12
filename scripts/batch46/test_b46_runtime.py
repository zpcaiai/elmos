"""Test suite verifying all 16 Batch 46 Runnable Smoke Factory skills in B46SkillRuntime."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from scripts.batch46.b46_skill_runtime import B46SkillRuntime


@pytest.fixture
def runtime():
    return B46SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 16
    for s in runtime.SKILLS:
        assert s.startswith("b46-")


def test_b46_runnable_smoke_factory(runtime):
    res = runtime.dispatch("b46-runnable-smoke-factory", "init", {"project_type": "spring-boot"})
    assert res["factory_id"] == "fac-smoke-spring-boot"
    assert "run-local.sh" in res["generated_entries"]
    assert res["status"] == "INITIALIZED"


def test_b46_b29_language_route_smoke(runtime):
    res = runtime.dispatch("b46-b29-language-route-smoke", "attach", {"route": "java-to-csharp"})
    assert res["route"] == "java-to-csharp"
    assert "dotnet run" in res["runtime_entrypoint"]


def test_b46_b30_framework_smoke(runtime):
    res = runtime.dispatch("b46-b30-framework-smoke", "configure", {"framework": "spring-boot-3"})
    assert res["expected_status"] == "UP"
    assert "actuator" in res["actuator_health_endpoint"]


def test_b46_b31_database_seed_smoke(runtime):
    res = runtime.dispatch("b46-b31-database-seed-smoke", "seed", {"database": "postgresql", "tables": ["users", "orders"]})
    assert res["seeded_tables"] == ["users", "orders"]
    assert res["ephemeral_cleanup_registered"] is True


def test_b46_b32_client_smoke(runtime):
    res = runtime.dispatch("b46-b32-client-smoke", "setup", {"client_framework": "vue3"})
    assert res["client_framework"] == "vue3"
    assert "3000" in res["dev_server_url"]


def test_b46_console_run_button(runtime):
    res = runtime.dispatch("b46-console-run-button", "wire", {"session_id": "sess-99"})
    assert res["run_button_state"] == "READY"
    assert "sess-99" in res["one_click_trigger_url"]


def test_b46_ephemeral_data_isolation_teardown(runtime):
    res = runtime.dispatch("b46-ephemeral-data-isolation-teardown", "isolate", {"container_id": "c1"})
    assert res["ephemeral_tmpfs_mounted"] is True
    assert res["teardown_hook_registered"] is True


def test_b46_minimal_runtime_data_analyzer(runtime):
    res = runtime.dispatch("b46-minimal-runtime-data-analyzer", "analyze", {"schema": {"items": ["id"]}})
    assert res["required_entities"] == ["items"]
    assert res["status"] == "MINIMAL_DATA_DERIVED"


def test_b46_one_click_entry_emitter(runtime):
    res = runtime.dispatch("b46-one-click-entry-emitter", "emit", {"target_dir": "/tmp/proj"})
    assert len(res["emitted_files"]) == 3
    assert res["zero_dependency_entry"] is True


def test_b46_polyglot_topology_smoke(runtime):
    res = runtime.dispatch("b46-polyglot-topology-smoke", "coordinate", {"services": ["db", "api", "ui"]})
    assert res["services_count"] == 3
    assert res["coordinated_startup"] is True


def test_b46_runnable_smoke_gate(runtime):
    res_pass = runtime.dispatch("b46-runnable-smoke-gate", "evaluate", {
        "evidence": {"startup_ok": True, "readiness_probe_ok": True, "functional_probe_ok": True, "teardown_clean": True}
    })
    assert res_pass["gate_decision"] == "RUNNABLE"
    assert res_pass["certification_status"] == "CERTIFIED"

    res_fail = runtime.dispatch("b46-runnable-smoke-gate", "evaluate", {
        "evidence": {"startup_ok": False}
    })
    assert res_fail["gate_decision"] == "BLOCKED"


def test_b46_runtime_lease_quota_reclaim(runtime):
    res = runtime.dispatch("b46-runtime-lease-quota-reclaim", "enforce", {"lease_duration_sec": 600})
    assert res["lease_duration_sec"] == 600
    assert res["watchdog_active"] is True


def test_b46_seed_data_provenance_policy(runtime):
    res_valid = runtime.dispatch("b46-seed-data-provenance-policy", "verify", {"data_source": "SYNTHETIC_GENERATOR"})
    assert res_valid["provenance_valid"] is True

    res_invalid = runtime.dispatch("b46-seed-data-provenance-policy", "verify", {"data_source": "RAW_PROD_DUMP"})
    assert res_invalid["provenance_valid"] is False


def test_b46_seed_data_synthesizer(runtime):
    res = runtime.dispatch("b46-seed-data-synthesizer", "synthesize", {"entities": ["User"]})
    assert res["obviously_fake_values"] is True
    assert res["status"] == "DATA_SYNTHESIZED"


def test_b46_smoke_assertion_design(runtime):
    res = runtime.dispatch("b46-smoke-assertion-design", "design", {"application": "svc"})
    assert res["assertion_count"] == 4
    assert res["status"] == "DESIGN_COMPLETE"


def test_b46_smoke_evidence_recorder(runtime):
    res = runtime.dispatch("b46-smoke-evidence-recorder", "record", {
        "logs": "OK",
        "checks": {"port": "PASS"}
    })
    assert res["all_checks_passed"] is True
    assert res["immutable_record_saved"] is True


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b46-unknown", "op")
