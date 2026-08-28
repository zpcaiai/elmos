"""Profile selection, changed-path planning and release orchestration."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .attestation import build_attestation_request, evidence_binding, verify_attestation_binding
from .campaign import validate_release_result_set
from .candidate import verify_frozen_candidate
from .gates import evaluate_gate
from .planner import build_plan as build_risk_plan, validate_plan
from .runner import case_seeds, expected_case_runs, run_cases
from .adapters import EXTERNAL_ADAPTERS
from .external_harness import ExternalExecutionContext, ExternalHarnessRouter
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


def build_plan(package_root: Path, *, changed_from: str | None = None, root_for_git: Path | None = None, history_path: Path | None = None, max_cases: int = 500, seed: int = 17, shard_count: int = 8, candidate_digest: str | None = None, profile: str | None = None) -> dict[str, Any]:
    """Build a digest-bound risk plan; release profiles must use full scope."""

    return build_risk_plan(package_root, changed_from=changed_from, history_path=history_path, max_cases=max_cases, seed=seed, shard_count=shard_count, candidate_digest=candidate_digest, profile=profile)


def shard_cases(cases: list[dict[str, Any]], *, shard_index: int, shard_count: int, corpus_commit: str = "", candidate_digest: str = "", seed: int = 0) -> list[dict[str, Any]]:
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError("invalid shard index/count")
    selected: list[dict[str, Any]] = []
    for case in cases:
        key = f"{case['id']}|{corpus_commit}|{candidate_digest}|{seed}".encode()
        if int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % shard_count == shard_index:
            selected.append(case)
    return selected


def run_profile(
    package_root: Path,
    cases: list[dict[str, Any]],
    *,
    profile: str,
    output: Path,
    state_db: Path | None = None,
    artifact_root: Path | None = None,
    allow_unavailable: bool = False,
    owner: str | None = None,
    run_id: str | None = None,
    resume: bool = False,
    candidate: dict[str, Any] | None = None,
    external_router: ExternalHarnessRouter | None = None,
    external_context: ExternalExecutionContext | None = None,
    trust_store: dict[str, Any] | None = None,
    license_reviews_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not cases:
        raise ValueError("refuse to execute an empty ETGB plan")
    validation = validate_package(package_root, release=profile in {"release", "golden"}, trust_store=trust_store, license_reviews_path=license_reviews_path)
    if not validation.get("valid"):
        raise ValueError("package validation failed; refuse execution")
    if profile in {"release", "golden"}:
        if candidate is None:
            raise ValueError("release/golden execution requires a frozen candidate")
        candidate_errors = verify_frozen_candidate(candidate)
        if candidate_errors:
            raise ValueError("invalid frozen candidate: " + "; ".join(candidate_errors))
    has_external_cases = any(str(case.get("execution", {}).get("adapter")) in EXTERNAL_ADAPTERS for case in cases)
    if has_external_cases and (external_router is None or external_context is None):
        if external_router is not None or external_context is not None:
            raise ValueError("external Harness router and execution context must be supplied together")
    if external_router is not None and external_context is None:
        raise ValueError("external Harness router requires execution context")
    if external_context is not None:
        if candidate is None:
            raise ValueError("external Harness execution requires a frozen candidate")
        candidate_errors = verify_frozen_candidate(candidate)
        if candidate_errors:
            raise ValueError("invalid frozen candidate: " + "; ".join(candidate_errors))
        if candidate.get("candidate_digest") != external_context.candidate_digest:
            raise ValueError("external Harness context is not bound to the frozen candidate")
    results = run_cases(
        cases,
        package_root,
        profile=profile,
        state_db=state_db,
        artifact_root=artifact_root,
        allow_unavailable=allow_unavailable,
        owner=owner,
        run_id=run_id,
        resume=resume,
        candidate=candidate,
        external_router=external_router,
        external_context=external_context,
    )
    expected_runs = expected_case_runs(cases, profile)
    observed_runs = [(str(result.get("case_id")), int(result.get("seed", 0))) for result in results]
    complete = len(observed_runs) == len(expected_runs) and set(observed_runs) == expected_runs and len(set(observed_runs)) == len(observed_runs) and not any(result.get("status") in {"unavailable", "skipped"} for result in results)
    score = score_results(results, package_root, expected_count=len(expected_runs), complete=complete, corpus_release=profile in {"release", "golden"}, trust_store=trust_store, license_reviews_path=license_reviews_path)
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


def gate_profile(package_root: Path, results: list[dict[str, Any]], *, profile: str, external_attested: bool = False, independent_verifier: str | None = None, external_attestation: dict[str, Any] | None = None, trust_store: dict[str, Any] | None = None, candidate_digest: str | None = None, license_reviews_path: Path | None = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    validation = validate_package(package_root, release=profile in {"release", "golden"}, trust_store=trust_store, license_reviews_path=license_reviews_path)
    coverage = coverage_report(package_root)
    expected_scope = select_cases(package_root, profile=profile)
    expected_runs = expected_case_runs(expected_scope, profile)
    observed_runs = [(str(result.get("case_id")), int(result.get("seed", 0))) for result in results]
    complete = len(observed_runs) == len(expected_runs) and set(observed_runs) == expected_runs and len(set(observed_runs)) == len(observed_runs) and not any(result.get("status") in {"unavailable", "skipped"} for result in results)
    result_set_validation: dict[str, Any] = {"status": "NOT_APPLICABLE", "certification_status": "NOT_CERTIFIED"}
    if profile in {"release", "golden"}:
        if plan is None:
            complete = False
            result_set_validation = {"status": "BLOCKED", "certification_status": "NOT_CERTIFIED", "errors": ["release/golden gate requires a digest-bound full plan"]}
        else:
            _, result_set_validation = validate_release_result_set(package_root, plan, results, candidate_digest=str(candidate_digest or ""), trust_store=trust_store or {})
            complete = complete and result_set_validation["status"] == "MERGED"
        validation = dict(validation)
        validation["release_result_set"] = {
            "status": result_set_validation.get("status"),
            "plan_digest": result_set_validation.get("plan_digest"),
            "result_set_digest": result_set_validation.get("result_set_digest"),
            "receipt_digest": result_set_validation.get("receipt_digest"),
        }
        if result_set_validation["status"] != "MERGED":
            validation["valid"] = False
            validation["errors"] = list(validation.get("errors", [])) + [f"result-set: {message}" for message in result_set_validation.get("errors", [])]
    score = score_results(results, package_root, expected_count=len(expected_runs), complete=complete, corpus_release=profile in {"release", "golden"}, trust_store=trust_store, license_reviews_path=license_reviews_path)
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
    decision = evaluate_gate(score=score, validation=validation, coverage=coverage, profile=profile, external_attested=external_attested, independent_verifier=independent_verifier, external_attestation=external_attestation, attestation_verification=attestation_verification, candidate_digest=candidate_digest)
    decision["result_set_validation"] = result_set_validation
    return decision


def release_preflight(package_root: Path, *, profile: str = "release", results: list[dict[str, Any]] | None = None, candidate_digest: str | None = None, trust_store: dict[str, Any] | None = None, license_reviews_path: Path | None = None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
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
    expected_runs = expected_case_runs(expected, profile)
    result_runs = [(str(result.get("case_id")), int(result.get("seed", 0))) for result in result_rows]
    missing_runs = sorted(expected_runs - set(result_runs))
    observed_ids = {case_id for case_id, _ in result_runs}
    missing = sorted(expected_ids - observed_ids)
    duplicates = sorted(f"{case_id}@{seed}" for (case_id, seed), count in Counter(result_runs).items() if count > 1)
    adapters = Counter(str(case.get("execution", {}).get("adapter", "")) for case in expected)
    external_cases = sum(count for adapter, count in adapters.items() if adapter in EXTERNAL_ADAPTERS)
    external_case_runs = sum(len(case_seeds(case, profile)) for case in expected if str(case.get("execution", {}).get("adapter", "")) in EXTERNAL_ADAPTERS)
    validation = validate_package(package_root, release=True, trust_store=trust_store, license_reviews_path=license_reviews_path)
    corpus = validation.get("corpus", {})
    blockers: list[str] = []
    if not validation.get("valid"):
        blockers.append("release package validation is not valid")
    if len(result_rows) != len(expected_runs) or missing_runs or duplicates:
        blockers.append(f"full {profile} scope requires {len(expected_runs)} distinct case-run results across {len(expected)} cases; received {len(result_rows)}")
    if external_cases:
        blockers.append(f"{external_cases} {profile} cases require independently attested external adapters")
    if corpus.get("unapproved", 0):
        blockers.append(f"{corpus['unapproved']} corpus license reviews remain unapproved or unverified")
    if not isinstance(candidate_digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest) is None:
        blockers.append("a content-bound frozen candidate digest must be supplied")
    plan_errors = ["digest-bound full release plan is not supplied"] if plan is None else validate_plan(plan)
    if plan is not None and plan.get("profile") != profile:
        plan_errors.append("plan profile does not match preflight profile")
    if plan is not None and plan.get("candidate_digest") != candidate_digest:
        plan_errors.append("plan candidate digest does not match frozen candidate")
    if plan_errors:
        blockers.append("release plan is invalid: " + "; ".join(plan_errors[:5]))
    blockers.append("independent verifier and external signed attestation remain required")
    return {
        "schema_version": "1.1",
        "profile": profile,
        "status": "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE",
        "certification_status": "NOT_CERTIFIED",
        "scope": {
            "expected_cases": len(expected),
            "expected_case_runs": len(expected_runs),
            "observed_results": len(result_rows),
            "missing_cases": len(missing),
            "missing_case_runs": len(missing_runs),
            "duplicate_case_runs": duplicates,
            "adapter_counts": dict(sorted(adapters.items())),
            "external_adapter_cases": external_cases,
            "external_adapter_case_runs": external_case_runs,
        },
        "corpus": {"repositories": corpus.get("repositories", 0), "approved": corpus.get("approved", 0), "unapproved": corpus.get("unapproved", 0), "errors": corpus.get("errors", []), "warnings": corpus.get("warnings", [])},
        "candidate_digest": candidate_digest,
        "plan": {"supplied": plan is not None, "plan_digest": plan.get("plan_digest") if isinstance(plan, dict) else None, "valid": not plan_errors, "errors": plan_errors},
        "blockers": blockers,
        "missing_case_examples": missing[:20],
        "missing_case_run_examples": [f"{case_id}@{seed}" for case_id, seed in missing_runs[:20]],
        "interpretation": "This preflight is an engineering handoff artifact; it cannot certify, sign, or approve a release.",
    }


def release_attestation_request(
    package_root: Path,
    results: list[dict[str, Any]],
    *,
    profile: str,
    candidate_digest: str | None,
    trust_store: dict[str, Any] | None = None,
    license_reviews_path: Path | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare, but never sign, the exact independent release request."""

    expected_scope = select_cases(package_root, profile=profile)
    expected_runs = expected_case_runs(expected_scope, profile)
    observed_runs = [(str(item.get("case_id")), int(item.get("seed", 0))) for item in results]
    complete = len(observed_runs) == len(expected_runs) and set(observed_runs) == expected_runs and len(set(observed_runs)) == len(expected_runs) and not any(item.get("status") in {"unavailable", "skipped"} for item in results)
    validation = validate_package(package_root, release=True, trust_store=trust_store, license_reviews_path=license_reviews_path)
    if plan is None:
        complete = False
        result_set = {"status": "BLOCKED", "errors": ["independent attestation request requires a digest-bound full plan"]}
    else:
        _, result_set = validate_release_result_set(package_root, plan, results, candidate_digest=str(candidate_digest or ""), trust_store=trust_store or {})
        complete = complete and result_set["status"] == "MERGED"
    if result_set["status"] != "MERGED":
        validation = dict(validation)
        validation["valid"] = False
        validation["errors"] = list(validation.get("errors", [])) + [f"result-set: {message}" for message in result_set.get("errors", [])]
    else:
        validation = dict(validation)
    validation["release_result_set"] = {
        "status": result_set.get("status"),
        "plan_digest": result_set.get("plan_digest"),
        "result_set_digest": result_set.get("result_set_digest"),
        "receipt_digest": result_set.get("receipt_digest"),
    }
    coverage = coverage_report(package_root)
    score = score_results(results, package_root, expected_count=len(expected_runs), complete=complete, corpus_release=True, trust_store=trust_store, license_reviews_path=license_reviews_path)
    return build_attestation_request(
        profile=profile,
        candidate_digest=candidate_digest,
        score=score,
        validation=validation,
        coverage=coverage,
        corpus=score.get("corpus", {}),
        evidence=evidence_binding(results),
    )
