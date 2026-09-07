#!/usr/bin/env python3
"""Independent B41 evidence, certificate, signing, and release-gate handlers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.precision_migration.runtime import Registry, evaluate
from scripts.precision_migration.trust import (
    TrustStore,
    canonical_bytes,
    canonical_digest,
    verify_content_reference,
)


def _write(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        raise ValueError(f"refusing to overwrite B41 artifact: {path}")
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(content)
    return {
        "uri": path.resolve().as_uri(),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        "media_type": "application/json",
    }


def _decision(
    request: dict[str, Any],
    skill_registry: Registry,
    evidence_roots: tuple[Path, ...],
    trust_store: TrustStore | None,
) -> dict[str, Any]:
    return evaluate(
        request,
        skill_registry,
        evidence_roots=evidence_roots,
        trust_store=trust_store,
    )


def _result(output_dir: Path, name: str, payload: dict[str, Any], *, state: str = "LOCAL_EXECUTED", exit_code: int = 0) -> dict[str, Any]:
    return {"execution_state": state, "artifacts": [_write(output_dir / name, payload)], "exit_code": exit_code}


def execute_evidence_manifest(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    payload = {
        "schema_version": 1,
        "manifest_id": canonical_digest({"request_id": request["request_id"], "skill": entry["skill"]}),
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "inputs": decision["inputs"],
        "evidence": decision["evidence"],
        "proofs": decision.get("proofs", []),
        "semantic_losses": request.get("semantic_losses", []),
        "approvals": request.get("approvals", []),
        "unresolved": decision["unresolved"],
        "release_gate": decision["release_gate"],
        "external_verification": "NOT_RUN",
    }
    return _result(output_dir, "evidence-manifest.json", payload)


def execute_conversion_provenance(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    parameters = request.get("inputs", {}).get("parameters", {})
    payload = {
        "schema_version": 1,
        "provenance_id": canonical_digest({"request_id": request["request_id"], "inputs": decision["inputs"]}),
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "source_inputs": decision["inputs"],
        "rule_versions": parameters.get("rule_versions", []),
        "agent_versions": parameters.get("agent_versions", []),
        "toolchain_versions": parameters.get("toolchain_versions", {}),
        "repair_history": parameters.get("repair_history", []),
        "artifact_evidence": decision["evidence"],
        "unresolved": decision["unresolved"],
    }
    return _result(output_dir, "conversion-provenance.json", payload)


def execute_rule_proof_certificate(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    proof_evidence = [item for item in decision["evidence"] if item.get("proof_verified") is True]
    proved = decision["status"] == "PROVED" and bool(proof_evidence)
    payload = {
        "schema_version": 1,
        "certificate_type": "RULE_PROOF",
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "proof_evidence": proof_evidence,
        "decision": "PROVED" if proved else "NOT_PROVED",
        "unresolved": decision["unresolved"],
        "independent_verification": "PASSED" if proved else "NOT_RUN",
    }
    return _result(output_dir, "rule-proof-certificate.json", payload, state="LOCAL_EXECUTED" if proved else decision["status"], exit_code=0 if proved else 4)


def execute_module_equivalence_certificate(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    passed = {item["kind"] for item in decision["evidence"] if item.get("state") == "PASS"}
    required = {"source-build", "target-build", "source-target-differential", "artifact-provenance"}
    equivalent = required <= passed and not decision["unresolved"]
    payload = {
        "schema_version": 1,
        "certificate_type": "MODULE_EQUIVALENCE",
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "required_evidence": sorted(required),
        "observed_pass_evidence": sorted(passed),
        "observational_equivalence": "VERIFIED" if equivalent else "NOT_VERIFIED",
        "unresolved": decision["unresolved"],
    }
    return _result(output_dir, "module-equivalence-certificate.json", payload, state="LOCAL_EXECUTED" if equivalent else decision["status"], exit_code=0 if equivalent else 4)


def execute_runtime_evidence_package(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    by_kind = {item["kind"]: item for item in decision["evidence"]}
    payload = {
        "schema_version": 1,
        "package_id": canonical_digest({"request_id": request["request_id"], "evidence": decision["evidence"]}),
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "evidence_by_kind": by_kind,
        "required_missing": sorted(item["kind"] for item in decision["evidence"] if item.get("state") != "PASS"),
        "unresolved": decision["unresolved"],
        "package_decision": decision["status"],
    }
    return _result(output_dir, "runtime-evidence-package.json", payload)


def execute_semantic_loss_report(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, **_: Any) -> dict[str, Any]:
    losses = request.get("semantic_losses", [])
    blockers = [item for item in losses if item.get("classification") != "LOSSLESS"]
    payload = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "losses": losses,
        "blocking_loss_count": len(blockers),
        "decision": "LOSSLESS" if not blockers else "BLOCK",
    }
    return _result(output_dir, "semantic-loss-report.json", payload)


def execute_unresolved_obligation_report(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    payload = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "obligations": decision["unresolved"],
        "blocking_count": sum(item.get("blocking") is True for item in decision["unresolved"]),
        "release_decision": decision["release_gate"]["decision"],
    }
    return _result(output_dir, "unresolved-obligations.json", payload)


def execute_release_gate(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    payload = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "status": decision["status"],
        "hard_gate": decision["release_gate"],
        "unresolved": decision["unresolved"],
        "average_score_used": False,
        "production_certification": "NOT_CERTIFIED",
    }
    passed = decision["release_gate"]["decision"] != "BLOCK"
    return _result(output_dir, "release-gate.json", payload, state="LOCAL_EXECUTED" if passed else decision["status"], exit_code=0 if passed else 4)


def execute_correctness_classifier(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, skill_registry: Registry, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    decision = _decision(request, skill_registry, evidence_roots, trust_store)
    passed = {item["kind"] for item in decision["evidence"] if item.get("state") == "PASS"}
    ordered = [
        ("PRODUCTION_EVIDENCE", {"production-canary", "production-rollback"}),
        ("SYSTEM_PROPERTIES", {"independent-review", "representative-workload"}),
        ("COMPOSED_BEHAVIOR", {"source-target-differential", "negative-tests"}),
        ("LOCAL_SEMANTICS", {"source-target-differential"}),
        ("TYPE_AND_BUILD", {"source-build", "target-build"}),
        ("SYNTAX", {"target-build"}),
    ]
    level = "UNVERIFIED"
    for candidate, required in ordered:
        if required <= passed:
            level = candidate
            break
    payload = {
        "schema_version": 1,
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "level": level,
        "passed_evidence_kinds": sorted(passed),
        "decision": decision["status"],
        "production_evidence": "PASSED" if level == "PRODUCTION_EVIDENCE" else "NOT_RUN",
    }
    return _result(output_dir, "correctness-level.json", payload)


def _confined_private_key(value: Any, roots: tuple[Path, ...]) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("certificate signing requires signing_key_path")
    supplied = Path(value).expanduser()
    if supplied.is_symlink():
        raise ValueError("signing key must not be a symlink")
    resolved = supplied.resolve(strict=True)
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ValueError("signing key escapes approved roots")
    if not resolved.is_file():
        raise ValueError("signing key must be a regular file")
    return resolved


def _signing_command(
    parameters: dict[str, Any],
    roots: tuple[Path, ...],
    payload_path: Path,
    signature_path: Path,
) -> tuple[list[str], dict[str, str], str, str]:
    backend = parameters.get("signing_backend", "local-openssl-ed25519")
    environment = {"PATH": os.environ.get("PATH", "")}
    if backend == "local-openssl-ed25519":
        key = _confined_private_key(parameters.get("signing_key_path"), roots)
        return (
            ["openssl", "pkeyutl", "-sign", "-inkey", str(key), "-rawin", "-in", str(payload_path), "-out", str(signature_path)],
            environment,
            "LOCAL_OPENSSL_ED25519",
            "NOT_RUN",
        )
    if backend != "pkcs11-openssl-ed25519":
        raise ValueError("signing_backend must be local-openssl-ed25519 or pkcs11-openssl-ed25519")
    provider = parameters.get("hsm_provider")
    key_uri = parameters.get("hsm_key_uri")
    if provider != "pkcs11":
        raise ValueError("HSM signing requires the allowlisted pkcs11 provider")
    if not isinstance(key_uri, str) or not key_uri.startswith("pkcs11:") or any(character in key_uri for character in "\r\n\0"):
        raise ValueError("HSM signing requires a valid PKCS#11 key URI")
    pin = os.environ.get("ELMOS_PRECISION_HSM_PIN")
    if not pin:
        raise ValueError("HSM signing requires ELMOS_PRECISION_HSM_PIN")
    environment["PKCS11_PIN"] = pin
    return (
        [
            "openssl", "pkeyutl", "-provider", "default", "-provider", "pkcs11",
            "-sign", "-inkey", key_uri, "-rawin", "-in", str(payload_path), "-out", str(signature_path),
        ],
        environment,
        "PKCS11_OPENSSL_ED25519",
        "EXECUTED_PENDING_VERIFICATION",
    )


def execute_certificate_signing(request: dict[str, Any], entry: dict[str, Any], output_dir: Path, *, evidence_roots: tuple[Path, ...], trust_store: TrustStore | None, **_: Any) -> dict[str, Any]:
    if trust_store is None:
        raise ValueError("certificate signing requires an independent trust store")
    parameters = request.get("inputs", {}).get("parameters", {})
    key_id = parameters.get("key_id")
    issued_at = parameters.get("issued_at")
    expires_at = parameters.get("expires_at")
    asset_index = parameters.get("payload_asset_index", 0)
    if not isinstance(key_id, str) or not key_id:
        raise ValueError("certificate signing requires key_id")
    if not isinstance(issued_at, str) or not isinstance(expires_at, str):
        raise TypeError("certificate signing requires issued_at and expires_at")
    if not isinstance(asset_index, int):
        raise TypeError("payload_asset_index must be an integer")
    assets = request.get("inputs", {}).get("assets", [])
    try:
        content = verify_content_reference(assets[asset_index], evidence_roots)
    except (IndexError, OSError, ValueError) as exc:
        raise ValueError(f"certificate payload verification failed: {exc}") from exc
    with tempfile.TemporaryDirectory(prefix="precision-sign-") as temporary:
        payload_path = Path(temporary) / "payload.json"
        signature_path = Path(temporary) / "signature.bin"
        command, signing_environment, signing_backend, hsm_execution = _signing_command(
            parameters, evidence_roots, payload_path, signature_path
        )
        payload = {
        "record_type": "PRECISION_MIGRATION_CERTIFICATE",
        "record_id": canonical_digest({"request_id": request["request_id"], "content": content["digest"]}),
        "request_id": request["request_id"],
        "skill": entry["skill"],
        "content_digest": content["digest"],
        "content_size_bytes": content["size_bytes"],
        "issued_at": issued_at,
        "expires_at": expires_at,
        "signing_backend": signing_backend,
        "hsm_execution": hsm_execution,
        }
        payload_path.write_bytes(canonical_bytes(payload))
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=30,
            env=signing_environment,
        )
        if completed.returncode != 0:
            raise ValueError("Ed25519 signing failed: " + completed.stderr.decode("utf-8", errors="replace")[-500:])
        envelope = {
            "algorithm": "ed25519",
            "key_id": key_id,
            "payload": payload,
            "signature": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        }
    trust_store.verify_envelope(
        envelope,
        required_role="certificate-signer",
        bindings={
            "record_type": "PRECISION_MIGRATION_CERTIFICATE",
            "request_id": request["request_id"],
            "skill": entry["skill"],
            "content_digest": content["digest"],
        },
        now=datetime.now(timezone.utc),
    )
    final_hsm_state = "PASSED" if payload["signing_backend"] == "PKCS11_OPENSSL_ED25519" else "NOT_RUN"
    return _result(
        output_dir,
        "signed-certificate.json",
        {"schema_version": 1, "envelope": envelope, "trust_store_digest": trust_store.digest, "verification": "PASSED", "hsm_execution": final_hsm_state},
    )
