import json
from pathlib import Path

from etgb.io import package_root
from etgb.materializer import smoke_cases


def test_materialized_case_count_and_smokes() -> None:
    root = package_root()
    summary = json.loads((root / "suites/summary.json").read_text(encoding="utf-8"))
    assert summary["total_cases"] >= 10_000
    assert summary["minimum_satisfied"] is True
    assert {c["business_line"] for c in smoke_cases()} == {
        "spring-modernization", "cross-language", "project-generation", "sql-conversion"
    }
