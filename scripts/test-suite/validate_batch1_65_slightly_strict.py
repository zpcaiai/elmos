#!/usr/bin/env python3
"""Validate the imported Batch 1-65 supplemental test catalog and results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPOSITORY_ROOT / "test-suites/batch1-65-slightly-strict"
EXPECTED_SUITE_ID = "batch1-65-slightly-strict-supplemental"
CASE_ID_RE = re.compile(r"^TC-(T\d{3})-(\d{3})$")
SKILL_ID_RE = re.compile(r"^T\d{3}$")
PG_ID_RE = re.compile(r"^id:\s*(PG\d{3})\s*$", re.MULTILINE)
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ALLOWED_STATUSES = {"NOT_RUN", "PASSED", "FAILED", "BLOCKED", "QUARANTINED"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
REQUIRED_TEST_HEADINGS = {
    "## 1. Objective",
    "## 2. Target Scope",
    "## 3. Strictness Profile",
    "## 4. Inputs",
    "## 5. Required Fixtures",
    "## 6. Preconditions",
    "## 7. Test Cases",
    "## 8. Deterministic Oracles",
    "## 9. Execution Procedure",
    "## 10. Failure Injection",
    "## 11. Security and Tenant Isolation",
    "## 12. Replay and Idempotency",
    "## 13. Evidence Contract",
    "## 14. Anti-Fraud Rules",
    "## 15. Reporting",
    "## 16. Acceptance Criteria",
    "## 17. Release Impact",
    "## 18. Definition of Done",
}
REQUIRED_PROJECT_HEADINGS = {
    "## 1. Objective",
    "## 3. Inputs",
    "## 4. Outputs",
    "## 6. Workflow",
    "## 12. Evidence Contract",
    "## 14. Unit Tests",
    "## 17. Acceptance Criteria",
    "## 18. Definition of Done",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def resolve_file(root: Path, relative: str) -> Path:
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


def validate_sha256s(source_root: Path) -> list[str]:
    errors: list[str] = []
    sums = source_root / "SHA256SUMS.txt"
    if not sums.is_file():
        return ["source package SHA256SUMS.txt is missing"]
    for line_number, line in enumerate(sums.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            errors.append(f"invalid SHA256SUMS line {line_number}")
            continue
        relative = parts[1].lstrip("*")
        try:
            path = resolve_file(source_root, relative)
        except (OSError, ValueError) as exc:
            errors.append(f"SHA256SUMS line {line_number}: {exc}")
            continue
        if sha256_file(path) != parts[0]:
            errors.append(f"source package digest mismatch: {relative}")
    return errors


def validate_case(case: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case must be an object"]
    case_id = case.get("case_id")
    skill_id = case.get("test_skill_id")
    match = CASE_ID_RE.fullmatch(case_id) if isinstance(case_id, str) else None
    if match is None or match.group(1) != skill_id:
        errors.append("case_id and test_skill_id disagree")
    if case.get("severity") not in SEVERITIES:
        errors.append("invalid severity")
    batches = case.get("target_batches")
    if (
        not isinstance(batches, list)
        or not batches
        or any(not isinstance(batch, int) or batch < 1 or batch > 65 for batch in batches)
    ):
        errors.append("target_batches must contain Batch 1-65 integers")
    for field in ("category", "title", "setup", "stimulus", "expected", "deterministic_oracle"):
        if not isinstance(case.get(field), str) or not case[field].strip():
            errors.append(f"{field} must be non-empty")
    evidence = case.get("required_evidence")
    if not isinstance(evidence, list) or not evidence or any(not isinstance(role, str) or not role for role in evidence):
        errors.append("required_evidence must contain non-empty roles")
    shortcuts = case.get("disallowed_shortcuts")
    if not isinstance(shortcuts, list) or "fabricate_evidence" not in shortcuts:
        errors.append("anti-fraud shortcuts are incomplete")
    return errors


def validate_passed_result(
    result: dict[str, Any],
    case: dict[str, Any],
    suite_root: Path,
    target_manifest_digest: str,
) -> list[str]:
    errors: list[str] = []
    for field in ("artifact_digest", "environment_digest"):
        if not isinstance(result.get(field), str) or not DIGEST_RE.fullmatch(result[field]):
            errors.append(f"{field} must be a non-zero SHA-256 digest")
    if result.get("target_manifest_digest") != target_manifest_digest:
        errors.append("target_manifest_digest is missing or stale")
    started = parse_time(result.get("started_at"), "started_at", errors)
    finished = parse_time(result.get("finished_at"), "finished_at", errors)
    if started and finished and finished < started:
        errors.append("finished_at precedes started_at")
    if result.get("execution_kind") not in {"real", "approved-equivalent"}:
        errors.append("passed result requires real or approved-equivalent execution")
    if not isinstance(result.get("replay_command"), str) or not result["replay_command"].strip():
        errors.append("passed result requires a replay command")
    if result.get("deterministic_repeat_runs", 0) < 2:
        errors.append("passed result requires at least two deterministic runs")
    if result.get("evidence_complete") is not True:
        errors.append("passed result must declare complete evidence")
    if result.get("flaky") is not False:
        errors.append("passed result requires an explicit non-flaky determination")

    executor = result.get("executor")
    verifier = result.get("verifier")
    if not isinstance(executor, dict) or not isinstance(executor.get("id"), str):
        errors.append("passed result requires executor identity")
    if (
        not isinstance(verifier, dict)
        or not isinstance(verifier.get("id"), str)
        or verifier.get("independent") is not True
    ):
        errors.append("passed result requires an independent verifier")
    if isinstance(executor, dict) and isinstance(verifier, dict) and executor.get("id") == verifier.get("id"):
        errors.append("executor and verifier must be different identities")
    refs = result.get("authorization_refs")
    if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
        errors.append("passed result requires authorization references")
    if result.get("anti_fraud_signals") != []:
        errors.append("passed result cannot contain anti-fraud signals")

    evidence = result.get("evidence")
    required_roles = set(case["required_evidence"])
    actual_roles: set[str] = set()
    if not isinstance(evidence, list) or not evidence:
        errors.append("passed result requires immutable evidence")
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
                path = resolve_file(suite_root, relative)
            except (OSError, ValueError) as exc:
                errors.append(f"evidence[{index}] {exc}")
                continue
            if item.get("sha256") != "sha256:" + sha256_file(path):
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
    suite_root: Path,
    target_manifest_digest: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    for field in ("case_id", "test_skill_id", "severity"):
        source_field = "case_id" if field == "case_id" else field
        if result.get(field) != case.get(source_field):
            errors.append(f"{field} does not match source case")
    if result.get("source_case_digest") != "sha256:" + sha256_json(case):
        errors.append("source_case_digest is stale or tampered")
    status = result.get("status")
    if status not in ALLOWED_STATUSES:
        errors.append("invalid result status")
        return errors
    if status == "NOT_RUN":
        claimed = (
            result.get("artifact_digest"),
            result.get("environment_digest"),
            result.get("started_at"),
            result.get("finished_at"),
            result.get("execution_kind"),
            result.get("replay_command"),
            result.get("executor"),
            result.get("verifier"),
        )
        if any(value is not None for value in claimed):
            errors.append("NOT_RUN result cannot contain execution claims")
        if result.get("evidence_complete") is not False or result.get("deterministic_repeat_runs") != 0:
            errors.append("NOT_RUN result must keep evidence incomplete and repeat count zero")
        if result.get("authorization_refs") != [] or result.get("evidence") != []:
            errors.append("NOT_RUN result cannot contain authorization or evidence")
        if result.get("anti_fraud_signals") != []:
            errors.append("NOT_RUN result cannot contain anti-fraud signals")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            errors.append("NOT_RUN result requires a reason")
    elif status == "PASSED":
        errors.extend(validate_passed_result(result, case, suite_root, target_manifest_digest))
    elif not isinstance(result.get("reason"), str) or not result["reason"].strip():
        errors.append(f"{status} result requires a reason")
    return errors


def validate_suite(root: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    metrics = {
        "batches": 0,
        "source_skills": 0,
        "test_skills": 0,
        "cases": 0,
        "results": 0,
        "project_synthesis_specs": 0,
    }
    try:
        suite = load_json(root / "suite.json")
        controls = load_json(root / suite["control_manifest"])
        catalog = load_json(root / suite["case_catalog"])
        source_manifest = load_json(root / suite["source_package"] / "manifest.json")
        target_manifest = load_json(root / suite["target_manifest"])
        profile = load_json(root / suite["strictness_profile"])
        results = load_json(root / suite["result_catalog"])
    except Exception as exc:  # noqa: BLE001
        return [f"cannot load suite inputs: {exc}"], metrics

    if suite.get("suite_id") != EXPECTED_SUITE_ID:
        errors.append("unexpected suite id")
    if suite.get("authority") != "supplemental-design-and-local-engineering-only":
        errors.append("suite authority must remain supplemental")
    if suite.get("replaces_batch1_37_strict_suite") is not False:
        errors.append("supplement cannot replace Batch 1-37 strict suite")
    if suite.get("certification_authority") is not False:
        errors.append("supplement cannot claim certification authority")
    if suite.get("maximum_success_decision") != "READY_FOR_EXTERNAL_GATE":
        errors.append("maximum decision must remain READY_FOR_EXTERNAL_GATE")
    if suite.get("source_evaluator_authoritative") is not False:
        errors.append("the incomplete source evaluator cannot be authoritative")
    if profile.get("profile_id") != "elmos-slightly-strict-v1":
        errors.append("unexpected strictness profile")

    if controls.get("manifest_version") != 1 or controls.get("suite_id") != EXPECTED_SUITE_ID:
        errors.append("invalid control manifest identity")
    for relative, expected in controls.get("controlled_files", {}).items():
        try:
            path = resolve_file(root, relative)
            if expected != "sha256:" + sha256_file(path):
                errors.append(f"controlled file digest mismatch: {relative}")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    source_root = root / suite["source_package"]
    if controls.get("source_package", {}).get("tree_sha256") != "sha256:" + tree_digest(source_root):
        errors.append("imported source package tree digest mismatch")
    errors.extend(validate_sha256s(source_root))

    source_skills = source_manifest.get("skills")
    if not isinstance(source_skills, list) or len(source_skills) != 88:
        errors.append("source manifest must declare exactly 88 test Skills")
        source_skills = []
    expected_test_ids = {f"T{number:03d}" for number in range(1, 89)}
    test_skill_ids = {skill.get("test_skill_id") for skill in source_skills if isinstance(skill, dict)}
    if test_skill_ids != expected_test_ids:
        errors.append("test Skill IDs must be exactly T001-T088")
    metrics["test_skills"] = len(test_skill_ids)
    batch_skills = [skill for skill in source_skills if skill.get("kind") == "batch"]
    cross_skills = [skill for skill in source_skills if skill.get("kind") == "cross-batch"]
    if len(batch_skills) != 65 or len(cross_skills) != 23:
        errors.append("expected 65 Batch and 23 cross-Batch test Skills")

    for skill in source_skills:
        relative = skill.get("path") or f"agent-skills/runtime/{skill.get('name', '')}/SKILL.md"
        try:
            text = resolve_file(source_root, relative).read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            errors.append(f"{skill.get('test_skill_id')}: {exc}")
            continue
        id_match = re.search(r"^test_skill_id:\s*(T\d{3})$", text, re.MULTILINE)
        if id_match is None or id_match.group(1) != skill.get("test_skill_id"):
            errors.append(f"{relative}: test_skill_id mismatch")
        missing = sorted(REQUIRED_TEST_HEADINGS - set(text.splitlines()))
        if missing:
            errors.append(f"{relative}: missing required headings {missing}")
        if "TODO" in text:
            errors.append(f"{relative}: contains TODO placeholder")

    cases = catalog.get("cases") if isinstance(catalog, dict) else None
    if not isinstance(cases, list) or len(cases) != 750:
        errors.append("catalog must contain exactly 750 cases")
        cases = []
    case_by_id: dict[str, dict[str, Any]] = {}
    cases_by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        label = case.get("case_id", "unknown") if isinstance(case, dict) else "unknown"
        for error in validate_case(case):
            errors.append(f"{label}: {error}")
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            continue
        if case["case_id"] in case_by_id:
            errors.append(f"duplicate case id: {case['case_id']}")
        case_by_id[case["case_id"]] = case
        cases_by_skill[case["test_skill_id"]].append(case)
    metrics["cases"] = len(case_by_id)
    expected_counts = {skill["test_skill_id"]: skill["case_count"] for skill in source_skills}
    actual_counts = {skill_id: len(items) for skill_id, items in cases_by_skill.items()}
    if actual_counts != expected_counts:
        errors.append("case counts do not match the test Skill manifest")
    for skill_id, skill_cases in cases_by_skill.items():
        try:
            split = load_json(root / suite["case_splits"] / f"{skill_id}.json")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{skill_id}: cannot load split catalog: {exc}")
            continue
        if split.get("cases") != skill_cases or split.get("test_skill_id") != skill_id:
            errors.append(f"{skill_id}: split catalog differs from master")

    coverage_path = root / suite["coverage_matrix"]
    with coverage_path.open(encoding="utf-8", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    if len(coverage) != 1296:
        errors.append("coverage matrix must contain exactly 1296 source Skills")
    metrics["source_skills"] = len(coverage)
    batches = {int(row["source_batch"]) for row in coverage if row.get("source_batch", "").isdigit()}
    if batches != set(range(1, 66)):
        errors.append("coverage matrix must cover every Batch 1-65")
    metrics["batches"] = len(batches)
    coverage_keys = {
        (row["source_line"], row["source_batch"], row["source_skill_id"], row["source_skill_name"])
        for row in coverage
    }
    if len(coverage_keys) != len(coverage):
        errors.append("coverage matrix contains duplicate source Skill rows")
    if any(row.get("direct_test_skill_id") not in expected_test_ids for row in coverage):
        errors.append("coverage matrix contains an invalid direct test Skill")
    target_skills = target_manifest.get("skills")
    if not isinstance(target_skills, list) or len(target_skills) != 1296:
        errors.append("target manifest must contain exactly 1296 source Skills")
        target_skills = []
    target_keys = {
        (item["line"], str(item["batch"]), item.get("id", ""), item["name"])
        for item in target_skills
    }
    if target_keys != coverage_keys:
        errors.append("coverage matrix and target manifest source Skill sets differ")

    result_items = results.get("results") if isinstance(results, dict) else None
    if results.get("suite_id") != EXPECTED_SUITE_ID or results.get("authority") != "supplemental-only":
        errors.append("result catalog exceeds supplemental authority")
    if results.get("certification_case_updates") != []:
        errors.append("supplement cannot mutate certification cases")
    if not isinstance(result_items, list) or len(result_items) != 750:
        errors.append("result catalog must contain exactly 750 results")
        result_items = []
    result_by_id: dict[str, dict[str, Any]] = {}
    for result in result_items:
        case_id = result.get("case_id") if isinstance(result, dict) else None
        if not isinstance(case_id, str) or case_id in result_by_id:
            errors.append(f"invalid or duplicate result id: {case_id}")
            continue
        result_by_id[case_id] = result
    metrics["results"] = len(result_by_id)
    if set(result_by_id) != set(case_by_id):
        errors.append("result and case ID sets differ")
    target_manifest_digest = "sha256:" + sha256_file(root / suite["target_manifest"])
    for case_id, case in case_by_id.items():
        if case_id not in result_by_id:
            continue
        for error in validate_result(result_by_id[case_id], case, root, target_manifest_digest):
            errors.append(f"{case_id}: {error}")

    extension = REPOSITORY_ROOT / controls.get("project_synthesis_extension", {}).get("repository_path", "")
    extension_files = sorted((extension / "skills").glob("batch-*/*.md")) if extension.is_dir() else []
    extension_ids: list[str] = []
    for path in extension_files:
        text = path.read_text(encoding="utf-8")
        match = PG_ID_RE.search(text)
        if match:
            extension_ids.append(match.group(1))
        else:
            errors.append(f"{path.relative_to(REPOSITORY_ROOT)}: missing PG id")
        missing = sorted(REQUIRED_PROJECT_HEADINGS - set(text.splitlines()))
        if missing:
            errors.append(f"{path.relative_to(REPOSITORY_ROOT)}: missing required headings {missing}")
    if extension_ids != [f"PG{number:03d}" for number in range(171, 223)]:
        errors.append("Project Synthesis extension IDs must be exactly PG171-PG222")
    metrics["project_synthesis_specs"] = len(extension_ids)
    expected_extension_tree = controls.get("project_synthesis_extension", {}).get("tree_sha256")
    if extension.is_dir() and expected_extension_tree != "sha256:" + tree_digest(extension):
        errors.append("Project Synthesis extension tree digest mismatch")
    base_ids = []
    for path in sorted((REPOSITORY_ROOT / "elmos-project-synthesis-batch46-60/skills").glob("batch-*/*.md")):
        match = PG_ID_RE.search(path.read_text(encoding="utf-8"))
        if match:
            base_ids.append(match.group(1))
    if base_ids + extension_ids != [f"PG{number:03d}" for number in range(1, 223)]:
        errors.append("combined Project Synthesis IDs must be contiguous PG001-PG222")
    return errors, metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    errors, metrics = validate_suite(args.suite.resolve())
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print(
        "PASS: "
        f"{metrics['batches']} batches, {metrics['source_skills']} source Skills, "
        f"{metrics['test_skills']} test Skills, {metrics['cases']} cases, "
        f"{metrics['results']} fail-closed results"
    )
    print(
        f"PASS: {metrics['project_synthesis_specs']} Batch 61-65 Project Synthesis specs; "
        "supplemental authority preserved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
