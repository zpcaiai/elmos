"""Profile selection, changed-path planning and release orchestration."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .attestation import evidence_binding, verify_attestation_binding
from .canonical import canonical_json, digest_json
from .candidate import verify_frozen_candidate
from .gates import evaluate_gate
from .planner import build_plan as build_risk_plan
from .runner import run_cases
from .adapters import EXTERNAL_ADAPTERS
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


def build_plan(package_root: Path, *, changed_from: str | None = None, root_for_git: Path | None = None, history_path: Path | None = None, max_cases: int = 500, seed: int = 17, shard_count: int = 8, candidate_digest: str | None = None) -> dict[str, Any]:
    """Build a digest-bound risk plan; release profiles must use full scope."""

    return build_risk_plan(package_root, changed_from=changed_from, history_path=history_path, max_cases=max_cases, seed=seed, shard_count=shard_count, candidate_digest=candidate_digest)


def shard_cases(cases: list[dict[str, Any]], *, shard_index: int, shard_count: int, corpus_commit: str = "", candidate_digest: str = "", seed: int = 0) -> list[dict[str, Any]]:
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError("invalid shard index/count")
    selected: list[dict[str, Any]] = []
    for case in cases:
        key = f"{case['id']}|{corpus_commit}|{candidate_digest}|{seed}".encode()
        if int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % shard_count == shard_index:
            selected.append(case)
    return selected


def run_profile(package_root: Path, cases: list[dict[str, Any]], *, profile: str, output: Path, state_db: Path | None = None, artifact_root: Path | None = None, allow_unavailable: bool = False, owner: str | None = None, run_id: str | None = None, resume: bool = False, candidate: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not cases:
        raise ValueError("refuse to execute an empty ETGB plan")
    validation = validate_package(package_root, release=profile in {"release", "golden"})
    if not validation.get("valid"):
        raise ValueError("package validation failed; refuse execution")
    if profile in {"release", "golden"}:
        if candidate is None:
            raise ValueError("release/golden execution requires a frozen candidate")
        candidate_errors = verify_frozen_candidate(candidate)
        if candidate_errors:
            raise ValueError("invalid frozen candidate: " + "; ".join(candidate_errors))
    results = run_cases(cases, package_root, profile=profile, state_db=state_db, artifact_root=artifact_root, allow_unavailable=allow_unavailable, owner=owner, run_id=run_id, resume=resume, candidate=candidate)
    complete = len(results) == len(cases) and not any(result.get("status") in {"unavailable", "skipped"} for result in results)
    score = score_results(results, package_root, expected_count=len(cases), complete=complete, corpus_release=profile in {"release", "golden"})
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


def gate_profile(package_root: Path, results: list[dict[str, Any]], *, profile: str, external_attested: bool = False, independent_verifier: str | None = None, external_attestation: dict[str, Any] | None = None, trust_store: dict[str, Any] | None = None, candidate_digest: str | None = None) -> dict[str, Any]:
    validation = validate_package(package_root, release=profile in {"release", "golden"}, trust_store=trust_store)
    coverage = coverage_report(package_root)
    expected_scope = select_cases(package_root, profile=profile)
    complete = len(results) == len(expected_scope) and not any(result.get("status") in {"unavailable", "skipped"} for result in results)
    score = score_results(results, package_root, expected_count=len(expected_scope), complete=complete, corpus_release=profile in {"release", "golden"}, trust_store=trust_store)
    attestation_verification = None
    if external_attestation is not None:
        attestation_verification = verify_attestation_binding(
            external_attestation,
            trust_store or {},
            candidate_digest=candidate_digest,
            score=score,
            validation=validation,
            coverage=coverage,
            corpus=score.get("corpus", {}),
            evidence=evidence_binding(results),
        )
    return evaluate_gate(score=score, validation=validation, coverage=coverage, profile=profile, external_attested=external_attested, independent_verifier=independent_verifier, external_attestation=external_attestation, attestation_verification=attestation_verification, candidate_digest=candidate_digest)


def release_preflight(package_root: Path, *, profile: str = "release", results: list[dict[str, Any]] | None = None, candidate_digest: str | None = None, trust_store: dict[str, Any] | None = None) -> dict[str, Any]:
    """Report release-scope readiness without executing or fabricating cases.

    The preflight makes the distinction between four native smoke routes and
    the full release corpus explicit. It is intentionally not a certification
    gate and never changes external evidence state.
    """

    if profile not in {"release", "golden"}:
        raise ValueError("release preflight requires release or golden profile")
    expected = select_cases(package_root, profile=profile)
    result_rows = list(results or [])
    expected_ids = {str(case["id"]) for case in expected}
    result_ids = [str(result.get("case_id")) for result in result_rows]
    missing = sorted(expected_ids - set(result_ids))
    duplicates = sorted(case_id for case_id, count in Counter(result_ids).items() if count > 1)
    adapters = Counter(str(case.get("execution", {}).get("adapter", "")) for case in expected)
    external_cases = sum(count for adapter, count in adapters.items() if adapter in EXTERNAL_ADAPTERS)
    validation = validate_package(package_root, release=True, trust_store=trust_store)
    corpus = validation.get("corpus", {})
    blockers: list[str] = []
    if not validation.get("valid"):
        blockers.append("release package validation is not valid")
    if len(result_rows) != len(expected) or missing or duplicates:
        blockers.append(f"full {profile} scope requires {len(expected)} distinct case results; received {len(result_rows)}")
    if external_cases:
        blockers.append(f"{external_cases} {profile} cases require independently attested external adapters")
    if corpus.get("unapproved", 0):
        blockers.append(f"{corpus['unapproved']} corpus license reviews remain unapproved or unverified")
    if not candidate_digest or not str(candidate_digest).startswith("sha256:"):
        blockers.append("a content-bound frozen candidate digest must be supplied")
    blockers.append("independent verifier and external signed attestation remain required")
    return {
        "schema_version": "1.1",
        "profile": profile,
        "status": "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE",
        "certification_status": "NOT_CERTIFIED",
        "scope": {
            "expected_cases": len(expected),
            "observed_results": len(result_rows),
            "missing_cases": len(missing),
            "duplicate_case_ids": duplicates,
            "adapter_counts": dict(sorted(adapters.items())),
            "external_adapter_cases": external_cases,
        },
        "corpus": {"repositories": corpus.get("repositories", 0), "approved": corpus.get("approved", 0), "unapproved": corpus.get("unapproved", 0), "errors": corpus.get("errors", []), "warnings": corpus.get("warnings", [])},
        "candidate_digest": candidate_digest,
        "blockers": blockers,
        "missing_case_examples": missing[:20],
        "interpretation": "This preflight is an engineering handoff artifact; it cannot certify, sign, or approve a release.",
    }
