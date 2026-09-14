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


def downgrade_structured_report(
    path: Path, record: dict[str, object]
) -> dict[str, object]:
    """Preserve useful local output while removing unsupported positive claims."""
    existing = json.loads(path.read_text(encoding="utf-8"))
    entries = existing.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"structured report has no entries: {path}")
    expected_count = record.get("prior_certified_claim_count")
    control = existing.get("release_control_downgrade")
    if not isinstance(control, dict):
        observed_count = sum(
            1
            for entry in entries
            if isinstance(entry, dict) and entry.get("certification") == "CERTIFIED"
        )
        if observed_count != expected_count:
            raise ValueError(
                f"structured report certified claim count mismatch: {path}: "
                f"expected {expected_count}, found {observed_count}"
            )
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"structured report entry is invalid: {path}")
        entry["runtime_evidence"] = record["required_entry_runtime_evidence"]
        entry["independent_evidence"] = record[
            "required_entry_independent_evidence"
        ]
        entry["certification"] = record["required_entry_certification"]
    existing["certification"] = "NOT_CERTIFIED"
    existing["release_control_downgrade"] = {
        "incident_id": INCIDENT_ID,
        "prior_report_sha256": record["prior_report_sha256"],
        "prior_certified_claim_count": expected_count,
        "local_evidence": "SELF_ATTESTED_ENGINEERING_ONLY",
        "external_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "trust_anchor_status": "REVOKED",
    }
    return existing


def mature_product_expected_files(record: dict[str, object]) -> dict[Path, object]:
    """Withdraw repository-key certification while preserving forensic inputs."""
    pack = ROOT / str(record["path"])
    batch = int(record["batch"])
    certification_path = pack / "certification.json"
    gate_path = pack / "gate-result.json"
    certification = json.loads(certification_path.read_text(encoding="utf-8"))
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if certification.get("status") == "CERTIFIED":
        if sha256(certification_path.read_bytes()) != record["prior_certification_sha256"]:
            raise ValueError(f"mature-product certification digest mismatch: {pack}")
    if gate.get("status") == "CERTIFIED":
        if sha256(gate_path.read_bytes()) != record["prior_gate_result_sha256"]:
            raise ValueError(f"mature-product gate digest mismatch: {pack}")

    certification["status"] = "NOT_RUN"
    certification["evidenceRefs"] = []
    certification["holdoutPassRate"] = 0
    certification["representativePassRate"] = 0
    certification["criticalFindings"] = 0
    certification["metrics"] = {
        name: 0 for name in certification.get("metrics", {})
    }
    certification.pop("approvedBy", None)

    gate["eligible"] = False
    gate["status"] = "BLOCKED"
    gate["failures"] = [
        f"certification withdrawn by {INCIDENT_ID}: repository-held certifier key is revoked"
    ]
    gate["evidenceRefs"] = []
    gate["externalOperationExecuted"] = False

    pack_document = json.loads((pack / "pack.json").read_text(encoding="utf-8"))
    pack_document["status"] = "experimental"
    support = json.loads((pack / "support-matrix.json").read_text(encoding="utf-8"))
    for capability in support.get("capabilities", []):
        capability["status"] = "experimental"

    claims = json.loads((pack / "claims.json").read_text(encoding="utf-8"))
    for claim in claims.get("claims", []):
        limitations = claim.get("limitations")
        if isinstance(limitations, str):
            claim["limitations"] = [limitations]
        claim.pop("status", None)
        claim.pop("provenanceRefs", None)

    expected: dict[Path, object] = {
        certification_path: certification,
        gate_path: gate,
        pack / "pack.json": pack_document,
        pack / "support-matrix.json": support,
        pack / "claims.json": claims,
        pack / "gate-report.md": (
            f"# Batch {batch} gate\n\n"
            "Status: `BLOCKED`\n\n"
            "## Failures\n\n"
            f"- Certification withdrawn by `{INCIDENT_ID}` because the repository-held "
            "certifier key is revoked. Re-execute exact-scope evidence and obtain a "
            "repository-external independent signature under a new trusted key.\n"
        ),
    }
    for review_path in sorted((pack / "evidence/independent-review").glob("*.json")):
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if str(review.get("decision", "")).upper() == "CERTIFIED":
            review["decision"] = "NOT_RUN"
        expected[review_path] = review
    if batch == 45:
        for domain_path in sorted((pack / "domain-gates").glob("batch*-gate-result.json")):
            domain = json.loads(domain_path.read_text(encoding="utf-8"))
            domain["eligible"] = False
            domain["status"] = "BLOCKED"
            domain["failures"] = [
                f"source domain certification withdrawn by {INCIDENT_ID}"
            ]
            domain["evidenceRefs"] = []
            domain["externalOperationExecuted"] = False
            expected[domain_path] = domain
    return expected


def encoded(payload: object) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


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

    for record in ledger.get("structured_reports", []):
        relative = record["path"]
        path = ROOT / relative
        expected = downgrade_structured_report(path, record)
        current = json.loads(path.read_text(encoding="utf-8"))
        if current != expected:
            drift.append(relative)
            if arguments.write:
                path.write_text(
                    json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

    for record in ledger.get("mature_product_packs", []):
        for path, expected in mature_product_expected_files(record).items():
            expected_bytes = encoded(expected)
            if path.read_bytes() != expected_bytes:
                relative = path.relative_to(ROOT).as_posix()
                drift.append(relative)
                if arguments.write:
                    path.write_bytes(expected_bytes)

    result = {
        "status": "UPDATED" if arguments.write and drift else ("PASS" if not drift else "FAIL"),
        "decision": "NOT_CERTIFIED",
        "incident_id": INCIDENT_ID,
        "report_count": (
            len(ledger["reports"])
            + len(ledger.get("structured_reports", []))
            + len(ledger.get("mature_product_packs", []))
        ),
        "drift": drift,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if arguments.write or not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
