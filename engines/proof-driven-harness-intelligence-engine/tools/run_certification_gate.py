#!/usr/bin/env python3
"""Run the conservative PDHI gate; local evidence can never certify."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SOURCE = ENGINE_ROOT / "src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_pdhi.canonical import digest_object, strict_json_loads  # noqa: E402


DEFAULT_LOCAL = ENGINE_ROOT / "qualification/local-v1/receipt.json"
DEFAULT_EXTERNAL = ENGINE_ROOT / "qualification/external-v1/receipt.json"


class GateError(RuntimeError):
    pass


def _object(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GateError(f"receipt is missing or unsafe: {path}")
    value = strict_json_loads(path.read_bytes(), source=str(path))
    if not isinstance(value, dict):
        raise GateError(f"receipt must be a JSON object: {path}")
    return value


def _verify_local(path: Path) -> Mapping[str, Any]:
    receipt = _object(path)
    expected = receipt.get("qualification_digest")
    body = {key: value for key, value in receipt.items() if key != "qualification_digest"}
    if expected != digest_object(body, domain="pdhi-local-qualification"):
        raise GateError("local qualification digest is invalid")
    if receipt.get("qualification_status") != "LOCAL_EXECUTED_SELF_ATTESTED" or receipt.get("readiness") != "READY_FOR_EXTERNAL_GATE":
        raise GateError("local qualification did not pass")
    if receipt.get("certification_status") != "NOT_CERTIFIED":
        raise GateError("local receipt made an unauthorized certification claim")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise GateError("local receipt has no artifact inventory")
    for relative, expected_digest in artifacts.items():
        if not isinstance(relative, str) or not isinstance(expected_digest, str):
            raise GateError("local artifact inventory is malformed")
        candidate = REPOSITORY_ROOT / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise GateError(f"qualified artifact is missing or unsafe: {relative}")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_digest:
            raise GateError(f"qualified artifact drifted: {relative}")
    raw = receipt.get("raw_outputs")
    if not isinstance(raw, dict) or not raw:
        raise GateError("local receipt has no raw outputs")
    for relative, expected_digest in raw.items():
        candidate = path.parent / "raw" / relative
        if not isinstance(expected_digest, str) or candidate.is_symlink() or not candidate.is_file():
            raise GateError(f"raw qualification output is missing or unsafe: {relative}")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_digest:
            raise GateError(f"raw qualification output drifted: {relative}")
    return receipt


def evaluate(local_path: Path, external_path: Path) -> Mapping[str, Any]:
    local = _verify_local(local_path)
    reasons = [
        "local self-attested evidence cannot certify",
        "independent external E0-E5 evidence is required",
        "an authorized base-v3 certification adapter and signature verifier are required",
    ]
    external_input = "MISSING"
    if external_path.exists() or external_path.is_symlink():
        # Never trust a JSON document merely because it claims to be signed.
        _object(external_path)
        external_input = "PRESENT_UNVERIFIED_NOT_ACCEPTED"
        reasons.append("external receipt was provided but no trusted base-v3 verifier is configured")
    return {
        "schema_version": "1.0.0",
        "package": local["package"],
        "local_qualification_digest": local["qualification_digest"],
        "local_qualification_status": local["qualification_status"],
        "decision": "READY_FOR_EXTERNAL_GATE",
        "external_receipt": external_input,
        "external_evidence_status": "NOT_RUN" if external_input == "MISSING" else "UNVERIFIED",
        "independent_verification": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "reasons": reasons,
        "process_exit_semantics": "nonzero until trusted external certification completes",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--external", type=Path, default=DEFAULT_EXTERNAL)
    args = parser.parse_args(argv)
    try:
        result = evaluate(args.local.resolve(), args.external.resolve())
    except Exception as exc:
        print(json.dumps({"decision": "BLOCKED", "certification_status": "NOT_CERTIFIED", "error": type(exc).__name__, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
