#!/usr/bin/env python3
"""Validate exact M38-M45 product-Skill and case coverage."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from _common import CATEGORIES, load_json


RANGES = {
    38: range(1325, 1347),
    39: range(1347, 1369),
    40: range(1369, 1393),
    41: range(1393, 1413),
    42: range(1413, 1435),
    43: range(1435, 1455),
    44: range(1455, 1475),
    45: range(1475, 1497),
}


def validate_coverage(path: Path, catalog_path: Path) -> list[str]:
    try:
        matrix = load_json(path)
        catalog = load_json(catalog_path)
    except Exception as exc:  # noqa: BLE001
        return [f"cannot read coverage inputs: {exc}"]
    mappings = matrix.get("mappings") if isinstance(matrix, dict) else None
    cases = catalog.get("cases") if isinstance(catalog, dict) else None
    if not isinstance(mappings, list) or not isinstance(cases, list):
        return ["coverage mappings and catalog cases must be arrays"]
    errors: list[str] = []
    if matrix.get("product_skill_count") != 172 or len(mappings) != 172:
        errors.append("coverage must contain exactly 172 product Skill mappings")
    if matrix.get("case_count") != 400:
        errors.append("coverage case_count must remain 400")
    by_id = {case.get("case_id"): case for case in cases if isinstance(case, dict)}
    expected_ids = set(range(1325, 1497))
    mapped_ids = [item.get("product_skill_id") for item in mappings if isinstance(item, dict)]
    if set(mapped_ids) != expected_ids or len(mapped_ids) != len(set(mapped_ids)):
        errors.append("product Skills must be exactly 1325 through 1496 without duplicates")
    inverse: dict[str, list[int]] = {}
    referenced: set[str] = set()
    for item in mappings:
        if not isinstance(item, dict):
            errors.append("mapping must be an object")
            continue
        product_id = item.get("product_skill_id")
        batch = item.get("batch")
        if batch not in RANGES or product_id not in RANGES.get(batch, ()):
            errors.append(f"invalid Batch/Skill tuple: Batch {batch}, Skill {product_id}")
        case_ids = item.get("case_ids")
        if not isinstance(case_ids, list) or len(case_ids) < 2 or len(case_ids) != len(set(case_ids)):
            errors.append(f"Skill {product_id} must link at least two unique cases")
            continue
        for case_id in case_ids:
            case = by_id.get(case_id)
            if case is None:
                errors.append(f"Skill {product_id} references unknown case {case_id}")
                continue
            if case.get("batch") != batch:
                errors.append(f"{case_id} Batch does not match Skill {product_id}")
            inverse.setdefault(case_id, []).append(product_id)
            referenced.add(case_id)
    batch_cases = [case for case in cases if isinstance(case, dict) and case.get("batch") != "cross"]
    missing_batch_cases = sorted({case["case_id"] for case in batch_cases} - referenced)
    if missing_batch_cases:
        errors.append(f"Batch-specific cases not linked from coverage: {missing_batch_cases}")
    for case in batch_cases:
        expected = sorted(inverse.get(case["case_id"], []))
        if case.get("product_skill_ids") != expected:
            errors.append(f"{case['case_id']}: product_skill_ids differ from coverage matrix")
    for batch in range(38, 46):
        scoped = [case for case in batch_cases if case.get("batch") == batch]
        if len(scoped) != 24:
            errors.append(f"Batch {batch} must contain exactly 24 direct cases")
            continue
        counts = Counter(case.get("category") for case in scoped)
        if set(counts) != CATEGORIES or any(value != 2 for value in counts.values()):
            errors.append(f"Batch {batch} must contain two cases for every strict category")
        priorities = {case.get("priority") for case in scoped}
        if not {"P0", "P1", "P2"}.issubset(priorities):
            errors.append(f"Batch {batch} must include P0, P1 and P2")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("coverage", nargs="?", default="test-suites/batch38-45-strict/coverage-matrix.json")
    parser.add_argument("--catalog")
    args = parser.parse_args()
    path = Path(args.coverage)
    catalog_path = Path(args.catalog) if args.catalog else path.parent / "cases/catalog.json"
    errors = validate_coverage(path, catalog_path)
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: exact Skills 1325-1496, Batch ranges and two-per-category coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
