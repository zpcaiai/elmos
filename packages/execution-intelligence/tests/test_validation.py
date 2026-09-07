import copy
import json

import pytest
from conftest import PRICING_PATH, PROJECT_PATH, TASKS_PATH

from elmos_execution_intelligence.validation import validate_all, validate_pricing, validate_tasks


@pytest.fixture(scope="module")
def bundle():
    return (
        json.loads(PROJECT_PATH.read_text(encoding="utf-8")),
        json.loads(TASKS_PATH.read_text(encoding="utf-8")),
        json.loads(PRICING_PATH.read_text(encoding="utf-8")),
    )


def test_shipped_elmos_profile_validates(bundle):
    project, tasks, pricing = bundle
    errors, warnings = validate_all(project, tasks, pricing)
    assert errors == []
    # every shipped rate is illustrative, so every model must warn
    assert len(warnings) == len(pricing["models"])


def test_cycle_is_rejected():
    tasks = {
        "tasks": [
            {"id": "a", "depends_on": ["b"], "system": {"optimistic_minutes": 1, "most_likely_minutes": 2,
             "pessimistic_minutes": 3, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
            {"id": "b", "depends_on": ["a"], "system": {"optimistic_minutes": 1, "most_likely_minutes": 2,
             "pessimistic_minutes": 3, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
        ]
    }
    assert "task DAG contains a cycle" in validate_tasks(tasks)


def test_unknown_dependency_is_rejected():
    tasks = {
        "tasks": [
            {"id": "a", "depends_on": ["ghost"], "system": {"optimistic_minutes": 1, "most_likely_minutes": 2,
             "pessimistic_minutes": 3, "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
        ]
    }
    assert any("unknown task ghost" in error for error in validate_tasks(tasks))


def test_duration_ordering_is_enforced():
    tasks = {
        "tasks": [
            {"id": "a", "system": {"optimistic_minutes": 9, "most_likely_minutes": 2, "pessimistic_minutes": 3,
             "token_profile": {"input": 1}}, "human": {"hours_by_role": {"qa": 1}}},
        ]
    }
    assert any("optimistic <= most_likely <= pessimistic" in error for error in validate_tasks(tasks))


def test_token_profile_must_declare_a_positive_category():
    tasks = {
        "tasks": [
            {"id": "a", "system": {"optimistic_minutes": 1, "most_likely_minutes": 2, "pessimistic_minutes": 3,
             "token_profile": {"input": 0}}, "human": {"hours_by_role": {"qa": 1}}},
        ]
    }
    assert any("at least one positive token category" in error for error in validate_tasks(tasks))


def test_pricing_template_with_null_rates_is_rejected():
    registry = {
        "registry_version": "TEMPLATE",
        "models": [{"id": "x", "effective_date": None, "verified_at": None, "source_reference": None,
                    "rates_per_million": {"input": None, "cached_input": None, "cache_write": None,
                                          "output": None, "reasoning_output": None}}],
    }
    errors, _ = validate_pricing(registry)
    assert any("rates_per_million.input" in error for error in errors)
    assert any("dated provenance" in error for error in errors)


def test_task_role_must_exist_in_project(bundle):
    project, tasks, pricing = bundle
    mutated = copy.deepcopy(tasks)
    mutated["tasks"][0]["human"]["hours_by_role"]["ghost_role"] = 4
    errors, _ = validate_all(project, mutated, pricing)
    assert any("ghost_role" in error for error in errors)


def test_worker_units_wider_than_capacity_is_blocked_at_validation(bundle):
    project, tasks, pricing = bundle
    shrunk = copy.deepcopy(project)
    shrunk["system"]["workers"] = 1
    errors, _ = validate_all(shrunk, tasks, pricing)
    assert any("effective capacity" in error for error in errors)
