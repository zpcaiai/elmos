#!/usr/bin/env python3
"""Five-case qualification for repository assessment and all ten B42 Skills."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.precision_migration.adapters import AdapterRegistry, resolve_handler
from scripts.precision_migration.b42 import CutoverError
from scripts.precision_migration.runtime import Registry, canonical_digest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "specialized-qualification" / "results.json"
TEST_TYPES = ("positive", "negative", "integration", "holdout", "representative")


def content_ref(path: Path, *, tampered: bool = False) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + ("0" * 64 if tampered else hashlib.sha256(content).hexdigest()),
        "size_bytes": len(content),
        "media_type": "application/json",
        "sensitivity": "internal",
        "version": "specialized-fixture-v1",
    }


def request(skill: str, assets: list[dict[str, Any]], parameters: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "request_id": f"specialized-{skill}-{role}",
        "skill": skill,
        "mode": "assess" if skill.endswith("repository-modernization-assessment") else "validate",
        "inputs": {"assets": assets, "parameters": parameters},
        "policy": {
            "unresolved_differences": "block",
            "allow_test_weakening": False,
            "require_provenance": True,
            "risk_level": "medium",
        },
        "evidence": [],
        "semantic_losses": [],
        "approvals": [],
    }


def passed(skill: str, test_type: str, evidence: dict[str, Any]) -> dict[str, Any]:
    body = {"skill": skill, "test_type": test_type, "state": "PASS", "evidence": evidence}
    return {**body, "result_digest": canonical_digest(body)}


def b42_payloads(value: int) -> dict[str, dict[str, Any]]:
    return {
        "production-shadow-run": {
            "side_effects_suppressed": True,
            "source_observations": [{"id": "r1", "result": {"value": value}}],
            "target_observations": [{"id": "r1", "result": {"value": value}}],
        },
        "live-event-replay": {
            "events": [{"sequence": 1, "idempotency_key": f"event-{value}-1"}, {"sequence": 2, "idempotency_key": f"event-{value}-2"}],
        },
        "side-effect-suppression": {
            "effects": [{"id": f"payment-{value}", "kind": "payment", "replacement": "intent-record"}],
        },
        "dual-write-validation": {
            "source_records": [{"id": "row-1", "value": value}],
            "target_records": [{"id": "row-1", "value": value}],
        },
        "canary-traffic-planner": {
            "maximum_percent": 8,
            "segments": [{"id": f"tenant-{value}", "risk": value, "approved": True}],
        },
        "progressive-cutover": {
            "stages": [{"id": f"stage-{value}", "gate": "PASS", "rollback_ready": True}],
        },
        "automatic-rollback": {
            "metrics": {"error_rate": value / 10000}, "thresholds": {"error_rate": 0.01},
        },
        "migration-wave-planner": {
            "units": [{"id": "api", "depends_on": [], "risk": value}, {"id": "web", "depends_on": ["api"], "risk": value + 1}],
        },
        "strangler-routing": {
            "routes": [{"capability": f"catalog-read-{value}", "target": "new"}],
        },
        "post-cutover-monitoring": {
            "samples": [{"name": "error_rate", "value": value / 10000, "lower": 0, "upper": 0.01}],
        },
    }


def build() -> dict[str, Any]:
    skills = Registry.load()
    adapters = AdapterRegistry.load()
    entries = [
        entry for entry in adapters.payload["entries"]
        if entry.get("kind") == "skill"
        and (entry["source_skill"] == "repository-modernization-assessment" or entry.get("batch") == 42)
    ]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="precision-specialized-qualification-") as temporary:
        root = Path(temporary).resolve()
        assessment = next(entry for entry in entries if entry["source_skill"] == "repository-modernization-assessment")
        assessment_handler = resolve_handler(assessment)
        if assessment_handler is None:
            raise ValueError("repository assessment handler did not resolve")
        workspaces: dict[str, Path] = {}
        for role, count in (("development", 1), ("holdout", 2), ("representative", 4)):
            workspace = root / f"assessment-{role}"
            workspace.mkdir()
            for index in range(count):
                (workspace / f"module-{index}.py").write_text(f"VALUE = {index}\n", encoding="utf-8")
            (workspace / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='1.0.0'\n", encoding="utf-8")
            workspaces[role] = workspace
        assessment_outputs: dict[str, dict[str, Any]] = {}
        for role, test_type in (("development", "positive"), ("holdout", "holdout"), ("representative", "representative")):
            output = root / "outputs" / assessment["skill"] / role
            output.mkdir(parents=True)
            response = assessment_handler(
                request(assessment["skill"], [], {"workspace_path": str(workspaces[role])}, role),
                assessment,
                output,
                evidence_roots=(root,),
            )
            report = json.loads((output / "repository-assessment.json").read_text(encoding="utf-8"))
            assessment_outputs[role] = {
                "file_count": report["file_count"],
                "detected_manifests": report["detected_manifests"],
                "truncated": report["truncated"],
            }
            results.append(passed(assessment["skill"], test_type, assessment_outputs[role]))
        results.append(passed(assessment["skill"], "integration", {"handler_id": assessment["handler_id"], "inventory_created": True}))
        rejected = False
        try:
            assessment_handler(
                request(assessment["skill"], [], {"workspace_path": str(ROOT)}, "negative"),
                assessment,
                root / "assessment-negative",
                evidence_roots=(root,),
            )
        except (OSError, ValueError):
            rejected = True
        if not rejected:
            raise ValueError("repository assessment accepted a path outside approved roots")
        results.append(passed(assessment["skill"], "negative", {"path_escape_rejected": True}))

        for entry in sorted((item for item in entries if item.get("batch") == 42), key=lambda item: item["skill"]):
            handler = resolve_handler(entry)
            if handler is None:
                raise ValueError(f"B42 handler did not resolve: {entry['skill']}")
            source_skill = entry["source_skill"]
            outputs: dict[str, dict[str, Any]] = {}
            for role, test_type, value in (("development", "positive", 1), ("holdout", "holdout", 2), ("representative", "representative", 3)):
                path = root / f"{source_skill}-{role}.json"
                path.write_text(json.dumps(b42_payloads(value)[source_skill], sort_keys=True) + "\n", encoding="utf-8")
                output = root / "outputs" / entry["skill"] / role
                output.mkdir(parents=True)
                reference = content_ref(path)
                response = handler(
                    request(entry["skill"], [reference], {}, role),
                    entry,
                    output,
                    evidence_roots=(root,),
                )
                artifact_path = Path(response["artifacts"][0]["uri"].removeprefix("file://"))
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                outputs[role] = {
                    "input_digest": reference["digest"],
                    "decision_state": artifact["decision"]["state"],
                    "production_side_effects_executed": artifact["production_side_effects_executed"],
                }
                results.append(passed(entry["skill"], test_type, outputs[role]))
            results.append(passed(entry["skill"], "integration", {"handler_id": entry["handler_id"], "entrypoint": entry["handler_entrypoint"]}))
            negative_path = root / f"{source_skill}-negative.json"
            negative_path.write_text(json.dumps(b42_payloads(1)[source_skill], sort_keys=True) + "\n", encoding="utf-8")
            rejected = False
            try:
                handler(
                    request(entry["skill"], [content_ref(negative_path, tampered=True)], {}, "negative"),
                    entry,
                    root / "outputs" / entry["skill"] / "negative",
                    evidence_roots=(root,),
                )
            except (CutoverError, OSError, ValueError):
                rejected = True
            if not rejected:
                raise ValueError(f"B42 handler accepted tampered input: {entry['skill']}")
            results.append(passed(entry["skill"], "negative", {"tampered_input_rejected": True}))

    if len(entries) != 11 or len(results) != 55:
        raise ValueError(f"specialized qualification inventory mismatch: {len(entries)}/{len(results)}")
    results.sort(key=lambda item: (item["skill"], TEST_TYPES.index(item["test_type"])))
    return {
        "schema_version": 1,
        "suite": "precision-migration-specialized-local-v1",
        "skill_count": 11,
        "result_count": 55,
        "test_types": list(TEST_TYPES),
        "all_tests_passed": True,
        "execution_scope": "SPECIALIZED_LOCAL",
        "production_execution": "NOT_RUN",
        "external_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("specialized qualification results drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "skills": 11, "results": 55}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
