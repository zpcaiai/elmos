#!/usr/bin/env python3
"""Validate the imported fail-closed Batch 66-80 450-case qualification suite."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPOSITORY_ROOT / "test-suites" / "batch66-80-slightly-strict"
TEST_PACKAGE = REPOSITORY_ROOT / "elmos-codex-skills-batch66-80-slightly-strict-tests"
SOURCE_PACKAGE = REPOSITORY_ROOT / "elmos-codex-skills-batch66-80-complete"
RUNTIME_ROOT = REPOSITORY_ROOT / "agent-skills" / "runtime"
IMPORTER_PATH = REPOSITORY_ROOT / "tooling" / "import_batch66_80_strict_test_assets.py"
EXPECTED_IDS = [f"PG{number:03d}" for number in range(223, 418)]
EXPECTED_PRIORITY_COUNTS = {"P0": 312, "P1": 120, "P2": 18}
ALLOWED_STATUSES = {"not-run", "passed", "failed", "blocked", "skipped", "waived", "flaky"}
DIGEST_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
REQUIRED_CASE_FIELDS = {
    "case_id",
    "batch",
    "source_skill_id",
    "source_skill_name",
    "source_skill_path",
    "source_skill_sha256",
    "owner_test_skill",
    "title",
    "priority",
    "category",
    "polarity",
    "given",
    "when",
    "then",
    "oracle",
    "evidence_required",
    "zero_tolerance",
    "required_real_system",
    "replayable",
    "status",
}
CONTROLLED_SUITE_FILES = (
    "suite.json",
    "cases/catalog.json",
    "cases/catalog.jsonl",
    "coverage-matrix.json",
    "source-package.json",
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_digest(path: Path, prefixed: bool = False) -> str:
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{value}" if prefixed else value


def normalize_digest(value: Any) -> str | None:
    match = DIGEST_RE.fullmatch(value) if isinstance(value, str) else None
    return match.group(1) if match else None


def load_importer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("batch66_80_test_importer", IMPORTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load importer: {IMPORTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_file(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("path must be a non-empty string")
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    if not path.is_file():
        raise ValueError(f"missing file: {relative}")
    return path


def parse_timestamp(value: Any, label: str, errors: list[str]) -> datetime | None:
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
    return parsed


def read_source_rows() -> list[dict[str, str]]:
    with (TEST_PACKAGE / "SOURCE_SKILL_HASHES.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def validate_not_run_result(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("attempts") != 0:
        errors.append("not-run must keep attempts at zero")
    for field in ("source_sha256", "environment_sha256", "fixture_sha256", "started_at", "finished_at"):
        if result.get(field) is not None:
            errors.append(f"not-run cannot claim {field}")
    if result.get("evidence") != [] or result.get("waiver_id") is not None:
        errors.append("not-run cannot contain evidence or a waiver")
    return errors


def validate_evidence_item(
    item: Any,
    suite: Path,
    index: int,
    roles: set[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return [f"evidence[{index}] must be an object"]
    role = item.get("kind")
    if not isinstance(role, str) or not role or role in roles:
        errors.append(f"evidence[{index}] kind is missing or duplicated")
    else:
        roles.add(role)
    try:
        path = resolve_file(suite, item.get("path"))
    except (OSError, ValueError) as exc:
        errors.append(f"evidence[{index}] {exc}")
        return errors
    expected = normalize_digest(item.get("sha256"))
    if expected is None or expected != file_digest(path):
        errors.append(f"evidence[{index}] digest is missing or mismatched")
    if path.stat().st_size < 1:
        errors.append(f"evidence[{index}] is empty")
    return errors


def validate_passed_result(result: dict[str, Any], case: dict[str, Any], suite: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(result.get("attempts"), int) or not 1 <= result["attempts"] <= case.get(
        "max_attempts", 3
    ):
        errors.append("passed attempts must be within the case retry bound")
    for field in ("source_sha256", "environment_sha256", "fixture_sha256"):
        if normalize_digest(result.get(field)) is None:
            errors.append(f"passed requires a valid {field}")
    if case.get("source_skill_id") and normalize_digest(result.get("source_sha256")) != case.get(
        "source_skill_sha256"
    ):
        errors.append("passed source_sha256 does not match the exact source Skill")
    started = parse_timestamp(result.get("started_at"), "started_at", errors)
    finished = parse_timestamp(result.get("finished_at"), "finished_at", errors)
    if started and finished and finished < started:
        errors.append("finished_at precedes started_at")
    evidence = result.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 2:
        errors.append("passed requires at least two immutable evidence objects")
        evidence = []
    roles: set[str] = set()
    for index, item in enumerate(evidence):
        errors.extend(validate_evidence_item(item, suite, index, roles))
    missing = sorted(set(case.get("evidence_required", [])) - roles)
    if missing:
        errors.append(f"passed is missing required evidence roles: {missing}")
    for role in ("independent-verification", "authorization"):
        if role not in roles:
            errors.append(f"passed requires repository overlay evidence role: {role}")
    if result.get("waiver_id") is not None:
        errors.append("passed cannot also claim a waiver")
    return errors


def validate_waived_result(result: dict[str, Any], case: dict[str, Any], suite: Path) -> list[str]:
    errors: list[str] = []
    waiver_id = result.get("waiver_id")
    if case.get("zero_tolerance"):
        errors.append("zero-tolerance cases cannot be waived")
    if not isinstance(waiver_id, str) or not waiver_id:
        return errors + ["waived requires waiver_id"]
    try:
        waiver = load_json(resolve_file(suite, f"waivers/{waiver_id}.json"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"waiver cannot be loaded: {exc}"]
    if waiver.get("waiver_id") != waiver_id or case["case_id"] not in waiver.get("case_ids", []):
        errors.append("waiver identity or case coverage is invalid")
    for field in ("owner", "reason", "approved_by", "scope"):
        if not isinstance(waiver.get(field), str) or not waiver[field].strip():
            errors.append(f"waiver {field} is missing")
    approved = parse_timestamp(waiver.get("approved_at"), "waiver approved_at", errors)
    expires = parse_timestamp(waiver.get("expires_at"), "waiver expires_at", errors)
    if approved and expires and expires <= approved:
        errors.append("waiver expires_at must follow approved_at")
    return errors


def validate_result(result: Any, case: dict[str, Any], suite: Path) -> list[str]:
    if not isinstance(result, dict):
        return ["result must be an object"]
    errors: list[str] = []
    if result.get("case_id") != case.get("case_id"):
        errors.append("result case_id does not match its filename/catalog case")
    status = result.get("status")
    if status not in ALLOWED_STATUSES:
        return errors + ["result status is invalid"]
    if status == "not-run":
        errors.extend(validate_not_run_result(result))
    elif status == "passed":
        errors.extend(validate_passed_result(result, case, suite))
    elif status == "waived":
        errors.extend(validate_waived_result(result, case, suite))
    elif not isinstance(result.get("notes"), list) or not result["notes"]:
        errors.append(f"{status} requires a non-empty notes explanation")
    return errors


def validate_suite(suite: Path = DEFAULT_SUITE) -> tuple[list[str], dict[str, Any]]:
    suite = suite.resolve()
    errors: list[str] = []
    metrics: dict[str, Any] = {
        "batches": 0,
        "test_skills": 0,
        "source_skills": 0,
        "cases": 0,
        "source_specific_cases": 0,
        "cross_cutting_cases": 0,
        "coverage_edges": 0,
        "results": 0,
        "zero_tolerance_cases": 0,
        "priority_counts": {},
        "status_counts": {},
    }
    try:
        load_importer().verify_install()
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        errors.append(f"imported package verification failed: {exc}")
    try:
        package_manifest = load_json(TEST_PACKAGE / "manifest.json")
        descriptor = load_json(suite / "suite.json")
        catalog = load_json(suite / "cases" / "catalog.json")
        coverage = load_json(suite / "coverage-matrix.json")
    except Exception as exc:  # noqa: BLE001
        return errors + [f"cannot load suite inputs: {exc}"], metrics

    canonical_suite = TEST_PACKAGE / "test-suites" / "batch66-80-slightly-strict"
    for relative in CONTROLLED_SUITE_FILES:
        try:
            installed = resolve_file(suite, relative)
            canonical = resolve_file(canonical_suite, relative)
        except (OSError, ValueError) as exc:
            errors.append(f"controlled suite file: {exc}")
            continue
        if file_digest(installed) != file_digest(canonical):
            errors.append(f"controlled suite file differs from canonical package: {relative}")

    if descriptor.get("suite_id") != "batch66-80-slightly-strict":
        errors.append("suite identity is invalid")
    if descriptor.get("version") != "1.0.0" or descriptor.get("status") != "not-run":
        errors.append("suite version/status contract is invalid")
    for field, expected in (
        ("test_skill_count", 35),
        ("case_count", 450),
        ("source_skill_count", 195),
    ):
        if descriptor.get(field) != expected or package_manifest.get(field) != expected:
            errors.append(f"{field} must remain exactly {expected}")
    if package_manifest.get("status") != "test-ready-not-run":
        errors.append("package status must remain test-ready-not-run")
    if package_manifest.get("batches") != list(range(66, 81)):
        errors.append("package must cover exactly Batch 66-80")
    metrics["batches"] = 15

    test_skills = package_manifest.get("skills")
    if not isinstance(test_skills, list):
        test_skills = []
    test_names = [entry.get("name") for entry in test_skills if isinstance(entry, dict)]
    if len(test_names) != 35 or len(set(test_names)) != 35:
        errors.append("test Skill inventory must contain 35 unique names")
    metrics["test_skills"] = len(test_names)

    source_rows = read_source_rows()
    source_by_id = {row["id"]: row for row in source_rows}
    if [row.get("id") for row in source_rows] != EXPECTED_IDS:
        errors.append("source Skill hashes must cover contiguous PG223-PG417")
    for row in source_rows:
        try:
            runtime_path = resolve_file(REPOSITORY_ROOT, row.get("path"))
        except (OSError, ValueError) as exc:
            errors.append(f"{row.get('id')}: {exc}")
            continue
        if file_digest(runtime_path) != row.get("source_sha256"):
            errors.append(f"{row.get('id')}: current Runtime Skill digest differs from test design")
    metrics["source_skills"] = len(source_rows)

    cases = catalog.get("cases")
    if catalog.get("case_count") != 450 or not isinstance(cases, list) or len(cases) != 450:
        errors.append("case catalog must contain exactly 450 cases")
        cases = cases if isinstance(cases, list) else []
    cases_by_id: dict[str, dict[str, Any]] = {}
    source_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    cross_case_ids: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            errors.append("case catalog contains a non-object")
            continue
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in cases_by_id:
            errors.append(f"case ID is invalid or duplicated: {case_id!r}")
            continue
        cases_by_id[case_id] = case
        missing = REQUIRED_CASE_FIELDS - set(case)
        if missing:
            errors.append(f"{case_id}: missing fields {sorted(missing)}")
        if case.get("owner_test_skill") not in test_names:
            errors.append(f"{case_id}: owner test Skill is unknown")
        if case.get("priority") not in EXPECTED_PRIORITY_COUNTS:
            errors.append(f"{case_id}: priority is invalid")
        if case.get("status") != "not-run":
            errors.append(f"{case_id}: catalog status must remain not-run")
        if not isinstance(case.get("oracle"), dict) or case["oracle"].get(
            "independence_required"
        ) is not True:
            errors.append(f"{case_id}: independent oracle is required")
        if not isinstance(case.get("evidence_required"), list) or len(case["evidence_required"]) < 3:
            errors.append(f"{case_id}: evidence contract is incomplete")
        source_id = case.get("source_skill_id")
        if source_id is None:
            if case.get("batch") != "cross" or case.get("polarity") != "cross-cutting":
                errors.append(f"{case_id}: cross-cutting identity is invalid")
            cross_case_ids.append(case_id)
        elif source_id not in source_by_id:
            errors.append(f"{case_id}: source Skill ID is unknown")
        else:
            row = source_by_id[source_id]
            source_cases[source_id].append(case)
            for field, source_field in (
                ("source_skill_name", "name"),
                ("source_skill_path", "path"),
                ("source_skill_sha256", "source_sha256"),
            ):
                if case.get(field) != row.get(source_field):
                    errors.append(f"{case_id}: {field} differs from SOURCE_SKILL_HASHES.csv")
    if len(source_cases) != 195 or sum(map(len, source_cases.values())) != 390:
        errors.append("source-specific catalog must contain exactly 390 cases across 195 Skills")
    if len(cross_case_ids) != 60:
        errors.append("catalog must contain exactly 60 cross-cutting cases")
    for source_id in EXPECTED_IDS:
        selected = source_cases.get(source_id, [])
        if len(selected) != 2 or {case.get("polarity") for case in selected} != {
            "positive",
            "negative",
        }:
            errors.append(f"{source_id}: requires exactly one positive and one negative case")
    priority_counts = Counter(case.get("priority") for case in cases if isinstance(case, dict))
    if dict(priority_counts) != EXPECTED_PRIORITY_COUNTS:
        errors.append(f"priority counts differ from {EXPECTED_PRIORITY_COUNTS}: {dict(priority_counts)}")
    zero_tolerance = sum(case.get("zero_tolerance") is True for case in cases if isinstance(case, dict))
    if zero_tolerance != 103:
        errors.append(f"zero-tolerance case count must be 103, found {zero_tolerance}")
    metrics.update(
        {
            "cases": len(cases_by_id),
            "source_specific_cases": sum(map(len, source_cases.values())),
            "cross_cutting_cases": len(cross_case_ids),
            "zero_tolerance_cases": zero_tolerance,
            "priority_counts": dict(sorted(priority_counts.items())),
        }
    )

    coverage_rows = coverage.get("source_skills")
    if coverage.get("source_skill_count") != 195 or not isinstance(coverage_rows, list):
        errors.append("coverage matrix must contain exactly 195 source Skill rows")
        coverage_rows = coverage_rows if isinstance(coverage_rows, list) else []
    if [row.get("source_skill_id") for row in coverage_rows if isinstance(row, dict)] != EXPECTED_IDS:
        errors.append("coverage rows must preserve contiguous PG223-PG417 order")
    edge_count = 0
    for row in coverage_rows:
        if not isinstance(row, dict):
            errors.append("coverage matrix contains a non-object")
            continue
        source_id = row.get("source_skill_id")
        expected = source_by_id.get(source_id, {})
        expected_case_ids = [case["case_id"] for case in source_cases.get(source_id, [])]
        for field, source_field in (
            ("source_skill_name", "name"),
            ("source_skill_path", "path"),
            ("source_skill_sha256", "source_sha256"),
        ):
            if row.get(field) != expected.get(source_field):
                errors.append(f"coverage {source_id}: {field} is stale")
        if row.get("case_ids") != expected_case_ids:
            errors.append(f"coverage {source_id}: positive/negative case binding is incomplete")
        edge_count += len(row.get("case_ids", [])) if isinstance(row.get("case_ids"), list) else 0
    if coverage.get("cross_cutting_case_ids") != cross_case_ids:
        errors.append("cross-cutting coverage must exactly follow the 60 catalog cases")
    edge_count += len(cross_case_ids)
    if edge_count != 450:
        errors.append(f"coverage must contain exactly 450 direct case edges, found {edge_count}")
    metrics["coverage_edges"] = edge_count

    result_paths = sorted((suite / "results").glob("*.json"))
    if len(result_paths) != 450 or {path.stem for path in result_paths} != set(cases_by_id):
        errors.append("result files must exactly and uniquely cover all 450 cases")
    status_counts: Counter[str] = Counter()
    for path in result_paths:
        try:
            result = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: cannot load result: {exc}")
            continue
        case = cases_by_id.get(path.stem)
        if case is None:
            errors.append(f"{path.name}: result references an unknown case")
            continue
        status_counts[result.get("status", "invalid")] += 1
        for error in validate_result(result, case, suite):
            errors.append(f"{path.stem}: {error}")
    metrics["results"] = len(result_paths)
    metrics["status_counts"] = dict(sorted(status_counts.items()))
    return errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    errors, metrics = validate_suite(args.suite)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", **metrics}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
