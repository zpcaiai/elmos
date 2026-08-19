from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

QUANTILE_LABELS = ("p50", "p80", "p90")


def load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object at {source}")
    return value


def write_json(path: str | Path, value: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def write_text(path: str | Path, value: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(value.rstrip() + "\n", encoding="utf-8")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        raw_text = source.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"File not found: {source}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(raw_text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {source}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object at {source}:{line_number}")
        rows.append(value)
    return rows


def quantile(values: Sequence[float], probability: float) -> float:
    """Linear-interpolation quantile (same definition as numpy's default)."""
    if not values:
        raise ValueError("Cannot calculate a quantile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"Probability must be within [0, 1]: {probability}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize(values: Sequence[float], worst_probability: float = 0.99, digits: int = 3) -> dict[str, float]:
    """Return the probabilistic envelope every elmos forecast must carry."""
    if not values:
        raise ValueError("Cannot summarize an empty sequence")
    if not 0.0 <= worst_probability <= 1.0:
        raise ValueError(f"worst_case_quantile must be within [0, 1]: {worst_probability}")
    result = {
        "mean": sum(values) / len(values),
        "p50": quantile(values, 0.50),
        "p80": quantile(values, 0.80),
        "p90": quantile(values, 0.90),
        "worst_case": quantile(values, worst_probability),
        "minimum": min(values),
        "maximum": max(values),
    }
    return {key: round(value, digits) for key, value in result.items()}


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join("" if item is None else str(item) for item in row) + " |")
    return "\n".join(lines)


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    return str(value)
