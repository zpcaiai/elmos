#!/usr/bin/env python3
"""Validate the imported Batch 81-95 supplemental qualification suite."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLING = REPOSITORY_ROOT / "tooling"
sys.path.insert(0, str(TOOLING))

import import_batch81_95_strict_test_assets as assets  # noqa: E402


DEFAULT_SUITE = REPOSITORY_ROOT / "test-suites/batch81-95-language-packs-slightly-strict"
DEFAULT_SOURCE = REPOSITORY_ROOT / "elmos-batch81-95-slightly-strict-test-skills"
LANGUAGE_INSTALL_MANIFEST = (
    REPOSITORY_ROOT / "docs/language-packs-batch81-95/installed-manifest.json"
)
SUITE_ID = "batch81-95-language-packs-slightly-strict"
ALLOWED_STATUSES = {
    "NOT_RUN",
    "PASSED",
    "FAILED",
    "BLOCKED",
    "QUARANTINED",
    "FLAKY",
}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EXPECTED_SEVERITIES = {"CRITICAL": 170, "HIGH": 400, "MEDIUM": 70}
EXPECTED_CASE_IDS = [f"CASE-{number:04d}" for number in range(1, 641)]
EXPECTED_TEST_IDS = [f"T{number:03d}" for number in range(81, 121)]
EXPECTED_SOURCE_IDS = [f"PG{number:03d}" for number in range(223, 403)]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_file(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("path must be a non-empty string")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    if not path.is_file():
        raise ValueError(f"missing file: {relative}")
    return path


def parse_time(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be an ISO-8601 timestamp")
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        errors.append(f"{label} must be an ISO-8601 timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} must include a timezone")
        return None
    return parsed


def validate_passed_result(
    result: dict[str, Any],
    case: dict[str, Any],
    suite: Path,
) -> list[str]:
    errors: list[str] = []
    for field in ("source_digest", "environment_digest", "fixture_digest", "artifact_digest"):
        if not isinstance(result.get(field), str) or not DIGEST_RE.fullmatch(result[field]):
            errors.append(f"PASSED requires a valid {field}")
    started = parse_time(result.get("started_at"), "started_at", errors)
    finished = parse_time(result.get("finished_at"), "finished_at", errors)
    if started and finished and finished < started:
        errors.append("finished_at precedes started_at")
    if result.get("execution_kind") not in {"real", "approved-equivalent"}:
        errors.append("PASSED requires real or approved-equivalent execution")
    if not isinstance(result.get("replay_command"), str) or not result["replay_command"].strip():
        errors.append("PASSED requires a replay command")
    if result.get("deterministic_repeat_runs", 0) < 2:
        errors.append("PASSED requires at least two deterministic runs")
    if result.get("evidence_complete") is not True:
        errors.append("PASSED requires complete evidence")
    if result.get("flaky") is not False or result.get("quarantined") is not False:
        errors.append("PASSED cannot be flaky or quarantined")
    if result.get("findings") != []:
        errors.append("PASSED cannot contain unresolved findings")

    executor = result.get("executor")
    verifier = result.get("verifier")
    if not isinstance(executor, dict) or not isinstance(executor.get("id"), str):
        errors.append("PASSED requires executor identity")
    if (
        not isinstance(verifier, dict)
        or not isinstance(verifier.get("id"), str)
        or verifier.get("independent") is not True
    ):
        errors.append("PASSED requires an independent verifier")
    if isinstance(executor, dict) and isinstance(verifier, dict):
        if executor.get("id") == verifier.get("id"):
            errors.append("executor and verifier must be different identities")
    refs = result.get("authorization_refs")
    if not isinstance(refs, list) or not refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in refs
    ):
        errors.append("PASSED requires authorization references")

    evidence = result.get("evidence")
    required_roles = set(case["required_evidence"])
    actual_roles: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        errors.append("PASSED requires immutable raw evidence")
    else:
        seen_paths: set[str] = set()
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence[{index}] must be an object")
                continue
            role = item.get("role")
            relative = item.get("path")
            if not isinstance(role, str) or not role or role in actual_roles:
                errors.append(f"evidence[{index}] role is missing or duplicated")
            else:
                actual_roles.add(role)
            if not isinstance(relative, str) or not relative or relative in seen_paths:
                errors.append(f"evidence[{index}] path is missing or duplicated")
                continue
            seen_paths.add(relative)
            try:
                path = resolve_file(suite, relative)
            except (OSError, ValueError) as exc:
                errors.append(f"evidence[{index}] {exc}")
                continue
            if item.get("sha256") != file_digest(path):
                errors.append(f"evidence[{index}] digest mismatch")
            if item.get("bytes") != path.stat().st_size or path.stat().st_size < 1:
                errors.append(f"evidence[{index}] byte count mismatch")
    missing_roles = sorted(required_roles - actual_roles)
    if missing_roles:
        errors.append(f"missing required evidence roles: {missing_roles}")
    return errors


def validate_result(
    result: Any,
    case: dict[str, Any],
    suite: Path,
    target_manifest_digest: str,
    language_install_digest: str,
) -> list[str]:
    if not isinstance(result, dict):
        return ["result must be an object"]
    errors: list[str] = []
    expected = {
        "case_id": case["id"],
        "test_skill_id": case["test_skill_id"],
        "batch": case.get("batch"),
        "severity": case["severity"].upper(),
        "target_skills": case["target_skills"],
        "source_case_digest": canonical_digest(case),
        "target_manifest_digest": target_manifest_digest,
        "language_install_manifest_digest": language_install_digest,
    }
    for field, value in expected.items():
        if result.get(field) != value:
            errors.append(f"{field} does not match the immutable case/environment binding")
    status = result.get("status")
    if status not in ALLOWED_STATUSES:
        return errors + ["invalid result status"]
    if status == "NOT_RUN":
        claim_fields = (
            "source_digest",
            "environment_digest",
            "fixture_digest",
            "artifact_digest",
            "started_at",
            "finished_at",
            "execution_kind",
            "replay_command",
            "executor",
            "verifier",
        )
        if any(result.get(field) is not None for field in claim_fields):
            errors.append("NOT_RUN result cannot contain execution claims")
        if result.get("evidence_complete") is not False:
            errors.append("NOT_RUN result must keep evidence incomplete")
        if result.get("deterministic_repeat_runs") != 0:
            errors.append("NOT_RUN result must keep repeat count zero")
        for field in ("authorization_refs", "evidence", "findings"):
            if result.get(field) != []:
                errors.append(f"NOT_RUN result cannot contain {field}")
        if result.get("flaky") is not False or result.get("quarantined") is not False:
            errors.append("NOT_RUN result cannot be flaky or quarantined")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            errors.append("NOT_RUN result requires a reason")
    elif status == "PASSED":
        errors.extend(validate_passed_result(result, case, suite))
    elif not isinstance(result.get("reason"), str) or not result["reason"].strip():
        errors.append(f"{status} result requires a reason")
    return errors


def read_coverage_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_suite(
    suite: Path = DEFAULT_SUITE,
    source: Path = DEFAULT_SOURCE,
) -> tuple[list[str], dict[str, int]]:
    suite = suite.resolve()
    source = source.resolve()
    errors: list[str] = []
    metrics = {
        "batches": 0,
        "test_skills": 0,
        "source_skills": 0,
        "cases": 0,
        "direct_edges": 0,
        "total_edges": 0,
        "results": 0,
        "critical_cases": 0,
        "high_cases": 0,
        "medium_cases": 0,
    }
    try:
        descriptor = load_json(suite / "suite.json")
        controls = load_json(suite / "control-manifest.json")
        profile = load_json(suite / descriptor["strictness_profile"])
        cases = load_json(suite / descriptor["case_catalog"])
        coverage = load_json(suite / descriptor["coverage_matrix"])
        results_catalog = load_json(suite / descriptor["result_catalog"])
    except Exception as exc:  # noqa: BLE001
        return [f"cannot load suite inputs: {exc}"], metrics

    try:
        source_manifest, test_skills, source_cases = assets.validate_source(
            source, require_source_zip=False
        )
    except SystemExit as exc:
        errors.append(f"source test package validation failed: {exc}")
        source_manifest, test_skills, source_cases = {}, [], []
    try:
        assets.verify_install(source)
    except SystemExit as exc:
        errors.append(f"installed test package validation failed: {exc}")
    try:
        target_manifest, language_install = assets.validate_language_binding(source)
    except SystemExit as exc:
        errors.append(f"Language Pack binding validation failed: {exc}")
        target_manifest, language_install = {}, {"skills": []}

    identity = {
        "suite_id": SUITE_ID,
        "authority": "supplemental-design-and-local-engineering-only",
        "batches": list(range(81, 96)),
        "source_namespace": "package-local-language-pack",
        "source_id_range": ["PG223", "PG402"],
        "source_skill_count": 180,
        "test_skill_count": 40,
        "case_count": 640,
        "direct_coverage_edges": 180,
        "total_target_edges": 47700,
        "replaces_batch1_37_strict_suite": False,
        "certification_authority": False,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "source_evaluator_authoritative": False,
        "field_evidence_status": "NOT_RUN",
        "source_test_skill_range": ["T081", "T120"],
    }
    for field, value in identity.items():
        if descriptor.get(field) != value:
            errors.append(f"suite {field} must preserve {value!r}")
    if descriptor.get("source_package") != "../../elmos-batch81-95-slightly-strict-test-skills":
        errors.append("suite source package binding is invalid")
    if descriptor.get("declared_source_zip_sha256") != assets.EXPECTED_SOURCE_ZIP_SHA256:
        errors.append("declared Language Pack ZIP digest is invalid")

    expected_thresholds = load_json(source / "references/STRICTNESS_PROFILE.json")
    if profile != expected_thresholds:
        errors.append("strictness profile differs from the immutable source package")
    if controls.get("manifest_version") != 1 or controls.get("suite_id") != SUITE_ID:
        errors.append("control manifest identity is invalid")
    controlled_files = controls.get("controlled_files")
    if not isinstance(controlled_files, dict) or len(controlled_files) != 6:
        errors.append("control manifest must bind exactly six immutable definition files")
        controlled_files = {}
    for relative, expected_digest in controlled_files.items():
        try:
            path = resolve_file(suite, relative)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if expected_digest != file_digest(path):
            errors.append(f"controlled file digest mismatch: {relative}")

    expected_source_control = controls.get("source_test_package", {})
    source_control_values = {
        "package": assets.PACKAGE_NAME,
        "manifest_sha256": file_digest(source / "manifest.json"),
        "file_manifest_sha256": file_digest(source / "package-manifest.json"),
        "sha256s_sha256": file_digest(source / "SHA256SUMS.txt"),
        "declared_source_zip_sha256": assets.EXPECTED_SOURCE_ZIP_SHA256,
    }
    if expected_source_control != source_control_values:
        errors.append("source test package control binding is stale or tampered")
    language_control = controls.get("language_package", {})
    expected_language_digest = file_digest(LANGUAGE_INSTALL_MANIFEST)
    expected_target_digest = file_digest(source / "references/TARGET_MANIFEST.json")
    if language_control != {
        "package": "elmos-language-packs-batch81-95-complete",
        "namespace": "package-local-language-pack",
        "target_manifest_sha256": expected_target_digest,
        "install_manifest_sha256": expected_language_digest,
    }:
        errors.append("installed Language Pack control binding is stale or tampered")

    if cases != source_cases:
        errors.append("case catalog differs from the immutable 640-case source catalog")
    if load_json(suite / "target-manifest.json") != target_manifest:
        errors.append("target manifest differs from the immutable package-local source target")
    if read_coverage_csv(suite / "coverage-matrix.csv") != read_coverage_csv(
        source / "COVERAGE_MATRIX.csv"
    ):
        errors.append("source coverage CSV differs from the immutable source package")

    metrics["batches"] = len({case.get("batch") for case in cases if case.get("batch")})
    metrics["test_skills"] = len(test_skills)
    metrics["source_skills"] = len(target_manifest.get("skills", []))
    metrics["cases"] = len(cases)
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if case_ids != EXPECTED_CASE_IDS:
        errors.append("case catalog must exactly preserve ordered CASE-0001 through CASE-0640")
    test_ids = [entry.get("id") for entry in test_skills if isinstance(entry, dict)]
    if test_ids != EXPECTED_TEST_IDS:
        errors.append("test Skills must exactly preserve ordered T081 through T120")
    severity_counts = Counter(
        str(case.get("severity", "")).upper() for case in cases if isinstance(case, dict)
    )
    if dict(severity_counts) != EXPECTED_SEVERITIES:
        errors.append(f"case severity counts are invalid: {dict(severity_counts)}")
    metrics["critical_cases"] = severity_counts["CRITICAL"]
    metrics["high_cases"] = severity_counts["HIGH"]
    metrics["medium_cases"] = severity_counts["MEDIUM"]
    cases_by_id = {
        case["id"]: case for case in cases if isinstance(case, dict) and "id" in case
    }

    rows = coverage.get("rows")
    if not isinstance(rows, list):
        rows = []
        errors.append("coverage matrix rows must be a list")
    installed_by_id = {
        entry.get("source_id"): entry for entry in language_install.get("skills", [])
    }
    target_by_id = {entry.get("id"): entry for entry in target_manifest.get("skills", [])}
    if [row.get("source_id") for row in rows if isinstance(row, dict)] != EXPECTED_SOURCE_IDS:
        errors.append("coverage matrix must contain exactly 180 ordered package-local source Skill rows")
    total_edges = sum(
        len(case.get("target_skills", [])) for case in cases if isinstance(case, dict)
    )
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or index >= len(EXPECTED_SOURCE_IDS):
            errors.append(f"coverage row {index} is invalid")
            continue
        source_id = EXPECTED_SOURCE_IDS[index]
        target = target_by_id.get(source_id, {})
        installed = installed_by_id.get(source_id, {})
        direct_case = cases_by_id.get(row.get("direct_case_id"), {})
        related = sum(
            source_id in case.get("target_skills", [])
            and case.get("id") != row.get("direct_case_id")
            for case in cases
            if isinstance(case, dict)
        )
        expected_row = {
            "source_id": source_id,
            "source_key": f"LP-B{target.get('batch')}-{source_id}",
            "source_name": target.get("name"),
            "source_batch": target.get("batch"),
            "source_sha256": installed.get("source_sha256"),
            "installed_alias": installed.get("installed_name"),
            "installed_sha256": installed.get("installed_sha256"),
            "direct_case_id": row.get("direct_case_id"),
            "related_case_count": related,
            "test_skill_id": row.get("test_skill_id"),
        }
        if row != expected_row:
            errors.append(f"coverage row {index} source/install binding is invalid")
        if (
            direct_case.get("category") != "source-skill-direct"
            or direct_case.get("target_skills") != [source_id]
            or direct_case.get("test_skill_id") != row.get("test_skill_id")
        ):
            errors.append(f"coverage row {index} direct case binding is invalid")
    metrics["direct_edges"] = len(rows)
    metrics["total_edges"] = total_edges
    if (
        coverage.get("suite_id") != SUITE_ID
        or coverage.get("source_namespace") != "package-local-language-pack"
        or coverage.get("source_skill_count") != 180
        or coverage.get("direct_coverage_edges") != 180
        or coverage.get("total_target_edges") != 47700
        or len(rows) != 180
        or total_edges != 47700
    ):
        errors.append("coverage totals must preserve 180 direct and 47,700 total target edges")

    if results_catalog.get("suite_id") != SUITE_ID:
        errors.append("result catalog suite identity is invalid")
    if results_catalog.get("target_manifest_digest") != expected_target_digest:
        errors.append("result catalog target manifest digest is stale or tampered")
    if results_catalog.get("language_install_manifest_digest") != expected_language_digest:
        errors.append("result catalog Language Pack install digest is stale or tampered")
    results = results_catalog.get("results")
    if not isinstance(results, list):
        results = []
        errors.append("result catalog results must be a list")
    if results_catalog.get("result_count") != 640 or len(results) != 640:
        errors.append(f"result catalog must contain exactly 640 results, found {len(results)}")
    result_ids = [result.get("case_id") for result in results if isinstance(result, dict)]
    if result_ids != EXPECTED_CASE_IDS or result_ids != case_ids:
        errors.append("result catalog must exactly and uniquely cover the ordered case catalog")
    for result in results:
        if not isinstance(result, dict) or result.get("case_id") not in cases_by_id:
            errors.append("result references an unknown case")
            continue
        for error in validate_result(
            result,
            cases_by_id[result["case_id"]],
            suite,
            expected_target_digest,
            expected_language_digest,
        ):
            errors.append(f"{result['case_id']}: {error}")
    metrics["results"] = len(results)
    if source_manifest and source_manifest.get("release_policy") != "non-compensating":
        errors.append("source release policy must remain non-compensating")
    return errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    errors, metrics = validate_suite(args.suite, args.source)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **metrics}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
