#!/usr/bin/env python3
"""Rehearse the strict-suite trust-anchor matrix with a throwaway key.

## What gap this closes

`tests/test-suite/test_toolkit.py` already exercises the certification path well:
it accepts a complete independently signed bundle and rejects NOT_RUN results,
unsigned synthetic passes, tampered raw evidence, forged requests,
self-verification, and non-independent corpora.

What it does not cover is the **trust-anchor validity matrix** inside
`verify_certification_request`. Those branches decide whether a signature is
honoured at all, and none of them had a test:

  - a revoked anchor
  - an anchor lacking the `independent-certifier` role
  - an algorithm other than rsa-sha256
  - an anchor outside its valid_from/valid_until window
  - a public key whose digest does not match the anchor
  - a signer with no anchor in the trust store
  - a request or signature located outside the suite root
  - an expired request, correctly re-signed so only the interval is wrong

Each is a path where a wrong answer silently grants certification to a signature
that should not be honoured. This rehearsal drives all of them against the real
gate function, plus the positive case, so the matrix cannot rot unnoticed.

## What this does NOT do

It certifies nothing. It runs entirely in a temporary directory, never writes
into `test-suites/`, and never touches a real result, evidence file, or trust
store. The throwaway key is discarded when the process exits.

Passing means the trust-anchor checks behave as the gate documents. It says
nothing about whether any case has been independently verified — those remain
`NOT_RUN` until a verifier independent of whoever executed the suite supplies
real evidence. See docs/INDEPENDENT_VERIFICATION.md.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "test-suite" / "run_strict_test_gate.py"
SUITE_ID = "batch1-37-strict"
SIGNER = "rehearsal-independent-certifier"


def load_gate():
    spec = importlib.util.spec_from_file_location("strict_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_keypair(directory: Path) -> tuple[Path, Path]:
    private = directory / "rehearsal-key.pem"
    public = directory / "rehearsal-key.pub.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-out", str(private),
         "-pkeyopt", "rsa_keygen_bits:2048"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(private), "-pubout", "-out", str(public)],
        check=True, capture_output=True,
    )
    return private, public


def sign(private: Path, payload: Path, signature: Path) -> None:
    subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private),
         "-out", str(signature), str(payload)],
        check=True, capture_output=True,
    )


def build_inputs(gate, workspace: Path, public: Path, private: Path,
                 controls: dict, bindings: list) -> tuple[Path, Path, Path]:
    """Write a well-formed request, its signature, and an external trust store."""
    suite = workspace / "suite"
    suite.mkdir(parents=True, exist_ok=True)
    # The gate requires request and signature to live beneath the suite root and
    # the trust store to live outside it, so mirror that layout exactly.
    outside = workspace / "external-trust"
    outside.mkdir(parents=True, exist_ok=True)
    shutil.copy(public, outside / public.name)

    now = datetime.now(timezone.utc)
    request = {
        "request_version": 1,
        "suite_id": SUITE_ID,
        "requested_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "signer_id": SIGNER,
        "authorization_refs": ["rehearsal://not-an-authorization"],
        "control_digests": controls,
        "case_bindings": bindings,
    }
    request_path = suite / "certification-request.json"
    request_path.write_text(json.dumps(request, indent=2, sort_keys=True), encoding="utf-8")

    signature_path = suite / "certification-request.sig"
    sign(private, request_path, signature_path)

    trust_store = {
        "authorities": [
            {
                "signer_id": SIGNER,
                "roles": ["independent-certifier"],
                "algorithm": "rsa-sha256",
                "revoked": False,
                "valid_from": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "valid_until": (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "public_key": public.name,
                "public_key_sha256": gate.sha256_file(outside / public.name),
            }
        ]
    }
    trust_path = outside / "trust-store.json"
    trust_path.write_text(json.dumps(trust_store, indent=2, sort_keys=True), encoding="utf-8")
    return request_path, signature_path, trust_path


def run_case(gate, label: str, suite_root: Path, request: Path, signature: Path,
             trust: Path, controls: dict, bindings: list, expect_ok: bool) -> bool:
    blockers: list[str] = []
    now = datetime.now(timezone.utc)
    try:
        ok = gate.verify_certification_request(
            suite_root, request, signature, trust,
            controls, bindings, {SIGNER}, now, blockers,
        )
    except Exception as exc:  # noqa: BLE001
        ok, blockers = False, [f"raised {type(exc).__name__}: {exc}"]

    passed = ok == expect_ok
    verdict = "OK " if passed else "BUG"
    outcome = "verified" if ok else "rejected"
    print(f"  [{verdict}] {label:<52} -> {outcome}")
    if not passed:
        wanted = "verify" if expect_ok else "reject"
        print(f"         expected the gate to {wanted}; blockers={blockers[:2]}")
    return passed


def main() -> int:
    gate = load_gate()
    # Minimal internally-consistent control/binding values. The gate compares the
    # request against whatever the caller computed from the suite, so rehearsing
    # the crypto and trust machinery does not require fabricating 408 results —
    # and deliberately must not, since fabricated results are exactly what the
    # surrounding gate exists to reject.
    controls = {"rehearsal-control": "sha256:" + "0" * 64}
    bindings = [{"case_id": "REHEARSAL-001", "result_sha256": "sha256:" + "1" * 64}]

    results: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="elmos-cert-rehearsal-") as raw:
        workspace = Path(raw)
        keys = workspace / "keys"
        keys.mkdir()
        private, public = make_keypair(keys)
        request, signature, trust = build_inputs(
            gate, workspace, public, private, controls, bindings
        )
        suite_root = workspace / "suite"

        print("positive path — a correct submission must verify:")
        results.append(run_case(
            gate, "well-formed, correctly signed, valid anchor",
            suite_root, request, signature, trust, controls, bindings, expect_ok=True,
        ))

        print("\nfail-closed paths — each tamper must be rejected:")

        original = request.read_text(encoding="utf-8")

        tampered = json.loads(original)
        tampered["case_bindings"] = [{"case_id": "SWAPPED", "result_sha256": "sha256:" + "2" * 64}]
        request.write_text(json.dumps(tampered, indent=2, sort_keys=True), encoding="utf-8")
        results.append(run_case(
            gate, "case bindings altered after signing",
            suite_root, request, signature, trust, controls, bindings, expect_ok=False,
        ))
        request.write_text(original, encoding="utf-8")

        store = json.loads(trust.read_text(encoding="utf-8"))
        for label, mutate in (
            ("trust anchor revoked", lambda s: s["authorities"][0].update({"revoked": True})),
            ("anchor lacks independent-certifier role",
             lambda s: s["authorities"][0].update({"roles": ["observer"]})),
            ("non rsa-sha256 algorithm",
             lambda s: s["authorities"][0].update({"algorithm": "ed25519"})),
            ("anchor outside its validity interval",
             lambda s: s["authorities"][0].update(
                 {"valid_until": "2020-01-01T00:00:00Z"})),
            ("public key digest mismatch",
             lambda s: s["authorities"][0].update(
                 {"public_key_sha256": "sha256:" + "9" * 64})),
            ("signer has no trust anchor at all",
             lambda s: s["authorities"][0].update({"signer_id": "somebody-else"})),
        ):
            mutated = json.loads(json.dumps(store))
            mutate(mutated)
            trust.write_text(json.dumps(mutated, indent=2, sort_keys=True), encoding="utf-8")
            results.append(run_case(
                gate, label, suite_root, request, signature, trust,
                controls, bindings, expect_ok=False,
            ))
        trust.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")

        stray = workspace / "outside-suite-request.json"
        stray.write_text(original, encoding="utf-8")
        results.append(run_case(
            gate, "request located outside the suite root",
            suite_root, stray, signature, trust, controls, bindings, expect_ok=False,
        ))

        expired = json.loads(original)
        expired["expires_at"] = "2020-01-02T00:00:00Z"
        expired["requested_at"] = "2020-01-01T00:00:00Z"
        request.write_text(json.dumps(expired, indent=2, sort_keys=True), encoding="utf-8")
        sign(private, request, signature)
        results.append(run_case(
            gate, "expired request (correctly re-signed)",
            suite_root, request, signature, trust, controls, bindings, expect_ok=False,
        ))

    total, good = len(results), sum(results)
    print()
    if good != total:
        print(f"REHEARSAL FAILED: {total - good}/{total} checks behaved incorrectly", file=sys.stderr)
        print("The certification path does not behave as its own gate documents.", file=sys.stderr)
        return 1
    print(f"REHEARSAL PASSED: {good}/{total} — trust-anchor matrix behaves as documented")
    print("Grants nothing. Every case remains NOT_RUN until a real independent")
    print("verifier, distinct from whoever executed the suite, supplies real evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
