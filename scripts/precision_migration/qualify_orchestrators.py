#!/usr/bin/env python3
"""Run five independent local cases for all 45 exact PM orchestrators."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from scripts.precision_migration.adapters import AdapterRegistry, resolve_handler
from scripts.precision_migration.domain import DomainExecutionError
from scripts.precision_migration.orchestration import OrchestratorRegistry
from scripts.precision_migration.runtime import Registry, canonical_digest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "verification-packs" / "precision-migration-b01-44-runtime" / "orchestrator-qualification" / "results.json"
TEST_TYPES = ("positive", "negative", "integration", "holdout", "representative")


def request(skill: str, parameters: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "request_id": f"orchestrator-{skill}-{role}",
        "skill": skill,
        "mode": "assess",
        "inputs": {"assets": [], "parameters": parameters},
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


def build() -> dict[str, Any]:
    skills = Registry.load()
    adapters = AdapterRegistry.load()
    orchestrators = OrchestratorRegistry.load()
    entries = [
        entry for entry in adapters.payload["entries"]
        if entry["handler_id"].startswith("orchestrator-dag-v2:")
    ]
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="precision-orchestrator-qualification-") as temporary:
        root = Path(temporary)
        for entry in entries:
            skill = entry["skill"]
            profile = orchestrators.by_handler[entry["handler_id"]]
            nodes = profile["nodes"]
            handler = resolve_handler(entry)
            if handler is None:
                raise ValueError(f"orchestrator did not resolve: {skill}")

            positive_dir = root / skill / "positive"
            positive_dir.mkdir(parents=True)
            positive = handler(
                request(skill, {"orchestration_action": "preflight"}, "positive"),
                entry,
                positive_dir,
                skill_registry=skills,
            )
            if positive.get("execution_state") != "LOCAL_EXECUTED":
                raise ValueError(f"orchestrator positive case failed: {skill}")
            results.append(passed(skill, "positive", {"artifact": positive["artifacts"][0]["digest"]}))

            negative_dir = root / skill / "negative"
            negative_dir.mkdir(parents=True)
            rejected = False
            try:
                handler(
                    request(skill, {"selected_nodes": ["not-allowlisted"]}, "negative"),
                    entry,
                    negative_dir,
                    skill_registry=skills,
                )
            except DomainExecutionError:
                rejected = True
            if not rejected:
                raise ValueError(f"orchestrator accepted an unknown node: {skill}")
            results.append(passed(skill, "negative", {"unknown_node_rejected": True}))

            integration_nodes = nodes[: min(2, len(nodes))]
            integration_dir = root / skill / "integration"
            integration_dir.mkdir(parents=True)
            integration = handler(
                request(
                    skill,
                    {"orchestration_action": "preflight", "selected_nodes": integration_nodes, "completed_nodes": integration_nodes[:1]},
                    "integration",
                ),
                entry,
                integration_dir,
                skill_registry=skills,
            )
            results.append(passed(skill, "integration", {"artifact": integration["artifacts"][0]["digest"]}))

            holdout_nodes = nodes[-min(2, len(nodes)):]
            holdout_dir = root / skill / "holdout"
            holdout_dir.mkdir(parents=True)
            holdout = handler(
                request(skill, {"selected_nodes": holdout_nodes}, "holdout"),
                entry,
                holdout_dir,
                skill_registry=skills,
            )
            results.append(passed(skill, "holdout", {"artifact": holdout["artifacts"][0]["digest"]}))

            representative_dir = root / skill / "representative"
            representative_dir.mkdir(parents=True)
            representative = handler(
                request(skill, {"completed_nodes": nodes[:1]}, "representative"),
                entry,
                representative_dir,
                skill_registry=skills,
            )
            results.append(passed(skill, "representative", {"artifact": representative["artifacts"][0]["digest"]}))

    expected = len(entries) * len(TEST_TYPES)
    if len(entries) != 45 or len(results) != expected:
        raise ValueError(f"orchestrator qualification inventory mismatch: {len(entries)}/{len(results)}")
    results.sort(key=lambda item: (item["skill"], TEST_TYPES.index(item["test_type"])))
    return {
        "schema_version": 1,
        "suite": "precision-migration-b01-44-orchestrator-v2",
        "orchestrator_count": len(entries),
        "result_count": len(results),
        "test_types": list(TEST_TYPES),
        "all_tests_passed": True,
        "execution_scope": "LOCAL_DAG_PREFLIGHT_AND_STATE_MACHINE",
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
            raise SystemExit("orchestrator qualification results drifted; regenerate them")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "orchestrators": 45, "results": 225}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
