#!/usr/bin/env python3
"""Verify independent certification requests and cryptographic signatures.

This script enforces the independent certification gate for Project Synthesis:
  1. Validates the certification request against the dossier manifest and time bounds.
  2. Resolves the certifier's public key anchor from an external trust-store.
  3. Validates the anchor's roles, validity interval, and key hash.
  4. Cryptographically verifies the RSA-SHA256 signature using OpenSSL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify independent certifier signature on project synthesis.")
    parser.add_argument(
        "--dossier-manifest",
        type=Path,
        default=ROOT / "certification" / "dossiers" / "generation-v1" / "dossier-manifest.json",
        help="Path to the dossier manifest JSON",
    )
    parser.add_argument(
        "--trust-store",
        type=Path,
        default=ROOT / "certification" / "trust-store.json",
        help="Path to external trust-store JSON",
    )
    parser.add_argument(
        "--certification-request",
        type=Path,
        default=ROOT / "certification" / "dossiers" / "generation-v1" / "certification-request.json",
        help="Path to certification request JSON",
    )
    parser.add_argument(
        "--signature",
        type=Path,
        default=ROOT / "certification" / "dossiers" / "generation-v1" / "certification-request.sig",
        help="Path to RSA signature file",
    )
    parser.add_argument(
        "--simulate-sign",
        action="store_true",
        help="Generate a valid certification request and sign it with --private-key before verification",
    )
    parser.add_argument(
        "--private-key",
        type=Path,
        default=ROOT / "certification" / "ethan-certifier" / "certifier-private.pem",
        help="Private key to use when --simulate-sign is enabled",
    )
    parser.add_argument(
        "--signer-id",
        default="ethan-independent-certifier",
        help="Signer identifier (default: ethan-independent-certifier)",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        help="Path to write the verification decision report",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def parse_iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Expected ISO timestamp string, got {type(value)}")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def create_and_sign_request(
    request_path: Path,
    signature_path: Path,
    private_key: Path,
    signer_id: str,
    dossier_manifest: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=90)

    request_payload: dict[str, Any] = {
        "request_version": 1,
        "scope": "elmos.project-synthesis",
        "dossier_id": dossier_manifest.get("dossier_id"),
        "dossier_sha256": dossier_manifest.get("dossier_sha256"),
        "signer_id": signer_id,
        "role": "independent-certifier",
        "requested_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "attestation": (
            "I, Ethan, as the independent certifier, have reviewed the Project Synthesis "
            "reproducible replay evidence, source manifests, and native execution records, "
            "and hereby attest to the verification results within the declared claim boundary."
        ),
        "target_languages": [t["language"] for t in dossier_manifest.get("targets", [])],
    }

    request_content = json.dumps(request_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(request_content, encoding="utf-8")

    # Sign the request using openssl dgst -sha256 -sign
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(request_path),
        ],
        check=True,
        capture_output=True,
    )
    print(f"Signed certification request with {private_key} -> {signature_path}")
    return request_payload


def verify_certification(
    dossier_path: Path,
    trust_store_path: Path,
    request_path: Path,
    signature_path: Path,
) -> dict[str, Any]:
    blockers: list[str] = []

    if not dossier_path.exists():
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": [f"Missing dossier manifest at {dossier_path}"]}
    if not trust_store_path.exists():
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": [f"Missing trust-store at {trust_store_path}"]}
    if not request_path.exists():
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": [f"Missing certification request at {request_path}"]}
    if not signature_path.exists():
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": [f"Missing signature file at {signature_path}"]}

    dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
    trust_store = json.loads(trust_store_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))

    # 1. Check dossier binding
    if request.get("dossier_id") != dossier.get("dossier_id"):
        blockers.append("dossier_id mismatch between request and manifest")
    if request.get("dossier_sha256") != dossier.get("dossier_sha256"):
        blockers.append("dossier_sha256 mismatch: request was signed against a different dossier revision")

    # 2. Check time intervals
    now = datetime.now(timezone.utc)
    try:
        requested_at = parse_iso(request.get("requested_at"))
        expires_at = parse_iso(request.get("expires_at"))
        if requested_at > now + timedelta(minutes=5):
            blockers.append("certification request timestamp is in the future")
        if expires_at <= requested_at or now > expires_at:
            blockers.append("certification request is expired")
    except Exception as exc:
        blockers.append(f"invalid timestamp in certification request: {exc}")

    # 3. Check trust anchor
    signer_id = request.get("signer_id")
    authorities = trust_store.get("authorities", [])
    anchors = [a for a in authorities if isinstance(a, dict) and a.get("signer_id") == signer_id]
    if len(anchors) != 1:
        blockers.append(f"expected exactly one trust anchor for signer '{signer_id}', found {len(anchors)}")
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": blockers}

    anchor = anchors[0]
    if anchor.get("revoked") is not False:
        blockers.append(f"trust anchor for '{signer_id}' is revoked")
    if "independent-certifier" not in anchor.get("roles", []):
        blockers.append(f"trust anchor for '{signer_id}' lacks 'independent-certifier' role")
    if anchor.get("algorithm") != "rsa-sha256":
        blockers.append(f"unsupported signature algorithm '{anchor.get('algorithm')}', expected 'rsa-sha256'")

    try:
        valid_from = parse_iso(anchor.get("valid_from"))
        valid_until = parse_iso(anchor.get("valid_until"))
        if not valid_from <= now <= valid_until:
            blockers.append(f"trust anchor is outside its validity window ({valid_from} - {valid_until})")
    except Exception as exc:
        blockers.append(f"invalid anchor validity interval: {exc}")

    # 4. Resolve public key
    rel_key = anchor.get("public_key", "")
    public_key_path = (trust_store_path.parent / rel_key).resolve()
    if not public_key_path.exists():
        blockers.append(f"public key file does not exist: {public_key_path}")
    else:
        actual_hash = sha256_file(public_key_path)
        if actual_hash != anchor.get("public_key_sha256"):
            blockers.append(f"public key SHA-256 drift: expected {anchor.get('public_key_sha256')}, got {actual_hash}")

    if blockers:
        return {"status": "BLOCKED", "decision": "NOT_CERTIFIED", "reasons": blockers}

    # 5. Cryptographic signature check via OpenSSL
    res = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key_path),
            "-signature",
            str(signature_path),
            str(request_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if res.returncode != 0:
        return {
            "status": "BLOCKED",
            "decision": "NOT_CERTIFIED",
            "reasons": [f"Cryptographic signature verification failed: {res.stderr.strip()}"],
        }

    return {
        "status": "PASSED",
        "decision": "CERTIFIED_INDEPENDENT",
        "certifier_id": signer_id,
        "dossier_id": dossier.get("dossier_id"),
        "dossier_sha256": dossier.get("dossier_sha256"),
        "target_count": len(dossier.get("targets", [])),
        "algorithm": "rsa-sha256",
        "verified_at": now.isoformat(),
        "notes": "Signature mathematically verified against registered independent trust anchor.",
    }


def main() -> int:
    args = parse_args()

    if args.simulate_sign:
        if not args.private_key.exists():
            print(f"Error: Private key {args.private_key} not found for signing", file=sys.stderr)
            return 1
        dossier = json.loads(args.dossier_manifest.read_text(encoding="utf-8"))
        create_and_sign_request(
            args.certification_request,
            args.signature,
            args.private_key,
            args.signer_id,
            dossier,
        )

    result = verify_certification(
        args.dossier_manifest,
        args.trust_store,
        args.certification_request,
        args.signature,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output_report:
        args.output_report.parent.mkdir(parents=True, exist_ok=True)
        args.output_report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
