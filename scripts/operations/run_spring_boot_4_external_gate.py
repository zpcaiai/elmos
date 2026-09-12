#!/usr/bin/env python3
"""External Production Certification & Independent Verification Gate for Spring Boot 4.x Modernization (M30).

Audits all 7 production routes of the Spring Boot 4.x Modernization business line:
  1. spring-boot-1-5-to-4-1-0 (Maven Boot 1.5.22.RELEASE -> Boot 4.1.0 Java 21)
  2. spring-boot-2-0-2-6-to-4-1-0 (Maven Boot 2.3.12.RELEASE -> Boot 4.1.0 Java 21)
  3. spring-boot-2-7-18-to-4-1-0 (Maven Boot 2.7.18 -> Boot 4.1.0 Java 21)
  4. spring-boot-3-0-3-4-to-4-1-0 (Maven Boot 3.4.1 -> Boot 4.1.0 Java 21)
  5. spring-boot-3-5-to-4-1-0 (Maven Boot 3.5.3 -> Boot 4.1.0 Java 21)
  6. spring-boot-2-x-gradle-to-4-1-0 (Gradle Boot 2.7.18 -> Boot 4.1.0 Java 21)
  7. spring-framework-5-3-mvc-to-boot-4-1-0 (Spring MVC 5.3.39 -> Boot 4.1.0 Java 21)

Enforces:
  - Batch 30 quality gates with 13 verified external evidence classes (P0-P11)
  - Zero-tolerance policy (0 critical regressions, 0 silent drops, 0 unknowns, 0 flakiness)
  - Cryptographic RSA-SHA256 signature verification of the centralized independent dossier
    against the external trust anchor (Ethan Enterprise Holdings).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

SPRING_BOOT_4_PACK_KEYS = [
    "spring-boot-1-5-to-4-1-0",
    "spring-boot-2-0-2-6-to-4-1-0",
    "spring-boot-2-7-18-to-4-1-0",
    "spring-boot-3-0-3-4-to-4-1-0",
    "spring-boot-3-5-to-4-1-0",
    "spring-boot-2-x-gradle-to-4-1-0",
    "spring-framework-5-3-mvc-to-boot-4-1-0",
]


def audit_framework_pack(pack_key: str) -> dict[str, Any]:
    pack_dir = ROOT / "framework-packs" / pack_key
    campaign_path = pack_dir / "certification" / "p0-p11-campaign.json"
    intake_path = pack_dir / "certification" / "campaign-runs" / "actor-ethan-certified" / "external-certification-intake.json"
    trust_store_path = pack_dir / "certification" / "campaign-runs" / "actor-ethan-certified" / "trust" / "trust-store.json"
    evidence_root = pack_dir / "certification" / "campaign-runs" / "actor-ethan-certified" / "evidence"

    gate_script = ROOT / "scripts" / "batch30" / "run_framework_gate.py"

    cmd = [
        sys.executable,
        str(gate_script),
        str(pack_dir),
        "--campaign", str(campaign_path),
        "--external-intake", str(intake_path),
        "--trust-store", str(trust_store_path),
        "--evidence-root", str(pack_dir),
        "--evidence-root", str(evidence_root),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    passed = res.returncode == 0 and "decision=CERTIFIED" in res.stdout

    return {
        "pack_key": pack_key,
        "passed": passed,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
        "exit_code": res.returncode,
    }


def verify_dossier() -> dict[str, Any]:
    dossier_dir = ROOT / "certification" / "dossiers" / "spring-boot-4-modernization-v1"
    manifest_path = dossier_dir / "dossier-manifest.json"
    req_path = dossier_dir / "certification-request.json"
    sig_path = dossier_dir / "certification-request.sig"
    pub_key_path = ROOT / "certification" / "keys" / "ethan-independent-certifier.pub.pem"
    trust_store_path = ROOT / "certification" / "trust-store.json"

    blockers = []
    if not manifest_path.exists():
        blockers.append(f"Missing dossier manifest: {manifest_path}")
    if not req_path.exists():
        blockers.append(f"Missing certification request: {req_path}")
    if not sig_path.exists():
        blockers.append(f"Missing cryptographic signature: {sig_path}")
    if not pub_key_path.exists():
        blockers.append(f"Missing public key: {pub_key_path}")
    if not trust_store_path.exists():
        blockers.append(f"Missing trust store: {trust_store_path}")

    if blockers:
        return {"passed": False, "blockers": blockers}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    req = json.loads(req_path.read_text(encoding="utf-8"))
    trust_store = json.loads(trust_store_path.read_text(encoding="utf-8"))

    if req.get("dossier_sha256") != manifest.get("dossier_sha256"):
        blockers.append("Dossier hash mismatch between request and manifest")

    if req.get("signer_id") != "ethan-independent-certifier":
        blockers.append(f"Unexpected signer_id: {req.get('signer_id')}")

    # Verify trust store contains active anchor
    anchors = [a for a in trust_store.get("authorities", []) if a.get("signer_id") == "ethan-independent-certifier"]
    if not anchors:
        blockers.append("No trust anchor found for ethan-independent-certifier in trust-store.json")
    elif anchors[0].get("revoked") is not False:
        blockers.append("Trust anchor is revoked")

    # Verify signature with openssl
    res = subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(pub_key_path),
            "-signature",
            str(sig_path),
            str(req_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if res.returncode != 0:
        blockers.append(f"OpenSSL signature verification failed: {res.stderr.strip()}")

    return {
        "passed": len(blockers) == 0,
        "blockers": blockers,
        "dossier_sha256": manifest.get("dossier_sha256"),
        "target_count": manifest.get("target_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit external production certification for Spring Boot 4.x Modernization.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    _args = parser.parse_args()

    results = []
    all_passed = True

    print("================================================================================")
    print("ELMOS INDUSTRIAL PRODUCTION CERTIFICATION GATE: SPRING BOOT 4.X MODERNIZATION (M30)")
    print("Independent Certifier: Ethan Enterprise Holdings (actor-ethan)")
    print("Zero-Tolerance Policy: 100% Behavioral Parity | 0 Critical Regressions")
    print("================================================================================")

    for pack_key in SPRING_BOOT_4_PACK_KEYS:
        audit = audit_framework_pack(pack_key)
        results.append(audit)
        status_str = "PASS [CERTIFIED]" if audit["passed"] else "FAIL"
        print(f"[{status_str}] Pack: {pack_key}")
        if not audit["passed"]:
            all_passed = False
            print(f"  Details: {audit['stderr'] or audit['stdout']}")

    dossier_audit = verify_dossier()
    if not dossier_audit["passed"]:
        all_passed = False
        print(f"[FAIL] Centralized Independent Dossier: {dossier_audit['blockers']}")
    else:
        print(f"[PASS [SIGNATURE_VALID]] Centralized Independent Dossier: {dossier_audit['dossier_sha256']} ({dossier_audit['target_count']} targets)")

    print("--------------------------------------------------------------------------------")
    if all_passed:
        print("RESULT: ALL 7 SPRING BOOT 4.X MODERNIZATION PRODUCTION ROUTES 100% CERTIFIED!")
        print("Status: REPOSITORY_CLOSED / CERTIFIED")
        print("Decision: CERTIFIED (Authentic cryptographic proof verified against trust store)")
        return 0
    else:
        print("RESULT: GATE FAILED. See errors above.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
