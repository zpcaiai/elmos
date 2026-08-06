#!/usr/bin/env python3
"""Generate immutable external-execution profiles for the 557 non-B16 Skills.

The 30 Batch 16 routes already own a native source/target route runner.  Every
other child Skill receives an exact production qualification profile here.
Profiles distinguish toolchain builds from domain-native execution instead of
pretending that assessment, evidence, or cutover Skills are compiler jobs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "docs" / "precision-migration-b01-44" / "adapter-registry.json"
CONTRACTS = ROOT / "docs" / "precision-migration-b01-44" / "executable-contracts.json"
IMPLEMENTATIONS = ROOT / "docs" / "precision-migration-b01-44" / "handler-implementations.json"
OUTPUT = ROOT / "docs" / "precision-migration-b01-44" / "external-execution-profiles.json"

STAGES = (
    "native_source_execution",
    "native_target_execution",
    "independent_holdout",
    "representative_customer_workload",
)
RELEASE_STAGES = (
    "production_hsm",
    "authorized_canary",
    "verified_rollback",
    "external_certification",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def execution_kind(handler_id: str, tools: list[str]) -> str:
    if tools:
        return "NATIVE_TOOLCHAIN"
    if handler_id == "repository-assessment-v1":
        return "REPOSITORY_RUNTIME"
    if handler_id.startswith("b41-"):
        return "EVIDENCE_RUNTIME"
    if handler_id.startswith("b42-"):
        return "CUTOVER_RUNTIME"
    return "DOMAIN_RUNTIME"


def build() -> dict[str, Any]:
    adapters = load(ADAPTERS)
    contracts = load(CONTRACTS)
    implementations = load(IMPLEMENTATIONS)
    contract_by_skill = {item["skill"]: item for item in contracts["contracts"]}
    implementation_by_skill = {item["skill"]: item for item in implementations["implementations"]}
    profiles: list[dict[str, Any]] = []
    for adapter in adapters["entries"]:
        handler_id = str(adapter["handler_id"])
        if adapter.get("kind") != "skill" or handler_id.startswith("batch29-route-executor-v1:"):
            continue
        skill = str(adapter["skill"])
        contract = contract_by_skill[skill]
        implementation = implementation_by_skill.get(skill)
        native_tools = list(implementation.get("native_tools", [])) if implementation else []
        profile_without_digest = {
            "schema_version": 1,
            "skill": skill,
            "source_skill": adapter["source_skill"],
            "batch": adapter["batch"],
            "risk_tier": contract["risk_tier"],
            "handler_id": handler_id,
            "handler_entrypoint": adapter["handler_entrypoint"],
            "contract_digest": contract["contract_digest"],
            "implementation_digest": implementation.get("implementation_digest") if implementation else None,
            "execution_kind": execution_kind(handler_id, native_tools),
            "native_tools": native_tools,
            "required_stages": list(STAGES),
            "release_stages": list(RELEASE_STAGES),
            "corpus_policy": {
                "development_holdout_overlap": "FORBIDDEN",
                "development_representative_overlap": "FORBIDDEN",
                "holdout_representative_overlap": "FORBIDDEN",
                "independent_verifier_required": True,
                "customer_authorization_required": True,
            },
            "operation_policy": {
                "repository_selected_commands": False,
                "signed_adapter_registry_required": True,
                "content_addressed_inputs_required": True,
                "write_once_evidence_required": True,
                "unknown_side_effect_outcome": "BLOCK_RECONCILIATION_REQUIRED",
                "test_weakening": "FORBIDDEN",
            },
        }
        profiles.append({**profile_without_digest, "profile_digest": canonical_digest(profile_without_digest)})
    profiles.sort(key=lambda item: (item["batch"], item["skill"]))
    if len(profiles) != 557 or len({item["skill"] for item in profiles}) != 557:
        raise ValueError("external execution registry must contain exactly 557 unique non-B16 child Skills")
    result_without_digest = {
        "schema_version": 1,
        "namespace": "precision-migration-b01-44",
        "registry_key": "precision-migration-external-execution-v1",
        "profile_count": 557,
        "excluded_native_b16_routes": 30,
        "required_stages": list(STAGES),
        "release_stages": list(RELEASE_STAGES),
        "profiles": profiles,
    }
    return {**result_without_digest, "registry_digest": canonical_digest(result_without_digest)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rendered = json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("external execution profile registry drifted; regenerate it")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"status": "PASS", "profiles": 557, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
