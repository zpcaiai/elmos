#!/usr/bin/env python3
"""Independently evaluate and sign one immutable external-gate report.

Deploy this process under a separate verifier identity and key. Running it as
the producer does not establish independence, and the producer gate rejects
matching producer/verifier actors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from external_verifier_crypto import (
    VerifierCryptoError,
    public_key_sha256,
    sign_receipt,
    validate_external_report,
)


def issue_receipt(
    report_bytes: bytes,
    producer_actor: str,
    verifier_actor: str,
    private_key: Path,
    public_key: Path,
) -> dict[str, object]:
    if not producer_actor or not verifier_actor or producer_actor == verifier_actor:
        raise VerifierCryptoError("producer and verifier actors must be distinct")
    try:
        report = json.loads(report_bytes)
    except json.JSONDecodeError as exc:
        raise VerifierCryptoError("producer report is not valid JSON") from exc
    if not isinstance(report, dict):
        raise VerifierCryptoError("producer report is not a JSON object")
    validate_external_report(report)
    receipt: dict[str, object] = {
        "schema_version": 1,
        "verification_id": str(uuid.uuid4()),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "producer_actor": producer_actor,
        "verifier_actor": verifier_actor,
        "signing_key_sha256": public_key_sha256(public_key),
    }
    receipt["signature"] = sign_receipt(receipt, private_key)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--producer-actor", required=True)
    parser.add_argument("--verifier-actor", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = issue_receipt(
            args.report.read_bytes(), args.producer_actor, args.verifier_actor,
            args.private_key, args.public_key,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "receipt": str(args.output)}, sort_keys=True))
        return 0
    except (OSError, VerifierCryptoError) as exc:
        print(f"independent verifier: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
