"""Profile selection, changed-path planning and release orchestration."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .attestation import build_attestation_request, evidence_binding, verify_attestation_binding
from .campaign import validate_release_result_set
from .candidate import verify_frozen_candidate
from .canonical import digest_json
from .gates import evaluate_gate
from .governance import campaign_context_from_results, verify_release_governance
from .planner import build_plan as build_risk_plan, validate_plan_scope
from .runner import case_seeds, expected_case_runs, run_cases
from .adapters import EXTERNAL_ADAPTERS
from .external_harness import ExternalExecutionContext, ExternalHarnessRouter
from .scoring import score_results
from .validation import coverage_report, load_cases, validate_package


PROTECTED_EXECUTION_PROFILES = frozenset({"release", "golden", "release-canary"})


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


def _external_adapter_set(cases: list[dict[str, Any]]) -> set[str]:
    return {
        str(case.get("execution", {}).get("adapter", ""))
        for case in cases
        if str(case.get("execution", {}).get("adapter", "")) in EXTERNAL_ADAPTERS
    }


def _validate_execution_plan(
    package_root: Path,
    cases: list[dict[str, Any]],
    *,
    profile: str,
    plan: Mapping[str, Any] | None,
) -> list[str]:
    """Require a complete immutable plan and an exact full-or-shard selection."""

    if profile not in PROTECTED_EXECUTION_PROFILES:
        return []
    if plan is None:
        return [f"{profile} execution requires a digest-bound immutable plan"]
    errors = validate_plan_scope(package_root, dict(plan))
    if plan.get("profile") != profile:
        errors.append("execution profile does not match the plan profile")
    selected = [str(case.get("id")) for case in cases]
    if len(selected) != len(set(selected)):
        errors.append("execution selection contains duplicate case identities")
    allowed_scopes = [set(str(value) for value in plan.get("case_ids", []))]
    allowed_scopes.extend(
        set(str(value) for value in shard.get("case_ids", []))
        for shard in plan.get("shards", [])
        if isinstance(shard, Mapping)
    )
    if set(selected) not in allowed_scopes:
        errors.append("execution selection must equal the full plan or exactly one declared shard")
    return errors


def _verify_result_governance(
    results: list[dict[str, Any]],
    *,
    candidate_digest: str | None,
    plan: Mapping[str, Any] | None,
    trust_store: Mapping[str, Any] | None,
    role_assignment: Mapping[str, Any] | None,
    production_authority: Mapping[str, Any] | None,
    verifier_id: str | None = None,
) -> dict[str, Any]:
    """Bind signed governance records to the exact observed campaign."""

    context = campaign_context_from_results(results)
    errors = list(context.get("errors", []))
    if context.get("candidate_digest") != candidate_digest:
        errors.append("campaign governance candidate digest does not match the gate input")
    plan_digest = plan.get("plan_digest") if isinstance(plan, Mapping) else None
    if context.get("plan_digest") != plan_digest:
        errors.append("campaign governance plan digest does not match the release plan")
    if errors:
        verification: dict[str, Any] = {
            "schema_version": "1.0",
            "valid": False,
            "status": "BLOCKED",
            "errors": errors,
            "certification_status": "NOT_CERTIFIED",
        }
    else:
        verification = verify_release_governance(
            role_assignment=role_assignment,
            production_authority=production_authority,
            trust_store=trust_store or {},
            candidate_digest=str(context["candidate_digest"]),
            plan_digest=str(context["plan_digest"]),
            tenant_id=str(context["tenant_id"]),
            project_id=str(context["project_id"]),
            task_id=str(context["task_id"]),
            environment_id=str(context["environment_id"]),
            authority_id=str(context["authority_id"]),
            executor_ids=context.get("executor_ids", []),
            owner_ids=context.get("owner_ids", []),
            verifier_id=verifier_id,
        )
    combined_errors = list(dict.fromkeys([*errors, *verification.get("errors", [])]))
    result = {
        "schema_version": "1.0",
        "valid": bool(context.get("valid")) and bool(verification.get("valid")),
        "status": "VERIFIED" if bool(context.get("valid")) and bool(verification.get("valid")) else "BLOCKED",
        "campaign_context": context,
        "verification": verification,
        "errors": combined_errors,
        "certification_status": "NOT_CERTIFIED",
    }
    result["governance_digest"] = digest_json(result)
    return result


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
    plan: Mapping[str, Any] | None = None,
    role_assignment: Mapping[str, Any] | None = None,
    production_authority: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not cases:
        raise ValueError("refuse to execute an empty ETGB plan")
    protected = profile in PROTECTED_EXECUTION_PROFILES
    plan_errors = _validate_execution_plan(package_root, cases, profile=profile, plan=plan)
    if plan_errors:
        raise ValueError("invalid protected execution plan: " + "; ".join(plan_errors))
    validation = validate_package(package_root, release=protected, trust_store=trust_store, license_reviews_path=license_reviews_path)
    if not validation.get("valid"):
        raise ValueError("package validation failed; refuse execution")
    if protected:
        if candidate is None:
            raise ValueError("release/golden/canary execution requires a frozen candidate")
        candidate_errors = verify_frozen_candidate(candidate)
        if candidate_errors:
            raise ValueError("invalid frozen candidate: " + "; ".join(candidate_errors))
    selected_external_adapters = _external_adapter_set(cases)
    if (external_router is None) != (external_context is None):
        raise ValueError("external Harness router and execution context must be supplied together")
    if protected and external_context is None:
        raise ValueError("release/golden/canary execution requires a trusted external execution context")
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
        if isinstance(plan, Mapping) and plan.get("plan_digest") != external_context.plan_digest:
            raise ValueError("external Harness context is not bound to the protected plan")
    if protected:
        assert isinstance(plan, Mapping)
        planned_ids = set(str(value) for value in plan.get("case_ids", []))
        required_adapters = _external_adapter_set(
            [case for case in load_cases(package_root) if str(case.get("id")) in planned_ids]
        )
        if required_adapters and external_router is None:
            raise ValueError("protected execution requires the external Harness router")
        assert external_router is not None
        assert external_context is not None
        capability = external_router.capability_report(required_adapters, require_production_transport=True)
        if capability.get("status") != "READY_FOR_EXTERNAL_EXECUTION_CONFIG":
            raise ValueError("external Harness configuration is not ready: " + "; ".join(
                [
                    f"missing adapters={capability.get('missing_adapters', [])}",
                    f"missing credentials={capability.get('missing_credential_adapters', [])}",
                    f"invalid mTLS keys={capability.get('invalid_mtls_key_adapters', [])}",
                    f"missing CA bundles={capability.get('missing_ca_bundle_adapters', [])}",
                    f"missing mTLS={capability.get('missing_mtls_adapters', [])}",
                ]
            ))
        governance = verify_release_governance(
            role_assignment=role_assignment,
            production_authority=production_authority,
            trust_store=trust_store or {},
            candidate_digest=external_context.candidate_digest,
            plan_digest=external_context.plan_digest,
            tenant_id=external_context.tenant_id,
            project_id=external_context.project_id,
            task_id=external_context.task_id,
            environment_id=external_context.environment_id,
            authority_id=external_context.authority_id,
            executor_ids=external_router.configured_executor_ids(required_adapters),
            owner_ids=[external_context.owner_id],
        )
        if not governance.get("valid"):
            raise ValueError("release governance is not valid: " + "; ".join(governance.get("errors", [])))
    elif selected_external_adapters and external_router is not None:
        capability = external_router.capability_report(selected_external_adapters)
        if capability.get("status") != "READY_FOR_EXTERNAL_EXECUTION_CONFIG":
            raise ValueError("selected external Harness configuration is not ready")
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
    score = score_results(results, package_root, expected_count=len(expected_runs), complete=complete, corpus_release=protected, trust_store=trust_store, license_reviews_path=license_reviews_path)
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


def gate_profile(package_root: Path, results: list[dict[str, Any]], *, profile: str, external_attested: bool = False, independent_verifier: str | None = None, external_attestation: dict[str, Any] | None = None, trust_store: dict[str, Any] | None = None, candidate_digest: str | None = None, license_reviews_path: Path | None = None, plan: dict[str, Any] | None = None, role_assignment: Mapping[str, Any] | None = None, production_authority: Mapping[str, Any] | None = None) -> dict[str, Any]:
    validation = validate_package(package_root, release=profile in {"release", "golden"}, trust_store=trust_store, license_reviews_path=license_reviews_path)
    coverage = coverage_report(package_root)
    expected_scope = select_cases(package_root, profile=profile)
    expected_runs = expected_case_runs(expected_scope, profile)
    observed_runs = [(str(result.get("case_id")), int(result.get("seed", 0))) for result in results]
    complete = len(observed_runs) == len(expected_runs) and set(observed_runs) == expected_runs and len(set(observed_runs)) == len(observed_runs) and not any(result.get("status") in {"unavailable", "skipped"} for result in results)
    result_set_validation: dict[str, Any] = {"status": "NOT_APPLICABLE", "certification_status": "NOT_CERTIFIED"}
    governance_validation: dict[str, Any] = {
        "status": "NOT_APPLICABLE",
        "valid": True,
        "certification_status": "NOT_CERTIFIED",
    }
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
        governance_validation = _verify_result_governance(
            results,
            candidate_digest=candidate_digest,
            plan=plan,
            trust_store=trust_store,
            role_assignment=role_assignment,
            production_authority=production_authority,
            verifier_id=independent_verifier,
        )
        validation["release_governance"] = governance_validation
        if not governance_validation.get("valid"):
            validation["valid"] = False
            validation["errors"] = list(validation.get("errors", [])) + [
                f"release-governance: {message}" for message in governance_validation.get("errors", [])
            ]
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
    decision["release_governance"] = governance_validation
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
    plan_errors = ["digest-bound full release plan is not supplied"] if plan is None else validate_plan_scope(package_root, plan)
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


def external_campaign_preflight(
    package_root: Path,
    *,
    candidate: Mapping[str, Any],
    plan: Mapping[str, Any],
    router: ExternalHarnessRouter,
    role_assignment: Mapping[str, Any] | None,
    production_authority: Mapping[str, Any] | None,
    trust_store: Mapping[str, Any],
    license_reviews_path: Path | None,
    tenant_id: str,
    project_id: str,
    task_id: str,
    environment_id: str,
    authority_id: str,
    owner_ids: list[str],
) -> dict[str, Any]:
    """Validate every prerequisite for a real external campaign without running it."""

    blockers: list[str] = []
    profile = str(plan.get("profile", ""))
    if profile not in PROTECTED_EXECUTION_PROFILES:
        blockers.append("external campaign requires a release, golden, or release-canary plan")
    candidate_errors = verify_frozen_candidate(dict(candidate))
    blockers.extend(f"candidate: {message}" for message in candidate_errors)
    plan_errors = validate_plan_scope(package_root, dict(plan))
    blockers.extend(f"plan: {message}" for message in plan_errors)
    candidate_digest = str(candidate.get("candidate_digest", ""))
    if plan.get("candidate_digest") != candidate_digest:
        blockers.append("plan candidate digest does not match the frozen candidate")
    if not owner_ids:
        blockers.append("at least one authorized campaign owner is required")
    for owner_id in owner_ids:
        try:
            ExternalExecutionContext(
                tenant_id=tenant_id,
                project_id=project_id,
                task_id=task_id,
                candidate_digest=candidate_digest,
                plan_digest=str(plan.get("plan_digest", "")),
                environment_id=environment_id,
                authority_id=authority_id,
                owner_id=owner_id,
                fencing_token=1,
                checkpoint_digest="sha256:" + "0" * 64,
            )
        except ValueError as exc:
            blockers.append(f"campaign context: {exc}")
    package_validation = validate_package(
        package_root,
        release=True,
        trust_store=dict(trust_store),
        license_reviews_path=license_reviews_path,
    )
    if not package_validation.get("valid"):
        blockers.append("release package and corpus validation is not valid")
    planned_ids = set(str(value) for value in plan.get("case_ids", []))
    planned_cases = [case for case in load_cases(package_root) if str(case.get("id")) in planned_ids]
    required_adapters = _external_adapter_set(planned_cases)
    harness = router.capability_report(required_adapters, require_production_transport=True)
    if harness.get("status") != "READY_FOR_EXTERNAL_EXECUTION_CONFIG":
        blockers.append("external Harness endpoints, credentials, CA, or mTLS configuration is incomplete")
    governance = verify_release_governance(
        role_assignment=role_assignment,
        production_authority=production_authority,
        trust_store=trust_store,
        candidate_digest=candidate_digest,
        plan_digest=str(plan.get("plan_digest", "")),
        tenant_id=tenant_id,
        project_id=project_id,
        task_id=task_id,
        environment_id=environment_id,
        authority_id=authority_id,
        executor_ids=router.configured_executor_ids(required_adapters),
        owner_ids=owner_ids,
    )
    if not governance.get("valid"):
        blockers.append("signed separation-of-duties and production authorization are not valid")
    return {
        "schema_version": "1.0",
        "status": "READY_FOR_EXTERNAL_EXECUTION" if not blockers else "BLOCKED",
        "certification_status": "NOT_CERTIFIED",
        "profile": profile,
        "candidate_digest": candidate_digest,
        "plan_digest": plan.get("plan_digest"),
        "scope": {
            "planned_cases": len(planned_cases),
            "required_external_adapters": sorted(required_adapters),
            "required_external_adapter_count": len(required_adapters),
        },
        "package": {
            "valid": bool(package_validation.get("valid")),
            "case_count": package_validation.get("case_count"),
            "corpus": package_validation.get("corpus", {}),
            "runtime_adapters": package_validation.get("runtime_adapters", {}),
            "errors": package_validation.get("errors", [])[:50],
        },
        "harness": harness,
        "governance": governance,
        "blockers": blockers,
        "external_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "interpretation": "READY permits the separately authorized campaign to start; it is not execution evidence or certification.",
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
    role_assignment: Mapping[str, Any] | None = None,
    production_authority: Mapping[str, Any] | None = None,
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
    governance = _verify_result_governance(
        results,
        candidate_digest=candidate_digest,
        plan=plan,
        trust_store=trust_store,
        role_assignment=role_assignment,
        production_authority=production_authority,
    )
    validation["release_governance"] = governance
    if not governance.get("valid"):
        complete = False
        validation["valid"] = False
        validation["errors"] = list(validation.get("errors", [])) + [
            f"release-governance: {message}" for message in governance.get("errors", [])
        ]
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
