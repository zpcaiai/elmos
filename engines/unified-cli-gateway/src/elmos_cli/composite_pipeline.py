"""Composite modernization plan with honest, digest-bound evidence states.

The unified CLI is a local control plane. It may ingest source, create an
exact directional transformation plan, create formal/fuzzing requests, and
produce a content-addressed plan bundle. It must not manufacture target code,
solver results, fuzz results, signatures, or certification receipts. Those
results require separately authorized native/provider runners and independent
verifiers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
import time
import uuid


_ACTION_CACHE_STORE: dict[str, dict[str, Any]] = {}
_NOT_RUN = "NOT_RUN"
_NOT_CERTIFIED = "NOT_CERTIFIED"


def derive_action_key(
    src_lang: str,
    tgt_lang: str,
    code_snippet: str,
    options: Mapping[str, Any] | None = None,
) -> str:
    seed = f"{src_lang}:{tgt_lang}:{code_snippet}:{json.dumps(options or {}, sort_keys=True)}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def _error_result(
    *,
    run_id: str,
    timestamp: str,
    route: str,
    action_key: str,
    reason: str,
    status: str = "INPUT_REJECTED",
) -> dict[str, Any]:
    return {
        "status": status,
        "run_id": run_id,
        "action_key": action_key,
        "cache_hit": False,
        "timestamp": timestamp,
        "route": route,
        "reason": reason,
        "external_evidence": _NOT_RUN,
        "certification": _NOT_CERTIFIED,
        "stages": {},
    }


def run_composite_pipeline(
    src_lang: str = "java",
    tgt_lang: str = "csharp",
    code_snippet: str = "",
    options: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Prepare a modernization run without claiming external execution.

    Backward-compatible keyword aliases are retained for callers of the old
    gateway. The returned ``transformed_code`` is intentionally ``None``; a
    target artifact may only be supplied by an authorized adapter after a
    typed semantic IR, build, runtime, and evidence chain exist.
    """

    if "source_language" in kwargs:
        src_lang = kwargs["source_language"]
    if "target_language" in kwargs:
        tgt_lang = kwargs["target_language"]
    if "source_code" in kwargs:
        code_snippet = kwargs["source_code"]
    if "budget_limit_usd" in kwargs:
        opts = dict(options or {})
        opts["budget_limit_usd"] = kwargs["budget_limit_usd"]
        options = opts

    opts = dict(options or {})
    start_time = time.perf_counter()
    run_id = f"elmos-run-{uuid.uuid4().hex[:12]}"
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    route = f"{src_lang} -> {tgt_lang}"
    action_key = derive_action_key(src_lang, tgt_lang, code_snippet, opts)

    try:
        budget_limit = float(opts.get("budget_limit_usd", 50.0))
    except (TypeError, ValueError):
        return _error_result(
            run_id=run_id,
            timestamp=timestamp,
            route=route,
            action_key=action_key,
            reason="budget_limit_usd must be numeric",
        )
    if budget_limit <= 0.0:
        return _error_result(
            run_id=run_id,
            timestamp=timestamp,
            route=route,
            action_key=action_key,
            status="BUDGET_EXHAUSTED",
            reason="Execution blocked: budget limit must be greater than 0",
        )

    cache_enabled = bool(opts.get("cache_enabled", True))
    if cache_enabled and action_key in _ACTION_CACHE_STORE:
        cached = dict(_ACTION_CACHE_STORE[action_key])
        cached["run_id"] = run_id
        cached["timestamp"] = timestamp
        cached["cache_hit"] = True
        cached["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 2)
        return cached

    source_bytes = code_snippet.encode("utf-8")
    source_hash = "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    stage_ingest = {
        "status": "INGESTED",
        "sha256": source_hash,
        "bytes": len(source_bytes),
        "duration_ms": 0.0,
    }

    try:
        from elmos_polyglot_compiler.service import (
            check_smt_formula,
            run_differential_fuzzing,
            transform_snippet,
        )

        transformation_plan = transform_snippet(src_lang, tgt_lang, code_snippet)
        proof_obligation = (
            f"forall x: Invariant_{src_lang}(x) ==> Invariant_{tgt_lang}(x)"
        )
        formal_plan = check_smt_formula(proof_obligation)
        fuzz_cases = opts.get("fuzz_cases", 25)
        if not isinstance(fuzz_cases, int) or isinstance(fuzz_cases, bool):
            raise ValueError("fuzz_cases must be an integer")
        fuzz_plan = run_differential_fuzzing(src_lang, tgt_lang, fuzz_cases)
    except (ImportError, TypeError, ValueError) as exc:
        return _error_result(
            run_id=run_id,
            timestamp=timestamp,
            route=route,
            action_key=action_key,
            reason=str(exc),
        )

    # The formal bridge emits source candidates only. It never verifies them;
    # retaining the request makes the missing native evidence inspectable.
    try:
        from elmos_formal_assurance.lean_dafny_bridge import generate_lean4_proof

        proof_request = generate_lean4_proof(
            obligation_name=f"PreserveInvariant_{src_lang}_to_{tgt_lang}",
            formula=proof_obligation,
            source_lang=src_lang,
            target_lang=tgt_lang,
        )
    except (ImportError, TypeError, ValueError) as exc:
        proof_request = {
            "verification_status": _NOT_RUN,
            "proof_status": _NOT_RUN,
            "error": str(exc),
            "external_evidence_status": _NOT_RUN,
            "independent_verification_status": _NOT_RUN,
            "certification_status": _NOT_CERTIFIED,
        }

    formal_verdict = {
        "formula": proof_obligation,
        "formula_digest": formal_plan.get("formula_digest"),
        "solver": formal_plan.get("solver_family", "SMT_Z3"),
        "status": _NOT_RUN,
        "verdict": "UNDETERMINED",
        "counterexamples_found": 0,
        "soundness_verified": False,
        "solver_plan": formal_plan,
        "proof_request": proof_request,
        "missing_evidence": [
            "AUTHORIZED_SOLVER_EXECUTION",
            "NATIVE_PROOF_VERIFICATION",
            "INDEPENDENT_PROOF_VERIFICATION",
        ],
    }
    fuzz_verdict = {
        **fuzz_plan,
        "status": _NOT_RUN,
        "cases_generated": 0,
        "cases_passed": 0,
        "oracle_divergences": 0,
        "missing_evidence": fuzz_plan.get("missing_evidence", []),
    }

    # This is a local estimate, not a charge, invoice, or accounting event.
    tokens = len(code_snippet.split()) * 4 + 120
    cost_usd = round(tokens * 0.0000035, 6)
    metering = {
        "tokens_metered": tokens,
        "estimated_cost_usd": cost_usd,
        "tier": "enterprise-standard",
        "currency": "USD",
        "status": "ESTIMATE_ONLY",
        "charge_created": False,
        "duration_ms": 0.0,
    }

    bundle_data = {
        "schema_version": "1.0",
        "kind": "composite-modernization-plan",
        "run_id": run_id,
        "action_key": action_key,
        "timestamp": timestamp,
        "route": route,
        "source_hash": source_hash,
        "target_hash": None,
        "transformation_plan": transformation_plan,
        "formal_assurance": formal_verdict,
        "differential_fuzzing": fuzz_verdict,
        "metering": metering,
        "readiness": "READY_FOR_EXTERNAL_GATE",
        "certification": _NOT_CERTIFIED,
    }
    bundle_digest = _digest(bundle_data)
    total_duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    stage_polyglot = {
        "status": transformation_plan.get("status", "EXTERNAL_ADAPTER_REQUIRED"),
        "sha256": None,
        "target_code": None,
        "plan_digest": _digest(transformation_plan),
        "duration_ms": 0.0,
    }

    result = {
        "status": "READY_FOR_EXTERNAL_GATE",
        "run_id": run_id,
        "action_key": action_key,
        "cache_hit": False,
        "timestamp": timestamp,
        "total_duration_ms": total_duration_ms,
        "duration_ms": total_duration_ms,
        "route": route,
        "source_hash": source_hash,
        "target_hash": None,
        "transformed_code": None,
        "transformation_plan": transformation_plan,
        "formal_assurance": formal_verdict,
        "differential_fuzzing": fuzz_verdict,
        "metering": metering,
        "evidence_bundle_digest": bundle_digest,
        "external_evidence": _NOT_RUN,
        "certification": _NOT_CERTIFIED,
        "stages": {
            "source_ingestion": stage_ingest,
            "polyglot_transform": stage_polyglot,
            "smt_formal_proof": formal_verdict,
            "differential_fuzz": fuzz_verdict,
            "finops_metering": metering,
        },
        "receipt": {
            "slsa_level": "NOT_ASSESSED",
            "provenance_status": _NOT_RUN,
            "certification": _NOT_CERTIFIED,
            "digest": bundle_digest,
        },
        "missing_evidence": sorted(
            {
                "AUTHORIZED_TRANSFORMATION_ADAPTER",
                "TARGET_BUILD_AND_RUNTIME",
                "AUTHORIZED_SOLVER_EXECUTION",
                "DIFFERENTIAL_FUZZ_EXECUTION",
                "INDEPENDENT_VERIFICATION",
                "SIGNED_CERTIFICATION_DECISION",
            }
        ),
    }

    if cache_enabled:
        _ACTION_CACHE_STORE[action_key] = dict(result)
    return result
