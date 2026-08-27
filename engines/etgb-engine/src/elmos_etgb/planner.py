"""Change-impact planning and stable, digest-bound shards."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .risk import select_risk_plan
from .validation import load_cases


def changed_paths(root: Path, changed_from: str) -> list[str]:
    result = subprocess.run(["git", "diff", "--name-only", f"{changed_from}...HEAD", "--"], cwd=root, text=True, capture_output=True, check=False)
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()}) if result.returncode == 0 else []


def affected_lines(paths: list[str]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        value = path.lower()
        if any(token in value for token in ("spring", "struts", "servlet", "java-modern")): lines.add("spring-modernization")
        if any(token in value for token in ("translate", "language", "semantic-ir", "frontend", "native")): lines.add("cross-language")
        if any(token in value for token in ("generator", "scaffold", "requirement", "template")): lines.add("project-generation")
        if any(token in value for token in ("sql", "dialect", "routine", "database")): lines.add("sql-conversion")
        if any(token in value for token in ("sandbox", "harness", "executor", "cache", "billing", "tenant", "checkpoint", "evidence", "oracle", "scheduler", "policy")):
            lines.update({"spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"})
    return lines


def stable_shards(case_ids: Iterable[str], shard_count: int) -> list[dict[str, Any]]:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    buckets: list[list[str]] = [[] for _ in range(shard_count)]
    for case_id in sorted(str(value) for value in case_ids):
        buckets[int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % shard_count].append(case_id)
    return [{"shard_id": index, "case_count": len(values), "case_ids": values, "shard_digest": "sha256:" + hashlib.sha256("\n".join(values).encode()).hexdigest()} for index, values in enumerate(buckets) if values]


def build_plan(root: Path, changed_from: str | None = None, *, history_path: Path | None = None, max_cases: int = 500, seed: int = 17, shard_count: int = 8, candidate_digest: str | None = None) -> dict[str, Any]:
    paths = changed_paths(root, changed_from) if changed_from else []
    lines = affected_lines(paths)
    fallback = bool(changed_from and not paths)
    if fallback:
        lines = {"spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"}
    historical = []
    if history_path and history_path.exists():
        historical = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    risk = select_risk_plan(load_cases(root), affected_lines=lines, historical_results=historical, max_cases=max_cases, seed=seed)
    plan = {**risk, "changed_from": changed_from, "changed_paths": paths, "diff_fallback_all_lines": fallback, "candidate_digest": candidate_digest}
    plan["shards"] = stable_shards(plan["case_ids"], shard_count)
    plan["plan_digest"] = "sha256:" + hashlib.sha256(json.dumps({key: value for key, value in plan.items() if key != "plan_digest"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return plan
