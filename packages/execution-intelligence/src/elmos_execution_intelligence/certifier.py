"""Skill 16 — production readiness certifier.

Evaluates release gates against evidence that is actually present. A gate with no
evidence is ``NOT_EXECUTED``; it never becomes ``PASS`` by omission, and the
overall decision is never ``release`` while any required gate is unproven.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from .external_trust import (
    ExternalTrustError,
    ExternalTrustOptions,
    VerifiedExternalTrust,
    load_external_trust,
)
from .io_utils import markdown_table
from .jsonschema_lite import Validator
from .provenance import (
    ProvenanceError,
    capture_evidence_snapshot,
    load_strict_json_bytes,
    verify_evidence_provenance,
)
from .resource_paths import SCHEMA_DIR

# Gate verdicts, not credentials (ruff's S105 heuristic sees the word "PASS").
PASS = "PASS"  # noqa: S105
FAIL = "FAIL"
NOT_EXECUTED = "NOT_EXECUTED"

MIN_CALIBRATION_SAMPLES = 20
EVIDENCE_INPUT_FILES = (
    "project-forecast.json",
    "risk-and-gap-register.json",
    "calibration.json",
    "chaos-test-report.json",
    "result-manifest.json",
    "model-routing-plan.json",
    "token-mix-comparison.json",
)
EVIDENCE_ARTIFACT_SCHEMAS = {
    "project-forecast.json": "project-forecast.schema.json",
    "risk-and-gap-register.json": "risk-and-gap-register.schema.json",
    "calibration.json": "calibration.schema.json",
    "chaos-test-report.json": "chaos-test-report.schema.json",
    "result-manifest.json": "result-manifest.schema.json",
    "model-routing-plan.json": "model-routing-plan.schema.json",
    "token-mix-comparison.json": "token-mix-comparison.schema.json",
    "evidence-provenance.json": "evidence-provenance.schema.json",
}
DEFAULT_SCHEMA_DIR = SCHEMA_DIR


def _validate_snapshot_inputs(
    snapshot: dict[str, bytes],
    snapshot_errors: list[str],
    schema_dir: str | Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Strict-parse and formally validate the exact bytes used by every gate.

    Parsed objects remain available for bounded diagnostic gates even when their
    schema is invalid, but the required ``evidence-schema-valid`` gate makes that
    state unreleasable. This preserves useful failure detail without ever
    treating a fragment or malformed artifact as certification evidence.
    """
    validator = Validator(schema_dir)
    parsed: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    errors = list(snapshot_errors)

    for name, schema_name in EVIDENCE_ARTIFACT_SCHEMAS.items():
        content = snapshot.get(name)
        if content is None:
            continue
        file_errors: list[str] = []
        try:
            value = load_strict_json_bytes(content, name)
            parsed[name] = value
        except (ProvenanceError, RecursionError) as exc:
            file_errors.append(str(exc))
        else:
            try:
                file_errors.extend(validator.validate(value, schema_name))
            except (OSError, TypeError, ValueError, RecursionError) as exc:
                file_errors.append(f"cannot enforce {schema_name}: {exc}")

        status = "INVALID" if file_errors else "VALID"
        records.append({
            "path": name,
            "schema": schema_name,
            "status": status,
            "errors": file_errors,
        })
        errors.extend(f"{name}: {error}" for error in file_errors)

    if errors:
        status = "INVALID"
    elif records:
        status = "VALID"
    else:
        status = "NOT_EXECUTED"
    return parsed, {"status": status, "errors": errors, "files": records}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _integer(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


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

    runtime_samples = _integer((calibration or {}).get("runtime_samples"))
    token_samples = _integer((calibration or {}).get("token_samples"))
    blocking = [
        gap for gap in _records((register or {}).get("gaps")) if gap.get("needs_human_input")
    ] if register else None
    chaos_ok = bool(chaos and _records(chaos.get("scenarios")) and chaos.get("passed"))
    models = _records(_mapping(forecast.get("costs")).get("models"))
    billable = [
        model for model in models if not model.get("not_for_billing")
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


def evaluate(
    evidence_dir: str | Path,
    min_calibration_samples: int = MIN_CALIBRATION_SAMPLES,
    trust_store: str | Path | None = None,
    trust_store_sha256: str | None = None,
    now: datetime | None = None,
    external_trust_options: ExternalTrustOptions | None = None,
) -> dict[str, Any]:
    root = Path(evidence_dir)
    # This threshold is a policy floor, not a convenience knob. A caller can
    # demand more samples, but can never turn a thin sample into a release by
    # passing a smaller integer on the command line.
    effective_min_samples = max(MIN_CALIBRATION_SAMPLES, int(min_calibration_samples))
    snapshot, snapshot_errors = capture_evidence_snapshot(
        root,
        (*EVIDENCE_INPUT_FILES, "evidence-provenance.json"),
    )
    parsed, evidence_schema = _validate_snapshot_inputs(
        snapshot,
        snapshot_errors,
        DEFAULT_SCHEMA_DIR,
    )
    forecast = parsed.get("project-forecast.json")
    register = parsed.get("risk-and-gap-register.json")
    calibration = parsed.get("calibration.json")
    chaos = parsed.get("chaos-test-report.json")
    manifest = parsed.get("result-manifest.json")
    routing = parsed.get("model-routing-plan.json")
    token_mix = parsed.get("token-mix-comparison.json")

    gates: list[dict[str, Any]] = []
    schema_status = {
        "VALID": PASS,
        "INVALID": FAIL,
        "NOT_EXECUTED": NOT_EXECUTED,
    }[evidence_schema["status"]]
    if schema_status == PASS:
        schema_detail = f"{len(evidence_schema['files'])} 个 read-once artifact 均通过正式 Schema"
    elif schema_status == FAIL:
        schema_detail = "；".join(evidence_schema["errors"])
    else:
        schema_detail = "没有可执行正式 Schema 校验的证据 artifact"
    gates.append(_gate(
        "evidence-schema-valid",
        "同一 read-once 证据快照符合正式 artifact Schema",
        True,
        schema_status,
        schema_detail,
    ))

    if forecast is None:
        gates.append(_gate("forecast-present", "存在可读的项目预测", True, NOT_EXECUTED,
                           "project-forecast.json 不存在"))
    else:
        tokens = _mapping(forecast.get("tokens"))
        ok = tokens.get("category_sum_equals_total") is True
        gates.append(_gate("forecast-present", "存在可读的项目预测", True,
                           PASS if ok else FAIL,
                           "token 分类互斥且 total 为分类之和" if ok else "token 分类核算不成立",
                           "project-forecast.json"))
        confidence = _number(_mapping(forecast.get("project")).get("confidence"))
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
            if _integer(calibration.get("token_samples")) == 0:
                missing_evidence.append("token 维度从未用真实用量校准")
            if _integer(calibration.get("runtime_samples")) == 0:
                missing_evidence.append("运行时维度从未用真实耗时校准")
        detail = f"confidence={confidence}（门槛 0.6）"
        if confidence < 0.6 and missing_evidence:
            detail += "；要在证据上支撑更高的置信度，还缺：" + "、".join(missing_evidence)
        gates.append(_gate(
            "forecast-confidence", "预测置信度达到发布门槛", True,
            PASS if confidence >= 0.6 else FAIL,
            detail, "project-forecast.json"))
        excludes_value = _mapping(forecast.get("system_runtime")).get("excludes")
        excludes = excludes_value if isinstance(excludes_value, list) else []
        gates.append(_gate(
            "eta-scope", "系统 ETA 明文排除人工等待", True,
            PASS if excludes else FAIL,
            f"排除项 {len(excludes)} 条", "project-forecast.json"))
        billable = [
            model for model in _records(_mapping(forecast.get("costs")).get("models"))
            if not model.get("not_for_billing")
        ]
        gates.append(_gate(
            "verified-rates", "费用基于已核验费率", False,
            PASS if billable else FAIL,
            f"{len(billable)} 个可计费费率" if billable else "全部费率为示例值，不可用于预算",
            "project-forecast.json"))

    if register is None:
        gates.append(_gate("scope-gaps", "范围缺口已清零或已决策", True, NOT_EXECUTED,
                           "risk-and-gap-register.json 不存在"))
    else:
        blocking = [
            gap for gap in _records(register.get("gaps")) if gap.get("needs_human_input")
        ]
        gates.append(_gate(
            "scope-gaps", "范围缺口已清零或已决策", True,
            PASS if not blocking else FAIL,
            f"{len(blocking)} 个缺口仍需人工决策："
            + ", ".join(str(gap.get("id", "<missing-id>")) for gap in blocking[:5])
            if blocking else "无待决缺口",
            "risk-and-gap-register.json"))

    if calibration is None:
        gates.append(_gate("calibrated", "预测已用真实遥测校准", True, NOT_EXECUTED,
                           "calibration.json 不存在；未校准的预测不构成承诺"))
    else:
        samples = _integer(calibration.get("valid_samples"))
        gates.append(_gate(
            "calibrated", "预测已用真实遥测校准", True,
            PASS if samples >= effective_min_samples else FAIL,
            f"{samples} 个有效样本（门槛 {effective_min_samples}）", "calibration.json"))

    if chaos is None:
        gates.append(_gate("chaos-recovery", "Chaos 与恢复验证通过", True, NOT_EXECUTED,
                           "chaos-test-report.json 不存在"))
    else:
        scenarios = _records(chaos.get("scenarios"))
        failed = [scenario for scenario in scenarios if not scenario.get("passed")]
        gates.append(_gate(
            "chaos-recovery", "Chaos 与恢复验证通过", True,
            PASS if scenarios and not failed else FAIL,
            f"{len(scenarios)} 个场景，{len(failed)} 个失败", "chaos-test-report.json"))

    if manifest is None:
        gates.append(_gate("artifacts-sealed", "结果 Manifest 已封存", True, NOT_EXECUTED,
                           "result-manifest.json 不存在"))
    else:
        sealed = bool(manifest.get("sealed"))
        count = _integer(manifest.get("artifact_count"))
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
        sessions = _integer(_mapping(token_mix.get("observed")).get("sessions"))
        # Prefer the depth curve over the headline range: the headline is the
        # full-session factor, which reads as a flat multiplier and is not one.
        depths = _records(token_mix.get("cost_by_session_depth"))
        factor = token_mix.get("overstatement_factor_range")
        first_factor = _number(depths[0].get("overstatement_factor")) if depths else 0.0
        last_factor = _number(depths[-1].get("overstatement_factor")) if depths else 0.0
        if first_factor and last_factor:
            spread = (
                f"，当前假设使费用偏离 {first_factor:.2f} 倍"
                f"（{_integer(depths[0].get('turns'))} 轮任务）到 {last_factor:.2f} 倍"
                f"（{_integer(depths[-1].get('turns'))} 轮），随任务长度变化"
            )
        elif (
            isinstance(factor, list)
            and len(factor) == 2
            and all(isinstance(item, int | float) and not isinstance(item, bool) for item in factor)
        ):
            spread = f"，当前假设使费用偏离最多 {float(factor[1]):.2f} 倍（整场会话口径）"
        else:
            spread = ""
        gates.append(_gate(
            "token-mix-verified", "token 分类占比已对照实测", True,
            PASS if token_mix.get("sample_sufficient") else FAIL,
            f"{sessions} 个会话（门槛 {token_mix.get('minimum_sessions', 20)}）{spread}",
            "token-mix-comparison.json"))

    if routing is not None:
        unroutable_value = routing.get("unroutable_tasks")
        unroutable = unroutable_value if isinstance(unroutable_value, list) else []
        gates.append(_gate(
            "routing-complete", "每个任务都有可用模型", False,
            PASS if not unroutable else FAIL,
            f"{len(unroutable)} 个任务无可用模型" if unroutable else "全部任务可路由",
            "model-routing-plan.json"))

    external_trust: VerifiedExternalTrust | None = None
    external_trust_error: str | None = None
    if external_trust_options is not None:
        try:
            external_trust = load_external_trust(
                external_trust_options,
                now=now,
                forbidden_root=root,
            )
        except ExternalTrustError as exc:
            external_trust_error = str(exc)

    present_inputs = sorted(name for name in EVIDENCE_INPUT_FILES if name in snapshot)
    provenance_bytes = snapshot.get("evidence-provenance.json")
    if not present_inputs and provenance_bytes is None and not snapshot_errors:
        provenance: dict[str, Any] = {
            "status": "NOT_EXECUTED",
            "errors": ["没有可验证的证据输入或 evidence-provenance.json"],
            "files": [],
            "signers": [],
        }
        provenance_status = NOT_EXECUTED
        provenance_detail = provenance["errors"][0]
    else:
        provenance = verify_evidence_provenance(
            root,
            trust_store,
            trust_store_sha256,
            present_inputs,
            effective_min_samples,
            {name: snapshot[name] for name in present_inputs},
            provenance_bytes,
            snapshot_errors,
            now=now,
            external_trust=external_trust,
            external_trust_error=external_trust_error,
        )
        provenance_status = PASS if provenance["status"] == "VERIFIED" else FAIL
        if provenance_status == PASS:
            signers = provenance.get("signers", [])
            trust_authority = provenance.get("trust_authority")
            authority_detail = ""
            if isinstance(trust_authority, dict):
                authority_detail = (
                    f"；外部 trust authority={trust_authority.get('issuer_id')}"
                    f"/{trust_authority.get('issuer_key_id')} epoch={trust_authority.get('epoch')} "
                    f"source={trust_authority.get('source')}，撤销状态新鲜且 ETag/digest 已绑定"
                )
            provenance_detail = (
                f"证据集 {provenance.get('evidence_set_id')} 已由 "
                + "、".join(
                    f"{item['role']}={item['principal_id']}@{item['organization_id']}"
                    f"/{item['authority_id']}({item['key_id']})"
                    for item in signers
                )
                + " 独立签署；文件字节、策略和外置信任库摘要一致"
                + authority_detail
            )
        else:
            provenance_detail = "；".join(str(item) for item in provenance.get("errors", []))
    gates.append(_gate(
        "evidence-provenance",
        "证据字节具备独立、有效且未撤销的双签来源",
        True,
        provenance_status,
        provenance_detail,
        "evidence-provenance.json",
    ))

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
        "evidence_snapshot": {
            "status": "FAILED" if snapshot_errors else "CAPTURED",
            "errors": snapshot_errors,
            "files": [
                {
                    "path": name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
                for name, content in sorted(snapshot.items())
            ],
        },
        "evidence_schema": evidence_schema,
        "evidence_provenance": provenance,
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
            "to have executed and passed against one read-once byte snapshot with valid executor and "
            "organizationally independent verifier attestations; anything else is 'not_certified' or 'block'."
        ),
    }


def build_evidence_manifest(report: dict[str, Any], evidence_dir: str | Path) -> dict[str, Any]:
    root = Path(evidence_dir)
    files = []
    provenance = report.get("evidence_provenance") or {}
    snapshot_entries = {
        item.get("path"): item
        for item in (report.get("evidence_snapshot") or {}).get("files", [])
        if isinstance(item, dict)
    }
    bound_paths = {
        item.get("path") for item in provenance.get("files", []) if isinstance(item, dict)
    }
    for gate in report["gates"]:
        name = gate.get("evidence")
        if not name:
            continue
        captured = snapshot_entries.get(name)
        if captured is None:
            continue
        entry = {
            "path": name,
            "sha256": captured["sha256"],
            "size_bytes": captured["size_bytes"],
            "supports_gate": gate["id"],
            "provenance_bound": name in bound_paths,
        }
        if entry not in files:
            files.append(entry)
    represented_paths = {entry["path"] for entry in files}
    for name, captured in sorted(snapshot_entries.items()):
        if name in represented_paths:
            continue
        files.append({
            "path": name,
            "sha256": captured["sha256"],
            "size_bytes": captured["size_bytes"],
            "supports_gate": (
                "evidence-provenance" if name == "evidence-provenance.json"
                else "evidence-schema-valid"
            ),
            "provenance_bound": name in bound_paths,
        })
    return {
        "schema_version": "2.0.0",
        "artifact": "evidence-manifest",
        "evidence_dir": str(root),
        "decision": report["decision"],
        "files": files,
        "provenance": provenance,
        "schema_validation": report["evidence_schema"],
        "missing_evidence": [
            gate["id"] for gate in report["gates"] if gate["status"] == "NOT_EXECUTED"
        ],
        "invalid_evidence": [
            gate["id"] for gate in report["gates"] if gate["required"] and gate["status"] == "FAIL"
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
        f"- 正式 Schema：`{report['evidence_schema']['status']}`",
        f"- 证据来源：`{report['evidence_provenance']['status']}`",
        f"- 通过 {report['counts']['pass']} · 失败 {report['counts']['fail']} · "
        f"未执行 {report['counts']['not_executed']}",
        "",
        markdown_table(["门禁", "内容", "必需性", "状态", "说明", "证据"], rows),
        "",
        f"> {report['rule']}",
    ])
