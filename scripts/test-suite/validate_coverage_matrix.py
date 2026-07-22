#!/usr/bin/env python3
"""Validate exact Batch coverage, test-type coverage, and cross-cutting ownership."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import TEST_TYPES, load_json


def validate_coverage(path: Path, catalog_path: Path) -> list[str]:
    try:
        matrix = load_json(path)
        catalog = load_json(catalog_path)
    except Exception as exc:  # noqa: BLE001
        return [f"cannot read coverage inputs: {exc}"]
    cases = catalog.get("cases", []) if isinstance(catalog, dict) else []
    by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
    errors: list[str] = []

    batches = matrix.get("batches") if isinstance(matrix, dict) else None
    if not isinstance(batches, dict):
        return ["coverage.batches must be an object"]
    expected_keys = {str(batch) for batch in range(1, 38)}
    if set(batches) != expected_keys:
        errors.append(
            f"batch keys must be exactly 1 through 37; missing={sorted(expected_keys-set(batches))} "
            f"extra={sorted(set(batches)-expected_keys)}"
        )

    referenced: list[str] = []
    for batch in range(1, 38):
        case_ids = batches.get(str(batch), [])
        if not isinstance(case_ids, list) or len(case_ids) != 8:
            errors.append(f"Batch {batch} must link exactly 8 cases")
            continue
        if len(case_ids) != len(set(case_ids)):
            errors.append(f"Batch {batch} contains duplicate case ids")
        referenced.extend(case_ids)
        batch_cases = []
        for case_id in case_ids:
            case = by_id.get(case_id)
            if case is None:
                errors.append(f"Batch {batch} references unknown case {case_id}")
                continue
            batch_cases.append(case)
            if case.get("batches") != [batch]:
                errors.append(f"{case_id} must be scoped only to Batch {batch}")
        types = {case.get("test_type") for case in batch_cases}
        if types != TEST_TYPES:
            errors.append(
                f"Batch {batch} test types differ; missing={sorted(TEST_TYPES-types)} "
                f"extra={sorted(types-TEST_TYPES)}"
            )
        severities = {case.get("severity") for case in batch_cases}
        if not {"P0", "P1"}.issubset(severities):
            errors.append(f"Batch {batch} must include both P0 and P1 cases")

    if len(referenced) != len(set(referenced)):
        errors.append("a Batch-specific case is linked by more than one Batch row")

    cross_cutting = matrix.get("cross_cutting") if isinstance(matrix, dict) else None
    if not isinstance(cross_cutting, list) or len(cross_cutting) != 11:
        errors.append("coverage.cross_cutting must list exactly 11 cross-cutting Skills")
    elif len(cross_cutting) != len(set(cross_cutting)):
        errors.append("coverage.cross_cutting contains duplicates")
    else:
        catalog_skills = {case.get("skill") for case in cases if isinstance(case, dict)}
        unknown = sorted(set(cross_cutting) - catalog_skills)
        if unknown:
            errors.append(f"cross-cutting Skills have no catalog cases: {unknown}")

    requirements = matrix.get("requirements", {}) if isinstance(matrix, dict) else {}
    if requirements.get("minimum_cases_per_batch") != 8:
        errors.append("minimum_cases_per_batch must remain 8")
    if set(requirements.get("required_test_types", [])) != TEST_TYPES:
        errors.append("required_test_types must contain all eight strict variants")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "coverage",
        nargs="?",
        default="test-suites/batch1-37-strict/coverage-matrix.json",
    )
    parser.add_argument("--catalog")
    args = parser.parse_args()
    path = Path(args.coverage)
    catalog_path = Path(args.catalog) if args.catalog else path.parent / "cases/catalog.json"
    errors = validate_coverage(path, catalog_path)
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: exact Batch 1-37 coverage and all eight required variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
