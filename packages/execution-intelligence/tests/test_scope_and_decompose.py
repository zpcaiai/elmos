import json

import pytest
from conftest import ROOT

from elmos_execution_intelligence.decompose import (
    compute_drivers,
    critical_path_seed,
    decompose,
    estimation_seed_rows,
)
from elmos_execution_intelligence.io_utils import load_json
from elmos_execution_intelligence.scope import audit_scope, seed_project_profile
from elmos_execution_intelligence.validation import validate_all, validate_tasks

MODEL = load_json(ROOT / "config" / "decomposition-model.json")
DEFAULTS = load_json(ROOT / "config" / "estimation-defaults.json")
HUMAN = load_json(ROOT / "config" / "human-baselines.json")

LANGS = ["java", "python", "kotlin", "react"]
PENDING = {"kotlin", "react"}


@pytest.fixture()
def repo(tmp_path):
    routes = [f"{a}-to-{b}" for a in LANGS for b in LANGS if a != b]
    (tmp_path / "routes").mkdir()
    inventory = {
        "route_count": len(routes),
        "routes": routes,
        "languages": {
            name: ({"analyzer_status": "PENDING_ANALYZER"} if name in PENDING else {"version": "1"})
            for name in LANGS
        },
        "route_sets": {"complete-12": {"route_count": len(routes)}},
    }
    (tmp_path / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    for name in routes:
        (tmp_path / "routes" / name).mkdir()
    (tmp_path / ".ai").mkdir()
    (tmp_path / ".ai" / "TASK.md").write_text(
        "the surface is 8 directed routes\nlast route matrix run was 64/72\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("print('x')\n" * 40, encoding="utf-8")
    (tmp_path / "src" / "B.java").write_text("class B {}\n" * 40, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    return tmp_path


def test_scope_reads_the_route_inventory_as_the_authority(repo):
    baseline = audit_scope(repo)
    matrix = baseline["route_matrix"]
    assert matrix["declared_route_count"] == 12
    assert matrix["route_directories"] == 12
    assert matrix["pending_analyzer_languages"] == ["kotlin", "react"]
    assert matrix["authority_path"] == "routes/inventory.json"


def test_scope_flags_every_pending_analyzer_language(repo):
    register = audit_scope(repo)["risk_and_gap_register"]
    ids = {gap["id"] for gap in register["gaps"]}
    assert "pending-analyzer-kotlin" in ids
    assert "pending-analyzer-react" in ids


def test_scope_flags_denominator_drift_in_an_authority_doc(repo):
    baseline = audit_scope(repo)
    assert baseline["denominator_claims_in_prose"][".ai/TASK.md"] == [8, 72]
    assert baseline["explicit_denominator_claims"][".ai/TASK.md"] == [8]
    assert ".ai/TASK.md" in baseline["denominator_authority_docs"]
    gap = next(g for g in baseline["risk_and_gap_register"]["gaps"]
               if g["id"] == "denominator-drift-in-authority-docs")
    assert gap["needs_human_input"] is True
    assert ".ai/TASK.md" in gap["evidence"]


def test_a_historical_document_is_informational_not_a_defect(repo):
    (repo / "docs").mkdir()
    (repo / "docs" / "history.md").write_text("back then it was 72 directed routes\n", encoding="utf-8")
    (repo / ".ai" / "TASK.md").write_text("the surface is 12 directed routes\n", encoding="utf-8")
    gaps = {g["id"]: g for g in audit_scope(repo)["risk_and_gap_register"]["gaps"]}
    assert "denominator-drift-in-authority-docs" not in gaps
    historical = gaps["historical-denominators-in-prose"]
    assert historical["severity"] == "low"
    assert historical["needs_human_input"] is False


def test_scope_does_not_flag_drift_when_the_authority_doc_agrees(repo):
    (repo / ".ai" / "TASK.md").write_text("the surface is 12 directed routes\n", encoding="utf-8")
    ids = {gap["id"] for gap in audit_scope(repo)["risk_and_gap_register"]["gaps"]}
    assert "denominator-drift-in-authority-docs" not in ids


def test_scope_flags_an_internally_inconsistent_inventory(repo):
    inventory = json.loads((repo / "routes" / "inventory.json").read_text(encoding="utf-8"))
    inventory["route_count"] = 999
    (repo / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    ids = {gap["id"] for gap in audit_scope(repo)["risk_and_gap_register"]["gaps"]}
    assert "route-count-internal-mismatch" in ids


def test_scope_handles_a_repository_with_no_route_matrix(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    baseline = audit_scope(tmp_path)
    assert baseline["route_matrix"] is None
    assert baseline["risk_and_gap_register"]["gaps"]


def test_seeded_profile_validates_against_a_generated_dag(repo):
    baseline = audit_scope(repo)
    widest = max(float(template.get("worker_units", 1)) for template in MODEL["templates"])
    profile = seed_project_profile(baseline, DEFAULTS, HUMAN, project_id="demo", min_worker_units=widest)
    document = decompose(baseline, MODEL, dag_id="demo")
    pricing = load_json(ROOT / "profiles" / "elmos" / "pricing-registry.example.json")
    errors, _ = validate_all(profile, document, pricing)
    assert errors == []


def test_drivers_are_derived_from_measured_facts(repo):
    drivers = compute_drivers(audit_scope(repo))
    assert drivers["routes"] == 12
    assert drivers["languages"] == 4
    assert drivers["pending_languages"] == 2
    # 4*3 total directed routes minus the 2*1 among non-pending languages
    assert drivers["pending_routes"] == 10
    assert drivers["language_pairs"] == 12


def test_one_analyzer_task_per_pending_language(repo):
    document = decompose(audit_scope(repo), MODEL)
    ids = {task["id"] for task in document["tasks"]}
    assert "analyzer-kotlin" in ids
    assert "analyzer-react" in ids
    route_packs = next(t for t in document["tasks"] if t["id"] == "route-packs")
    assert set(route_packs["depends_on"]) == {"analyzer-kotlin", "analyzer-react"}


def test_no_analyzer_tasks_when_nothing_is_pending(repo):
    inventory = json.loads((repo / "routes" / "inventory.json").read_text(encoding="utf-8"))
    for meta in inventory["languages"].values():
        meta.pop("analyzer_status", None)
        meta["version"] = "1"
    (repo / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    document = decompose(audit_scope(repo), MODEL)
    ids = {task["id"] for task in document["tasks"]}
    assert not any(task_id.startswith("analyzer-") and task_id != "analyzer-performance" for task_id in ids)
    # a template whose parents vanished must not keep dangling dependencies
    assert validate_tasks(document) == []


def test_generated_dag_is_always_valid(repo):
    assert validate_tasks(decompose(audit_scope(repo), MODEL)) == []


def test_sizing_scales_with_the_route_count(repo):
    small = decompose(audit_scope(repo), MODEL)
    inventory = json.loads((repo / "routes" / "inventory.json").read_text(encoding="utf-8"))
    inventory["route_count"] = 156
    (repo / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    big = decompose(audit_scope(repo), MODEL)

    def medium_minutes(document):
        return next(t for t in document["tasks"] if t["id"] == "matrix-medium")["system"]["most_likely_minutes"]

    assert medium_minutes(big) > medium_minutes(small)


def test_token_split_is_enforced(repo):
    broken = json.loads(json.dumps(MODEL))
    broken["token_split"]["input"] = 0.9
    with pytest.raises(ValueError, match="token_split"):
        decompose(audit_scope(repo), broken)


def test_unknown_driver_in_the_model_is_refused(repo):
    broken = json.loads(json.dumps(MODEL))
    broken["templates"][0]["minutes"]["per"] = {"moon_phase": 1}
    with pytest.raises(ValueError, match="unknown driver"):
        decompose(audit_scope(repo), broken)


def test_critical_path_is_a_real_chain_and_a_lower_bound(repo):
    document = decompose(audit_scope(repo), MODEL)
    seed = critical_path_seed(document)
    tasks = {task["id"]: task for task in document["tasks"]}

    path = seed["critical_path"]
    assert len(path) >= 2
    # deliberately unequal lengths: this walks consecutive pairs along the chain
    for parent, child in zip(path, path[1:], strict=False):
        assert parent in tasks[child]["depends_on"]

    expected = sum(tasks[task_id]["system"]["most_likely_minutes"] for task_id in path)
    assert seed["critical_path_minutes"] == pytest.approx(expected)
    assert seed["critical_path_minutes"] <= seed["total_task_minutes"]


def test_estimation_seed_rows_cover_every_task_and_sum_correctly(repo):
    document = decompose(audit_scope(repo), MODEL)
    rows = estimation_seed_rows(document)
    assert len(rows) == len(document["tasks"])
    for row in rows:
        assert row["total_tokens"] == pytest.approx(
            row["input"] + row["cached_input"] + row["cache_write"]
            + row["output"] + row["reasoning_output"])


def test_seeded_worker_count_can_schedule_the_widest_task(repo):
    baseline = audit_scope(repo)
    widest = max(float(template.get("worker_units", 1)) for template in MODEL["templates"])
    profile = seed_project_profile(baseline, DEFAULTS, HUMAN, project_id="demo", min_worker_units=widest)
    system = profile["system"]
    capacity = (system["workers"] * system["worker_availability"] * system["parallel_efficiency"]
                * system["model_concurrency_factor"] * system["code_conflict_factor"])
    assert capacity >= widest


def test_seeded_profile_records_blocking_gaps(repo):
    baseline = audit_scope(repo)
    profile = seed_project_profile(baseline, DEFAULTS, HUMAN, project_id="demo")
    assert "denominator-drift-in-authority-docs" in profile["seed_provenance"]["blocking_gaps"]


def test_a_reconciled_directory_surplus_stops_needing_a_human(repo):
    inventory = json.loads((repo / "routes" / "inventory.json").read_text(encoding="utf-8"))
    strays = ["java-to-ghost", "python-to-ghost"]
    for name in strays:
        (repo / "routes" / name).mkdir()
    inventory["routes"] = [{"route_key": key} for key in inventory["routes"]]
    inventory["route_sets"]["complete-12"]["deprecated_route_keys"] = strays
    (repo / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")

    baseline = audit_scope(repo)
    assert baseline["route_matrix"]["directory_surplus_reconciled"].startswith("2 retained pack")
    gap = next(g for g in baseline["risk_and_gap_register"]["gaps"]
               if g["id"] == "route-directory-count-differs")
    assert gap["needs_human_input"] is False
    assert gap["severity"] == "low"


def test_an_unexplained_directory_surplus_still_needs_a_human(repo):
    (repo / "routes" / "java-to-ghost").mkdir()
    inventory = json.loads((repo / "routes" / "inventory.json").read_text(encoding="utf-8"))
    inventory["routes"] = [{"route_key": key} for key in inventory["routes"]]
    (repo / "routes" / "inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    gap = next(g for g in audit_scope(repo)["risk_and_gap_register"]["gaps"]
               if g["id"] == "route-directory-count-differs")
    assert gap["needs_human_input"] is True


def test_a_bare_ratio_outside_route_context_is_not_a_denominator_claim(repo):
    (repo / ".ai" / "TASK.md").write_text(
        "the surface is 12 directed routes\nseverity counts are 170/400/70\n", encoding="utf-8")
    baseline = audit_scope(repo)
    assert baseline["denominator_claims_in_prose"][".ai/TASK.md"] == [12]
    ids = {gap["id"] for gap in baseline["risk_and_gap_register"]["gaps"]}
    assert "denominator-drift-in-authority-docs" not in ids


def test_an_authority_doc_with_only_a_stray_ratio_is_not_a_defect(repo):
    (repo / ".ai" / "TASK.md").write_text("P0/P1/P2 counts are 312/120/18\n", encoding="utf-8")
    ids = {gap["id"] for gap in audit_scope(repo)["risk_and_gap_register"]["gaps"]}
    assert "denominator-drift-in-authority-docs" not in ids
