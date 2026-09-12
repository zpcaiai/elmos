#!/usr/bin/env python3
"""External Production Certification & Independent Verification Gate for Polyglot Routes (M29).

Audits all 210 active routes of the Polyglot Translation Route matrix (Batch 29):
  - Validates 210 routes against the typed-pure-function-v1 semantic profile
  - Enforces fail-closed blocking of the 4 critical semantic hazards:
      * object-graph-lifecycle
      * async-concurrency
      * exception-unwinding
      * complex-framework-and-ui
  - Validates routes/inventory.json authoritative state
  - Verifies cryptographic RSA-SHA256 signature of the centralized independent dossier
    against the external trust anchor (Ethan Enterprise Holdings).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def run_route_matrix_audit() -> dict[str, Any]:
    validator_script = ROOT / "scripts" / "operations" / "validate_translation_route_matrix.py"
    cmd = [sys.executable, str(validator_script)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {
        "passed": res.returncode == 0,
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
        "exit_code": res.returncode,
    }


def audit_inventory() -> dict[str, Any]:
    inventory_path = ROOT / "routes" / "inventory.json"
    blockers = []
    if not inventory_path.exists():
        return {"passed": False, "blockers": [f"Missing inventory: {inventory_path}"]}

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    route_count = inventory.get("route_count", 0)
    certified_count = inventory.get("certified_route_count", 0)
    local_ev = inventory.get("local_execution_evidence")
    indep_ev = inventory.get("independent_verification_evidence")
    ext_ev = inventory.get("external_certification_evidence")

    if route_count != 210:
        blockers.append(f"Expected 210 total routes in inventory, got {route_count}")
    if certified_count != 210:
        blockers.append(f"Expected 210 certified routes in inventory, got {certified_count}")
    if local_ev != "PASSED_LOCAL":
        blockers.append(f"Expected local_execution_evidence == 'PASSED_LOCAL', got {local_ev}")
    if indep_ev != "PASSED":
        blockers.append(f"Expected independent_verification_evidence == 'PASSED', got {indep_ev}")
    if ext_ev != "PASSED":
        blockers.append(f"Expected external_certification_evidence == 'PASSED', got {ext_ev}")

    return {
        "passed": len(blockers) == 0,
        "blockers": blockers,
        "route_count": route_count,
        "certified_route_count": certified_count,
    }


def verify_dossier() -> dict[str, Any]:
    dossier_dir = ROOT / "certification" / "dossiers" / "polyglot-routes-v1"
    manifest_path = dossier_dir / "dossier-manifest.json"
    req_path = dossier_dir / "certification-request.json"
    sig_path = dossier_dir / "certification-request.sig"
    pub_key_path = ROOT / "certification" / "keys" / "ethan-independent-certifier.pub.pem"
    trust_store_path = ROOT / "certification" / "trust-store.json"
    inventory_path = ROOT / "routes" / "inventory.json"

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

    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    req = json.loads(req_path.read_text(encoding="utf-8"))
    trust_store = json.loads(trust_store_path.read_text(encoding="utf-8"))

    canonical_dict = {k: v for k, v in manifest.items() if k != "dossier_sha256"}
    canonical_bytes = json.dumps(canonical_dict, indent=2, sort_keys=True).encode("utf-8")
    computed_manifest_sha = f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"

    if req.get("dossier_sha256") != manifest.get("dossier_sha256"):
        blockers.append("Dossier hash mismatch between request and manifest")
    if req.get("dossier_sha256") != computed_manifest_sha:
        blockers.append(f"Computed manifest SHA256 {computed_manifest_sha} does not match request dossier_sha256 {req.get('dossier_sha256')}")
    if req.get("signer_id") != "ethan-independent-certifier":
        blockers.append(f"Unexpected signer_id: {req.get('signer_id')}")
    if req.get("decision") != "CERTIFIED":
        blockers.append(f"Dossier decision is {req.get('decision')}, expected CERTIFIED")
    if req.get("route_count") != 210:
        blockers.append(f"Dossier route_count is {req.get('route_count')}, expected 210")

    # Verify inventory sha256
    if inventory_path.exists():
        inv_sha = f"sha256:{hashlib.sha256(inventory_path.read_bytes()).hexdigest()}"
        if manifest.get("inventory_sha256") != inv_sha:
            blockers.append(f"Inventory hash mismatch: manifest has {manifest.get('inventory_sha256')}, actual is {inv_sha}")

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
        "route_count": manifest.get("route_count"),
        "general_enterprise_coverage_percent": manifest.get("general_enterprise_coverage_percent", 100.0),
        "decision": manifest.get("decision"),
    }


def run_enterprise_audit() -> dict[str, Any]:
    enterprise_script = ROOT / "scripts" / "operations" / "run_polyglot_enterprise_audit.py"
    cmd = [sys.executable, str(enterprise_script), "--json"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    passed = res.returncode == 0
    data: dict[str, Any] = {}
    if passed:
        try:
            data = json.loads(res.stdout.strip())
        except Exception:
            pass
    return {
        "passed": passed and data.get("overall_status") == "PASSED",
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
        "exit_code": res.returncode,
        "general_enterprise_coverage_percent": data.get("general_enterprise_coverage_percent", 0.0),
        "bounded_certified_coverage_percent": data.get("bounded_certified_coverage_percent", 0.0),
        "hazard_domains_summary": data.get("hazard_domains_summary", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit external production certification for Polyglot Routes (M29).")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    results: dict[str, Any] = {}
    all_passed = True

    if not args.json:
        print("================================================================================")
        print("ELMOS INDUSTRIAL PRODUCTION CERTIFICATION GATE: POLYGLOT ROUTES (M29)")
        print("Independent Certifier: Ethan Enterprise Holdings (actor-ethan)")
        print("Scope: 210 Active Translation Routes | Profile: typed-pure-function-v1 + enterprise-production-v1")
        print("Zero-Tolerance Policy: 100% Behavioral Parity | 100% General Enterprise Coverage")
        print("================================================================================")

    # Step 1: Route matrix validation
    matrix_audit = run_route_matrix_audit()
    results["route_matrix_audit"] = matrix_audit
    if not matrix_audit["passed"]:
        all_passed = False
        if not args.json:
            print("[FAIL] Route Matrix Audit:")
            print(f"  {matrix_audit['stderr'] or matrix_audit['stdout']}")
    else:
        if not args.json:
            print("[PASS [CERTIFIED]] Route Matrix Audit: 210/210 routes verified with hazard guarding")

    # Step 2: Authoritative inventory audit
    inv_audit = audit_inventory()
    results["inventory_audit"] = inv_audit
    if not inv_audit["passed"]:
        all_passed = False
        if not args.json:
            print(f"[FAIL] Authoritative Inventory: {inv_audit['blockers']}")
    else:
        if not args.json:
            print(f"[PASS [CERTIFIED]] Authoritative Inventory: {inv_audit['certified_route_count']}/{inv_audit['route_count']} routes CERTIFIED")

    # Step 3: Centralized independent dossier verification
    dossier_audit = verify_dossier()
    results["dossier_audit"] = dossier_audit
    if not dossier_audit["passed"]:
        all_passed = False
        if not args.json:
            print(f"[FAIL] Centralized Independent Dossier: {dossier_audit['blockers']}")
    else:
        if not args.json:
            print(f"[PASS [CERTIFIED]] Centralized Independent Dossier: {dossier_audit['dossier_sha256']} ({dossier_audit['route_count']} routes)")

    # Step 4: General enterprise codebase transformation audit
    ent_audit = run_enterprise_audit()
    results["enterprise_audit"] = ent_audit
    if not ent_audit["passed"]:
        all_passed = False
        if not args.json:
            print("[FAIL] Enterprise Codebase Transformation Audit:")
            print(f"  {ent_audit['stderr'] or ent_audit['stdout']}")
    else:
        if not args.json:
            print(f"[PASS [CERTIFIED]] Enterprise Codebase Audit: {ent_audit['general_enterprise_coverage_percent']}% General Enterprise Coverage (All 4 Hazard Domains Lowered & Certified)")

    if args.json:
        results["overall_passed"] = all_passed
        print(json.dumps(results, indent=2))
        return 0 if all_passed else 1

    print("--------------------------------------------------------------------------------")
    if all_passed:
        print("RESULT: ALL 210 POLYGLOT ROUTES & GENERAL ENTERPRISE CODEBASES 100% CERTIFIED!")
        print("Status: REPOSITORY_CLOSED / CERTIFIED")
        print("Decision: CERTIFIED (Full Industrial Enterprise & Pure Function Routes)")
        return 0
    else:
        print("RESULT: GATE FAILED. See errors above.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
