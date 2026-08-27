"""Profile selection, changed-path planning and release orchestration."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .canonical import canonical_json, digest_json
from .gates import evaluate_gate
from .runner import run_cases
from .scoring import score_results
from .validation import coverage_report, load_cases, validate_package


def changed_paths(root: Path, changed_from: str) -> list[str]:
    completed = subprocess.run(["git", "diff", "--name-only", f"{changed_from}...HEAD", "--"], cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"unable to resolve changed paths from {changed_from}: {completed.stderr.strip()}")
    return sorted({line.strip() for line in completed.stdout.splitlines() if line.strip()})


def affected_lines(paths: list[str]) -> set[str]:
    lines: set[str] = set()
    for path in paths:
        value = path.lower()
        if any(token in value for token in ("spring", "struts", "servlet", "java-modern")):
            lines.add("spring-modernization")
        if any(token in value for token in ("translate", "language", "semantic-ir", "frontend")):
            lines.add("cross-language")
        if any(token in value for token in ("generator", "scaffold", "requirement", "template")):
            lines.add("project-generation")
        if any(token in value for token in ("sql", "dialect", "routine", "database")):
            lines.add("sql-conversion")
        if any(token in value for token in ("sandbox", "harness", "executor", "cache", "billing", "tenant", "evidence")):
            lines.update({"spring-modernization", "cross-language", "project-generation", "sql-conversion", "cross-cutting"})
    return lines


def select_cases(package_root: Path, *, profile: str | None = None, business_line: str | None = None, priority: str | None = None, case_id: str | None = None, plan_ids: set[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for case in load_cases(package_root):
        if plan_ids is not None and case.get("id") not in plan_ids:
            continue
        if profile and profile not in case.get("profiles", []):
            continue
        if business_line and case.get("business_line") != business_line:
            continue
        if priority and case.get("priority") != priority:
            continue
        if case_id and case.get("id") != case_id:
            continue
        selected.append(case)
        if limit is not None and limit > 0 and len(selected) >= limit:
            break
    return selected


def build_plan(package_root: Path, *, changed_from: str | None = None, root_for_git: Path | None = None) -> dict[str, Any]:
    paths = changed_paths(root_for_git or package_root, changed_from) if changed_from else []
    lines = affected_lines(paths)
    cases = select_cases(package_root)
    selected = [case["id"] for case in cases if "smoke" in case.get("profiles", []) or (case.get("business_line") in lines and case.get("priority") == "P0" and "pr" in case.get("profiles", []))]
    payload = {"schema_version": "1.0", "suite_id": "elmos-etgb-sota-v1", "changed_from": changed_from, "changed_paths": paths, "affected_business_lines": sorted(lines), "case_ids": selected}
    return {**payload, "plan_digest": digest_json(payload)}


def shard_cases(cases: list[dict[str, Any]], *, shard_index: int, shard_count: int, corpus_commit: str = "", candidate_digest: str = "", seed: int = 0) -> list[dict[str, Any]]:
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError("invalid shard index/count")
    selected: list[dict[str, Any]] = []
    for case in cases:
        key = f"{case['id']}|{corpus_commit}|{candidate_digest}|{seed}".encode()
        if int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % shard_count == shard_index:
            selected.append(case)
    return selected


def run_profile(package_root: Path, cases: list[dict[str, Any]], *, profile: str, output: Path, state_db: Path | None = None, artifact_root: Path | None = None, allow_unavailable: bool = False, owner: str | None = None, run_id: str | None = None, resume: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not cases:
        raise ValueError("refuse to execute an empty ETGB plan")
    validation = validate_package(package_root)
    if not validation.get("valid"):
        raise ValueError("package validation failed; refuse execution")
    results = run_cases(cases, package_root, profile=profile, state_db=state_db, artifact_root=artifact_root, allow_unavailable=allow_unavailable, owner=owner, run_id=run_id, resume=resume)
    score = score_results(results, package_root, expected_count=len(cases) if profile == "smoke" else None, complete=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(__import__("json").dumps(result, ensure_ascii=False, separators=(",", ":")) for result in results) + ("\n" if results else "")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return results, score


def gate_profile(package_root: Path, results: list[dict[str, Any]], *, profile: str, external_attested: bool = False, independent_verifier: str | None = None) -> dict[str, Any]:
    validation = validate_package(package_root, release=profile in {"release", "golden"})
    coverage = coverage_report(package_root)
    score = score_results(results, package_root, expected_count=len(results), complete=not any(result.get("status") in {"unavailable", "skipped"} for result in results))
    return evaluate_gate(score=score, validation=validation, coverage=coverage, profile=profile, external_attested=external_attested, independent_verifier=independent_verifier)
