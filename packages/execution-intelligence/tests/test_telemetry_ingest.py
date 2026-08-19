"""Real-telemetry ingestion: what it measures, and what it refuses to claim."""
import json

import pytest
from conftest import TASKS_PATH

from elmos_execution_intelligence.calibration import calibrate
from elmos_execution_intelligence.io_utils import load_json
from elmos_execution_intelligence.telemetry import (
    ingest_report,
    parse_pytest_log,
    rows_from_pytest_logs,
)

TASKS = load_json(TASKS_PATH)
MATRIX_MEDIUM = next(t for t in TASKS["tasks"] if t["id"] == "matrix-medium")

REAL_TAIL = """\
tests/test_repository_pipeline_language_matrix.py::test_x[swift-java] FAILED
=========================== short test summary info ============================
FAILED tests/test_repository_pipeline_language_matrix.py::test_x[swift-java]
1 failed, 83 passed in 4759.49s (1:19:19)
"""

DESELECTED = "9 failed, 38 passed, 135 deselected in 8066.46s (2:14:26)\n"


def _log(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_the_summary_line(tmp_path):
    summary = parse_pytest_log(_log(tmp_path, "run.log", REAL_TAIL))
    assert summary["executed_nodes"] == 84
    assert summary["passed"] == 83
    assert summary["failed"] == 1
    assert summary["total_seconds"] == pytest.approx(4759.49)
    assert summary["mean_seconds_per_node"] == pytest.approx(4759.49 / 84, rel=1e-4)


def test_deselected_nodes_are_not_counted_as_executed(tmp_path):
    summary = parse_pytest_log(_log(tmp_path, "tail.log", DESELECTED))
    assert summary["executed_nodes"] == 47
    assert summary["deselected"] == 135
    assert summary["aborted_early"] is True


def test_a_log_without_a_summary_line_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no pytest summary line"):
        parse_pytest_log(_log(tmp_path, "collect.log", "collected 182 items\n"))


def test_a_log_reporting_zero_executed_nodes_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no executed nodes"):
        parse_pytest_log(_log(tmp_path, "empty.log", "182 deselected in 1.20s\n"))


def test_comparison_is_made_per_unit_not_per_task(tmp_path):
    rows, _ = rows_from_pytest_logs([_log(tmp_path, "run.log", REAL_TAIL)],
                                    MATRIX_MEDIUM, unit_count=156)
    row = rows[0]
    assert row["estimated_minutes"] == pytest.approx(
        MATRIX_MEDIUM["system"]["most_likely_minutes"] / 156)
    assert row["actual_minutes"] == pytest.approx(4759.49 / 84 / 60)
    assert row["measurement"] == "aggregate_mean_per_node"


def test_unit_count_is_mandatory(tmp_path):
    with pytest.raises(ValueError, match="unit_count"):
        rows_from_pytest_logs([_log(tmp_path, "run.log", REAL_TAIL)], MATRIX_MEDIUM, unit_count=0)


def test_rows_carry_their_caveats_and_no_token_data(tmp_path):
    rows, _ = rows_from_pytest_logs([_log(tmp_path, "run.log", REAL_TAIL)],
                                    MATRIX_MEDIUM, unit_count=156,
                                    caveats=("older 182-node suite, not the current 156-route matrix",))
    row = rows[0]
    assert "estimated_total_tokens" not in row
    assert "actual_total_tokens" not in row
    assert any("182-node" in caveat for caveat in row["caveats"])
    assert any("runtime only" in caveat for caveat in row["caveats"])


def test_ingested_rows_calibrate_runtime_and_leave_tokens_unavailable(tmp_path):
    rows, parsed = rows_from_pytest_logs(
        [_log(tmp_path, "a.log", REAL_TAIL), _log(tmp_path, "b.log", DESELECTED)],
        MATRIX_MEDIUM, unit_count=156)
    result = calibrate(rows)
    assert result["runtime_samples"] == 2
    assert result["token_samples"] == 0
    assert result["global"]["runtime_multiplier"] is not None
    assert result["global"]["token_multiplier"] is None

    report = ingest_report(rows, parsed)
    assert report["token_data_available"] is False
    assert report["total_executed_nodes"] == 84 + 47


def test_the_measured_ratio_says_the_estimate_was_too_high(tmp_path):
    """The real matrix runs were faster per node than the DAG assumed. That is a
    finding, not a bug: it is exactly what calibration is for."""
    rows, _ = rows_from_pytest_logs([_log(tmp_path, "run.log", REAL_TAIL)],
                                    MATRIX_MEDIUM, unit_count=156)
    ratio = rows[0]["actual_minutes"] / rows[0]["estimated_minutes"]
    assert ratio < 1.0


# --------------------------------------------------------------- per-node durations --

DURATIONS_LOG = """\
============================= slowest durations ==============================
120.51s call     tests/test_matrix.py::test_route[java-python]
 60.25s call     tests/test_matrix.py::test_route[python-java]
  1.50s setup    tests/test_matrix.py::test_route[java-python]
  0.02s teardown tests/test_matrix.py::test_route[java-python]
=========================== short test summary info ==========================
2 passed in 182.30s
"""


def test_durations_are_read_per_node_with_phases_summed(tmp_path):
    from elmos_execution_intelligence.telemetry import parse_pytest_durations

    report = parse_pytest_durations(_log(tmp_path, "d.log", DURATIONS_LOG))
    assert report["node_count"] == 2
    by_node = {n["nodeid"]: n for n in report["nodes"]}
    java = by_node["tests/test_matrix.py::test_route[java-python]"]
    assert java["seconds"] == pytest.approx(120.51 + 1.50 + 0.02)
    assert set(java["phases"]) == {"call", "setup", "teardown"}


def test_a_log_without_durations_is_refused(tmp_path):
    from elmos_execution_intelligence.telemetry import parse_pytest_durations

    with pytest.raises(ValueError, match="--durations=0"):
        parse_pytest_durations(_log(tmp_path, "plain.log", REAL_TAIL))


def test_durations_produce_one_row_per_node_not_one_per_log(tmp_path):
    from elmos_execution_intelligence.telemetry import rows_from_pytest_durations

    rows, parsed = rows_from_pytest_durations(
        [_log(tmp_path, "d.log", DURATIONS_LOG)], MATRIX_MEDIUM, unit_count=156)
    assert len(rows) == 2
    assert {row["measurement"] for row in rows} == {"per_node_observed"}
    assert parsed[0]["executed_nodes"] == 2
    slow = max(rows, key=lambda r: r["actual_minutes"])
    assert slow["nodeid"].endswith("[java-python]")


# ------------------------------------------------------------- agent transcripts ----

CLAUDE_TRANSCRIPT = "\n".join([
    json.dumps({"type": "user", "timestamp": "2026-08-19T10:00:00Z"}),
    json.dumps({"type": "assistant", "timestamp": "2026-08-19T10:05:00Z",
                "message": {"model": "claude-opus-5", "usage": {
                    "input_tokens": 1000, "cache_read_input_tokens": 40000,
                    "cache_creation_input_tokens": 5000, "output_tokens": 800}}}),
    json.dumps({"type": "assistant", "timestamp": "2026-08-19T10:20:00Z",
                "message": {"model": "claude-opus-5", "usage": {
                    "input_tokens": 500, "cache_read_input_tokens": 60000,
                    "cache_creation_input_tokens": 0, "output_tokens": 1200}}}),
])

CODEX_TRANSCRIPT = "\n".join([
    json.dumps({"type": "token_count", "timestamp": "2026-08-19T11:00:00Z",
                "info": {"model": "gpt-5.6-sol", "total_token_usage": {
                    "input_tokens": 10000, "cached_input_tokens": 2000,
                    "output_tokens": 500, "reasoning_output_tokens": 300}}}),
    json.dumps({"type": "token_count", "timestamp": "2026-08-19T11:30:00Z",
                "info": {"model": "gpt-5.6-sol", "total_token_usage": {
                    "input_tokens": 25000, "cached_input_tokens": 9000,
                    "output_tokens": 1400, "reasoning_output_tokens": 900}}}),
])


def test_claude_transcript_usage_is_summed(tmp_path):
    from elmos_execution_intelligence.telemetry import parse_agent_transcript

    report = parse_agent_transcript(_log(tmp_path, "s.jsonl", CLAUDE_TRANSCRIPT))
    assert report["usage_records"] == 2
    assert report["tokens"]["input"] == 1500
    assert report["tokens"]["cached_input"] == 100_000
    assert report["tokens"]["cache_write"] == 5000
    assert report["tokens"]["output"] == 2000
    assert report["tokens"]["total"] == 108_500
    assert report["models"] == {"claude-opus-5": 2}
    assert report["elapsed_minutes"] == pytest.approx(20.0)


def test_a_cumulative_transcript_is_not_double_counted(tmp_path):
    """Codex reports a running total on every event; summing them would double-count."""
    from elmos_execution_intelligence.telemetry import parse_agent_transcript

    report = parse_agent_transcript(_log(tmp_path, "c.jsonl", CODEX_TRANSCRIPT))
    assert report["tokens"]["input"] == 25000, "the last total, not the sum of both"
    assert report["tokens"]["cached_input"] == 9000
    assert report["tokens"]["reasoning_output"] == 900
    assert report["accounting"]["cumulative_shapes_reduced_with"] == "max"


def test_an_unreadable_transcript_shape_is_refused_not_zeroed(tmp_path):
    from elmos_execution_intelligence.telemetry import parse_agent_transcript

    weird = json.dumps({"type": "assistant", "cost": {"tokens_we_do_not_know": 5}})
    with pytest.raises(ValueError, match="no usage block matched"):
        parse_agent_transcript(_log(tmp_path, "w.jsonl", weird))


def test_an_all_zero_usage_block_is_not_counted(tmp_path):
    from elmos_execution_intelligence.telemetry import parse_agent_transcript

    zeros = json.dumps({"message": {"usage": {"input_tokens": 0, "output_tokens": 0}}})
    with pytest.raises(ValueError, match="no usage block matched"):
        parse_agent_transcript(_log(tmp_path, "z.jsonl", zeros))


def test_transcript_rows_carry_both_dimensions_and_the_asserted_mapping(tmp_path):
    from elmos_execution_intelligence.telemetry import rows_from_transcripts

    rows, _ = rows_from_transcripts(
        [_log(tmp_path, "s.jsonl", CLAUDE_TRANSCRIPT)], MATRIX_MEDIUM)
    row = rows[0]
    assert row["actual_total_tokens"] == 108_500
    assert row["estimated_total_tokens"] > 0
    assert row["measurement"] == "per_session_observed"
    assert any("asserted by the caller" in c for c in row["caveats"])
    assert any("upper bound on execution time" in c for c in row["caveats"])


def test_transcripts_are_the_only_source_that_can_calibrate_tokens(tmp_path):
    from elmos_execution_intelligence.telemetry import rows_from_transcripts

    rows, parsed = rows_from_transcripts(
        [_log(tmp_path, "s.jsonl", CLAUDE_TRANSCRIPT),
         _log(tmp_path, "c.jsonl", CODEX_TRANSCRIPT)], MATRIX_MEDIUM)
    result = calibrate(rows)
    assert result["token_samples"] == 2
    assert result["global"]["token_multiplier"] is not None

    from elmos_execution_intelligence.telemetry import transcript_ingest_report
    report = transcript_ingest_report(rows, parsed)
    assert report["token_data_available"] is True
    assert report["measurement"] == "per_session_observed"
