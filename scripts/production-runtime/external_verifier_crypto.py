#!/usr/bin/env python3
"""Canonical external-verifier decisions and detached PEM-key signatures."""

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


EXPECTED_PACKAGE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"
SIGNED_FIELDS = (
    "schema_version",
    "verification_id",
    "verified_at",
    "status",
    "report_sha256",
    "producer_actor",
    "verifier_actor",
    "signing_key_sha256",
)


class VerifierCryptoError(ValueError):
    pass


def canonical_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    payload = {field: receipt.get(field) for field in SIGNED_FIELDS}
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def public_key_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise VerifierCryptoError("verifier public key must be a regular non-symlink file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_external_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != 1 or report.get("mode") != "EXECUTE":
        raise VerifierCryptoError("external report is not an executed schema-version-1 report")
    if report.get("source_archive_sha256") != EXPECTED_PACKAGE_SHA256:
        raise VerifierCryptoError("external report source package digest mismatch")
    if report.get("production_certification") != "NOT_CERTIFIED":
        raise VerifierCryptoError("producer report may not predeclare production certification")
    operations = report.get("operations")
    if not isinstance(operations, dict):
        raise VerifierCryptoError("external report operation inventory is missing")
    required = {
        "provider_runtime",
        "target_cluster_load",
        "chaos",
        "worker_process_kill",
        "redis_loss",
        "backup_pitr",
        "production_deployment",
    }
    if any(not isinstance(operations.get(name), dict) or operations[name].get("status") != "PASS" for name in required):
        raise VerifierCryptoError("one or more independently reviewable operations did not PASS")
    independent = operations.get("independent_verification")
    if not isinstance(independent, dict) or independent.get("status") not in {"NOT_RUN", "UNKNOWN"}:
        raise VerifierCryptoError("producer report contains an invalid self-verification state")
    evidence = report.get("external_evidence")
    if not isinstance(evidence, dict) or any(evidence.get(name) != "PASS" for name in required):
        raise VerifierCryptoError("external evidence summary does not match operation results")


def sign_receipt(receipt: dict[str, Any], private_key: Path) -> str:
    if private_key.is_symlink() or not private_key.is_file():
        raise VerifierCryptoError("verifier private key must be a regular non-symlink file")
    try:
        permissions = private_key.stat().st_mode & 0o777
        if permissions & 0o077:
            raise VerifierCryptoError("verifier private key must be owner-only")
    except OSError as exc:
        raise VerifierCryptoError("cannot inspect verifier private key") from exc
    with tempfile.TemporaryDirectory(prefix="elmos-verifier-sign-") as temporary:
        payload = Path(temporary) / "receipt.json"
        signature = Path(temporary) / "receipt.sig"
        payload.write_bytes(canonical_receipt_bytes(receipt))
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(private_key), "-out", str(signature), str(payload)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise VerifierCryptoError("OpenSSL could not sign the verifier receipt")
        return base64.b64encode(signature.read_bytes()).decode("ascii")


def verify_receipt_signature(
    receipt: dict[str, Any],
    public_key: Path,
    expected_key_sha256: str,
) -> None:
    actual_key_sha256 = public_key_sha256(public_key)
    if actual_key_sha256 != expected_key_sha256 or receipt.get("signing_key_sha256") != actual_key_sha256:
        raise VerifierCryptoError("independent verifier signing-key digest mismatch")
    try:
        signature_bytes = base64.b64decode(receipt.get("signature", ""), validate=True)
    except (ValueError, TypeError) as exc:
        raise VerifierCryptoError("independent verifier signature is not valid base64") from exc
    if len(signature_bytes) < 64 or len(signature_bytes) > 16_384:
        raise VerifierCryptoError("independent verifier signature length is invalid")
    with tempfile.TemporaryDirectory(prefix="elmos-verifier-check-") as temporary:
        payload = Path(temporary) / "receipt.json"
        signature = Path(temporary) / "receipt.sig"
        payload.write_bytes(canonical_receipt_bytes(receipt))
        signature.write_bytes(signature_bytes)
        result = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature), str(payload)],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise VerifierCryptoError("independent verifier signature verification failed")


def validate_receipt_time(receipt: dict[str, Any], maximum_age_seconds: int) -> None:
    try:
        verified = datetime.fromisoformat(str(receipt["verified_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise VerifierCryptoError("independent verifier timestamp is invalid") from exc
    if verified.tzinfo is None:
        raise VerifierCryptoError("independent verifier timestamp has no timezone")
    now = datetime.now(timezone.utc)
    age = (now - verified.astimezone(timezone.utc)).total_seconds()
    if age < -300 or age > maximum_age_seconds:
        raise VerifierCryptoError("independent verifier receipt is stale or future-dated")
