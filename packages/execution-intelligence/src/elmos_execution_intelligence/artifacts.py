"""Split the combined forecast into the per-skill artifacts the Skills declare.

Skills 03-07 each declare their own output file. Emitting one combined blob and
telling downstream consumers to reach inside it makes every consumer depend on
this package's internal shape. Each split file is therefore self-contained:
schema version, project id, the口径 that applies to it, and its own payload.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .io_utils import write_json
from .simulation import SYSTEM_EXCLUSIONS


def _header(forecast: dict[str, Any], artifact: str) -> dict[str, Any]:
    project = forecast["project"]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": artifact,
        "project_id": project["project_id"],
        "mode": project["mode"],
        "definition_of_done": project["definition_of_done"],
        "confidence": float(project.get("confidence", 0.5)),
        "assumptions": list(project.get("assumptions", [])),
        "exclusions": list(project.get("exclusions", [])),
    }


def token_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    payload = _header(forecast, "token-forecast")
    payload.update({
        "runs": forecast["system_runtime"]["runs"],
        "seed": forecast["system_runtime"]["seed"],
        "totals": forecast["tokens"],
        "by_task": forecast["task_tokens"],
        "static_scan_totals": (forecast.get("static_scan") or {}).get("totals"),
        "accounting_rule": forecast["tokens"]["accounting_rule"],
    })
    return payload


def cost_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    payload = _header(forecast, "cost-forecast")
    costs = forecast["costs"]
    payload.update({
        "registry_version": costs["registry_version"],
        "base_currency": costs["base_currency"],
        "currencies": costs["currencies"],
        "models": costs["models"],
        "rankings_by_currency": costs["rankings_by_currency"],
        "cross_currency_comparison": None,
        "cross_currency_note": costs["cross_currency_note"],
        "warning": costs["warning"],
        "token_totals_used": forecast["tokens"]["total"],
    })
    return payload


def autonomous_runtime(forecast: dict[str, Any]) -> dict[str, Any]:
    payload = _header(forecast, "autonomous-runtime")
    runtime = dict(forecast["system_runtime"])
    payload.update(runtime)
    payload["scope"] = "machine-autonomous execution only"
    payload["excludes"] = list(SYSTEM_EXCLUSIONS)
    return payload


def human_effort(forecast: dict[str, Any]) -> dict[str, Any]:
    payload = _header(forecast, "human-effort")
    payload.update(forecast["human_effort"])
    payload["baseline_rule"] = (
        "The human baseline consumes the same task DAG as the system estimate and therefore "
        "the same Definition of Done."
    )
    return payload


def time_comparison(forecast: dict[str, Any]) -> dict[str, Any]:
    payload = _header(forecast, "time-comparison")
    comparison = forecast["comparison"]
    payload.update({
        "system_autonomous": {
            "wall_clock_hours": comparison["system_autonomous"]["wall_clock_hours"],
            "excludes": comparison["system_autonomous"]["excludes"],
        },
        "human_only": {
            "person_hours": comparison["human_only"]["person_hours"],
            "person_months": comparison["human_only"]["person_months"],
            "calendar_weeks": comparison["human_only"]["calendar_weeks"],
        },
        "human_assisted": comparison["human_assisted"],
        "comparison": comparison["comparison"],
        "same_definition_of_done_for_both_baselines": True,
    })
    return payload


SPLIT_ARTIFACTS = (
    ("token-forecast.json", token_forecast),
    ("cost-forecast.json", cost_forecast),
    ("autonomous-runtime.json", autonomous_runtime),
    ("human-effort.json", human_effort),
    ("time-comparison.json", time_comparison),
)


def write_split_artifacts(forecast: dict[str, Any], output: str | Path) -> list[str]:
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, builder in SPLIT_ARTIFACTS:
        write_json(out / name, builder(forecast))
        written.append(name)
    return written
