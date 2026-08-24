"""Ingest *real* execution telemetry from artefacts a run actually left behind.

The simulated executor produces synthetic rows: useful for proving the calibrate
loop closes, useless as evidence about how long real work takes. This module
reads what real runs actually recorded.

Today the only real timing this repository persists is the pytest summary line of
a matrix run (``N failed, M passed in T s``). That is a genuine measurement, but
it is an **aggregate**: it gives a mean per node, not a per-node duration. Every
row this module emits therefore carries ``measurement`` and ``caveats``, and rows
derived from an aggregate are labelled as such rather than being passed off as
per-task observations.

Token counts are absent from those logs, so the rows are runtime-only. The
calibrator handles that by reporting the token multiplier as unavailable instead
of inventing one.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: pytest's final summary line, e.g.
#: "1 failed, 83 passed in 4759.49s (1:19:19)" or "38 passed in 8066.46s"
SUMMARY = re.compile(
    r"^(?P<body>(?:\d+\s+\w+(?:,\s*)?)+)\s+in\s+(?P<seconds>[\d.]+)s",
    re.MULTILINE,
)
COUNT = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|deselected|xfailed|xpassed)")


def parse_pytest_log(path: str | Path) -> dict[str, Any]:
    """Extract the executed-node counts and wall-clock from a pytest log.

    Raises ValueError when the log has no summary line -- a collect-only log or a
    run killed before it finished has no measurement to offer, and guessing one
    would be worse than saying so.
    """
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="replace")
    matches = list(SUMMARY.finditer(text))
    if not matches:
        raise ValueError(
            f"{source}: no pytest summary line found; this log records no completed measurement"
        )
    last = matches[-1]
    counts = {name: int(value) for value, name in COUNT.findall(last.group("body"))}
    executed = (
        counts.get("passed", 0)
        + counts.get("failed", 0)
        + counts.get("error", 0)
        + counts.get("errors", 0)
    )
    if executed <= 0:
        raise ValueError(f"{source}: summary line reports no executed nodes")
    total_seconds = float(last.group("seconds"))
    return {
        "log": source.name,
        "total_seconds": total_seconds,
        "executed_nodes": executed,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0),
        "deselected": counts.get("deselected", 0),
        "skipped": counts.get("skipped", 0),
        "mean_seconds_per_node": round(total_seconds / executed, 4),
        "aborted_early": counts.get("deselected", 0) > 0 or "stopping after" in text,
    }


def rows_from_pytest_logs(
    logs: list[str | Path],
    task: dict[str, Any],
    unit_count: int,
    task_type: str | None = None,
    complexity: str | None = None,
    model: str = "not-a-model-run",
    caveats: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Turn pytest logs into calibrate rows for one DAG task.

    ``unit_count`` is how many units (routes, nodes) the task's estimate covers.
    The comparison is made per unit, because a task estimate covering 156 routes
    and a log covering 84 nodes are not otherwise comparable -- and pretending
    they are is exactly the kind of silent unit error this package refuses to make.
    """
    if unit_count <= 0:
        raise ValueError("unit_count must be > 0; without it the per-unit comparison is meaningless")
    estimated_task_minutes = float(task["system"]["most_likely_minutes"])
    estimated_per_unit = estimated_task_minutes / unit_count

    rows: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    for log in logs:
        summary = parse_pytest_log(log)
        parsed.append(summary)
        actual_per_unit = summary["total_seconds"] / summary["executed_nodes"] / 60.0
        rows.append({
            "task_id": task["id"],
            "task_type": task_type or task.get("category", "unknown"),
            "complexity": complexity or task.get("complexity", "unknown"),
            "model": model,
            "estimated_minutes": round(estimated_per_unit, 6),
            "actual_minutes": round(actual_per_unit, 6),
            "measurement": "aggregate_mean_per_node",
            "source_log": summary["log"],
            "executed_nodes": summary["executed_nodes"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "total_seconds": summary["total_seconds"],
            "aborted_early": summary["aborted_early"],
            "caveats": list(caveats) + [
                "Derived from a pytest summary line: a mean over executed nodes, not a per-node measurement.",
                "No token counts exist in these logs, so this row calibrates runtime only.",
            ],
        })
    return rows, parsed


def ingest_report(rows: list[dict[str, Any]], parsed: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact": "telemetry-ingest",
        "source": "pytest-log",
        "rows": len(rows),
        "logs": parsed,
        "total_executed_nodes": sum(item["executed_nodes"] for item in parsed),
        "total_seconds": round(sum(item["total_seconds"] for item in parsed), 2),
        "measurement": "aggregate_mean_per_node",
        "token_data_available": False,
        "rule": (
            "These rows are real measurements of real runs, aggregated per node. They calibrate runtime "
            "only. Any token multiplier derived from them would be invented, so none is."
        ),
    }


# ---------------------------------------------------------------------------
# pytest --durations: per-node timings
# ---------------------------------------------------------------------------

#: A line from pytest's duration report, e.g. "120.51s call     tests/x.py::test_y[java-python]"
DURATION_LINE = re.compile(
    r"^\s*(?P<seconds>[\d.]+)s\s+(?P<phase>call|setup|teardown)\s+(?P<nodeid>\S+)\s*$",
    re.MULTILINE,
)


#: pytest's own admission that it truncated the duration report, e.g.
#: "(768 durations < 0.005s hidden.  Use -vv to show these durations.)"
#:
#: This matters far more than it looks. ``--durations=0`` does NOT mean "every
#: node": pytest still hides entries below 0.005s. The hidden ones are the FAST
#: ones, so what survives is a slow-biased sample, and a calibration multiplier
#: computed from it is wrong in a consistent direction while looking entirely
#: reasonable. The complete incantation is ``--durations=0 --durations-min=0``.
DURATIONS_TRUNCATED = re.compile(
    r"\((?P<hidden>\d+)\s+durations?\s*<\s*(?P<threshold>[\d.]+)s\s+hidden",
)


class TruncatedDurations(ValueError):
    """Raised when a durations log is a slow-biased subset rather than the full set."""


def parse_pytest_durations(
    path: str | Path, allow_truncated: bool = False
) -> dict[str, Any]:
    """Read per-node timings from a log produced with ``--durations=0 --durations-min=0``.

    This is the measurement the aggregate parser cannot give you: a real duration
    per node instead of a mean over all of them. setup, call and teardown are
    summed per node, because from a scheduler's point of view they are all time
    the node occupied a worker.

    Raises ValueError when the log has no duration report -- a run without
    ``--durations`` has nothing per-node to offer, and estimating one from the
    total would be exactly the aggregate this function exists to replace.
    """
    source = Path(path)
    text = source.read_text(encoding="utf-8", errors="replace")
    matches = list(DURATION_LINE.finditer(text))
    if not matches:
        raise ValueError(
            f"{source}: no per-node duration lines found; re-run pytest with "
            "--durations=0 --durations-min=0"
        )

    truncated = DURATIONS_TRUNCATED.search(text)
    if truncated and not allow_truncated:
        raise TruncatedDurations(
            f"{source}: pytest hid {truncated.group('hidden')} durations below "
            f"{truncated.group('threshold')}s, so this log holds only the slowest "
            f"{len(matches)} phase entries. Calibrating on it would inflate the mean in a "
            "consistent direction while looking reasonable. Re-run with "
            "--durations=0 --durations-min=0, or pass allow_truncated=True if you "
            "genuinely want the slow tail only."
        )

    per_node: dict[str, dict[str, float]] = {}
    for match in matches:
        node = per_node.setdefault(match.group("nodeid"), {})
        phase = match.group("phase")
        # pytest prints at most one line per (node, phase); a repeat means the log
        # concatenates two runs, and taking the larger is the conservative read.
        seconds = float(match.group("seconds"))
        node[phase] = max(node.get(phase, 0.0), seconds)

    nodes: list[dict[str, Any]] = [
        {
            "nodeid": nodeid,
            "seconds": round(sum(phases.values()), 4),
            "phases": {phase: round(value, 4) for phase, value in sorted(phases.items())},
        }
        for nodeid, phases in sorted(per_node.items())
    ]
    total = sum(float(node["seconds"]) for node in nodes)
    return {
        "log": source.name,
        "nodes": nodes,
        "node_count": len(nodes),
        "truncated": bool(truncated),
        "hidden_durations": int(truncated.group("hidden")) if truncated else 0,
        "total_seconds": round(total, 4),
        "mean_seconds_per_node": round(total / len(nodes), 4),
        "phases_summed": True,
    }


def rows_from_pytest_durations(
    logs: list[str | Path],
    task: dict[str, Any],
    unit_count: int,
    task_type: str | None = None,
    complexity: str | None = None,
    caveats: tuple[str, ...] = (),
    allow_truncated: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One calibrate row per measured node, instead of one per log.

    The estimate side is still per unit (the task estimate divided by the number
    of units it covers), because that is the only comparison that has matching
    units on both sides.
    """
    if unit_count <= 0:
        raise ValueError("unit_count must be > 0; without it the per-unit comparison is meaningless")
    estimated_per_unit = float(task["system"]["most_likely_minutes"]) / unit_count

    rows: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    for log in logs:
        report = parse_pytest_durations(log, allow_truncated=allow_truncated)
        parsed.append({
            "log": report["log"],
            "total_seconds": report["total_seconds"],
            "executed_nodes": report["node_count"],
            "passed": report["node_count"],
            "failed": 0,
            "mean_seconds_per_node": report["mean_seconds_per_node"],
            "aborted_early": False,
        })
        for node in report["nodes"]:
            rows.append({
                "task_id": task["id"],
                "task_type": task_type or task.get("category", "unknown"),
                "complexity": complexity or task.get("complexity", "unknown"),
                "model": "not-a-model-run",
                "estimated_minutes": round(estimated_per_unit, 6),
                "actual_minutes": round(node["seconds"] / 60.0, 6),
                "measurement": "per_node_observed",
                "source_log": report["log"],
                "nodeid": node["nodeid"],
                "phases": node["phases"],
                "caveats": list(caveats) + [
                    "Measured per node from pytest --durations; setup, call and teardown are summed.",
                    "No token counts exist in these logs, so this row calibrates runtime only.",
                ],
            })
    return rows, parsed


# ---------------------------------------------------------------------------
# Agent session transcripts: the only source of real token usage
# ---------------------------------------------------------------------------

#: Where a usage block hides, by CLI. The key names differ between tools and
#: between versions of the same tool, so every shape that is understood is listed
#: explicitly. A transcript whose shape is not here produces "no usage found"
#: rather than a silently empty result.
USAGE_PATHS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("claude-code", ("message", "usage")),
    ("claude-code-flat", ("usage",)),
    ("codex-total", ("info", "total_token_usage")),
    ("codex-last", ("info", "last_token_usage")),
    ("codex-payload", ("payload", "info", "total_token_usage")),
)

#: Normalises the many spellings of the five disjoint categories.
USAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "input": ("input_tokens", "prompt_tokens", "uncached_input_tokens"),
    "cached_input": ("cache_read_input_tokens", "cached_input_tokens", "cache_read_tokens"),
    "cache_write": ("cache_creation_input_tokens", "cache_write_tokens", "cache_creation_tokens"),
    "output": ("output_tokens", "completion_tokens"),
    "reasoning_output": ("reasoning_output_tokens", "reasoning_tokens"),
}

#: Reasoning tokens are not always a sibling field. Both major CLIs report them
#: inside a *details* sub-object of the output count, and every provider that
#: does this counts them as PART OF the output total rather than beside it.
#:
#: Each entry is (category, container_key, leaf_key, subtract_from). When the
#: nested value is found, it is subtracted from ``subtract_from`` so the five
#: categories stay disjoint -- which is the whole reason ``total`` is allowed to
#: be their sum. Reading both without subtracting would inflate output by the
#: reasoning count on every single turn.
USAGE_NESTED_ALIASES: tuple[tuple[str, str, str, str], ...] = (
    ("reasoning_output", "output_tokens_details", "thinking_tokens", "output"),
    ("reasoning_output", "output_tokens_details", "reasoning_tokens", "output"),
    ("reasoning_output", "completion_tokens_details", "reasoning_tokens", "output"),
)


class InclusiveReasoningViolation(ValueError):
    """Raised when a transcript falsifies the reasoning-is-inside-output assumption.

    The subtraction above rests on an assumption about the provider's accounting.
    An assumption that cannot fail is not an assumption, it is a belief, so the
    parser checks it on every record: a turn reporting more reasoning tokens than
    output tokens is impossible under inclusion and stops the ingest instead of
    silently clamping to zero and reporting a plausible number.
    """


def _dig(record: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any] | None:
    node: Any = record
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def _nested_int(block: dict[str, Any], container: str, leaf: str) -> int | None:
    node = block.get(container)
    if not isinstance(node, dict):
        return None
    value = node.get(leaf)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    return None


def _normalise_usage(block: dict[str, Any]) -> dict[str, int] | None:
    found: dict[str, int] = {}
    for field, aliases in USAGE_ALIASES.items():
        for alias in aliases:
            value = block.get(alias)
            if isinstance(value, int | float) and not isinstance(value, bool):
                found[field] = int(value)
                break

    # Nested reasoning counts, corrected for inclusion. Only applied when the
    # category was not already present as a flat sibling field -- a provider that
    # reports it flat is telling us it is a separate line item.
    for field, container, leaf, parent in USAGE_NESTED_ALIASES:
        if field in found:
            continue
        nested = _nested_int(block, container, leaf)
        if nested is None:
            continue
        parent_value = found.get(parent)
        if parent_value is not None and nested > parent_value:
            raise InclusiveReasoningViolation(
                f"{container}.{leaf} = {nested} exceeds {parent} = {parent_value}. "
                "This parser assumes reasoning tokens are counted inside the output total "
                "and subtracts them to keep the five categories disjoint; that assumption "
                "does not hold for this transcript, so the mapping must be revisited "
                "rather than the number clamped."
            )
        found[field] = nested
        if parent_value is not None:
            found[parent] = parent_value - nested

    # A block with no output and no input is not a usage block; treating it as
    # one would add a zero row that drags every average toward zero.
    if not found or all(value == 0 for value in found.values()):
        return None
    return {field: found.get(field, 0) for field in USAGE_ALIASES}


def parse_agent_transcript(path: str | Path) -> dict[str, Any]:
    """Sum real token usage out of a Claude Code or Codex session transcript.

    Codex writes a running *total* on every token_count event, so summing those
    would multiply the real usage by the number of events. Cumulative shapes are
    therefore reduced with max(), incremental shapes with sum(); which rule was
    applied is reported in ``accounting``.
    """
    source = Path(path)
    cumulative_shapes = {"codex-total", "codex-payload"}

    summed: dict[str, int] = {field: 0 for field in USAGE_ALIASES}
    peak: dict[str, int] = {field: 0 for field in USAGE_ALIASES}
    shapes: dict[str, int] = {}
    models: dict[str, int] = {}
    records = 0
    usage_records = 0
    timestamps: list[str] = []
    per_turn: list[dict[str, int]] = []

    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        records += 1
        for stamp_key in ("timestamp", "ts", "time"):
            value = record.get(stamp_key)
            if isinstance(value, str):
                timestamps.append(value)
                break

        for shape, path_keys in USAGE_PATHS:
            block = _dig(record, path_keys)
            if block is None:
                continue
            usage = _normalise_usage(block)
            if usage is None:
                continue
            usage_records += 1
            shapes[shape] = shapes.get(shape, 0) + 1
            if shape in cumulative_shapes:
                for field, value in usage.items():
                    peak[field] = max(peak[field], value)
            else:
                for field, value in usage.items():
                    summed[field] += value
                # Per-turn rows only make sense for incremental shapes: a
                # cumulative shape's "turn" is a running total, not a turn.
                per_turn.append(dict(usage))
            model = _model_of(record)
            if model:
                models[model] = models.get(model, 0) + 1
            break

    if usage_records == 0:
        raise ValueError(
            f"{source}: no usage block matched a known transcript shape "
            f"({', '.join(name for name, _ in USAGE_PATHS)}); "
            "this file records no token usage this parser can read"
        )

    totals = {field: summed[field] + peak[field] for field in USAGE_ALIASES}
    totals["total"] = sum(totals[field] for field in USAGE_ALIASES)
    return {
        "transcript": source.name,
        "records": records,
        "usage_records": usage_records,
        "shapes": dict(sorted(shapes.items())),
        "accounting": {
            "cumulative_shapes_reduced_with": "max",
            "incremental_shapes_reduced_with": "sum",
            "why": (
                "Codex reports a running total on every event; summing those would multiply real "
                "usage by the event count."
            ),
        },
        "models": dict(sorted(models.items(), key=lambda item: -item[1])),
        "tokens": totals,
        # Ordered, one entry per incremental usage block. The aggregate above
        # hides that the mix is not constant across a session; this does not.
        "turns": per_turn,
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "elapsed_minutes": _elapsed_minutes(timestamps),
    }


def _model_of(record: dict[str, Any]) -> str | None:
    for path in (("message", "model"), ("model",), ("info", "model"), ("payload", "model")):
        node: Any = record
        for key in path:
            if not isinstance(node, dict) or key not in node:
                node = None
                break
            node = node[key]
        if isinstance(node, str) and node:
            return node
    return None


def _elapsed_minutes(timestamps: list[str]) -> float | None:
    if len(timestamps) < 2:
        return None
    from datetime import datetime

    parsed = []
    for stamp in (min(timestamps), max(timestamps)):
        try:
            parsed.append(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
        except ValueError:
            return None
    delta = (parsed[1] - parsed[0]).total_seconds() / 60.0
    return round(delta, 4) if delta > 0 else None


def rows_from_transcripts(
    transcripts: list[str | Path],
    task: dict[str, Any],
    task_type: str | None = None,
    complexity: str | None = None,
    caveats: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One calibrate row per session, carrying **both** token and runtime pairs.

    This is the only source in this package that can calibrate the token
    dimension, because it is the only one where real token counts exist.

    The mapping from a session to a task is asserted by whoever runs the command;
    the parser cannot know it. That assertion is recorded on every row so a later
    reader can challenge it.
    """
    profile = task["system"].get("token_profile", {})
    estimated_tokens = sum(
        float(profile.get(field, 0.0))
        for field in ("input", "cached_input", "cache_write", "output", "reasoning_output")
    )
    if estimated_tokens <= 0:
        raise ValueError(f"task {task['id']} has no positive token estimate to compare against")
    estimated_minutes = float(task["system"].get("most_likely_minutes", 0.0))

    rows: list[dict[str, Any]] = []
    parsed: list[dict[str, Any]] = []
    for transcript in transcripts:
        report = parse_agent_transcript(transcript)
        parsed.append(report)
        row: dict[str, Any] = {
            "task_id": task["id"],
            "task_type": task_type or task.get("category", "unknown"),
            "complexity": complexity or task.get("complexity", "unknown"),
            "model": next(iter(report["models"]), "unknown"),
            "estimated_total_tokens": estimated_tokens,
            "actual_total_tokens": float(report["tokens"]["total"]),
            "actual_tokens_by_category": {
                field: report["tokens"][field] for field in USAGE_ALIASES
            },
            "measurement": "per_session_observed",
            "source_transcript": report["transcript"],
            "usage_records": report["usage_records"],
            "caveats": list(caveats) + [
                "Token counts are real, read from the agent's own session record.",
                f"The session-to-task mapping is asserted by the caller: this session is claimed to be "
                f"work on task '{task['id']}'.",
            ],
        }
        if estimated_minutes > 0 and report["elapsed_minutes"]:
            row["estimated_minutes"] = estimated_minutes
            row["actual_minutes"] = report["elapsed_minutes"]
            row["caveats"].append(
                "Elapsed wall-clock spans the whole session including idle time between turns; "
                "it is an upper bound on execution time, not execution time."
            )
        rows.append(row)
    return rows, parsed


def transcript_ingest_report(rows: list[dict[str, Any]], parsed: list[dict[str, Any]]) -> dict[str, Any]:
    shapes: dict[str, int] = {}
    for report in parsed:
        for shape, count in report["shapes"].items():
            shapes[shape] = shapes.get(shape, 0) + count
    return {
        "schema_version": "1.0.0",
        "artifact": "telemetry-ingest",
        "source": "agent-transcript",
        "rows": len(rows),
        "logs": [
            {
                "log": report["transcript"],
                "total_seconds": round((report["elapsed_minutes"] or 0.0) * 60.0, 4) or 0.001,
                "executed_nodes": max(1, report["usage_records"]),
                "passed": max(1, report["usage_records"]),
                "failed": 0,
                "mean_seconds_per_node": max(
                    0.001, round((report["elapsed_minutes"] or 0.0) * 60.0 / max(1, report["usage_records"]), 4)),
                "aborted_early": False,
            }
            for report in parsed
        ],
        "total_executed_nodes": sum(max(1, report["usage_records"]) for report in parsed),
        "total_seconds": round(sum((report["elapsed_minutes"] or 0.0) * 60.0 for report in parsed), 2),
        "measurement": "per_session_observed",
        "token_data_available": True,
        "transcript_shapes": dict(sorted(shapes.items())),
        "total_tokens": sum(int(row["actual_total_tokens"]) for row in rows),
        "rule": (
            "Token counts here are real. The session-to-task mapping is an assertion by whoever ran the "
            "command, and is recorded on every row so it can be challenged."
        ),
    }
