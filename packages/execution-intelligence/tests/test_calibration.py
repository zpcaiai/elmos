import pytest

from elmos_execution_intelligence.calibration import calibrate

ROW = {"task_type": "verification", "complexity": "high", "model": "m",
       "estimated_minutes": 100, "actual_minutes": 150,
       "estimated_total_tokens": 1000, "actual_total_tokens": 2000}


def test_multipliers_are_actual_over_estimate():
    result = calibrate([ROW])
    assert result["global"]["runtime_multiplier"]["p50"] == pytest.approx(1.5)
    assert result["global"]["token_multiplier"]["p50"] == pytest.approx(2.0)


def test_a_row_missing_one_dimension_still_calibrates_the_other():
    token_only = dict(ROW)
    token_only["actual_minutes"] = None
    result = calibrate([ROW, token_only])
    assert result["valid_samples"] == 2
    assert result["runtime_samples"] == 1
    assert result["token_samples"] == 2
    assert result["dropped_samples"] == 0


def test_a_row_missing_both_dimensions_is_dropped_not_guessed():
    useless = dict(ROW)
    useless["actual_minutes"] = None
    useless["actual_total_tokens"] = None
    result = calibrate([ROW, useless])
    assert result["valid_samples"] == 1
    assert result["dropped_samples"] == 1


def test_runtime_only_history_reports_tokens_as_unavailable_not_one():
    from elmos_execution_intelligence.calibration import apply_calibration, estimator_profiles

    row = {"task_type": "verification", "complexity": "high", "model": "m",
           "estimated_minutes": 10, "actual_minutes": 5}
    result = calibrate([row])
    assert result["global"]["runtime_multiplier"]["p50"] == pytest.approx(0.5)
    assert result["global"]["token_multiplier"] is None
    assert any("token" in item for item in result["unavailable"])

    profiles = estimator_profiles(result)
    assert profiles["default"]["runtime_measured"] is True
    assert profiles["default"]["token_measured"] is False

    dag = {"tasks": [{"id": "t", "category": "verification", "complexity": "high",
                      "system": {"most_likely_minutes": 100, "optimistic_minutes": 50,
                                 "pessimistic_minutes": 200,
                                 "token_profile": {"input": 1000}}}]}
    updated, changelog = apply_calibration(dag, profiles)
    system = updated["tasks"][0]["system"]
    assert system["most_likely_minutes"] == pytest.approx(50.0), "runtime was measured, so it is rewritten"
    assert system["token_profile"]["input"] == 1000, "tokens were not measured, so they are left alone"
    assert system["calibration"]["token_multiplier"] is None
    assert changelog[0]["token_measured"] is False


def test_all_rows_invalid_raises():
    with pytest.raises(ValueError):
        calibrate([{"task_type": "x"}])


def test_empty_history_raises():
    with pytest.raises(ValueError):
        calibrate([])


def test_small_groups_are_marked_not_applicable():
    result = calibrate([ROW])
    group = next(iter(result["groups"].values()))
    assert group["applicable"] is False
    assert group["samples"] == 1


def test_large_groups_become_applicable():
    result = calibrate([dict(ROW) for _ in range(6)])
    group = next(iter(result["groups"].values()))
    assert group["applicable"] is True
