from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from etgb.io import iter_cases
from etgb.materializer import (
    cross_cutting_cases,
    cross_language_cases,
    full_product_cases,
    product_journey_cases,
    project_generation_cases,
    spring_cases,
    sql_cases,
    standards_cases,
)


def expected_cases(root: Path) -> Iterable[dict[str, Any]]:
    yield from spring_cases(root)
    yield from cross_language_cases(root)
    yield from project_generation_cases(root)
    yield from sql_cases(root)
    yield from full_product_cases(root)
    yield from product_journey_cases(root)
    yield from standards_cases(root)
    yield from cross_cutting_cases(root)


def _cell(case: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    # Matrix dimensions contain only scalar values. String normalization keeps
    # memory bounded and makes YAML/JSON scalar representation deterministic.
    return tuple(sorted((str(key), str(value)) for key, value in case["coverage"]["dimensions"].items()))


def coverage_report(root: Path) -> dict[str, Any]:
    actual_ids: set[str] = set()
    expected_ids: set[str] = set()
    counts = Counter()
    expected_cells: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)
    actual_cells: dict[str, set[tuple[tuple[str, str], ...]]] = defaultdict(set)

    for case in iter_cases(root):
        case_id = case["id"]
        actual_ids.add(case_id)
        counts[case["business_line"]] += 1
        if "SMOKE" not in case_id:
            actual_cells[case["business_line"]].add(_cell(case))

    for case in expected_cases(root):
        expected_ids.add(case["id"])
        expected_cells[case["business_line"]].add(_cell(case))

    missing = sorted(expected_ids - actual_ids)
    extra_non_smoke = sorted(case_id for case_id in actual_ids - expected_ids if "SMOKE" not in case_id)

    lines: dict[str, Any] = {}
    for line in sorted(expected_cells):
        expected_count = len(expected_cells[line])
        covered_count = len(actual_cells[line] & expected_cells[line])
        lines[line] = {
            "expected_cells": expected_count,
            "covered_cells": covered_count,
            "coverage": covered_count / expected_count if expected_count else 1.0,
        }

    required_techniques = {
        "example-based", "property-based", "differential", "metamorphic", "fuzz", "mutation",
        "fault-injection", "temporal-hidden",
    }
    assurance = yaml.safe_load((root / "suites/assurance-techniques.yaml").read_text(encoding="utf-8"))
    declared_techniques = {item["id"] for item in assurance["techniques"]}
    missing_techniques = sorted(required_techniques - declared_techniques)
    complete = (
        not missing
        and not extra_non_smoke
        and not missing_techniques
        and all(value["coverage"] == 1.0 for value in lines.values())
    )
    return {
        "complete": complete,
        "declared_model": "ETGB-FULL-PRODUCT-COVERAGE-2.0",
        "case_counts": dict(counts),
        "lines": lines,
        "missing_case_count": len(missing),
        "missing_case_examples": missing[:20],
        "unexpected_case_count": len(extra_non_smoke),
        "unexpected_case_examples": extra_non_smoke[:20],
        "mandatory_techniques": sorted(required_techniques),
        "missing_techniques": missing_techniques,
    }
