#!/usr/bin/env python3
"""Derive the fail-closed repository gate for Precision Migration B01-B44."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import (
    TrustStore,
    canonical_digest,
    configured_roots,
    verify_content_reference,
)


MANIFEST = ROOT / "docs" / "precision-migration-b01-44" / "installed-manifest.json"
LOCAL_CHECKS = (
    "source_package_integrity",
    "installed_skill_integrity",
    "runtime_interfaces",
    "runtime_unit_tests",
    "schema_validation",
    "web_catalog",
)
EXTERNAL_CHECKS = (
    "exact_source_target_builds",
    "native_toolchain_matrix",
    "independent_holdout",
    "representative_workloads",
    "formal_proof_where_claimed",
    "shadow_canary_rollback",
    "security_review",
    "customer_acceptance",
)
STATES = {"PASSED", "FAILED", "INCONCLUSIVE", "NOT_RUN"}


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def gate_binding_digest(request: dict[str, Any]) -> str:
    return canonical_digest(
        {
            "schema_version": request.get("schema_version"),
            "package_identity": request.get("package_identity"),
            "local_check_states": {
                name: request.get("local_checks", {}).get(name, {}).get("state")
                for name in LOCAL_CHECKS
            },
            "external_check_states": {
                name: request.get("external_checks", {}).get(name, {}).get("state")
                for name in EXTERNAL_CHECKS
            },
        }
    )


def validate_checks(
    group: str,
    payload: Any,
    required: tuple[str, ...],
    *,
    roots: tuple[Path, ...],
    trust_store: TrustStore | None,
    request_digest: str,
) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    failures: list[str] = []
    verified: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(payload, dict):
        return [f"{group} must be an object"], verified
    if set(payload) != set(required):
        failures.append(f"{group} must contain exactly {list(required)}")
    for name in required:
        item = payload.get(name)
        if not isinstance(item, dict):
            failures.append(f"{group}.{name} is missing")
            continue
        state = item.get("state")
        refs = item.get("evidence_refs")
        if state not in STATES:
            failures.append(f"{group}.{name}.state is invalid")
        if not isinstance(refs, list):
            failures.append(f"{group}.{name}.evidence_refs is invalid")
            continue
        if state == "PASSED" and not refs:
            failures.append(f"{group}.{name} claims PASSED without evidence")
            continue
        if state != "PASSED" and refs:
            failures.append(f"{group}.{name} must not attach positive evidence to state {state}")
            continue
        observations: list[dict[str, Any]] = []
        for index, reference in enumerate(refs):
            try:
                observed = verify_content_reference(reference, roots)
                if trust_store is None:
                    raise ValueError("a trust store is required for PASSED gate evidence")
                authorization = trust_store.verify_envelope(
                    reference.get("authorization") if isinstance(reference, dict) else None,
                    required_role="gate-evidence-authorizer",
                    bindings={
                        "record_type": "GATE_EVIDENCE_AUTHORIZATION",
                        "gate_request_digest": request_digest,
                        "check_group": group,
                        "check_name": name,
                        "artifact_digest": reference.get("digest") if isinstance(reference, dict) else None,
                    },
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                failures.append(f"{group}.{name}.evidence_refs[{index}] failed verification: {exc}")
            else:
                observations.append({**observed, "authorization": authorization})
        if observations:
            verified[name] = observations
    return failures, verified


def evaluate_gate(
    request: dict[str, Any],
    *,
    installed: dict[str, Any],
    evidence_roots: Iterable[Path] | None = None,
    trust_store: TrustStore | Path | None = None,
) -> dict[str, Any]:
    roots = configured_roots(evidence_roots)
    if isinstance(trust_store, Path):
        trust_store = TrustStore.load(trust_store)
    failures: list[str] = []
    if request.get("schema_version") != 1:
        failures.append("schema_version must be 1")
    identity = request.get("package_identity")
    if not isinstance(identity, dict):
        failures.append("package_identity must be an object")
    else:
        for key in ("source_package_manifest_sha256", "source_tree_sha256"):
            if identity.get(key) != installed.get(key):
                failures.append(f"package identity mismatch: {key}")
    request_digest = gate_binding_digest(request)
    local_failures, local_verified = validate_checks(
        "local_checks",
        request.get("local_checks"),
        LOCAL_CHECKS,
        roots=roots,
        trust_store=trust_store,
        request_digest=request_digest,
    )
    external_failures, external_verified = validate_checks(
        "external_checks",
        request.get("external_checks"),
        EXTERNAL_CHECKS,
        roots=roots,
        trust_store=trust_store,
        request_digest=request_digest,
    )
    failures.extend(local_failures)
    failures.extend(external_failures)
    local = request.get("local_checks") if isinstance(request.get("local_checks"), dict) else {}
    external = request.get("external_checks") if isinstance(request.get("external_checks"), dict) else {}
    local_ready = not failures and all(
        local.get(name, {}).get("state") == "PASSED" and name in local_verified
        for name in LOCAL_CHECKS
    )
    external_complete = not failures and all(
        external.get(name, {}).get("state") == "PASSED" and name in external_verified
        for name in EXTERNAL_CHECKS
    )
    if failures:
        decision = "REJECTED"
    elif local_ready:
        decision = "READY_FOR_EXTERNAL_GATE"
    else:
        decision = "NOT_READY"
    result_without_digest = {
        "schema_version": 1,
        "namespace": installed.get("namespace"),
        "batch_count": installed.get("batch_count"),
        "child_skill_count": installed.get("child_skill_count"),
        "runtime_skill_count": installed.get("runtime_skill_count"),
        "decision": decision,
        "local_ready": local_ready,
        "external_checks_complete": external_complete,
        "external_check_states": {
            name: external.get(name, {}).get("state", "NOT_RUN") for name in EXTERNAL_CHECKS
        },
        "verified_evidence": {"local": local_verified, "external": external_verified},
        "gate_request_digest": request_digest,
        "trust_store_digest": trust_store.digest if isinstance(trust_store, TrustStore) else None,
        "failures": failures,
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "production_certification": "NOT_CERTIFIED",
        "production_operation_authorized": False,
    }
    return {**result_without_digest, "result_digest": digest(result_without_digest)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-root", type=Path, action="append", default=[])
    parser.add_argument("--trust-store", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    installed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = evaluate_gate(
        request,
        installed=installed,
        evidence_roots=args.evidence_root,
        trust_store=args.trust_store,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 2 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
