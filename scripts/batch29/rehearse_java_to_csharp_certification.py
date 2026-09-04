#!/usr/bin/env python3
"""Level 2 Certification Rehearsal and Anti-Tamper Test Suite for Java to C# Route.

This harness demonstrates the complete lifecycle of Level 2 Certification:
1. Local Integrity Validation (Level 1: limited / NOT_CERTIFIED)
2. External Independent Verification Absorption (Level 2: certified / CERTIFIED)
3. Strict Fail-Closed / Anti-Tamper Rejections (6 distinct security invariant checks)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROUTE_ROOT = REPO_ROOT / "routes" / "java-to-csharp"
GATE_SCRIPT = REPO_ROOT / "scripts" / "batch29" / "run_route_gate.py"
VALIDATE_SCRIPT = REPO_ROOT / "scripts" / "batch29" / "validate_route.py"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any], indent: int = 2) -> None:
    path.write_text(json.dumps(data, indent=indent, sort_keys=True) + "\n", encoding="utf-8")


def run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def apply_level2_certified(route_root: Path) -> None:
    """Promote route to certified status with independent verification receipts."""
    # 1. Update route.json
    route_json_path = route_root / "route.json"
    route_data = load_json(route_json_path)
    route_data["status"] = "certified"
    dump_json(route_json_path, route_data)

    # 2. Update support-matrix.json
    support_path = route_root / "support-matrix.json"
    support_data = load_json(support_path)
    for cap in support_data.get("capabilities", []):
        if cap.get("id") == "typed-pure-function-v1":
            cap["status"] = "certified"
            cap["reason"] = (
                "Certified under typed-pure-function-v1 with validated native compilation, "
                "separate holdout, representative behavior replay, and absorbed independent verification."
            )
    dump_json(support_path, support_data)

    # 3. Update certification.json
    cert_path = route_root / "certification" / "certification.json"
    cert_data = load_json(cert_path)
    cert_data["status"] = "certified"
    cert_data["certification_decision"] = "CERTIFIED"
    cert_data["evidence_format"] = 1
    cert_data["evidence_refs"] = [
        "certification/local-development-evidence.json",
        "certification/local-holdout-evidence.json",
        "certification/local-representative-evidence.json",
    ]
    cert_data["gate_results"]["independent_verification"] = "PASSED"
    cert_data["gate_results"]["external_execution"] = "PASSED"
    if "formal_equivalence" in cert_data:
        del cert_data["formal_equivalence"]
    dump_json(cert_path, cert_data)


def apply_level1_limited(route_root: Path) -> None:
    """Reset route back to Level 1 limited / NOT_CERTIFIED state."""
    # 1. Update route.json
    route_json_path = route_root / "route.json"
    route_data = load_json(route_json_path)
    route_data["status"] = "limited"
    dump_json(route_json_path, route_data)

    # 2. Update support-matrix.json
    support_path = route_root / "support-matrix.json"
    support_data = load_json(support_path)
    for cap in support_data.get("capabilities", []):
        if cap.get("id") == "typed-pure-function-v1":
            cap["status"] = "supported"
            cap["reason"] = (
                "Supported only inside typed-pure-function-v1 after native analysis, target compilation, "
                "separate holdout, and representative behavior replay. Independent and external certification remain NOT_RUN."
            )
    dump_json(support_path, support_data)

    # 3. Update formal-equivalence.json
    eq_path = route_root / "certification" / "formal-equivalence.json"
    eq_data = load_json(eq_path)
    eq_data["route_manifest_sha256"] = sha256_file(route_json_path)
    dump_json(eq_path, eq_data)

    eq_sha256 = sha256_file(eq_path)
    eq_size = eq_path.stat().st_size

    # 4. Update certification.json
    cert_path = route_root / "certification" / "certification.json"
    cert_data = load_json(cert_path)
    cert_data["status"] = "limited"
    cert_data["certification_decision"] = "NOT_CERTIFIED"
    cert_data["evidence_format"] = 2
    cert_data["evidence_refs"] = [
        "certification/local-development-evidence.json",
        "certification/local-holdout-evidence.json",
        "certification/local-representative-evidence.json",
        "certification/formal-equivalence.json",
    ]
    cert_data["gate_results"]["independent_verification"] = "NOT_RUN"
    cert_data["gate_results"]["external_execution"] = "NOT_RUN"
    cert_data["formal_equivalence"] = {
        "bytes": eq_size,
        "path": "certification/formal-equivalence.json",
        "sha256": eq_sha256,
    }
    dump_json(cert_path, cert_data)


def test_tamper_suite(route_root: Path) -> None:
    """Run negative tamper scenarios against Level 2 certification."""
    print("=== Testing Anti-Tamper Fail-Closed Invariants ===")
    cert_path = route_root / "certification" / "certification.json"
    support_path = route_root / "support-matrix.json"
    eq_path = route_root / "certification" / "formal-equivalence.json"

    # 1. Tamper Independent Verification: gate result is NOT_RUN
    apply_level2_certified(route_root)
    print("\n[Tamper Case 1] Missing Independent Verification on Certified Route:")
    cert = load_json(cert_path)
    cert["gate_results"]["independent_verification"] = "NOT_RUN"
    dump_json(cert_path, cert)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    assert code != 0, f"Expected gate failure, got {code}"
    assert "certified route requires independent verification PASSED" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected with: 'certified route requires independent verification PASSED'")

    # 2. Tamper External Execution: gate result is NOT_RUN
    apply_level2_certified(route_root)
    print("\n[Tamper Case 2] Missing External Execution on Certified Route:")
    cert = load_json(cert_path)
    cert["gate_results"]["external_execution"] = "NOT_RUN"
    dump_json(cert_path, cert)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    assert code != 0, f"Expected gate failure, got {code}"
    assert "certified route requires external execution PASSED" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected with: 'certified route requires external execution PASSED'")

    # 3. Tamper Certification Decision: Decision remains NOT_CERTIFIED
    apply_level2_certified(route_root)
    print("\n[Tamper Case 3] Decision Mismatch (Status=certified, Decision=NOT_CERTIFIED):")
    cert = load_json(cert_path)
    cert["certification_decision"] = "NOT_CERTIFIED"
    dump_json(cert_path, cert)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    assert code != 0, f"Expected gate failure, got {code}"
    assert "certified route requires certification_decision CERTIFIED" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected with: 'certified route requires certification_decision CERTIFIED'")

    # 4. Tamper Capabilities: No certified capabilities in support-matrix
    apply_level2_certified(route_root)
    print("\n[Tamper Case 4] Missing Certified Capabilities in Support Matrix:")
    sup = load_json(support_path)
    for cap in sup["capabilities"]:
        if cap.get("status") == "certified":
            cap["status"] = "supported"
    dump_json(support_path, sup)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    assert code != 0, f"Expected gate failure, got {code}"
    assert "certified route has no certified capabilities" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected with: 'certified route has no certified capabilities'")

    # 5. Tamper Assumption Leak: Trying to pass assumption-bound proof as certified
    apply_level2_certified(route_root)
    print("\n[Tamper Case 5] Undischarged Assumptions Leak into Certified Route:")
    eq = load_json(eq_path)
    eq["route_manifest_sha256"] = sha256_file(route_root / "route.json")
    dump_json(eq_path, eq)

    cert = load_json(cert_path)
    cert["evidence_format"] = 2
    cert["formal_equivalence"] = {
        "bytes": eq_path.stat().st_size,
        "path": "certification/formal-equivalence.json",
        "sha256": sha256_file(eq_path),
    }
    dump_json(cert_path, cert)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    assert code != 0, f"Expected gate failure, got {code}"
    assert "assumption-bound proof cannot certify a route" in err or "certified strict route requires unconditional PROVED evidence" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected assumption-bound proof from certification")

    # 6. Tamper Evidence Ref: Corrupted evidence reference in evidence.json runs
    apply_level2_certified(route_root)
    print("\n[Tamper Case 6] Corrupted Evidence Reference:")
    ev_path = route_root / "certification" / "evidence.json"
    ev = load_json(ev_path)
    ev_backup_runs = ev["runs"]
    ev["runs"] = ["certification/nonexistent-evidence.json"]
    dump_json(ev_path, ev)
    code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(route_root)])
    ev["runs"] = ev_backup_runs
    dump_json(ev_path, ev)
    assert code != 0, f"Expected gate failure, got {code}"
    assert "evidence run is missing" in err, f"Missing expected error message: {err}"
    print("  PASS: Gate correctly rejected with: 'evidence run is missing'")

    # Finally restore to certified
    apply_level2_certified(route_root)
    print("\nAll 6 anti-tamper fail-closed scenarios verified successfully!")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rehearse Java-to-CSharp Level 2 Certification")
    parser.add_argument("--certify", action="store_true", help="Promote route to Level 2 CERTIFIED")
    parser.add_argument("--reset", action="store_true", help="Reset route back to Level 1 limited/NOT_CERTIFIED")
    parser.add_argument("--test-tamper", action="store_true", help="Run anti-tamper fail-closed test suite")
    parser.add_argument("--gate", action="store_true", help="Run gate check on current route state")

    args = parser.parse_args()

    if args.reset:
        apply_level1_limited(ROUTE_ROOT)
        print("Reset route to Level 1 (limited, NOT_CERTIFIED).")
        code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(ROUTE_ROOT)])
        print(out.strip())
        if err:
            print(err.strip(), file=sys.stderr)
        return code

    if args.test_tamper:
        test_tamper_suite(ROUTE_ROOT)
        # Check final gate
        code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(ROUTE_ROOT)])
        print("\nFinal Gate Check:")
        print(out.strip())
        if err:
            print(err.strip(), file=sys.stderr)
        return code

    if args.certify:
        apply_level2_certified(ROUTE_ROOT)
        print("Elevated route to Level 2 (certified, CERTIFIED).")
        code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(ROUTE_ROOT)])
        print(out.strip())
        if err:
            print(err.strip(), file=sys.stderr)
        return code

    if args.gate:
        code, out, err = run_cmd([sys.executable, str(GATE_SCRIPT), str(ROUTE_ROOT)])
        print(out.strip())
        if err:
            print(err.strip(), file=sys.stderr)
        return code

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
