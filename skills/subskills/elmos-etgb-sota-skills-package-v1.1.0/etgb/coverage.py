from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from etgb.io import iter_cases
from etgb.materializer import cross_cutting_cases, cross_language_cases, project_generation_cases, spring_cases, sql_cases


def expected_cases(root: Path) -> Iterable[dict[str, Any]]:
    yield from spring_cases(root)
    yield from cross_language_cases(root)
    yield from project_generation_cases(root)
    yield from sql_cases(root)
    yield from cross_cutting_cases(root)


def coverage_report(root: Path) -> dict[str, Any]:
    actual: dict[str, dict[str, Any]] = {}
    counts = Counter()
    techniques = {
        "example-based", "property-based", "differential", "metamorphic", "fuzz", "mutation",
        "fault-injection", "temporal-hidden"
    }
    for case in iter_cases(root):
        actual[case["id"]] = case
        counts[case["business_line"]] += 1
    expected = {case["id"]: case for case in expected_cases(root)}
    missing = sorted(set(expected) - set(actual))
    extra_non_smoke = sorted(cid for cid in set(actual) - set(expected) if "SMOKE" not in cid)

    expected_cells = defaultdict(set)
    actual_cells = defaultdict(set)
    for case in expected.values():
        expected_cells[case["business_line"]].add(tuple(sorted(case["coverage"]["dimensions"].items())))
    for case in actual.values():
        if "SMOKE" not in case["id"]:
            actual_cells[case["business_line"]].add(tuple(sorted(case["coverage"]["dimensions"].items())))

    lines: dict[str, Any] = {}
    for line in sorted(expected_cells):
        exp = len(expected_cells[line])
        got = len(actual_cells[line] & expected_cells[line])
        lines[line] = {"expected_cells": exp, "covered_cells": got, "coverage": got / exp if exp else 1.0}

    assurance = __import__('yaml').safe_load((root / "suites/assurance-techniques.yaml").read_text(encoding="utf-8"))
    declared_techniques = {x["id"] for x in assurance["techniques"]}
    missing_techniques = sorted(techniques - declared_techniques)
    complete = not missing and not extra_non_smoke and not missing_techniques and all(v["coverage"] == 1.0 for v in lines.values())
    return {
        "complete": complete, "declared_model": "ETGB-COVERAGE-1.0", "case_counts": dict(counts),
        "lines": lines, "missing_case_count": len(missing), "missing_case_examples": missing[:20],
        "unexpected_case_count": len(extra_non_smoke), "unexpected_case_examples": extra_non_smoke[:20],
        "mandatory_techniques": sorted(techniques), "missing_techniques": missing_techniques,
    }
