"""Skill 16 — production readiness certifier.

Evaluates release gates against evidence that is actually present. A gate with no
evidence is ``NOT_EXECUTED``; it never becomes ``PASS`` by omission, and the
overall decision is never ``release`` while any required gate is unproven.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import markdown_table

# Gate verdicts, not credentials (ruff's S105 heuristic sees the word "PASS").
PASS = "PASS"  # noqa: S105
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _gate(gate_id: str, title: str, required: bool, status: str, detail: str,
          evidence: str | None = None) -> dict[str, Any]:
    return {
        "id": gate_id, "title": title, "required": required, "status": status,
        "detail": detail, "evidence": evidence,
    }


#: What each piece of evidence is worth, as a confidence increment above the
#: floor. These are judgement, but they are *written down* judgement: the
#: alternative is a hand-typed confidence that anyone can raise by editing a
#: number, which is not evidence of anything.
CONFIDENCE_FLOOR = 0.30
CONFIDENCE_WEIGHTS = {
    "runtime_calibrated": (0.15, "运行时维度已用真实遥测校准"),
    "runtime_sample_depth": (0.10, "运行时样本 >= 20"),
    "token_calibrated": (0.20, "token 维度已用真实用量校准"),
    "token_sample_depth": (0.10, "token 样本 >= 20"),
    "no_blocking_gaps": (0.10, "无待人工决策的范围缺口"),
    "chaos_passing": (0.05, "Chaos 场景全部执行并通过"),
    "verified_rates": (0.05, "费用基于已核验费率"),
    "token_mix_verified": (0.05, "token 分类占比已对照实测用量"),
}


def supported_confidence(
    forecast: dict[str, Any],
    register: dict[str, Any] | None,
    calibration: dict[str, Any] | None,
    chaos: dict[str, Any] | None,
    token_mix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive the highest confidence the available evidence can carry.

    A declared confidence above this ceiling is not a judgement call, it is an
    unsupported claim -- and it is the one number in the whole forecast that a
    person can raise without doing any work, which is exactly why it needs a
    check that reads the evidence instead of the number.
    """
    earned: dict[str, float] = {}
    withheld: list[str] = []

    runtime_samples = int((calibration or {}).get("runtime_samples", 0))
    token_samples = int((calibration or {}).get("token_samples", 0))
    blocking = [
        gap for gap in (register or {}).get("gaps", []) if gap.get("needs_human_input")
    ] if register else None
    chaos_ok = bool(chaos and chaos.get("scenarios") and chaos.get("passed"))
    billable = [
        model for model in forecast.get("costs", {}).get("models", [])
        if not model.get("not_for_billing")
    ]

    checks = {
        "runtime_calibrated": runtime_samples > 0,
        "runtime_sample_depth": runtime_samples >= 20,
        "token_calibrated": token_samples > 0,
        "token_sample_depth": token_samples >= 20,
        "no_blocking_gaps": register is not None and not blocking,
        "chaos_passing": chaos_ok,
        "verified_rates": bool(billable),
        "token_mix_verified": bool(token_mix and token_mix.get("sample_sufficient")),
    }
    for key, passed in checks.items():
        weight, label = CONFIDENCE_WEIGHTS[key]
        if passed:
            earned[key] = weight
        else:
            withheld.append(f"缺 {label}（+{weight:.2f}）")

    ceiling = round(CONFIDENCE_FLOOR + sum(earned.values()), 4)
    return {
        "floor": CONFIDENCE_FLOOR,
        "ceiling": min(1.0, ceiling),
        "earned": earned,
        "withheld": withheld,
        "rule": (
            "The ceiling starts at the floor and rises only for evidence that exists. Editing the "
            "declared confidence cannot move it."
        ),
    }


def evaluate(evidence_dir: str | Path, min_calibration_samples: int = 20) -> dict[str, Any]:
    root = Path(evidence_dir)
    forecast = _load(root / "project-forecast.json")
    register = _load(root / "risk-and-gap-register.json")
    calibration = _load(root / "calibration.json")
    chaos = _load(root / "chaos-test-report.json")
    manifest = _load(root / "result-manifest.json")
    routing = _load(root / "model-routing-plan.json")
    token_mix = _load(root / "token-mix-comparison.json")

    gates: list[dict[str, Any]] = []

    if forecast is None:
        gates.append(_gate("forecast-present", "存在可读的项目预测", True, NOT_EXECUTED,
                           "project-forecast.json 不存在"))
    else:
        tokens = forecast.get("tokens", {})
        ok = tokens.get("category_sum_equals_total") is True
        gates.append(_gate("forecast-present", "存在可读的项目预测", True,
                           PASS if ok else FAIL,
                           "token 分类互斥且 total 为分类之和" if ok else "token 分类核算不成立",
                           "project-forecast.json"))
        confidence = float(forecast.get("project", {}).get("confidence", 0.0))
        supported = supported_confidence(forecast, register, calibration, chaos, token_mix)
        gates.append(_gate(
            "confidence-is-supported", "声明的置信度不高于证据支撑的上限", True,
            PASS if confidence <= supported["ceiling"] + 1e-9 else FAIL,
            f"声明 {confidence}，证据支撑上限 {supported['ceiling']}"
            + ("；" + "；".join(supported["withheld"]) if supported["withheld"] else ""),
            "project-forecast.json"))
        # A declared confidence is only as good as the evidence behind it. When the
        # gate fails, say what evidence would move it -- otherwise the only way to
        # pass is to edit the number, which is the failure mode this whole package
        # exists to prevent.
        missing_evidence: list[str] = []
        if calibration is None:
            missing_evidence.append("没有校准记录")
        else:
            if int(calibration.get("token_samples", 0)) == 0:
                missing_evidence.append("token 维度从未用真实用量校准")
            if int(calibration.get("runtime_samples", 0)) == 0:
                missing_evidence.append("运行时维度从未用真实耗时校准")
        detail = f"confidence={confidence}（门槛 0.6）"
        if confidence < 0.6 and missing_evidence:
            detail += "；要在证据上支撑更高的置信度，还缺：" + "、".join(missing_evidence)
        gates.append(_gate(
            "forecast-confidence", "预测置信度达到发布门槛", True,
            PASS if confidence >= 0.6 else FAIL,
            detail, "project-forecast.json"))
        excludes = forecast.get("system_runtime", {}).get("excludes", [])
        gates.append(_gate(
            "eta-scope", "系统 ETA 明文排除人工等待", True,
            PASS if excludes else FAIL,
            f"排除项 {len(excludes)} 条", "project-forecast.json"))
        billable = [m for m in forecast.get("costs", {}).get("models", []) if not m.get("not_for_billing")]
        gates.append(_gate(
            "verified-rates", "费用基于已核验费率", False,
            PASS if billable else FAIL,
            f"{len(billable)} 个可计费费率" if billable else "全部费率为示例值，不可用于预算",
            "project-forecast.json"))

    if register is None:
        gates.append(_gate("scope-gaps", "范围缺口已清零或已决策", True, NOT_EXECUTED,
                           "risk-and-gap-register.json 不存在"))
    else:
        blocking = [gap for gap in register.get("gaps", []) if gap.get("needs_human_input")]
        gates.append(_gate(
            "scope-gaps", "范围缺口已清零或已决策", True,
            PASS if not blocking else FAIL,
            f"{len(blocking)} 个缺口仍需人工决策：{', '.join(g['id'] for g in blocking[:5])}"
            if blocking else "无待决缺口",
            "risk-and-gap-register.json"))

    if calibration is None:
        gates.append(_gate("calibrated", "预测已用真实遥测校准", True, NOT_EXECUTED,
                           "calibration.json 不存在；未校准的预测不构成承诺"))
    else:
        samples = int(calibration.get("valid_samples", 0))
        gates.append(_gate(
            "calibrated", "预测已用真实遥测校准", True,
            PASS if samples >= min_calibration_samples else FAIL,
            f"{samples} 个有效样本（门槛 {min_calibration_samples}）", "calibration.json"))

    if chaos is None:
        gates.append(_gate("chaos-recovery", "Chaos 与恢复验证通过", True, NOT_EXECUTED,
                           "chaos-test-report.json 不存在"))
    else:
        failed = [s for s in chaos.get("scenarios", []) if not s.get("passed")]
        gates.append(_gate(
            "chaos-recovery", "Chaos 与恢复验证通过", True,
            PASS if chaos.get("scenarios") and not failed else FAIL,
            f"{len(chaos.get('scenarios', []))} 个场景，{len(failed)} 个失败", "chaos-test-report.json"))

    if manifest is None:
        gates.append(_gate("artifacts-sealed", "结果 Manifest 已封存", True, NOT_EXECUTED,
                           "result-manifest.json 不存在"))
    else:
        sealed = bool(manifest.get("sealed"))
        count = int(manifest.get("artifact_count", 0))
        gates.append(_gate(
            "artifacts-sealed", "结果 Manifest 已封存", True,
            PASS if sealed and count else FAIL,
            f"sealed={sealed}，artifact {count} 个"
            + (f"；{manifest.get('seal_refused_reason')}" if manifest.get("seal_refused_reason") else ""),
            "result-manifest.json"))

    # A forecast can predict the token COUNT well and still be wrong about the
    # bill by an order of magnitude, because the five categories are priced up to
    # fifty times apart. Nothing else in this gate list would notice.
    if token_mix is None:
        gates.append(_gate(
            "token-mix-verified", "token 分类占比已对照实测", True, NOT_EXECUTED,
            "token-mix-comparison.json 不存在；分类占比从未与真实用量对照过，"
            "而费用完全取决于这个占比"))
    else:
        sessions = int((token_mix.get("observed") or {}).get("sessions", 0))
        # Prefer the depth curve over the headline range: the headline is the
        # full-session factor, which reads as a flat multiplier and is not one.
        depths = token_mix.get("cost_by_session_depth") or []
        factor = token_mix.get("overstatement_factor_range")
        if depths and depths[0].get("overstatement_factor") and depths[-1].get("overstatement_factor"):
            spread = (
                f"，当前假设使费用偏离 {depths[0]['overstatement_factor']:.2f} 倍"
                f"（{depths[0]['turns']} 轮任务）到 {depths[-1]['overstatement_factor']:.2f} 倍"
                f"（{depths[-1]['turns']} 轮），随任务长度变化"
            )
        elif factor:
            spread = f"，当前假设使费用偏离最多 {factor[1]:.2f} 倍（整场会话口径）"
        else:
            spread = ""
        gates.append(_gate(
            "token-mix-verified", "token 分类占比已对照实测", True,
            PASS if token_mix.get("sample_sufficient") else FAIL,
            f"{sessions} 个会话（门槛 {token_mix.get('minimum_sessions', 20)}）{spread}",
            "token-mix-comparison.json"))

    if routing is not None:
        unroutable = routing.get("unroutable_tasks", [])
        gates.append(_gate(
            "routing-complete", "每个任务都有可用模型", False,
            PASS if not unroutable else FAIL,
            f"{len(unroutable)} 个任务无可用模型" if unroutable else "全部任务可路由",
            "model-routing-plan.json"))

    required = [gate for gate in gates if gate["required"]]
    failed_required = [gate for gate in required if gate["status"] == FAIL]
    unproven_required = [gate for gate in required if gate["status"] == NOT_EXECUTED]

    if failed_required:
        decision = "block"
    elif unproven_required:
        decision = "not_certified"
    else:
        decision = "release"

    return {
        "schema_version": "1.0.0",
        "artifact": "production-readiness",
        "evidence_dir": str(root),
        "decision": decision,
        "supported_confidence": (
            supported_confidence(forecast, register, calibration, chaos, token_mix)
            if forecast else None
        ),
        "gates": gates,
        "counts": {
            "pass": sum(1 for g in gates if g["status"] == PASS),
            "fail": sum(1 for g in gates if g["status"] == FAIL),
            "not_executed": sum(1 for g in gates if g["status"] == NOT_EXECUTED),
        },
        "rule": (
            "A gate with no evidence is NOT_EXECUTED, never PASS. 'release' requires every required gate "
            "to have executed and passed; anything else is 'not_certified' or 'block'."
        ),
    }


def build_evidence_manifest(report: dict[str, Any], evidence_dir: str | Path) -> dict[str, Any]:
    import hashlib

    root = Path(evidence_dir)
    files = []
    for gate in report["gates"]:
        name = gate.get("evidence")
        if not name:
            continue
        path = root / name
        if not path.exists():
            continue
        content = path.read_bytes()
        entry = {
            "path": name,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "supports_gate": gate["id"],
        }
        if entry not in files:
            files.append(entry)
    return {
        "schema_version": "1.0.0",
        "artifact": "evidence-manifest",
        "evidence_dir": str(root),
        "decision": report["decision"],
        "files": files,
        "missing_evidence": [
            gate["id"] for gate in report["gates"] if gate["status"] == "NOT_EXECUTED"
        ],
    }


def render_report(report: dict[str, Any]) -> str:
    symbol = {PASS: "✅ PASS", FAIL: "❌ FAIL", NOT_EXECUTED: "⛔ NOT_EXECUTED"}
    rows = [
        [gate["id"], gate["title"], "必需" if gate["required"] else "可选",
         symbol[gate["status"]], gate["detail"], gate["evidence"] or "—"]
        for gate in report["gates"]
    ]
    decision_text = {
        "release": "**release** — 所有必需门禁均已执行并通过",
        "not_certified": "**NOT_CERTIFIED** — 有必需门禁从未执行；缺证据不等于通过",
        "block": "**block** — 有必需门禁执行后失败",
    }[report["decision"]]
    return "\n".join([
        "# PRODUCTION_READINESS_REPORT",
        "",
        f"- 证据目录：`{report['evidence_dir']}`",
        f"- 结论：{decision_text}",
        f"- 通过 {report['counts']['pass']} · 失败 {report['counts']['fail']} · "
        f"未执行 {report['counts']['not_executed']}",
        "",
        markdown_table(["门禁", "内容", "必需性", "状态", "说明", "证据"], rows),
        "",
        f"> {report['rule']}",
    ])
