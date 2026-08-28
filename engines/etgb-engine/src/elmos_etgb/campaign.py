"""Fail-closed aggregation for distributed ETGB release shards."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapters import EXTERNAL_ADAPTERS
from .attestation import verify_signed_record
from .canonical import digest_json, sha256_file
from .planner import validate_plan
from .runner import case_seeds, expected_case_runs
from .validation import load_cases, validate_results


def _load_result_files(paths: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_paths: set[Path] = set()
    for supplied in paths:
        if supplied.is_symlink() or not supplied.is_file():
            errors.append(f"result shard must be a regular file: {supplied}")
            continue
        path = supplied.resolve(strict=True)
        if path in seen_paths:
            errors.append(f"duplicate result shard path: {path}")
            continue
        seen_paths.add(path)
        count = 0
        try:
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError("result row must be an object")
                    results.append(value)
                    count += 1
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"unable to read result shard {path}: {type(exc).__name__}")
            continue
        inputs.append({"path": str(path), "sha256": sha256_file(path), "results": count})
    return results, inputs, errors


def validate_release_result_set(
    package_root: Path,
    plan: Mapping[str, Any],
    results: list[dict[str, Any]],
    *,
    candidate_digest: str,
    trust_store: Mapping[str, Any],
    input_files: list[dict[str, Any]] | None = None,
    initial_errors: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate every expected case/seed result and signed outcome exactly once."""

    errors = list(initial_errors or []) + validate_plan(dict(plan))
    if plan.get("profile") not in {"release", "golden"}:
        errors.append("result aggregation requires a release or golden plan")
    if plan.get("candidate_digest") != candidate_digest:
        errors.append("plan candidate digest mismatch")
    planned_ids = set(str(value) for value in plan.get("case_ids", []))
    cases = {str(case["id"]): case for case in load_cases(package_root) if str(case["id"]) in planned_ids}
    if set(cases) != planned_ids:
        errors.append("plan contains case identities absent from the immutable package")
    profile = str(plan.get("profile"))
    expected_runs = expected_case_runs(list(cases.values()), profile)
    observed_runs: list[tuple[str, int]] = []
    for index, result in enumerate(results, 1):
        case_id = str(result.get("case_id"))
        seed = result.get("seed", 0)
        if not isinstance(seed, int) or isinstance(seed, bool):
            errors.append(f"result {index} seed must be an integer")
            continue
        key = (case_id, seed)
        observed_runs.append(key)
        case = cases.get(case_id)
        if case is None:
            errors.append(f"unexpected result case: {case_id}@{seed}")
            continue
        if seed not in case_seeds(case, profile):
            errors.append(f"unexpected result seed: {case_id}@{seed}")
        if result.get("case_digest") != digest_json(case):
            errors.append(f"case digest mismatch: {case_id}@{seed}")
        evidence = result.get("evidence")
        binding = evidence.get("campaign_binding") if isinstance(evidence, Mapping) else None
        if not isinstance(binding, Mapping):
            errors.append(f"campaign binding missing: {case_id}@{seed}")
            continue
        required_binding = {
            "candidate_digest": candidate_digest,
            "plan_digest": plan.get("plan_digest"),
            "case_digest": result.get("case_digest"),
        }
        for field, expected in required_binding.items():
            if binding.get(field) != expected:
                errors.append(f"campaign binding mismatch for {field}: {case_id}@{seed}")
        adapter = str(case.get("execution", {}).get("adapter", ""))
        if adapter in EXTERNAL_ADAPTERS:
            record = evidence.get("signed_response") if isinstance(evidence, Mapping) else None
            if not isinstance(record, Mapping):
                errors.append(f"signed external response missing: {case_id}@{seed}")
                continue
            verification = verify_signed_record(record, trust_store, record_type="adapter-execution")
            if not verification["valid"]:
                errors.extend(f"signed external response invalid {case_id}@{seed}: {message}" for message in verification["errors"])
                continue
            payload = record.get("payload")
            if not isinstance(payload, Mapping) or payload.get("bindings") != binding or payload.get("adapter") != adapter:
                errors.append(f"signed external response binding mismatch: {case_id}@{seed}")
                continue
            if payload.get("status") != result.get("status") or payload.get("oracle_results") != result.get("oracle_results"):
                errors.append(f"signed external outcome mismatch: {case_id}@{seed}")
            if payload.get("evidence") != evidence.get("external_evidence"):
                errors.append(f"signed external evidence mismatch: {case_id}@{seed}")
    duplicates = sorted(f"{case_id}@{seed}" for (case_id, seed), count in Counter(observed_runs).items() if count > 1)
    if duplicates:
        errors.append("duplicate case-run results: " + ", ".join(duplicates[:20]))
    missing = sorted(expected_runs - set(observed_runs))
    if missing:
        errors.append(f"missing {len(missing)} expected case-run results")
    if len(observed_runs) != len(expected_runs):
        errors.append(f"result count {len(observed_runs)} does not match expected case-run count {len(expected_runs)}")
    schema_errors = validate_results(results, package_root)
    errors.extend(schema_errors[:50])
    ordered = sorted(results, key=lambda item: (str(item.get("case_id")), int(item.get("seed", 0))))
    receipt = {
        "schema_version": "1.0",
        "status": "MERGED" if not errors else "BLOCKED",
        "certification_status": "NOT_CERTIFIED",
        "profile": profile,
        "candidate_digest": candidate_digest,
        "plan_digest": plan.get("plan_digest"),
        "expected_cases": len(cases),
        "expected_case_runs": len(expected_runs),
        "observed_results": len(results),
        "input_files": list(input_files or []),
        "result_set_digest": digest_json(ordered) if not errors else None,
        "errors": errors[:100],
    }
    receipt["receipt_digest"] = digest_json(receipt)
    return ordered if not errors else [], receipt


def merge_release_results(
    package_root: Path,
    plan: Mapping[str, Any],
    result_paths: list[Path],
    *,
    candidate_digest: str,
    trust_store: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read shard files and validate their exact distributed result set."""

    results, input_files, input_errors = _load_result_files(result_paths)
    return validate_release_result_set(
        package_root,
        plan,
        results,
        candidate_digest=candidate_digest,
        trust_store=trust_store,
        input_files=input_files,
        initial_errors=input_errors,
    )
