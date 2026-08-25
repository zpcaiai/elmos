"""Turn executed telemetry into multipliers that correct the next forecast."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .io_utils import summarize

GROUP_FIELDS = ("task_type", "complexity", "model")
MIN_GROUP_SAMPLES = 5


def _positive(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _ratio(row: dict[str, Any], estimated_field: str, actual_field: str) -> float | None:
    estimated = row.get(estimated_field)
    actual = row.get(actual_field)
    if _positive(estimated) and _positive(actual):
        return float(actual) / float(estimated)  # type: ignore[arg-type]  # guarded by _positive
    return None


def calibrate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive runtime and token multipliers from executed telemetry.

    Runtime and token are calibrated independently. A row that carries a runtime
    pair but no token counts still calibrates runtime; the token multiplier is
    then reported as unavailable rather than invented. Real logs frequently have
    timings and no token accounting, and dropping those rows entirely would throw
    away the only real measurement on hand.
    """
    if not rows:
        raise ValueError("Calibration history is empty")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dropped: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if _ratio(row, "estimated_minutes", "actual_minutes") is None and \
                _ratio(row, "estimated_total_tokens", "actual_total_tokens") is None:
            dropped.append({
                "row": index,
                "reason": "neither a runtime nor a token estimate/actual pair is present and positive",
            })
            continue
        key = "|".join(str(row.get(field, "unknown")) for field in GROUP_FIELDS)
        grouped[key].append(row)

    valid = sum(len(items) for items in grouped.values())
    if not valid:
        raise ValueError("No calibration row carried a usable estimate/actual pair")

    groups: dict[str, Any] = {}
    all_time: list[float] = []
    all_tokens: list[float] = []
    for key, items in sorted(grouped.items()):
        time_ratios = [r for r in (_ratio(i, "estimated_minutes", "actual_minutes") for i in items) if r]
        token_ratios = [
            r for r in (_ratio(i, "estimated_total_tokens", "actual_total_tokens") for i in items) if r
        ]
        all_time.extend(time_ratios)
        all_tokens.extend(token_ratios)
        groups[key] = {
            "samples": len(items),
            "runtime_samples": len(time_ratios),
            "token_samples": len(token_ratios),
            "runtime_multiplier": summarize(time_ratios) if time_ratios else None,
            "token_multiplier": summarize(token_ratios) if token_ratios else None,
            "confidence": round(min(0.95, 0.35 + len(items) / 20.0), 4),
            "applicable": len(items) >= MIN_GROUP_SAMPLES,
        }

    unavailable = []
    if not all_time:
        unavailable.append("runtime: no row carried a positive estimated/actual minute pair")
    if not all_tokens:
        unavailable.append("token: no row carried a positive estimated/actual token pair")

    return {
        "schema_version": "1.0.0",
        "valid_samples": valid,
        "runtime_samples": len(all_time),
        "token_samples": len(all_tokens),
        "dropped_samples": len(dropped),
        "dropped_detail": dropped[:20],
        "global": {
            "runtime_multiplier": summarize(all_time) if all_time else None,
            "token_multiplier": summarize(all_tokens) if all_tokens else None,
            "confidence": round(min(0.95, 0.35 + valid / 50.0), 4),
        },
        "unavailable": unavailable,
        "groups": groups,
        "rule": (
            f"Use a group multiplier only when that group has at least {MIN_GROUP_SAMPLES} samples "
            "(applicable=true); otherwise fall back to the global multiplier and keep the wider interval."
        ),
    }


def estimator_profiles(calibration: dict[str, Any]) -> dict[str, Any]:
    """Turn a calibration into the multipliers an estimator should actually apply.

    A group multiplier is only offered when that group cleared MIN_GROUP_SAMPLES.
    Everything else falls back to the global multiplier, which keeps the wider
    interval instead of pretending a two-sample group is informative.
    """
    global_block = calibration["global"]

    def multiplier(block: dict[str, Any] | None) -> tuple[float, bool]:
        """A missing multiplier means 'leave the estimate alone', not 'multiply by 1 because we measured 1'."""
        if block is None:
            return 1.0, False
        return float(block["p50"]), True

    runtime_value, runtime_measured = multiplier(global_block["runtime_multiplier"])
    token_value, token_measured = multiplier(global_block["token_multiplier"])

    profiles: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact": "estimator-profiles",
        "derived_from_samples": calibration["valid_samples"],
        "default": {
            "runtime_multiplier": runtime_value,
            "runtime_measured": runtime_measured,
            "token_multiplier": token_value,
            "token_measured": token_measured,
            "confidence": global_block["confidence"],
            "basis": "global",
        },
        "by_group": {},
        "unavailable": calibration.get("unavailable", []),
        "rule": calibration["rule"],
    }
    for key, group in calibration["groups"].items():
        if not group["applicable"]:
            continue
        group_runtime, group_runtime_measured = multiplier(group["runtime_multiplier"])
        group_token, group_token_measured = multiplier(group["token_multiplier"])
        profiles["by_group"][key] = {
            "runtime_multiplier": group_runtime,
            "runtime_measured": group_runtime_measured,
            "token_multiplier": group_token,
            "token_measured": group_token_measured,
            "confidence": group["confidence"],
            "samples": group["samples"],
            "basis": "group",
        }
    return profiles


def _profile_for(task: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    """Match a DAG task to a calibration group.

    Telemetry rows group on ``task_type``; a DAG task calls the same thing
    ``category``. A task that does not declare ``model`` cannot match a
    model-specific group and falls back to the global multiplier -- which is the
    safe direction, since the global interval is the wider one.
    """
    key = "|".join(str(task.get(field, "unknown")) for field in ("category", "complexity", "model"))
    profile: dict[str, Any] = profiles["by_group"].get(key, profiles["default"])
    return profile


def apply_calibration(
    task_document: dict[str, Any], profiles: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Rewrite a task DAG's durations and token profiles with calibrated multipliers.

    The DAG is returned as a new document; the input is not mutated. Every task
    records which multiplier was applied and on what basis, so a later reader can
    tell a calibrated estimate from a raw one.
    """
    import copy

    updated = copy.deepcopy(task_document)
    changelog: list[dict[str, Any]] = []
    for task in updated.get("tasks", []):
        profile = _profile_for(task, profiles)
        runtime_multiplier = float(profile["runtime_multiplier"])
        token_multiplier = float(profile["token_multiplier"])
        # An unmeasured dimension is left untouched. Multiplying by a 1.0 that
        # nobody measured would look identical to a measurement that came out at
        # 1.0, and the difference matters when someone later asks what the number
        # is based on.
        runtime_measured = bool(profile.get("runtime_measured", True))
        token_measured = bool(profile.get("token_measured", True))

        system = task.get("system", {})
        if runtime_measured:
            for key in ("optimistic_minutes", "most_likely_minutes", "pessimistic_minutes"):
                if key in system:
                    system[key] = round(float(system[key]) * runtime_multiplier, 3)
        token_profile = system.get("token_profile", {})
        if token_measured:
            for field in ("input", "cached_input", "cache_write", "output", "reasoning_output"):
                if field in token_profile:
                    token_profile[field] = round(float(token_profile[field]) * token_multiplier)
        system["calibration"] = {
            "runtime_multiplier": runtime_multiplier if runtime_measured else None,
            "token_multiplier": token_multiplier if token_measured else None,
            "runtime_measured": runtime_measured,
            "token_measured": token_measured,
            "basis": profile["basis"],
            "confidence": profile["confidence"],
        }
        changelog.append({
            "task_id": task.get("id"),
            "runtime_multiplier": runtime_multiplier if runtime_measured else None,
            "token_multiplier": token_multiplier if token_measured else None,
            "runtime_measured": runtime_measured,
            "token_measured": token_measured,
            "basis": profile["basis"],
        })
    updated["calibrated"] = True
    updated["calibration_basis_samples"] = profiles["derived_from_samples"]
    return updated, changelog


def accuracy_report(calibration: dict[str, Any], profiles: dict[str, Any]) -> str:
    """Render forecast-accuracy-report.md from a calibration result."""
    from .io_utils import fmt, markdown_table

    global_block = calibration["global"]

    def cell(block: dict[str, Any] | None, key: str) -> str:
        return fmt(block[key], 3) if block else "无数据"

    # The group key is "a|b|c"; a raw pipe would tear the markdown table apart.
    group_rows = [
        [key.replace("|", " / "), group["samples"],
         cell(group["runtime_multiplier"], "p50"), cell(group["token_multiplier"], "p50"),
         fmt(group["confidence"], 3), "是" if group["applicable"] else "否"]
        for key, group in calibration["groups"].items()
    ]

    def direction(block: dict[str, Any] | None) -> str:
        if block is None:
            return "**无数据**（不推断倍率）"
        bias = block["p50"] - 1.0
        if bias > 0.05:
            return f"**低估 {fmt(bias * 100, 1)}%**"
        if bias < -0.05:
            return f"**高估 {fmt(-bias * 100, 1)}%**"
        return "基本无偏"

    body = [
        "# FORECAST_ACCURACY_REPORT",
        "",
        f"- 有效样本：{calibration['valid_samples']}"
        f"（运行时 {calibration.get('runtime_samples', 0)} · Token {calibration.get('token_samples', 0)}）"
        f"，丢弃：{calibration['dropped_samples']}",
        f"- 全局置信度：{global_block['confidence']}",
        "",
        "## 全局偏差",
        "",
        markdown_table(
            ["维度", "P50 倍率", "P80", "P90", "结论"],
            [
                ["运行时", cell(global_block["runtime_multiplier"], "p50"),
                 cell(global_block["runtime_multiplier"], "p80"),
                 cell(global_block["runtime_multiplier"], "p90"),
                 direction(global_block["runtime_multiplier"])],
                ["Token", cell(global_block["token_multiplier"], "p50"),
                 cell(global_block["token_multiplier"], "p80"),
                 cell(global_block["token_multiplier"], "p90"),
                 direction(global_block["token_multiplier"])],
            ],
        ),
        "",
        "> 倍率的定义是 `实际 / 预测`。大于 1 表示预测偏低。",
        *([""] + [f"> 无数据的维度：{item}" for item in calibration.get("unavailable", [])]
          if calibration.get("unavailable") else []),
        "",
        "## 分组倍率",
        "",
        markdown_table(
            ["分组 (task_type / complexity / model)", "样本", "运行时 P50", "Token P50", "置信度", "可用"],
            group_rows),
        "",
        f"> {calibration['rule']}",
        "",
        "## 将被应用的 estimator profiles",
        "",
        f"- 默认（全局）：运行时 ×{profiles['default']['runtime_multiplier']}"
        f"（{'实测' if profiles['default'].get('runtime_measured', True) else '无数据，不改写'}），"
        f"Token ×{profiles['default']['token_multiplier']}"
        f"（{'实测' if profiles['default'].get('token_measured', True) else '无数据，不改写'}）",
        f"- 可用分组数：{len(profiles['by_group'])}",
        "",
        "## 丢弃的样本",
        "",
        *([f"- 第 {row['row']} 行：{row['reason']}" for row in calibration.get("dropped_detail", [])]
          or ["- 无"]),
        "",
        "> 丢弃的行不会被补全或猜测。预测与实测缺任一侧的记录一律不参与倍率计算。",
    ]
    return "\n".join(body)
