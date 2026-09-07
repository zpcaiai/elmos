from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from etgb.io import iter_cases


def changed_paths(root: Path, changed_from: str) -> list[str]:
    completed = subprocess.run(["git", "diff", "--name-only", f"{changed_from}...HEAD"], cwd=root, text=True, capture_output=True)
    if completed.returncode != 0:
        return []
    return [x.strip() for x in completed.stdout.splitlines() if x.strip()]


def affected_lines(paths: list[str]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        p = path.lower()
        if any(x in p for x in ["spring", "struts", "servlet", "java-modern"]):
            lines.add("spring-modernization")
        if any(x in p for x in ["translate", "language", "semantic-ir", "frontend"]):
            lines.add("cross-language")
        if any(x in p for x in ["generator", "scaffold", "requirement", "template"]):
            lines.add("project-generation")
        if any(x in p for x in ["sql", "dialect", "routine", "database"]):
            lines.add("sql-conversion")
        if any(x in p for x in ["sandbox", "harness", "executor", "cache", "billing", "tenant"]):
            lines.update(["spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"])
    return lines


def build_plan(root: Path, changed_from: str | None = None) -> dict[str, Any]:
    paths = changed_paths(root, changed_from) if changed_from else []
    lines = affected_lines(paths)
    selected: list[str] = []
    for case in iter_cases(root):
        if "smoke" in case["profiles"] or (case["business_line"] in lines and case["priority"] == "P0" and "pr" in case["profiles"]):
            selected.append(case["id"])
    return {"schema_version": "1.0", "changed_from": changed_from, "changed_paths": paths, "affected_business_lines": sorted(lines), "case_ids": selected}
