#!/usr/bin/env python3
"""Bounded Batch 42 shadow, canary, cutover, and rollback handlers.

These handlers never send traffic or mutate production.  They consume
content-addressed observations/plans and produce deterministic decisions that
an independently authorised control plane may execute.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from scripts.precision_migration.runtime import canonical_digest
from scripts.precision_migration.trust import verify_content_reference


class CutoverError(ValueError):
    pass


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise CutoverError(f"refusing to overwrite B42 artifact: {path}")
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(content)
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "media_type": "application/json",
    }


def _input(request: dict[str, Any], roots: tuple[Path, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    assets = request.get("inputs", {}).get("assets", [])
    if len(assets) != 1:
        raise CutoverError("B42 handlers require exactly one content-addressed JSON asset")
    try:
        observed = verify_content_reference(assets[0], roots)
        uri = assets[0].get("uri", "")
        if not isinstance(uri, str) or not uri.startswith("file://"):
            raise CutoverError("B42 input must be a local file URI")
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise CutoverError("B42 input file URI is invalid")
        path = Path(unquote(parsed.path))
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise CutoverError(f"B42 input verification failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise CutoverError("B42 input root must be an object")
    return payload, observed


def _result(
    request: dict[str, Any],
    entry: dict[str, Any],
    output_dir: Path,
    name: str,
    decision: dict[str, Any],
    observed: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "input": observed,
        "decision_id": canonical_digest({"skill": entry["skill"], "input": observed["digest"], "decision": decision}),
        "decision": decision,
        "production_side_effects_executed": False,
        "production_authorization": "NOT_RUN",
        "external_verification": "NOT_RUN",
    }
    return {"execution_state": "LOCAL_EXECUTED", "artifacts": [_write(output_dir / name, body)], "exit_code": 0}


def _records(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CutoverError(f"{label} must be an array of objects")
    return value


def _by_id(records: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in records:
        identity = item.get("id")
        if not isinstance(identity, str) or not identity or identity in result:
            raise CutoverError(f"{label} contains a missing or duplicate id")
        result[identity] = item
    return result


def execute_production_shadow_run(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    if payload.get("side_effects_suppressed") is not True:
        raise CutoverError("shadow comparison requires side_effects_suppressed=true")
    source = _by_id(_records(payload.get("source_observations"), "source_observations"), "source_observations")
    target = _by_id(_records(payload.get("target_observations"), "target_observations"), "target_observations")
    missing = sorted(set(source) ^ set(target))
    differences = [key for key in sorted(set(source) & set(target)) if source[key].get("result") != target[key].get("result")]
    decision = {"state": "PASS" if not missing and not differences else "BLOCK", "missing_ids": missing, "different_ids": differences, "compared": len(set(source) & set(target))}
    return _result(request, entry, output_dir, "shadow-run-decision.json", decision, observed)


def execute_live_event_replay(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    events = _records(payload.get("events"), "events")
    sequences: list[int] = []
    keys: set[str] = set()
    duplicates: list[str] = []
    for event in events:
        sequence, key = event.get("sequence"), event.get("idempotency_key")
        if not isinstance(sequence, int) or not isinstance(key, str) or not key:
            raise CutoverError("every replay event requires integer sequence and idempotency_key")
        sequences.append(sequence)
        if key in keys:
            duplicates.append(key)
        keys.add(key)
    ordered = sequences == sorted(sequences) and len(sequences) == len(set(sequences))
    decision = {"state": "PASS" if ordered and not duplicates else "BLOCK", "event_count": len(events), "ordered": ordered, "duplicate_idempotency_keys": sorted(set(duplicates)), "replay_executed": False}
    return _result(request, entry, output_dir, "event-replay-plan.json", decision, observed)


def execute_side_effect_suppression(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    effects = _records(payload.get("effects"), "effects")
    allowed = {"intent-record", "shadow-store", "drop-with-audit"}
    unsafe = []
    plan = []
    for effect in effects:
        identity, replacement = effect.get("id"), effect.get("replacement")
        if not isinstance(identity, str) or replacement not in allowed:
            unsafe.append(str(identity or "<missing>"))
        else:
            plan.append({"id": identity, "original_kind": effect.get("kind"), "replacement": replacement})
    decision = {"state": "PASS" if not unsafe else "BLOCK", "suppression_plan": plan, "unsafe_effects": unsafe}
    return _result(request, entry, output_dir, "side-effect-suppression.json", decision, observed)


def execute_dual_write_validation(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    source = _by_id(_records(payload.get("source_records"), "source_records"), "source_records")
    target = _by_id(_records(payload.get("target_records"), "target_records"), "target_records")
    missing = sorted(set(source) ^ set(target))
    different = [key for key in sorted(set(source) & set(target)) if source[key] != target[key]]
    decision = {"state": "PASS" if not missing and not different else "BLOCK", "missing_ids": missing, "different_ids": different, "matched": len(source) - len(different) - len(set(source) - set(target))}
    return _result(request, entry, output_dir, "dual-write-validation.json", decision, observed)


def execute_canary_traffic_planner(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    segments = _records(payload.get("segments"), "segments")
    maximum = payload.get("maximum_percent")
    if not isinstance(maximum, (int, float)) or not 0 < maximum <= 100:
        raise CutoverError("maximum_percent must be in (0, 100]")
    eligible = [item for item in segments if item.get("approved") is True and isinstance(item.get("risk"), (int, float))]
    eligible.sort(key=lambda item: (item["risk"], str(item.get("id", ""))))
    stages = []
    percentage = min(1.0, float(maximum))
    while percentage <= float(maximum):
        stages.append({"percent": round(percentage, 4), "required_gate": "ALL_SLI_PASS", "rollback_on_failure": True})
        if percentage == float(maximum):
            break
        percentage = min(float(maximum), percentage * 2)
    decision = {"state": "PASS" if eligible and stages else "BLOCK", "eligible_segment_ids": [item.get("id") for item in eligible], "stages": stages}
    return _result(request, entry, output_dir, "canary-traffic-plan.json", decision, observed)


def execute_progressive_cutover(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    stages = _records(payload.get("stages"), "stages")
    eligible = []
    blocked_at = None
    for stage in stages:
        if stage.get("gate") != "PASS" or stage.get("rollback_ready") is not True:
            blocked_at = stage.get("id")
            break
        eligible.append(stage.get("id"))
    decision = {"state": "PASS" if stages and blocked_at is None else "BLOCK", "eligible_stages": eligible, "blocked_at": blocked_at, "cutover_executed": False}
    return _result(request, entry, output_dir, "progressive-cutover-decision.json", decision, observed)


def execute_automatic_rollback(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    metrics, thresholds = payload.get("metrics"), payload.get("thresholds")
    if not isinstance(metrics, dict) or not isinstance(thresholds, dict) or not thresholds:
        raise CutoverError("automatic rollback requires metrics and non-empty thresholds")
    breaches = []
    for name, threshold in thresholds.items():
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or not isinstance(threshold, (int, float)):
            raise CutoverError("rollback metrics and thresholds must be numeric")
        if value > threshold:
            breaches.append({"metric": name, "value": value, "threshold": threshold})
    decision = {"state": "ROLLBACK_REQUIRED" if breaches else "CONTINUE", "breaches": breaches, "rollback_executed": False, "requires_authorized_controller": bool(breaches)}
    return _result(request, entry, output_dir, "automatic-rollback-decision.json", decision, observed)


def execute_migration_wave_planner(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    units = _by_id(_records(payload.get("units"), "units"), "units")
    remaining = set(units)
    waves: list[list[str]] = []
    completed: set[str] = set()
    while remaining:
        ready = sorted(key for key in remaining if set(units[key].get("depends_on", [])) <= completed)
        if not ready:
            raise CutoverError("migration units contain a dependency cycle or unknown dependency")
        ready.sort(key=lambda key: (units[key].get("risk", 0), key))
        waves.append(ready)
        completed.update(ready)
        remaining.difference_update(ready)
    decision = {"state": "PASS", "waves": waves, "unit_count": len(units)}
    return _result(request, entry, output_dir, "migration-wave-plan.json", decision, observed)


def execute_strangler_routing(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    routes = _records(payload.get("routes"), "routes")
    seen: set[str] = set()
    conflicts = []
    plan = []
    for route in routes:
        capability, target = route.get("capability"), route.get("target")
        if not isinstance(capability, str) or target not in {"legacy", "shadow", "new"} or capability in seen:
            conflicts.append(str(capability or "<missing>"))
            continue
        seen.add(capability)
        plan.append({"capability": capability, "target": target, "fallback": "legacy" if target != "legacy" else None})
    decision = {"state": "PASS" if routes and not conflicts else "BLOCK", "routes": plan, "conflicts": conflicts, "routing_applied": False}
    return _result(request, entry, output_dir, "strangler-routing-plan.json", decision, observed)


def execute_post_cutover_monitoring(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], **_: Any) -> dict[str, Any]:
    payload, observed = _input(request, evidence_roots)
    samples = _records(payload.get("samples"), "samples")
    violations = []
    for sample in samples:
        value, lower, upper = sample.get("value"), sample.get("lower"), sample.get("upper")
        if not all(isinstance(item, (int, float)) for item in (value, lower, upper)) or lower > upper:
            raise CutoverError("monitor samples require numeric value/lower/upper")
        if value < lower or value > upper:
            violations.append(sample.get("name"))
    decision = {"state": "PASS" if samples and not violations else "ROLLBACK_REQUIRED", "sample_count": len(samples), "violations": violations, "monitoring_source": "supplied-content-addressed-observations"}
    return _result(request, entry, output_dir, "post-cutover-monitoring.json", decision, observed)
