"""The mix comparison, and the reasoning-token accounting it depends on."""
from __future__ import annotations

import json

import pytest

from elmos_execution_intelligence.telemetry import (
    InclusiveReasoningViolation,
    _normalise_usage,
    parse_agent_transcript,
)
from elmos_execution_intelligence.token_mix import (
    CATEGORIES,
    compare_mix,
    cost_of_mix,
    forecast_mix,
    mix_warmup,
    render_mix,
)

PRICING = {
    "models": [
        {
            "id": "m-expensive-input", "display_name": "Expensive input", "currency": "USD",
            "not_for_billing": False, "source_reference": "https://example.invalid/pricing",
            "verified_at": "2026-08-19T00:00:00Z",
            "rates_per_million": {
                "input": 10.0, "cached_input": 1.0, "cache_write": 12.0,
                "output": 50.0, "reasoning_output": 50.0,
            },
        },
        {
            "id": "m-unpriced", "display_name": "Not for billing", "currency": "USD",
            "not_for_billing": True, "source_reference": "https://example.invalid/pricing",
            "verified_at": "2026-08-19T00:00:00Z",
            "rates_per_million": {
                "input": 1.0, "cached_input": 1.0, "cache_write": 1.0,
                "output": 1.0, "reasoning_output": 1.0,
            },
        },
    ]
}


# --------------------------------------------------------------- accounting --

def test_nested_thinking_tokens_are_subtracted_from_output():
    """Providers report reasoning inside the output total; the five must stay disjoint."""
    usage = _normalise_usage({
        "input_tokens": 10,
        "cache_read_input_tokens": 100,
        "cache_creation_input_tokens": 20,
        "output_tokens": 500,
        "output_tokens_details": {"thinking_tokens": 120},
    })
    assert usage is not None
    assert usage["reasoning_output"] == 120
    # 500 reported, 120 of which was reasoning -> 380 is the non-reasoning output.
    assert usage["output"] == 380
    # The invariant the whole package rests on: total is the sum, with no overlap.
    assert sum(usage[field] for field in CATEGORIES) == 10 + 100 + 20 + 380 + 120


def test_flat_reasoning_field_is_not_subtracted():
    """A provider reporting reasoning as a sibling is telling us it is a separate line."""
    usage = _normalise_usage({
        "input_tokens": 10, "output_tokens": 500, "reasoning_tokens": 120,
    })
    assert usage is not None
    assert usage["reasoning_output"] == 120
    assert usage["output"] == 500  # untouched


def test_reasoning_larger_than_output_is_refused_not_clamped():
    """Falsifies the inclusion assumption, so it must stop rather than produce a number."""
    with pytest.raises(InclusiveReasoningViolation) as excinfo:
        _normalise_usage({
            "input_tokens": 10,
            "output_tokens": 100,
            "output_tokens_details": {"thinking_tokens": 250},
        })
    assert "assumption" in str(excinfo.value)


def test_openai_completion_details_shape(tmp_path):
    record = {"message": {"model": "some-model", "usage": {
        "prompt_tokens": 7, "completion_tokens": 90,
        "completion_tokens_details": {"reasoning_tokens": 40},
    }}}
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    report = parse_agent_transcript(path)
    assert report["tokens"]["reasoning_output"] == 40
    assert report["tokens"]["output"] == 50
    assert report["tokens"]["total"] == 7 + 50 + 40


# --------------------------------------------------------------- comparison --

def test_forecast_mix_aggregates_task_profiles():
    tasks = [
        {"id": "a", "system": {"token_profile": {
            "input": 100.0, "cached_input": 300.0, "cache_write": 50.0,
            "output": 40.0, "reasoning_output": 10.0}}},
        {"id": "b", "system": {"token_profile": {
            "input": 100.0, "cached_input": 300.0, "cache_write": 50.0,
            "output": 40.0, "reasoning_output": 10.0}}},
    ]
    assert forecast_mix(tasks)["cached_input"] == 600.0


def test_cost_of_mix_prices_each_category_separately():
    mix = {"input": 1.0, "cached_input": 0.0, "cache_write": 0.0,
           "output": 0.0, "reasoning_output": 0.0}
    rates = {f: 10.0 for f in CATEGORIES}
    assert cost_of_mix(1_000_000, mix, rates) == pytest.approx(10.0)


def test_mix_shift_moves_cost_without_moving_the_token_total():
    """The point of the artifact: same tokens, different bill."""
    forecast = {"input": 240.0, "cached_input": 630.0, "cache_write": 70.0,
                "output": 40.0, "reasoning_output": 20.0}
    observed = {"input": 1.0, "cached_input": 980.0, "cache_write": 9.0,
                "output": 8.0, "reasoning_output": 2.0}
    report = compare_mix(forecast, observed, 1_000_000.0, PRICING,
                         observed_sessions=1, observed_models=["some-model"])

    assert report["forecast"]["total"] == 1000.0
    assert report["observed"]["total"] == 1000.0  # identical totals...
    priced = report["cost_restatement"]
    assert len(priced) == 1  # not_for_billing is excluded
    # ...and a materially different bill, purely from the mix.
    assert priced[0]["cost_under_forecast_mix"] > priced[0]["cost_under_observed_mix"]
    assert priced[0]["overstatement_factor"] > 1.0


def test_comparison_never_writes_back_and_never_ranks_currencies():
    report = compare_mix(
        {f: 1.0 for f in CATEGORIES}, {f: 1.0 for f in CATEGORIES},
        1000.0, PRICING, observed_sessions=99, observed_models=["m"])
    assert report["applied_to_forecast"] is False
    assert report["cross_currency_comparison"] is None


def test_sample_floor_is_reported_not_enforced_silently():
    thin = compare_mix({f: 1.0 for f in CATEGORIES}, {f: 1.0 for f in CATEGORIES},
                       1000.0, PRICING, observed_sessions=1, observed_models=["m"],
                       minimum_sessions=20)
    assert thin["sample_sufficient"] is False
    assert "20" in thin["why_not_applied"]

    thick = compare_mix({f: 1.0 for f in CATEGORIES}, {f: 1.0 for f in CATEGORIES},
                        1000.0, PRICING, observed_sessions=20, observed_models=["m"],
                        minimum_sessions=20)
    assert thick["sample_sufficient"] is True


def test_zero_counts_are_refused():
    with pytest.raises(ValueError):
        compare_mix({f: 0.0 for f in CATEGORIES}, {f: 1.0 for f in CATEGORIES},
                    1000.0, PRICING, observed_sessions=1, observed_models=["m"])


def test_render_names_the_overstatement():
    forecast = {"input": 240.0, "cached_input": 630.0, "cache_write": 70.0,
                "output": 40.0, "reasoning_output": 20.0}
    observed = {"input": 1.0, "cached_input": 980.0, "cache_write": 9.0,
                "output": 8.0, "reasoning_output": 2.0}
    text = render_mix(compare_mix(forecast, observed, 1_000_000.0, PRICING,
                                  observed_sessions=1, observed_models=["m"]))
    assert "TOKEN_MIX_COMPARISON" in text
    assert "高估" in text
    assert "**否**" in text  # the sample floor is visible in the report, not buried


# ------------------------------------------------------------------- warm-up --

def _turn(cached, write, out=10, inp=1, reasoning=2):
    return {"input": inp, "cached_input": cached, "cache_write": write,
            "output": out, "reasoning_output": reasoning}


def test_warmup_shows_the_cache_share_climbing():
    """Cache reads are earned: turn one reads nothing, later turns read a lot."""
    turns = [_turn(0, 1000)] + [_turn(1000, 10) for _ in range(99)]
    warmup = mix_warmup(turns, depths=(5, 20))
    shares = [point["mix"]["cached_input"] for point in warmup["depths"]]
    assert shares == sorted(shares), "cumulative cache share must be non-decreasing here"
    assert warmup["cached_input_share_at_shallowest"] < warmup["cached_input_share_at_full_session"]
    assert warmup["warmup_spread"] > 0


def test_warmup_marks_the_full_session_row():
    turns = [_turn(100, 10) for _ in range(30)]
    warmup = mix_warmup(turns, depths=(5, 10))
    full = [point for point in warmup["depths"] if point["is_full_session"]]
    assert len(full) == 1
    assert full[0]["turns"] == 30


def test_warmup_does_not_emit_duplicate_depths():
    """A depth past the end of the session collapses onto the full-session row."""
    turns = [_turn(100, 10) for _ in range(7)]
    warmup = mix_warmup(turns, depths=(5, 10, 20, 50))
    counts = [point["turns"] for point in warmup["depths"]]
    assert counts == sorted(set(counts))
    assert max(counts) == 7


def test_warmup_needs_turns():
    with pytest.raises(ValueError):
        mix_warmup([])


def test_overstatement_is_reported_as_a_curve_not_a_constant():
    """Quoting the full-session factor alone would mislead for short tasks."""
    turns = [_turn(0, 5000)] * 3 + [_turn(5000, 10) for _ in range(97)]
    warmup = mix_warmup(turns, depths=(5, 50))
    forecast = {"input": 240.0, "cached_input": 630.0, "cache_write": 70.0,
                "output": 40.0, "reasoning_output": 20.0}
    observed = {f: float(sum(t[f] for t in turns)) for f in CATEGORIES}
    report = compare_mix(forecast, observed, 1_000_000.0, PRICING,
                         observed_sessions=1, observed_models=["m"], warmup=warmup)

    depths = report["cost_by_session_depth"]
    assert len(depths) == len(warmup["depths"])
    # The shallow end must be cheaper to justify (smaller factor) than the deep end.
    assert depths[0]["overstatement_factor"] < depths[-1]["overstatement_factor"]
    assert report["overstatement_factor_is_full_session_only"] is True
    assert "not the typical one" in report["overstatement_caveat"]
    assert report["cost_by_session_depth_basis"]["reference_model"] == "m-expensive-input"


def test_depth_pricing_is_absent_without_warmup():
    report = compare_mix({f: 1.0 for f in CATEGORIES}, {f: 1.0 for f in CATEGORIES},
                         1000.0, PRICING, observed_sessions=1, observed_models=["m"])
    assert report["cost_by_session_depth"] == []
    assert report["warmup"] is None


def test_render_warns_the_factor_is_not_flat():
    turns = [_turn(0, 5000)] * 3 + [_turn(5000, 10) for _ in range(97)]
    warmup = mix_warmup(turns, depths=(5, 50))
    observed = {f: float(sum(t[f] for t in turns)) for f in CATEGORIES}
    text = render_mix(compare_mix(
        {"input": 240.0, "cached_input": 630.0, "cache_write": 70.0,
         "output": 40.0, "reasoning_output": 20.0},
        observed, 1_000_000.0, PRICING,
        observed_sessions=1, observed_models=["m"], warmup=warmup))
    assert "不是一个固定倍数" in text
    assert "上限" in text
