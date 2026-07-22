#!/usr/bin/env python3
"""Import the supplied Batch 61-65 synthesis and Batch 1-65 test assets.

This is a one-shot, fail-safe importer. It refuses to overwrite an existing
integration so local execution evidence can never be erased by re-importing
the source package.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEST_SOURCE = Path("/Users/stephen/Downloads/elmos-batch1-65-slightly-strict-test-skills")
SYNTHESIS_SOURCE = Path("/Users/stephen/Downloads/elmos-project-synthesis-batch-61-65")
SUITE = ROOT / "test-suites/batch1-65-slightly-strict"
SYNTHESIS_DESTINATION = ROOT / "elmos-project-synthesis-batch61-65"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_source(path: Path, label: str) -> None:
    if not path.is_dir():
        raise SystemExit(f"missing {label}: {path}")


def main() -> int:
    require_source(TEST_SOURCE, "Batch 1-65 test package")
    require_source(SYNTHESIS_SOURCE, "Batch 61-65 Project Synthesis package")
    for destination in (SUITE, SYNTHESIS_DESTINATION):
        if destination.exists():
            raise SystemExit(f"refusing to overwrite existing integration: {destination}")

    shutil.copytree(SYNTHESIS_SOURCE, SYNTHESIS_DESTINATION)
    shutil.copytree(TEST_SOURCE, SUITE / "source-package")

    source_catalog = json.loads((TEST_SOURCE / "CASE_CATALOG.json").read_text(encoding="utf-8"))
    cases = source_catalog["cases"]
    write_json(SUITE / "cases/catalog.json", source_catalog)

    manifest = json.loads((TEST_SOURCE / "manifest.json").read_text(encoding="utf-8"))
    skill_by_id = {skill["test_skill_id"]: skill for skill in manifest["skills"]}
    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_skill[case["test_skill_id"]].append(case)
    for skill_id in sorted(by_skill):
        skill = skill_by_id[skill_id]
        write_json(
            SUITE / f"cases/by-skill/{skill_id}.json",
            {
                "schema_version": source_catalog["schema_version"],
                "test_skill_id": skill_id,
                "test_skill_name": skill["name"],
                "kind": skill["kind"],
                "target_batches": skill["target_batches"],
                "cases": by_skill[skill_id],
            },
        )

    shutil.copy2(TEST_SOURCE / "COVERAGE_MATRIX.csv", SUITE / "coverage-matrix.csv")
    shutil.copy2(TEST_SOURCE / "references/TARGET_MANIFEST.json", SUITE / "target-manifest.json")
    shutil.copy2(TEST_SOURCE / "references/STRICTNESS_PROFILE.json", SUITE / "strictness-profile.json")

    source_package_hash = "sha256:" + sha256_file(TEST_SOURCE / "manifest.json")
    results = []
    for case in cases:
        results.append(
            {
                "case_id": case["case_id"],
                "test_skill_id": case["test_skill_id"],
                "severity": case["severity"],
                "source_case_digest": "sha256:" + sha256_json(case),
                "status": "NOT_RUN",
                "evidence_complete": False,
                "deterministic_repeat_runs": 0,
                "artifact_digest": None,
                "environment_digest": None,
                "started_at": None,
                "finished_at": None,
                "execution_kind": None,
                "replay_command": None,
                "executor": None,
                "verifier": None,
                "authorization_refs": [],
                "evidence": [],
                "anti_fraud_signals": [],
                "reason": "No authorized case-specific execution and independent verification evidence has been supplied.",
            }
        )
    write_json(
        SUITE / "results/catalog.json",
        {
            "schema_version": "elmos.supplemental-test-results.v1",
            "suite_id": "batch1-65-slightly-strict-supplemental",
            "run_id": "batch1-65-initial-not-run",
            "source_package_hash": source_package_hash,
            "profile_id": "elmos-slightly-strict-v1",
            "authority": "supplemental-only",
            "certification_case_updates": [],
            "results": results,
        },
    )

    suite = {
        "suite_id": "batch1-65-slightly-strict-supplemental",
        "version": "1.0.0",
        "scope": {
            "batches": {"from": 1, "to": 65},
            "source_skills": 1296,
            "test_skills": 88,
            "cases": 750,
            "batch_test_skills": 65,
            "cross_batch_test_skills": 23,
        },
        "authority": "supplemental-design-and-local-engineering-only",
        "replaces_batch1_37_strict_suite": False,
        "certification_authority": False,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "source_package": "source-package",
        "case_catalog": "cases/catalog.json",
        "case_splits": "cases/by-skill",
        "coverage_matrix": "coverage-matrix.csv",
        "target_manifest": "target-manifest.json",
        "strictness_profile": "strictness-profile.json",
        "result_catalog": "results/catalog.json",
        "control_manifest": "control-manifest.json",
        "gate": "scripts/test-suite/run_batch1_65_slightly_strict_gate.py",
        "default_decision": "BLOCKED",
        "field_evidence_status": "NOT_RUN",
        "source_evaluator_authoritative": False,
        "source_evaluator_note": "The supplied evaluator does not enforce exact case completeness; the repository gate is authoritative only for this supplemental integration.",
    }
    write_json(SUITE / "suite.json", suite)

    controlled_files: dict[str, str] = {}
    for relative in [
        "suite.json",
        "cases/catalog.json",
        "coverage-matrix.csv",
        "target-manifest.json",
        "strictness-profile.json",
    ]:
        controlled_files[relative] = "sha256:" + sha256_file(SUITE / relative)
    for path in sorted((SUITE / "cases/by-skill").glob("*.json")):
        relative = path.relative_to(SUITE).as_posix()
        controlled_files[relative] = "sha256:" + sha256_file(path)

    control_manifest = {
        "manifest_version": 1,
        "suite_id": suite["suite_id"],
        "source_package": {
            "original_path": str(TEST_SOURCE),
            "tree_sha256": "sha256:" + tree_digest(TEST_SOURCE),
            "manifest_sha256": source_package_hash,
            "declared_test_skills": 88,
            "declared_cases": 750,
            "declared_source_skills": 1296,
        },
        "project_synthesis_extension": {
            "original_path": str(SYNTHESIS_SOURCE),
            "repository_path": SYNTHESIS_DESTINATION.relative_to(ROOT).as_posix(),
            "tree_sha256": "sha256:" + tree_digest(SYNTHESIS_SOURCE),
            "package_manifest_sha256": "sha256:" + sha256_file(SYNTHESIS_SOURCE / "package-manifest.json"),
            "declared_skills": 52,
            "skill_id_range": ["PG171", "PG222"],
        },
        "controlled_files": controlled_files,
    }
    write_json(SUITE / "control-manifest.json", control_manifest)
    print(
        f"Imported {len(cases)} cases across {len(by_skill)} test Skills and "
        "52 Project Synthesis specifications without creating execution claims."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
