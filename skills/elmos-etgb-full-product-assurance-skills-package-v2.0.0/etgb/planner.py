from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from etgb.io import iter_cases, iter_jsonl
from etgb.risk import select_risk_plan


def changed_paths(root: Path, changed_from: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{changed_from}...HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return []
    return [x.strip() for x in completed.stdout.splitlines() if x.strip()]


def affected_lines(paths: list[str]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        p = path.lower()
        if any(x in p for x in ["spring", "struts", "servlet", "java-modern"]):
            lines.add("spring-modernization")
        if any(x in p for x in ["translate", "language", "semantic-ir", "frontend", "native"]):
            lines.add("cross-language")
        if any(x in p for x in ["generator", "scaffold", "requirement", "template"]):
            lines.add("project-generation")
        if any(x in p for x in ["sql", "dialect", "routine", "database"]):
            lines.add("sql-conversion")
        if any(
            x in p
            for x in [
                "sandbox",
                "harness",
                "executor",
                "cache",
                "billing",
                "tenant",
                "checkpoint",
                "evidence",
                "oracle",
                "scheduler",
                "policy",
            ]
        ):
            lines.update(
                [
                    "spring-modernization",
                    "cross-language",
                    "project-generation",
                    "sql-conversion",
                    "cross-cutting",
                ]
            )
    return lines


def stable_shards(case_ids: Iterable[str], shard_count: int) -> list[dict[str, Any]]:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    buckets: list[list[str]] = [[] for _ in range(shard_count)]
    for case_id in sorted(case_ids):
        bucket = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest(), 16) % shard_count
        buckets[bucket].append(case_id)
    return [
        {
            "shard_id": index,
            "case_count": len(case_ids_in_shard),
            "case_ids": case_ids_in_shard,
            "shard_digest": "sha256:"
            + hashlib.sha256("\n".join(case_ids_in_shard).encode("utf-8")).hexdigest(),
        }
        for index, case_ids_in_shard in enumerate(buckets)
        if case_ids_in_shard
    ]


def build_plan(
    root: Path,
    changed_from: str | None = None,
    *,
    history_path: Path | None = None,
    max_cases: int = 500,
    seed: int = 17,
    shard_count: int = 8,
    candidate_digest: str | None = None,
) -> dict[str, Any]:
    paths = changed_paths(root, changed_from) if changed_from else []
    lines = affected_lines(paths)
    diff_fallback = False
    if changed_from and not paths:
        # A failed or empty diff must not silently produce a near-empty plan.
        lines = {
            "spring-modernization",
            "cross-language",
            "project-generation",
            "sql-conversion",
            "cross-cutting",
        }
        diff_fallback = True
    historical = list(iter_jsonl(history_path)) if history_path and history_path.exists() else []
    risk_plan = select_risk_plan(
        iter_cases(root),
        affected_lines=lines,
        historical_results=historical,
        max_cases=max_cases,
        control_fraction=0.05,
        seed=seed,
    )
    plan: dict[str, Any] = {
        **risk_plan,
        "changed_from": changed_from,
        "changed_paths": paths,
        "diff_fallback_all_lines": diff_fallback,
        "candidate_digest": candidate_digest,
        "shards": stable_shards(risk_plan["case_ids"], shard_count),
    }
    material = {key: value for key, value in plan.items() if key != "plan_digest"}
    plan["plan_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return plan
