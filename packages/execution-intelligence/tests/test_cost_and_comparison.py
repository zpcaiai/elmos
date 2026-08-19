import json

import pytest
from conftest import PRICING_PATH, PROJECT_PATH, TASKS_PATH

from elmos_execution_intelligence.comparison import compare
from elmos_execution_intelligence.cost import estimate_costs
from elmos_execution_intelligence.simulation import simulate_human, simulate_system

SAMPLES = [{"input": 1_000_000, "cached_input": 1_000_000, "cache_write": 1_000_000,
            "output": 1_000_000, "reasoning_output": 1_000_000, "total": 5_000_000}]


def _registry(**overrides):
    model = {
        "id": "m", "currency": "USD", "effective_date": "2026-01-01", "verified_at": "2026-01-01T00:00:00Z",
        "source_reference": "test", "rates_per_million": {
            "input": 1.0, "cached_input": 2.0, "cache_write": 3.0, "output": 4.0, "reasoning_output": 5.0},
    }
    model.update(overrides)
    return {"registry_version": "test", "base_currency": "USD", "models": [model]}


def test_cost_is_the_sum_of_per_category_rates():
    result = estimate_costs(SAMPLES, _registry())
    assert result["models"][0]["cost"]["p50"] == pytest.approx(15.0)


def test_empty_samples_are_refused():
    with pytest.raises(ValueError):
        estimate_costs([], _registry())


def test_currencies_are_never_ranked_against_each_other():
    registry = _registry()
    registry["models"].append({
        "id": "cny", "currency": "CNY", "effective_date": "2026-01-01", "verified_at": "2026-01-01T00:00:00Z",
        "source_reference": "test", "rates_per_million": {
            "input": 0.1, "cached_input": 0.1, "cache_write": 0.1, "output": 0.1, "reasoning_output": 0.1},
    })
    result = estimate_costs(SAMPLES, registry)
    assert result["cross_currency_comparison"] is None
    assert set(result["rankings_by_currency"]) == {"USD", "CNY"}
    assert result["rankings_by_currency"]["USD"]["ranked_model_ids_by_p50"] == ["m"]
    assert result["rankings_by_currency"]["CNY"]["ranked_model_ids_by_p50"] == ["cny"]


def test_illustrative_rates_are_excluded_from_the_verified_ranking_pool():
    registry = _registry(not_for_billing=True)
    result = estimate_costs(SAMPLES, registry)
    assert result["rankings_by_currency"]["USD"]["ranking_pool"] == "illustrative_rates"


def test_comparison_keeps_human_waits_out_of_the_system_eta():
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    project["simulation"] = {"runs": 200, "seed": 11}
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))

    runtime, samples, _ = simulate_system(project, tasks)
    costs = estimate_costs(samples, pricing)
    human = simulate_human(project, tasks)
    result = compare(project, runtime, human, costs)

    system_p50 = runtime["wall_clock_hours"]["p50"]
    assisted_p50 = result["human_assisted"]["end_to_end_hours"]["p50"]
    assert assisted_p50 > system_p50, "human review and waits must sit outside the system ETA"
    assert result["same_definition_of_done_for_both_baselines"] is True
    assert result["comparison"]["calendar_speedup"]["p50"] > 0


def test_review_parallel_fraction_of_one_removes_serial_review():
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    project["simulation"] = {"runs": 150, "seed": 3}
    project["human_assisted"]["review_parallel_fraction"] = 1.0
    project["human_assisted"]["approval_wait_hours"] = 0
    project["human_assisted"]["external_wait_hours"] = 0
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    pricing = json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    runtime, samples, _ = simulate_system(project, tasks)
    result = compare(project, runtime, simulate_human(project, tasks), estimate_costs(samples, pricing))
    assert result["human_assisted"]["end_to_end_hours"]["p50"] == pytest.approx(runtime["wall_clock_hours"]["p50"])


# --------------------------------------------- mix verification declaration ---

def test_cost_report_declares_an_unchecked_mix_as_unchecked():
    """Silence would let an assumed mix read as a settled one."""
    from elmos_execution_intelligence.cost import mix_verification
    verification = mix_verification(None)
    assert verification["checked"] is False
    assert "假设" in verification["detail"]


def test_cost_report_carries_the_mix_finding_when_one_exists():
    from elmos_execution_intelligence.cost import mix_verification
    verification = mix_verification({
        "observed": {"sessions": 1, "mix": {"cached_input": 0.9882}},
        "forecast": {"mix": {"cached_input": 0.63}},
        "minimum_sessions": 20,
        "sample_sufficient": False,
        "cost_by_session_depth": [
            {"turns": 5, "overstatement_factor": 1.17},
            {"turns": 500, "overstatement_factor": 5.54},
        ],
    })
    assert verification["checked"] is True
    assert verification["sample_sufficient"] is False
    assert verification["observed_cached_input_share"] == 0.9882
    assert verification["forecast_cached_input_share"] == 0.63
    assert [row["factor"] for row in verification["overstatement_by_depth"]] == [1.17, 5.54]


def test_estimate_costs_attaches_the_verification_block():
    from elmos_execution_intelligence.cost import estimate_costs
    registry = {
        "base_currency": "USD",
        "registry_version": "test",
        "models": [{
            "id": "m", "display_name": "M", "currency": "USD",
            "not_for_billing": False,
            "rates_per_million": {
                "input": 1.0, "cached_input": 0.1, "cache_write": 1.2,
                "output": 5.0, "reasoning_output": 5.0,
            },
        }],
    }
    samples = [{"input": 10.0, "cached_input": 100.0, "cache_write": 5.0,
                "output": 2.0, "reasoning_output": 1.0}]
    result = estimate_costs(samples, registry)
    assert result["mix_verification"]["checked"] is False


def test_rendered_cost_report_warns_when_the_mix_was_never_checked():
    from elmos_execution_intelligence.report import _mix_verification_lines
    lines = _mix_verification_lines({"checked": False, "detail": "从未对照过"})
    assert any("未经核对" in line for line in lines)


def test_rendered_cost_report_states_the_sample_shortfall():
    from elmos_execution_intelligence.report import _mix_verification_lines
    lines = _mix_verification_lines({
        "checked": True, "detail": "已对照",
        "observed_cached_input_share": 0.9882,
        "forecast_cached_input_share": 0.63,
        "sessions": 1, "minimum_sessions": 20, "sample_sufficient": False,
        "overstatement_by_depth": [
            {"turns": 5, "factor": 1.17}, {"turns": 500, "factor": 5.54}],
    })
    text = "\n".join(lines)
    assert "98.82%" in text and "63.00%" in text
    assert "1.17x" in text and "5.54x" in text
    # A checked-but-thin sample must not read as a settled calibration.
    assert "发现" in text and "不是一次校准" in text
