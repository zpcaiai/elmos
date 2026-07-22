#!/usr/bin/env python3
"""Validate the imported Batch 1-55 supplemental test design and results."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from _common import ZERO_DIGEST, load_json, require_digest, sha256_file, sha256_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = REPOSITORY_ROOT / "test-suites/batch1-55-slightly-strict"
CASE_ID_RE = re.compile(r"^B(?P<batch>0[1-9]|[1-4][0-9]|5[0-5])-P[0-3]-\d{2}$")
PRIORITIES = {"P0", "P1", "P2", "P3"}
STATUSES = {"passed", "failed", "blocked", "not-run", "waived"}


def resolve_beneath(root: Path, relative: str) -> Path:
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


def validate_source_case(case: Any, batch_number: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(case, dict):
        return ["case must be an object"]
    if set(case) != {"id", "title", "priority", "type", "given", "when", "then", "evidence"}:
        errors.append("case fields do not match the source schema")
    case_id = case.get("id")
    match = CASE_ID_RE.fullmatch(case_id) if isinstance(case_id, str) else None
    if not match or int(match.group("batch")) != batch_number:
        errors.append("case id does not match its batch")
    priority = case.get("priority")
    if priority not in PRIORITIES:
        errors.append("invalid priority")
    elif isinstance(case_id, str) and f"-{priority}-" not in case_id:
        errors.append("case id priority segment disagrees with priority")
    for field, minimum in (("title", 3), ("type", 2), ("given", 5), ("when", 3), ("then", 5)):
        value = case.get(field)
        if not isinstance(value, str) or len(value.strip()) < minimum:
            errors.append(f"{field} is too short")
    evidence = case.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(item, str) or not item.strip() for item in evidence
    ):
        errors.append("evidence must contain non-empty roles")
    return errors


def validate_result(
    result: Any,
    case: dict[str, Any],
    batch_number: int,
    root: Path,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    if result.get("case_id") != case["id"]:
        errors.append("result case_id mismatch")
    if result.get("batch") != batch_number:
        errors.append("result batch mismatch")
    if result.get("priority") != case["priority"]:
        errors.append("result priority mismatch")
    if result.get("source_case_digest") != sha256_json(case):
        errors.append("source case digest is stale or tampered")
    status = result.get("status")
    if status not in STATUSES:
        errors.append("invalid result status")
        return errors

    if status == "not-run":
        if result.get("artifact_digest") != ZERO_DIGEST or result.get("environment_digest") != ZERO_DIGEST:
            errors.append("not-run result must use zero artifact/environment digests")
        forbidden_values = (
            result.get("execution_kind"),
            result.get("started_at"),
            result.get("finished_at"),
            result.get("replay_command"),
            result.get("executor"),
            result.get("verifier"),
        )
        if any(value is not None for value in forbidden_values):
            errors.append("not-run result cannot contain execution claims")
        if result.get("authorization_refs") != [] or result.get("evidence") != []:
            errors.append("not-run result cannot contain authorization or evidence")
        if not isinstance(result.get("reason"), str) or not result["reason"].strip():
            errors.append("not-run result requires a reason")
        return errors

    for field in ("artifact_digest", "environment_digest"):
        try:
            require_digest(result.get(field), field)
        except ValueError as exc:
            errors.append(str(exc))
    started = parse_time(result.get("started_at"), "started_at", errors)
    finished = parse_time(result.get("finished_at"), "finished_at", errors)
    if started and finished and finished < started:
        errors.append("finished_at precedes started_at")
    evidence = result.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("executed result requires immutable evidence")
    else:
        roles: set[str] = set()
        paths: set[str] = set()
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"evidence[{index}] must be an object")
                continue
            role = item.get("role")
            relative = item.get("path")
            if not isinstance(role, str) or not role or role in roles:
                errors.append(f"evidence[{index}] role is missing or duplicated")
            else:
                roles.add(role)
            if not isinstance(relative, str) or not relative or relative in paths:
                errors.append(f"evidence[{index}] path is missing or duplicated")
                continue
            paths.add(relative)
            try:
                path = resolve_beneath(root, relative)
            except (ValueError, OSError) as exc:
                errors.append(f"evidence[{index}] {exc}")
                continue
            if item.get("sha256") != "sha256:" + sha256_file(path):
                errors.append(f"evidence[{index}] digest mismatch")
            if item.get("bytes") != path.stat().st_size or path.stat().st_size < 1:
                errors.append(f"evidence[{index}] byte count mismatch")

    if status == "passed":
        if result.get("execution_kind") not in {"real", "approved-equivalent"}:
            errors.append("passed result requires real or approved-equivalent execution")
        if not isinstance(result.get("replay_command"), str) or not result["replay_command"].strip():
            errors.append("passed result requires replay_command")
        executor = result.get("executor")
        verifier = result.get("verifier")
        if not isinstance(executor, dict) or not isinstance(executor.get("id"), str):
            errors.append("passed result requires executor identity")
        if (
            not isinstance(verifier, dict)
            or not isinstance(verifier.get("id"), str)
            or verifier.get("independent") is not True
        ):
            errors.append("passed result requires independent verifier identity")
        if (
            isinstance(executor, dict)
            and isinstance(verifier, dict)
            and executor.get("id") == verifier.get("id")
        ):
            errors.append("executor and verifier must be different identities")
        refs = result.get("authorization_refs")
        if not isinstance(refs, list) or not refs or any(not isinstance(ref, str) or not ref for ref in refs):
            errors.append("passed result requires authorization references")
        if batch_number >= 40 and not isinstance(result.get("domain_owner_approval_ref"), str):
            errors.append("planning-edition Batch 40-55 pass requires domain-owner approval")
    return errors


def validate_suite(root: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    metrics = {"batches": 0, "cases": 0, "results": 0, "aliases": 0}
    try:
        suite = load_json(root / "suite.json")
        catalog = load_json(root / suite["case_catalog"])
        results = load_json(root / suite["result_catalog"])
        controls = load_json(root / suite["control_manifest"])
    except Exception as exc:  # noqa: BLE001
        return [f"cannot load suite: {exc}"], metrics

    if suite.get("suite_id") != "batch1-55-slightly-strict-supplemental":
        errors.append("unexpected suite id")
    if suite.get("authority") != "supplemental-design-and-local-engineering-only":
        errors.append("suite authority must remain supplemental")
    if suite.get("replaces_batch1_37_strict_suite") is not False:
        errors.append("supplement cannot replace Batch 1-37 strict suite")
    if suite.get("certification_authority") is not False:
        errors.append("supplement cannot claim certification authority")
    if suite.get("maximum_success_decision") != "READY_FOR_EXTERNAL_GATE":
        errors.append("supplement maximum decision must be READY_FOR_EXTERNAL_GATE")

    if controls.get("manifest_version") != 1 or controls.get("suite_id") != suite.get("suite_id"):
        errors.append("invalid control manifest identity")
    controlled_files = controls.get("controlled_files")
    if not isinstance(controlled_files, dict) or not controlled_files:
        errors.append("control manifest has no controlled files")
    else:
        for relative, expected in controlled_files.items():
            try:
                path = resolve_beneath(root, relative)
                actual = "sha256:" + sha256_file(path)
                if expected != actual:
                    errors.append(f"controlled file digest mismatch: {relative}")
            except (ValueError, OSError) as exc:
                errors.append(str(exc))
    source = controls.get("source_package", {})
    if source.get("declared_skills") != 71 or source.get("declared_cases") != 660:
        errors.append("source package declarations must remain 71 Skills and 660 cases")

    batches = catalog.get("batches") if isinstance(catalog, dict) else None
    if not isinstance(batches, dict) or set(batches) != {str(number) for number in range(1, 56)}:
        errors.append("catalog must contain exact batch keys 1 through 55")
        batches = {}
    case_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for batch_number in range(1, 56):
        batch = batches.get(str(batch_number))
        if not isinstance(batch, dict):
            continue
        metrics["batches"] += 1
        if batch.get("batch") != batch_number:
            errors.append(f"batch {batch_number}: batch field mismatch")
        cases = batch.get("cases")
        if not isinstance(cases, list) or len(cases) != 12:
            errors.append(f"batch {batch_number}: expected exactly 12 cases")
            continue
        metrics["cases"] += len(cases)
        try:
            split = load_json(root / f"cases/batch-{batch_number:02d}.json")
            if split != batch:
                errors.append(f"batch {batch_number}: split catalog differs from master")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"batch {batch_number}: cannot load split catalog: {exc}")
        for case in cases:
            label = case.get("id", f"batch-{batch_number}") if isinstance(case, dict) else f"batch-{batch_number}"
            for error in validate_source_case(case, batch_number):
                errors.append(f"{label}: {error}")
            if isinstance(case, dict) and isinstance(case.get("id"), str):
                if case["id"] in case_by_id:
                    errors.append(f"duplicate case id: {case['id']}")
                case_by_id[case["id"]] = (batch_number, case)

    aliases_path = root / "cases/id-aliases.json"
    try:
        aliases = load_json(aliases_path).get("aliases")
        if not isinstance(aliases, list) or len(aliases) != 42:
            errors.append("expected 42 source priority-id repairs")
        else:
            metrics["aliases"] = len(aliases)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cannot load id aliases: {exc}")

    result_cases = results.get("cases") if isinstance(results, dict) else None
    if results.get("authority") != "supplemental-only" or results.get("certification_case_updates") != []:
        errors.append("result catalog exceeds supplemental authority")
    if not isinstance(result_cases, list) or len(result_cases) != 660:
        errors.append("result catalog must contain exactly 660 results")
        result_cases = []
    result_by_id: dict[str, dict[str, Any]] = {}
    for result in result_cases:
        case_id = result.get("case_id") if isinstance(result, dict) else None
        if not isinstance(case_id, str) or case_id in result_by_id:
            errors.append(f"invalid or duplicate result id: {case_id}")
            continue
        result_by_id[case_id] = result
    metrics["results"] = len(result_by_id)
    if set(result_by_id) != set(case_by_id):
        errors.append("result and case id sets differ")
    for case_id, (batch_number, case) in case_by_id.items():
        result = result_by_id.get(case_id)
        if result is None:
            continue
        for error in validate_result(result, case, batch_number, root):
            errors.append(f"{case_id}: {error}")
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
        f"{metrics['batches']} batches, {metrics['cases']} cases, "
        f"{metrics['results']} fail-closed results, {metrics['aliases']} repaired source ids"
    )
    print("PASS: supplemental authority preserved; Batch 1-37 strict suite not replaced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
