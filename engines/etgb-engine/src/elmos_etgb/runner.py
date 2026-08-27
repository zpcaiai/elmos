"""ETGB execution lifecycle and adapter dispatch."""

from __future__ import annotations

import datetime as dt
import platform
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from .adapters import AdapterUnavailable, EXTERNAL_ADAPTERS, EXECUTORS
from .canonical import digest_json
from .evidence import EvidenceStore, build_evidence_manifest
from .state import StateConflict, StateStore


TERMINAL_STATUSES = frozenset({"passed", "failed", "skipped", "unavailable", "error"})


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def environment_evidence() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": shutil.which("python3") or shutil.which("python"),
        "java_available": shutil.which("java") is not None,
        "javac_available": shutil.which("javac") is not None,
        "docker_available": shutil.which("docker") is not None,
        "network_policy": "deny-by-default-local-process-only",
        "sandbox_attestation": "local-defense-in-depth-not-os-sandbox",
    }


def _finalize_result(result: dict[str, Any], *, store: EvidenceStore | None) -> dict[str, Any]:
    evidence = result.setdefault("evidence", {})
    artifacts = list(evidence.get("artifacts", []))
    if store is not None:
        manifest = build_evidence_manifest(run_id=result["run_id"], case_id=result["case_id"], result=result, artifacts=artifacts)
        manifest_artifact = store.put_json(manifest, role="evidence-manifest")
        artifacts.append(manifest_artifact)
        evidence["artifacts"] = artifacts
        evidence["manifest"] = manifest_artifact
    result["evidence"] = evidence
    return result


def execute_case(case: dict[str, Any], root: Path, *, allow_unavailable: bool = False, store: EvidenceStore | None = None, run_id: str | None = None, seed: int = 0, attempt: int = 1) -> dict[str, Any]:
    started_at = utc_now()
    started = time.monotonic()
    run_identifier = run_id or str(uuid.uuid4())
    adapter = str(case.get("execution", {}).get("adapter", ""))
    input_digest = digest_json(case)
    evidence: dict[str, Any] = {"environment": environment_evidence(), "adapter": adapter, "input_digest": input_digest, "seed": seed, "attempt": attempt, "artifacts": []}
    if store is not None:
        evidence["artifacts"].append(store.put_json(case, role="case-input"))
        evidence["artifacts"].append(store.put_json(evidence["environment"], role="environment"))
    status = "error"
    oracles: list[dict[str, Any]] = []
    silent = False
    failure_class: str | None = None
    try:
        executor = EXECUTORS.get(adapter)
        if executor is None:
            status = "unavailable"
            failure_class = "environment/dependency" if adapter in EXTERNAL_ADAPTERS else "unsupported-undisclosed"
            oracles = [{"type": "adapter-availability", "critical": True, "passed": False, "reason": f"adapter '{adapter}' is not installed or attested"}]
            evidence["required_adapter"] = adapter
        else:
            status, adapter_oracles, adapter_evidence, silent = executor(case, root, store=store)
            oracles = adapter_oracles
            for key, value in adapter_evidence.items():
                if key == "artifacts":
                    evidence.setdefault("artifacts", []).extend(value)
                else:
                    evidence[key] = value
    except TimeoutError as exc:
        status = "error"
        failure_class = "environment/dependency"
        oracles = [{"type": "execution-timeout", "critical": True, "passed": False, "message": str(exc)}]
    except Exception as exc:  # retain the failure; a runner exception is never a pass
        status = "error"
        failure_class = "harness/oracle defect" if adapter in EXECUTORS else "environment/dependency"
        oracles = [{"type": "runner-error", "critical": True, "passed": False, "error_type": type(exc).__name__, "message": str(exc)}]
    finished_at = utc_now()
    result = {
        "schema_version": "1.0",
        "run_id": run_identifier,
        "case_id": case["id"],
        "case_digest": input_digest,
        "business_line": case.get("business_line"),
        "priority": case.get("priority"),
        "level": case.get("level"),
        "seed": seed,
        "attempt": attempt,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "oracle_results": oracles,
        "evidence": evidence,
        "silent_semantic_error": bool(silent),
        "failure_class": failure_class,
        "claim_state": "success" if status == "passed" else "not-claimable",
        "cost": {"token_input": 0, "token_output": 0, "credit_usd": 0.0, "wall_clock_ms": int((time.monotonic() - started) * 1000)},
    }
    return _finalize_result(result, store=store)


def _seeds(case: dict[str, Any], profile: str | None) -> list[int]:
    declared = case.get("execution", {}).get("random_seeds")
    if not declared or profile not in {"nightly", "weekly", "release", "golden", "exhaustive"}:
        return [0]
    return [int(seed) for seed in declared]


def run_cases(cases: list[dict[str, Any]], root: Path, *, allow_unavailable: bool = False, state_db: Path | None = None, run_id: str | None = None, profile: str | None = None, owner: str | None = None, resume: bool = False, artifact_root: Path | None = None, candidate: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run selected cases deterministically, optionally with durable state."""

    root = root.resolve(strict=True)
    owner = owner or f"local:{uuid.uuid4()}"
    selected_run_id = run_id or str(uuid.uuid4())
    store = EvidenceStore((artifact_root or root / ".etgb" / "evidence") / selected_run_id)
    durable: StateStore | None = StateStore(state_db) if state_db else None
    token = ""
    try:
        if durable:
            plan_digest = digest_json([case["id"] for case in cases])
            row = durable.create_run(run_id=selected_run_id, idempotency_key=digest_json({"plan": plan_digest, "profile": profile or "adhoc", "candidate": candidate or {}}), suite_id="elmos-etgb-sota-v1", profile=profile or "adhoc", owner=owner, plan_digest=plan_digest, candidate=candidate or {}, budget={})
            selected_run_id = row["run_id"]
            store = EvidenceStore((artifact_root or root / ".etgb" / "evidence") / selected_run_id)
            if row["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                persisted = durable.get_case_results(selected_run_id)
                if not persisted:
                    raise StateConflict(f"terminal run {selected_run_id} has no persisted case results")
                return [json_result(item["result_json"]) for item in persisted if item.get("result_json")]
            token = durable.claim_run(selected_run_id, owner=owner)
            if row["status"] == "PLANNED":
                durable.transition(selected_run_id, owner=owner, fencing_token=token, expected="PLANNED", new_status="PREPARING")
            current = durable.get_run(selected_run_id)
            if current and current["status"] == "PREPARING":
                durable.transition(selected_run_id, owner=owner, fencing_token=token, expected="PREPARING", new_status="RUNNING")
            elif current and current["status"] != "RUNNING":
                raise StateConflict(f"run cannot resume from lifecycle status {current['status']}")
        results: list[dict[str, Any]] = []
        for case in cases:
            for seed in _seeds(case, profile):
                if durable and resume:
                    existing = [row for row in durable.get_case_results(selected_run_id) if row["case_id"] == case["id"] and row["seed"] == seed and row["result_digest"]]
                    if existing:
                        results.append(json_result(existing[0]["result_json"]))
                        continue
                result = execute_case(case, root, allow_unavailable=allow_unavailable, store=store, run_id=selected_run_id, seed=seed)
                results.append(result)
                if durable:
                    durable.save_case_result(selected_run_id, case["id"], seed, owner=owner, fencing_token=token, result=result)
        if durable:
            current = durable.get_run(selected_run_id)
            if not current or current["status"] != "RUNNING":
                raise StateConflict("run lifecycle changed before scoring")
            durable.transition(selected_run_id, owner=owner, fencing_token=token, expected="RUNNING", new_status="SCORING")
            durable.transition(selected_run_id, owner=owner, fencing_token=token, expected="SCORING", new_status="COMPLETED")
        return results
    finally:
        if durable:
            durable.close()


def json_result(value: str) -> dict[str, Any]:
    import json
    result = json.loads(value)
    if not isinstance(result, dict):
        raise StateConflict("persisted result is not an object")
    return result
