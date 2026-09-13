#!/usr/bin/env python3
"""Replace revoked-key certification reports with deterministic tombstones."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INCIDENT_ID = "ELMOS-CERT-KEY-2026-09-13-01"


def sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def tombstone(path: Path) -> dict[str, object]:
    existing_bytes = path.read_bytes()
    existing = json.loads(existing_bytes)
    if existing.get("incident_id") == INCIDENT_ID and existing.get("decision") == "NOT_CERTIFIED":
        return existing
    return {
        "schema_version": 1,
        "status": "BLOCKED",
        "decision": "NOT_CERTIFIED",
        "incident_id": INCIDENT_ID,
        "scope": path.stem,
        "prior_report_sha256": sha256(existing_bytes),
        "prior_claim_status": "REVOKED_UNTRUSTED",
        "local_evidence": "SELF_ATTESTED_ENGINEERING_ONLY",
        "external_execution": "NOT_RUN",
        "customer_acceptance": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "trust_anchor_status": "REVOKED",
        "release_effect": "NONE",
        "reason": "the prior positive claim relied on repository-held signing keys or exceeded the authoritative evidence boundary",
        "required_action": "re-execute exact-SHA evidence in the named real environment and obtain an authenticated repository-external independent signature under a new key",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args()

    ledger = json.loads((ROOT / "release-control/untrusted-certification-reports.json").read_text(encoding="utf-8"))
    drift: list[str] = []
    for relative in ledger["reports"]:
        path = ROOT / relative
        expected = tombstone(path)
        current = json.loads(path.read_text(encoding="utf-8"))
        if current != expected:
            drift.append(relative)
            if arguments.write:
                path.write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = {
        "status": "UPDATED" if arguments.write and drift else ("PASS" if not drift else "FAIL"),
        "decision": "NOT_CERTIFIED",
        "incident_id": INCIDENT_ID,
        "report_count": len(ledger["reports"]),
        "drift": drift,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if arguments.write or not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
