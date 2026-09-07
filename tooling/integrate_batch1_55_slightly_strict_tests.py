#!/usr/bin/env python3
"""Import the Batch 1-55 design catalog as a non-authoritative supplement.

The downloaded package contains test designs, not executable evidence.  This
importer preserves those designs byte-for-byte, creates fail-closed result
placeholders, and records source provenance without installing a second test
certification authority over the repository's Batch 1-37 strict suite.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(
    "/Users/stephen/Downloads/elmos-codex-skills-batch1-55-slightly-strict-tests"
)
DEFAULT_DESTINATION = REPOSITORY_ROOT / "test-suites/batch1-55-slightly-strict"
ZERO_DIGEST = "sha256:" + "0" * 64


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()

    if not source.is_dir():
        raise SystemExit(f"source package does not exist: {source}")
    if destination.exists():
        raise SystemExit(f"refusing to overwrite existing destination: {destination}")

    source_manifest_path = source / "manifest.json"
    source_catalog_path = source / "test-catalog/all-batch-cases.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_catalog = json.loads(source_catalog_path.read_text(encoding="utf-8"))
    batches = source_catalog.get("batches")
    if not isinstance(batches, dict) or len(batches) != 55:
        raise SystemExit("source catalog must contain exactly 55 batches")

    all_cases: list[dict[str, Any]] = []
    for batch_number in range(1, 56):
        key = str(batch_number)
        batch = batches.get(key)
        if not isinstance(batch, dict):
            raise SystemExit(f"source catalog is missing batch {batch_number}")
        cases = batch.get("cases")
        if not isinstance(cases, list) or len(cases) != 12:
            raise SystemExit(f"batch {batch_number} must contain exactly 12 cases")
        all_cases.extend(cases)
    if len(all_cases) != 660:
        raise SystemExit(f"source catalog must contain 660 cases, found {len(all_cases)}")

    copy_file(
        source_catalog_path,
        destination / "source-package/test-catalog/all-batch-cases.json",
    )
    for batch_number in range(1, 56):
        copy_file(
            source / f"test-catalog/batch-{batch_number:02d}-cases.json",
            destination / f"source-package/test-catalog/batch-{batch_number:02d}-cases.json",
        )

    normalized_catalog = copy.deepcopy(source_catalog)
    aliases: list[dict[str, Any]] = []
    for batch_number in range(1, 56):
        batch = normalized_catalog["batches"][str(batch_number)]
        for case in batch["cases"]:
            source_id = case["id"]
            match = re.fullmatch(rf"B{batch_number:02d}-P[0-3]-(\d{{2}})", source_id)
            if not match:
                raise SystemExit(f"invalid source case id: {source_id}")
            normalized_id = f"B{batch_number:02d}-{case['priority']}-{match.group(1)}"
            if normalized_id != source_id:
                aliases.append(
                    {
                        "source_id": source_id,
                        "normalized_id": normalized_id,
                        "reason": "source id priority segment disagreed with priority field",
                    }
                )
                case["id"] = normalized_id
    write_json(destination / "cases/catalog.json", normalized_catalog)
    for batch_number in range(1, 56):
        write_json(
            destination / f"cases/batch-{batch_number:02d}.json",
            normalized_catalog["batches"][str(batch_number)],
        )
    write_json(
        destination / "cases/id-aliases.json",
        {"alias_version": 1, "aliases": aliases},
    )
    copy_file(
        source / "templates/test-case.schema.json",
        destination / "schemas/source-test-case.schema.json",
    )
    copy_file(
        source / "templates/test-gate.schema.json",
        destination / "schemas/source-test-gate.schema.json",
    )
    copy_file(source_manifest_path, destination / "source-package/manifest.json")
    for filename in (
        "README.md",
        "VALIDATION.md",
        "AGENTS.md",
        "docs/slightly-strict-test-strategy.md",
        "docs/batch-test-matrix.md",
        "docs/source-and-provenance.md",
    ):
        copy_file(source / filename, destination / "source-package" / filename)

    suite = {
        "suite_id": "batch1-55-slightly-strict-supplemental",
        "version": "2.0.0",
        "status": "active",
        "authority": "supplemental-design-and-local-engineering-only",
        "replaces_batch1_37_strict_suite": False,
        "scope": {"batch_from": 1, "batch_to": 55, "seed_cases": 660},
        "source_namespace_model": "single-numeric-batch-1-55",
        "repository_namespace_model": {
            "migration-pack": "M1-M45",
            "product-commercialization": "B34-B55",
        },
        "namespace_interpretation": {
            "source_batches_1_33": "migration-pack design references",
            "source_batches_34_55": "product-commercialization design references",
        },
        "uncovered_repository_namespaces": ["migration-pack:M34-M45"],
        "case_catalog": "cases/catalog.json",
        "result_catalog": "results/catalog.json",
        "control_manifest": "control-manifest.json",
        "gate": "scripts/test-suite/run_batch1_55_slightly_strict_gate.py",
        "default_decision": "BLOCKED",
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "certification_authority": False,
        "source_skill_count": source_manifest.get("skillCount"),
        "source_skills_installed": False,
        "source_skills_note": (
            "The 71 source Skills are preserved by source-package provenance but are not "
            "installed because the repository's 52 Batch 1-37 tst-* Skills remain the "
            "stronger authoritative certification workflow."
        ),
    }
    write_json(destination / "suite.json", suite)

    result_cases: list[dict[str, Any]] = []
    normalized_batches = normalized_catalog["batches"]
    for batch_number in range(1, 56):
        batch = normalized_batches[str(batch_number)]
        for case in batch["cases"]:
            result_cases.append(
                {
                    "case_id": case["id"],
                    "batch": batch_number,
                    "priority": case["priority"],
                    "source_case_digest": sha256_json(case),
                    "status": "not-run",
                    "reason": (
                        "No case-specific real or approved-equivalent execution, independent "
                        "verification, authorization, and immutable raw evidence were supplied."
                    ),
                    "artifact_digest": ZERO_DIGEST,
                    "environment_digest": ZERO_DIGEST,
                    "execution_kind": None,
                    "started_at": None,
                    "finished_at": None,
                    "replay_command": None,
                    "executor": None,
                    "verifier": None,
                    "authorization_refs": [],
                    "evidence": [],
                    "domain_owner_approval_ref": None,
                }
            )
    results = {
        "result_version": 1,
        "suite_id": suite["suite_id"],
        "authority": "supplemental-only",
        "certification_case_updates": [],
        "cases": result_cases,
    }
    write_json(destination / "results/catalog.json", results)

    controlled_paths = [
        "suite.json",
        "cases/catalog.json",
        "schemas/source-test-case.schema.json",
        "schemas/source-test-gate.schema.json",
        "source-package/manifest.json",
        "source-package/test-catalog/all-batch-cases.json",
        "cases/id-aliases.json",
    ] + [f"cases/batch-{batch_number:02d}.json" for batch_number in range(1, 56)]
    controls = {
        relative: "sha256:" + sha256_file(destination / relative)
        for relative in controlled_paths
    }
    control_manifest = {
        "manifest_version": 1,
        "suite_id": suite["suite_id"],
        "source_package": {
            "path": str(source),
            "manifest_sha256": "sha256:" + sha256_file(source_manifest_path),
            "tree_sha256": "sha256:" + tree_digest(source),
            "declared_skills": source_manifest.get("skillCount"),
            "declared_cases": source_manifest.get("testCaseCount"),
        },
        "controlled_files": controls,
    }
    write_json(destination / "control-manifest.json", control_manifest)
    print(
        json.dumps(
            {
                "destination": str(destination),
                "batches": 55,
                "cases": 660,
                "initial_status": "not-run",
                "authority": suite["authority"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
