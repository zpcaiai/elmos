import json

import pytest
from conftest import PROJECT_PATH, TASKS_PATH

from elmos_execution_intelligence.simulation import (
    TOKEN_FIELDS,
    effective_capacity,
    simulate_human,
    simulate_system,
    summarize_task_tokens,
    summarize_tokens,
)


@pytest.fixture(scope="module")
def small_bundle():
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    project["simulation"] = {"runs": 200, "seed": 7}
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    return project, tasks


def test_simulation_is_deterministic_for_a_fixed_seed(small_bundle):
    project, tasks = small_bundle
    first, _, _ = simulate_system(project, tasks)
    second, _, _ = simulate_system(project, tasks)
    assert first["wall_clock_hours"] == second["wall_clock_hours"]


def test_wall_clock_never_undercuts_the_critical_path(small_bundle):
    project, tasks = small_bundle
    runtime, _, _ = simulate_system(project, tasks)
    assert runtime["wall_clock_hours"]["p50"] >= runtime["critical_path_hours"]["p50"] - 1e-6


def test_active_worker_hours_bound_wall_clock_from_above(small_bundle):
    project, tasks = small_bundle
    runtime, _, _ = simulate_system(project, tasks)
    assert runtime["active_worker_hours"]["p50"] >= runtime["wall_clock_hours"]["p50"] - 1e-6


def test_token_categories_sum_to_total_without_double_counting(small_bundle):
    project, tasks = small_bundle
    _, samples, _ = simulate_system(project, tasks)
    for sample in samples[:50]:
        assert sample["total"] == pytest.approx(sum(sample[field] for field in TOKEN_FIELDS))


def test_token_envelope_is_ordered(small_bundle):
    project, tasks = small_bundle
    _, samples, _ = simulate_system(project, tasks)
    tokens = summarize_tokens(samples, 0.99)
    total = tokens["total"]
    assert total["p50"] <= total["p80"] <= total["p90"] <= total["worst_case"]
    assert tokens["category_sum_equals_total"] is True


def test_every_task_is_traceable_in_the_token_breakdown(small_bundle):
    project, tasks = small_bundle
    _, _, per_task = simulate_system(project, tasks)
    rows = summarize_task_tokens(per_task, tasks["tasks"], 0.99)
    assert {row["task_id"] for row in rows} == {task["id"] for task in tasks["tasks"]}
    assert all(row["total_tokens"]["p50"] > 0 for row in rows)


def test_system_runtime_declares_its_exclusions(small_bundle):
    project, tasks = small_bundle
    runtime, _, _ = simulate_system(project, tasks)
    joined = " ".join(runtime["excludes"]).lower()
    assert "approval" in joined and "acceptance" in joined


def test_effective_capacity_never_drops_below_one_worker():
    system = {"workers": 1, "worker_availability": 0.1, "parallel_efficiency": 0.1,
              "model_concurrency_factor": 0.1, "code_conflict_factor": 0.1}
    assert effective_capacity(system) == 1.0


def test_cycle_raises_during_simulation(small_bundle):
    project, _ = small_bundle
    tasks = {"tasks": [
        {"id": "a", "depends_on": ["b"], "system": {"optimistic_minutes": 1, "most_likely_minutes": 1,
         "pessimistic_minutes": 1, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
        {"id": "b", "depends_on": ["a"], "system": {"optimistic_minutes": 1, "most_likely_minutes": 1,
         "pessimistic_minutes": 1, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
    ]}
    with pytest.raises(ValueError, match="cycle"):
        simulate_system(project, tasks)


def test_task_wider_than_capacity_is_refused(small_bundle):
    project, _ = small_bundle
    project = json.loads(json.dumps(project))
    tasks = {"tasks": [
        {"id": "a", "system": {"optimistic_minutes": 1, "most_likely_minutes": 1, "pessimistic_minutes": 1,
         "worker_units": 999, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
    ]}
    with pytest.raises(ValueError, match="worker units"):
        simulate_system(project, tasks)


def test_human_baseline_uses_the_same_definition_of_done(small_bundle):
    project, tasks = small_bundle
    human = simulate_human(project, tasks)
    assert human["same_definition_of_done"] is True
    assert human["person_hours"]["p50"] > 0
    assert set(human["role_person_hours"]) == set(project["human"]["roles"])


def test_person_days_and_months_derive_from_person_hours(small_bundle):
    project, tasks = small_bundle
    human = simulate_human(project, tasks)
    hours_per_day = project["human"]["work_hours_per_day"]
    assert human["person_days"]["p50"] == pytest.approx(human["person_hours"]["p50"] / hours_per_day, rel=1e-3)
    assert human["person_months"]["p50"] == pytest.approx(
        human["person_hours"]["p50"] / (hours_per_day * project["human"]["month_working_days"]), rel=1e-3)
