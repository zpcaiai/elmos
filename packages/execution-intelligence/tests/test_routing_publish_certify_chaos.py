import json

import pytest
from conftest import PRICING_PATH, PROJECT_PATH, ROOT, TASKS_PATH

from elmos_execution_intelligence.certifier import build_evidence_manifest, evaluate
from elmos_execution_intelligence.chaos import SCENARIOS, render_recovery_evidence, run_chaos
from elmos_execution_intelligence.durable import DurableStore, LogicalClock
from elmos_execution_intelligence.io_utils import load_json
from elmos_execution_intelligence.publisher import build_manifest, verify_manifest
from elmos_execution_intelligence.routing import optimize_routing, render_routing_comparison
from elmos_execution_intelligence.runner import execute_run, execution_waves, render_execution_plan, render_template

PROJECT = load_json(PROJECT_PATH)
TASKS = load_json(TASKS_PATH)
PRICING = load_json(PRICING_PATH)
CAPABILITIES = load_json(ROOT / "config" / "provider-capabilities.json")


# ------------------------------------------------------------------ 14 routing -------

def test_every_task_gets_a_model_that_meets_its_floor():
    plan = optimize_routing(TASKS, PRICING, CAPABILITIES)
    order = CAPABILITIES["tier_order"]
    assert plan["assignments"]
    assert plan["unroutable_tasks"] == []
    for assignment in plan["assignments"]:
        assert order.index(assignment["assigned_tier"]) >= order.index(assignment["required_tier"])


def test_routing_never_costs_more_than_the_frontier_baseline():
    plan = optimize_routing(TASKS, PRICING, CAPABILITIES)
    assert plan["totals"]["optimized"] <= plan["totals"]["frontier_baseline"]
    assert plan["totals"]["saving"] >= 0


def test_routing_stays_inside_one_currency():
    plan = optimize_routing(TASKS, PRICING, CAPABILITIES)
    assert plan["optimised_within_currency_only"] is True
    priced = {model["id"]: model.get("currency") for model in PRICING["models"]}
    for assignment in plan["assignments"]:
        assert priced[assignment["assigned_model"]] == plan["currency"]


def test_a_model_without_a_capability_profile_is_never_routed_to():
    pricing = json.loads(json.dumps(PRICING))
    pricing["models"].append({
        "id": "mystery-model", "currency": "USD", "effective_date": "2026-01-01",
        "verified_at": "2026-01-01T00:00:00Z", "source_reference": "x",
        "rates_per_million": {f: 0.0001 for f in
                              ("input", "cached_input", "cache_write", "output", "reasoning_output")},
    })
    plan = optimize_routing(pricing=pricing, task_document=TASKS, capabilities=CAPABILITIES)
    assigned = {a["assigned_model"] for a in plan["assignments"]}
    assert "mystery-model" not in assigned


def test_routing_refuses_when_nothing_has_a_capability_profile():
    with pytest.raises(ValueError, match="capability profile"):
        optimize_routing(TASKS, PRICING, {**CAPABILITIES, "models": {}})


def test_unroutable_tasks_are_reported_not_dropped():
    capabilities = json.loads(json.dumps(CAPABILITIES))
    capabilities["models"] = {"economy-usd-illustrative": capabilities["models"]["economy-usd-illustrative"]}
    plan = optimize_routing(TASKS, PRICING, capabilities)
    assert plan["unroutable_tasks"]
    reported = {u["task_id"] for u in plan["unroutable_tasks"]}
    assigned = {a["task_id"] for a in plan["assignments"]}
    assert reported | assigned == {task["id"] for task in TASKS["tasks"]}


def test_routing_report_surfaces_illustrative_rates():
    text = render_routing_comparison(optimize_routing(TASKS, PRICING, CAPABILITIES))
    assert "illustrative" in text or "示例" in text or "不可用于预算" in text or "must not back a budget" in text


# ------------------------------------------------------------------ 15 publishing ----

@pytest.fixture()
def executed_run():
    store = DurableStore(":memory:", clock=LogicalClock(start=1000.0, step=1.0))
    result = execute_run(PROJECT, TASKS, store, capacity=4.0, seed=3, failure_scale=0.0)
    yield store, result["run_id"]
    store.close()


def test_manifest_covers_every_published_artifact(executed_run):
    store, run_id = executed_run
    manifest = build_manifest(store, run_id)
    assert manifest["artifact_count"] == len(store.artifacts(run_id))
    assert manifest["artifact_count"] == len(TASKS["tasks"])
    assert manifest["sealed"] is True


def test_manifest_digest_detects_tampering(executed_run):
    store, run_id = executed_run
    manifest = build_manifest(store, run_id)
    contents = {f"{task['id']}.result": None for task in TASKS["tasks"]}

    def resolver(entry):
        name = entry["logical_name"]
        return contents[name] if contents[name] is not None else \
            f"{name.removesuffix('.result')}:1".encode()

    assert verify_manifest(manifest, resolver)["verified"] is True

    tampered = json.loads(json.dumps(manifest))
    tampered["artifacts"][0]["sha256"] = "0" * 64
    report = verify_manifest(tampered, resolver)
    assert report["verified"] is False
    assert report["manifest_digest_matches"] is False


def test_manifest_reports_missing_artifacts(executed_run):
    store, run_id = executed_run
    manifest = build_manifest(store, run_id)

    def resolver(entry):
        raise FileNotFoundError(entry["logical_name"])

    report = verify_manifest(manifest, resolver)
    assert report["verified"] is False
    assert len(report["missing_artifacts"]) == manifest["artifact_count"]


def test_an_unfinished_run_is_not_sealed():
    store = DurableStore(":memory:", clock=LogicalClock())
    run_id = store.create_run(PROJECT, TASKS)
    manifest = build_manifest(store, run_id)
    assert manifest["sealed"] is False
    assert "still" in manifest["seal_refused_reason"]
    store.close()


def test_superseded_versions_are_listed_not_deleted(executed_run):
    store, run_id = executed_run
    store.publish_artifact(run_id, "matrix-small.result", b"different bytes")
    manifest = build_manifest(store, run_id)
    superseded = {entry["logical_name"] for entry in manifest["superseded_logical_names"]}
    assert "matrix-small.result" in superseded


# ------------------------------------------------------------------ 16 certification --

def _evidence(tmp_path, **files):
    for name, payload in files.items():
        (tmp_path / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_missing_evidence_is_not_executed_never_pass(tmp_path):
    report = evaluate(tmp_path)
    assert report["decision"] == "not_certified"
    assert all(gate["status"] != "PASS" for gate in report["gates"])
    assert report["counts"]["not_executed"] >= 5


def test_a_failing_required_gate_blocks(tmp_path):
    _evidence(tmp_path, **{"risk-and-gap-register.json": {
        "gaps": [{"id": "g1", "severity": "high", "kind": "x", "detail": "d", "needs_human_input": True}]}})
    report = evaluate(tmp_path)
    assert report["decision"] == "block"


def test_unsigned_full_evidence_is_blocked(tmp_path):
    _evidence(
        tmp_path,
        **{
            "project-forecast.json": {
                "tokens": {"category_sum_equals_total": True},
                "project": {"confidence": 0.75},
                "system_runtime": {"excludes": ["human approvals"]},
                "costs": {"models": [{"not_for_billing": False}]},
            },
            "risk-and-gap-register.json": {"gaps": []},
            "calibration.json": {"valid_samples": 40, "runtime_samples": 40, "token_samples": 40},
            "chaos-test-report.json": {"scenarios": [{"passed": True}]},
            "result-manifest.json": {"sealed": True, "artifact_count": 3},
            "model-routing-plan.json": {"unroutable_tasks": []},
            "token-mix-comparison.json": {
                "observed": {"sessions": 25}, "minimum_sessions": 20,
                "sample_sufficient": True,
            },
        },
    )
    report = evaluate(tmp_path, min_calibration_samples=20)
    assert report["decision"] == "block"
    provenance = next(g for g in report["gates"] if g["id"] == "evidence-provenance")
    assert provenance["status"] == "FAIL"
    assert "evidence-provenance.json is required" in provenance["detail"]


def test_too_few_calibration_samples_fails_the_gate(tmp_path):
    _evidence(tmp_path, **{"calibration.json": {"valid_samples": 3}})
    gate = next(g for g in evaluate(tmp_path, min_calibration_samples=20)["gates"] if g["id"] == "calibrated")
    assert gate["status"] == "FAIL"


def test_unchecked_token_mix_blocks_release(tmp_path):
    """Everything else proven, mix never checked: still not a release.

    The forecast can be right about the token count and wrong about the bill by
    an order of magnitude, so "we never looked" is not the same as "it is fine".
    """
    _evidence(
        tmp_path,
        **{
            "project-forecast.json": {
                "tokens": {"category_sum_equals_total": True},
                "project": {"confidence": 0.75},
                "system_runtime": {"excludes": ["human approvals"]},
                "costs": {"models": [{"not_for_billing": False}]},
            },
            "risk-and-gap-register.json": {"gaps": []},
            "calibration.json": {"valid_samples": 40, "runtime_samples": 40, "token_samples": 40},
            "chaos-test-report.json": {"scenarios": [{"passed": True}]},
            "result-manifest.json": {"sealed": True, "artifact_count": 3},
        },
    )
    report = evaluate(tmp_path, min_calibration_samples=20)
    gate = next(g for g in report["gates"] if g["id"] == "token-mix-verified")
    assert gate["status"] == "NOT_EXECUTED"
    assert report["decision"] != "release"


def test_thin_token_mix_sample_fails_rather_than_passes(tmp_path):
    _evidence(tmp_path, **{
        "token-mix-comparison.json": {
            "observed": {"sessions": 1}, "minimum_sessions": 20,
            "sample_sufficient": False,
            "overstatement_factor_range": [5.51, 10.9],
            "cost_by_session_depth": [
                {"turns": 5, "overstatement_factor": 1.17},
                {"turns": 500, "overstatement_factor": 5.54},
            ],
        },
    })
    gate = next(g for g in evaluate(tmp_path)["gates"] if g["id"] == "token-mix-verified")
    assert gate["status"] == "FAIL"
    # The gate must carry the CURVE, not the flat headline: quoting 5.54x alone
    # would overstate the error for every short task in the DAG.
    assert "1.17" in gate["detail"] and "5.54" in gate["detail"]


def test_gate_falls_back_to_the_headline_when_no_depth_curve_exists(tmp_path):
    _evidence(tmp_path, **{
        "token-mix-comparison.json": {
            "observed": {"sessions": 2}, "minimum_sessions": 20,
            "sample_sufficient": False,
            "overstatement_factor_range": [5.51, 10.9],
        },
    })
    gate = next(g for g in evaluate(tmp_path)["gates"] if g["id"] == "token-mix-verified")
    assert "10.90" in gate["detail"]
    assert "整场会话口径" in gate["detail"]


def test_evidence_manifest_hashes_what_it_cites(tmp_path):
    _evidence(tmp_path, **{"calibration.json": {"valid_samples": 40}})
    report = evaluate(tmp_path)
    manifest = build_evidence_manifest(report, tmp_path)
    assert any(entry["path"] == "calibration.json" for entry in manifest["files"])
    assert all(len(entry["sha256"]) == 64 for entry in manifest["files"])
    assert manifest["missing_evidence"]


# ------------------------------------------------------------------ 17 chaos ---------

def test_every_declared_scenario_passes():
    report = run_chaos(PROJECT)
    assert report["counts"]["run"] == len(SCENARIOS)
    failing = [s["scenario"] for s in report["scenarios"] if not s["passed"]]
    assert failing == []
    assert report["passed"] is True


def test_each_scenario_asserts_something():
    for scenario in run_chaos(PROJECT)["scenarios"]:
        assert scenario["assertions"], scenario["scenario"]


def test_a_partial_run_is_not_reported_as_a_full_pass():
    report = run_chaos(PROJECT, ["orchestrator-restart"])
    assert report["counts"]["run"] == 1
    assert report["scenarios_not_run"]
    assert report["passed"] is False, "not-run scenarios must stop the overall pass"


def test_unknown_scenario_is_refused():
    with pytest.raises(ValueError, match="unknown chaos scenario"):
        run_chaos(PROJECT, ["definitely-not-a-scenario"])


def test_recovery_evidence_renders_every_scenario():
    report = run_chaos(PROJECT)
    text = render_recovery_evidence(report)
    for scenario in report["scenarios"]:
        assert scenario["scenario"] in text
    assert "{{" not in text


# ------------------------------------------------------------------ plan rendering ---

def test_execution_waves_respect_dependencies():
    waves = execution_waves(TASKS)
    seen = set()
    tasks = {task["id"]: task for task in TASKS["tasks"]}
    for wave in waves:
        for task_id in wave:
            assert all(dep in seen for dep in tasks[task_id]["depends_on"])
        seen |= set(wave)
    assert seen == set(tasks)


def test_execution_plan_has_no_unfilled_placeholders():
    text = render_execution_plan(PROJECT, TASKS, run_id="r1", generated_at="2026-08-19")
    assert "{{" not in text
    assert "r1" in text


def test_template_refuses_to_render_with_a_missing_value():
    with pytest.raises(ValueError, match="unfilled placeholders"):
        render_template("TASK_EXECUTION_PLAN.md.tmpl", {"project_id": "x"})


# ------------------------------------------------- 14b context window constraint ----

def _task_with_context(peak):
    task = json.loads(json.dumps(TASKS["tasks"][0]))
    task["id"] = "ctx"
    task["complexity"] = "medium"
    task["category"] = "verification"
    if peak is not None:
        task["system"]["peak_context_tokens"] = peak
    else:
        task["system"].pop("peak_context_tokens", None)
    return {"schema_version": "1.0.0", "dag_id": "ctx", "tasks": [task]}


VERIFIED_PRICING = load_json(ROOT / "config" / "model-pricing.json")


def test_a_model_whose_window_is_too_narrow_is_not_eligible():
    caps = json.loads(json.dumps(CAPABILITIES))
    for profile in caps["models"].values():
        profile["max_context_tokens"] = 128_000
    caps["models"]["openai-gpt-5-6-sol"]["max_context_tokens"] = 400_000

    plan = optimize_routing(_task_with_context(300_000), VERIFIED_PRICING, caps)
    assigned = {a["task_id"]: a["assigned_model"] for a in plan["assignments"]}
    assert assigned.get("ctx") == "openai-gpt-5-6-sol", assigned


def test_a_task_wider_than_every_window_is_unroutable_with_the_reason_named():
    caps = json.loads(json.dumps(CAPABILITIES))
    for profile in caps["models"].values():
        profile["max_context_tokens"] = 128_000

    plan = optimize_routing(_task_with_context(5_000_000), VERIFIED_PRICING, caps)
    assert plan["assignments"] == []
    reason = plan["unroutable_tasks"][0]["reason"]
    assert "peak context" in reason and "window" in reason
    assert plan["unroutable_tasks"][0]["peak_context_tokens"] == 5_000_000


def test_a_task_that_declares_no_peak_is_listed_not_assumed_to_fit():
    plan = optimize_routing(_task_with_context(None), VERIFIED_PRICING, CAPABILITIES)
    context = plan["context_constraint"]
    assert context["not_declared_for"] == ["ctx"]
    assert context["enforced_for"] == []
    assert any("could not be checked" in caveat for caveat in plan["caveats"])
    assert plan["assignments"], "an undeclared peak must not make the task unroutable"


def test_the_generated_dag_declares_a_peak_context_for_every_task(tmp_path):
    from elmos_execution_intelligence.decompose import decompose
    from elmos_execution_intelligence.scope import audit_scope

    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    document = decompose(audit_scope(tmp_path),
                         load_json(ROOT / "config" / "decomposition-model.json"))
    peaks = [t["system"].get("peak_context_tokens") for t in document["tasks"]]
    assert all(isinstance(p, int) and p > 0 for p in peaks), peaks

    plan = optimize_routing(document, VERIFIED_PRICING, CAPABILITIES)
    assert plan["context_constraint"]["not_declared_for"] == []
    assert len(plan["context_constraint"]["enforced_for"]) == len(document["tasks"])


# ------------------------------------------- 16b confidence has to be earned ---------

def _forecast(confidence):
    return {
        "tokens": {"category_sum_equals_total": True},
        "project": {"confidence": confidence},
        "system_runtime": {"excludes": ["human approvals"]},
        "costs": {"models": [{"not_for_billing": False}]},
    }


def test_confidence_ceiling_starts_at_the_floor_with_no_evidence(tmp_path):
    from elmos_execution_intelligence.certifier import CONFIDENCE_FLOOR, supported_confidence

    supported = supported_confidence(_forecast(0.9), None, None, None)
    # verified rates are the one thing the bare forecast still evidences
    assert supported["ceiling"] == pytest.approx(CONFIDENCE_FLOOR + 0.05)
    assert supported["withheld"]


def test_every_piece_of_evidence_raises_the_ceiling(tmp_path):
    from elmos_execution_intelligence.certifier import supported_confidence

    bare = supported_confidence(_forecast(0.9), None, None, None)["ceiling"]
    full = supported_confidence(
        _forecast(0.9),
        {"gaps": []},
        {"runtime_samples": 40, "token_samples": 40},
        {"scenarios": [{"passed": True}], "passed": True},
    )["ceiling"]
    assert full > bare
    assert full == pytest.approx(1.0)


def test_a_declared_confidence_above_the_ceiling_fails_the_gate(tmp_path):
    _evidence(tmp_path, **{
        "project-forecast.json": _forecast(0.95),
        "risk-and-gap-register.json": {"gaps": []},
    })
    report = evaluate(tmp_path)
    gate = next(g for g in report["gates"] if g["id"] == "confidence-is-supported")
    assert gate["status"] == "FAIL"
    assert "token" in gate["detail"], "the gate must name what evidence is missing"
    assert report["decision"] == "block"


def test_editing_the_number_cannot_pass_the_gate_but_evidence_can(tmp_path):
    _evidence(tmp_path, **{
        "project-forecast.json": _forecast(0.95),
        "risk-and-gap-register.json": {"gaps": []},
        "calibration.json": {"valid_samples": 40, "runtime_samples": 40, "token_samples": 40},
        "chaos-test-report.json": {"scenarios": [{"passed": True}], "passed": True},
    })
    gate = next(g for g in evaluate(tmp_path)["gates"] if g["id"] == "confidence-is-supported")
    assert gate["status"] == "PASS"


def test_the_derivation_is_published_in_the_report(tmp_path):
    _evidence(tmp_path, **{"project-forecast.json": _forecast(0.4)})
    report = evaluate(tmp_path)
    assert report["supported_confidence"]["floor"] == 0.30
    assert "Editing the declared confidence cannot move it" in report["supported_confidence"]["rule"]
