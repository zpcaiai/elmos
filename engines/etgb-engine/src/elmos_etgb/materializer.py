"""Materialized-suite integrity API.

Case generation is intentionally performed from reviewed package inputs, while
normal runtime only reads the immutable materialization. This prevents a worker
from silently rewriting the release corpus during evaluation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import iter_cases, package_root


def smoke_cases(root: Path | None = None) -> list[dict[str, Any]]:
    return [case for case in iter_cases(root or package_root()) if "smoke" in case.get("profiles", [])]


def materialize(root: Path | None = None) -> dict[str, Any]:
    base = root or package_root()
    cases = list(iter_cases(base))
    summary = base / "suites/summary.json"
    if not summary.is_file():
        raise FileNotFoundError(summary)
    import json
    declared = json.loads(summary.read_text(encoding="utf-8"))
    if int(declared.get("total_cases", -1)) != len(cases):
        raise ValueError("materialized case count does not match suite summary")
    return {"total_cases": len(cases), "minimum_satisfied": len(cases) >= int(declared.get("minimum_required", 10000)), "by_business_line": declared.get("by_business_line", {})}
