#!/usr/bin/env python3
"""Derive the conservative repository readiness decision for FRT G01-G30."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from external_evidence import validate_external_check


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json"
REQUIRED_LOCAL = (
    "package_integrity",
    "runtime_interfaces",
    "contract_validation",
    "trusted_identity_evidence",
    "semantic_skill_coverage",
    "durable_run_lifecycle",
    "real_route_build",
    "runtime_tests",
    "web_build",
    "browser_journey",
    "keyboard_i18n",
    "accessibility",
    "external_qualification_harness",
)
REQUIRED_EXTERNAL = (
    "real_source_target_builds",
    "device_matrix",
    "independent_holdout",
    "formal_proof",
    "performance",
    "chaos_dr",
    "penetration_test",
    "production_observation",
    "customer_acceptance",
)
STATES = {"PASSED", "FAILED", "INCONCLUSIVE", "NOT_RUN"}
REQUEST_KEYS = {
    "schema_version",
    "package_manifest_sha256",
    "source_tree_sha256",
    "local_checks",
    "external_checks",
}


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def evidence_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validate_result_binding(result: Any, request_path: Path) -> list[str]:
    """Reject a copied, stale, or internally tampered gate result."""
    if not isinstance(result, dict):
        return ["gate result must be an object"]
    failures: list[str] = []
    if result.get("gate_request_sha256") != evidence_digest(request_path):
        failures.append("gate result is not bound to the current request bytes")
    unsigned = {key: value for key, value in result.items() if key != "result_digest"}
    if result.get("result_digest") != digest(unsigned):
        failures.append("gate result digest mismatch")
    return failures


def validate_evidence_ref(ref: Any, evidence_root: Path = ROOT) -> list[str]:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "bytes"}:
        return ["must contain exactly path, sha256, and bytes"]
    relative_path = ref.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        return ["path must be a non-empty repository-relative string"]
    path = Path(relative_path)
    if path.is_absolute():
        return ["path must be repository-relative"]
    root = evidence_root.resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ["path escapes the repository evidence root"]
    if not candidate.is_file():
        return ["path does not resolve to a regular evidence file"]
    failures: list[str] = []
    if ref.get("bytes") != candidate.stat().st_size:
        failures.append("byte count mismatch")
    if ref.get("sha256") != evidence_digest(candidate):
        failures.append("sha256 mismatch")
    return failures


def check_group(
    name: str,
    value: Any,
    required: tuple[str, ...],
    evidence_root: Path = ROOT,
) -> list[str]:
    failures: list[str] = []
    if not isinstance(value, dict):
        return [f"{name} must be an object"]
    unexpected = set(value) - set(required)
    if unexpected:
        failures.append(f"{name} contains unexpected checks: {sorted(unexpected)}")
    for key in required:
        item = value.get(key)
        if not isinstance(item, dict):
            failures.append(f"{name}.{key} is missing")
            continue
        if set(item) != {"state", "evidence_refs"}:
            failures.append(
                f"{name}.{key} must contain exactly state and evidence_refs"
            )
        state = item.get("state")
        refs = item.get("evidence_refs")
        if state not in STATES:
            failures.append(f"{name}.{key}.state is invalid")
        if not isinstance(refs, list):
            failures.append(f"{name}.{key}.evidence_refs is invalid")
            continue
        if state == "PASSED" and not refs:
            failures.append(f"{name}.{key} claims PASSED without evidence")
        if state in {"FAILED", "INCONCLUSIVE"} and not refs:
            failures.append(f"{name}.{key} must preserve evidence for {state}")
        if state == "NOT_RUN" and refs:
            failures.append(f"{name}.{key} claims NOT_RUN but contains evidence refs")
        for index, ref in enumerate(refs):
            failures.extend(
                f"{name}.{key}.evidence_refs[{index}] {message}"
                for message in validate_evidence_ref(ref, evidence_root)
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--output")
    parser.add_argument("--external-trust-store", type=Path)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    installed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    if not isinstance(request, dict):
        raise SystemExit("gate request must be a JSON object")
    if set(request) != REQUEST_KEYS:
        failures.append("gate request root fields are not exact")
    if request.get("schema_version") != 1:
        failures.append("schema_version must be 1")
    if request.get("package_manifest_sha256") != installed.get(
        "source_package_manifest_sha256"
    ):
        failures.append("package manifest digest mismatch")
    if request.get("source_tree_sha256") != installed.get("source_tree_sha256"):
        failures.append("source tree digest mismatch")
    failures.extend(check_group("local_checks", request.get("local_checks"), REQUIRED_LOCAL))
    failures.extend(
        check_group("external_checks", request.get("external_checks"), REQUIRED_EXTERNAL)
    )
    external = request.get("external_checks", {})
    if isinstance(external, dict):
        for key in REQUIRED_EXTERNAL:
            failures.extend(
                validate_external_check(
                    key,
                    external.get(key),
                    args.external_trust_store,
                )
            )
    local = request.get("local_checks", {})
    local_ready = not failures and all(
        local.get(key, {}).get("state") == "PASSED" for key in REQUIRED_LOCAL
    )
    external_ready = not failures and all(
        external.get(key, {}).get("state") == "PASSED" for key in REQUIRED_EXTERNAL
    )
    if failures:
        decision = "REJECTED"
    elif not local_ready:
        decision = "NOT_READY"
    else:
        decision = "READY_FOR_EXTERNAL_GATE"
    result_without_digest = {
        "schema_version": 1,
        "gate_request_sha256": evidence_digest(request_path),
        "package": installed.get("source_package"),
        "batch_count": 30,
        "skill_count": 472,
        "directed_route_count": 30,
        "decision": decision,
        "local_ready": local_ready,
        "external_checks_complete": external_ready,
        "external_check_states": {
            key: external.get(key, {}).get("state", "NOT_RUN")
            for key in REQUIRED_EXTERNAL
        },
        "failures": failures,
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "production_certification": "NOT_CERTIFIED",
        "production_operation_authorized": False,
        "external_trust_store_sha256": (
            evidence_digest(args.external_trust_store)
            if args.external_trust_store and args.external_trust_store.is_file()
            else None
        ),
    }
    result = {**result_without_digest, "result_digest": digest(result_without_digest)}
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
