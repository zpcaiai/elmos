from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "test-suites/batch38-45-strict"
SCRIPTS = ROOT / "scripts/test-suite-b38-45"
SCHEMAS = ROOT / "schemas/test-suite-b38-45"
SKILLS = ROOT / ".agents/skills"
sys.path.insert(0, str(SCRIPTS))
from _common import load_json, sha256_file, sha256_json  # noqa: E402


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_record(role: str, path: Path, base: Path) -> dict[str, object]:
    return {
        "role": role,
        "path": os.path.relpath(path, base),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def external_record(path: Path, suite: Path, **fields) -> dict[str, object]:
    return {
        **fields,
        "path": os.path.relpath(path, suite),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


class SyntheticFixture:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.suite = base / "suite"
        shutil.copytree(SUITE, self.suite)
        self.trust = base / "trust"
        self.trust.mkdir()
        self.request = self.suite / "certification-request.json"
        self.signature = self.suite / "certification-request.sig"
        self.trust_store = self.trust / "trust-store.json"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self._materialize()

    def _materialize(self) -> None:
        evidence = self.suite / "evidence"
        manifests = evidence / "manifests"
        shared = manifests / "shared"
        cases_dir = manifests / "cases"
        for path in (manifests, shared, cases_dir):
            path.mkdir(parents=True, exist_ok=True)
        write_json(shared / "artifact.json", {"artifact_id": "synthetic-gate-test", "scope": "M38-M45"})
        write_json(shared / "environment.json", {"environment_id": "synthetic-approved-equivalent", "scope": "M38-M45"})
        write_json(shared / "provenance.json", {"builder": "synthetic-test-builder", "production_evidence": False})
        (shared / "replay.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (shared / "replay.sh").chmod(0o755)
        write_json(shared / "holdout-attestation.json", {"kind": "holdout", "independent": True, "production_evidence": False})
        write_json(shared / "representative-attestation.json", {"kind": "representative", "independent": True, "production_evidence": False})
        for kind in ("development", "holdout", "representative"):
            write_json(shared / f"{kind}-corpus.json", {"kind": kind, "fixture": f"synthetic-{kind}", "production_evidence": False})
        artifact_digest = sha256_file(shared / "artifact.json")
        environment_digest = sha256_file(shared / "environment.json")
        catalog = load_json(self.suite / "cases/catalog.json")
        catalog_digest = sha256_file(self.suite / "cases/catalog.json")
        zero_keys = load_json(self.suite / "strict-profile.json")["zero_tolerance"]
        started = (self.now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
        finished = (self.now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        for case in catalog["cases"]:
            case_id = case["case_id"]
            log = cases_dir / f"{case_id}-execution.log"
            log.write_text(f"synthetic gate logic exercise for {case_id}\n", encoding="utf-8")
            execution = cases_dir / f"{case_id}-execution.json"
            write_json(execution, {"case_id": case_id, "status": "passed", "artifact_digest": artifact_digest, "environment_digest": environment_digest})
            verification = cases_dir / f"{case_id}-verification.json"
            write_json(verification, {"case_id": case_id, "status": "accepted", "verifier_id": "synthetic-certifier", "production_evidence": False})
            manifest_path = manifests / f"{case_id}.json"
            replay = f"./evidence/manifests/shared/replay.sh --case {case_id}"
            raw = [
                file_record("artifact-binding", shared / "artifact.json", manifests),
                file_record("environment-binding", shared / "environment.json", manifests),
                file_record("execution-log", log, manifests),
                file_record("execution-result", execution, manifests),
                file_record("provenance", shared / "provenance.json", manifests),
                file_record("verification", verification, manifests),
                file_record("replay-script", shared / "replay.sh", manifests),
                file_record("holdout-attestation", shared / "holdout-attestation.json", manifests),
                file_record("representative-attestation", shared / "representative-attestation.json", manifests),
            ]
            corpora = []
            for kind, attestation, access in (
                ("development", verification, True),
                ("holdout", shared / "holdout-attestation.json", False),
                ("representative", shared / "representative-attestation.json", False),
            ):
                corpus_path = shared / f"{kind}-corpus.json"
                corpora.append({
                    "kind": kind,
                    "digest": sha256_file(corpus_path),
                    "manifest_path": os.path.relpath(corpus_path, manifests),
                    "authoring_access": access,
                    "attestation_ref": os.path.relpath(attestation, manifests),
                    "verifier_id": "synthetic-certifier",
                })
            manifest = {
                "manifest_version": 2,
                "manifest_id": f"synthetic-{case_id}",
                "case_id": case_id,
                "case_digest": sha256_json(case),
                "catalog_digest": catalog_digest,
                "artifact_digest": artifact_digest,
                "environment_digest": environment_digest,
                "execution_kind": "real",
                "started_at": started,
                "finished_at": finished,
                "executor": {"id": "synthetic-runner", "role": "executor"},
                "verifier": {"id": "synthetic-certifier", "role": "independent-verifier", "independent": True},
                "authorization_refs": ["synthetic-gate-test-only"],
                "replay_command": replay,
                "files": raw,
                "corpora": corpora,
            }
            write_json(manifest_path, manifest)
            result = {
                "case_id": case_id,
                "status": "passed",
                "artifact_digest": artifact_digest,
                "environment_digest": environment_digest,
                "started_at": started,
                "finished_at": finished,
                "execution_kind": "real",
                "evidence": [os.path.relpath(manifest_path, self.suite)],
                "replay_command": replay,
                "trace_coverage": 1.0,
                "authorization_refs": ["synthetic-gate-test-only"],
                "counters": {key: 0 for key in zero_keys},
                "findings": [],
            }
            if case["category"] == "performance":
                result["metrics"] = {"p95_latency_regression": 0.0, "p99_latency_regression": 0.0, "unit_cost_regression": 0.0}
            write_json(self.suite / "results" / f"{case_id}.json", result)

        external = self.suite / "external"
        external.mkdir()
        accepted_at = finished
        customer_records = []
        for suffix in ("a", "b"):
            raw = {
                "evidence_version": 1,
                "evidence_id": f"synthetic-customer-{suffix}",
                "organization_id": f"synthetic-org-{suffix}",
                "scope": "batch38-45-strict",
                "artifact_digest": artifact_digest,
                "environment_digest": environment_digest,
                "accepted": True,
                "independent": True,
                "accepted_at": accepted_at,
                "verifier_id": "synthetic-certifier",
                "authorization_refs": ["synthetic-gate-test-only"],
                "findings": [],
            }
            path = external / f"customer-{suffix}.json"
            write_json(path, raw)
            customer_records.append(external_record(path, self.suite, evidence_id=raw["evidence_id"], organization_id=raw["organization_id"], accepted=True, independent=True, accepted_at=accepted_at, verifier_id="synthetic-certifier"))
        review_raw = {"evidence_id": "synthetic-independent-review", "scope": "batch38-45-strict", "accepted": True, "independent": True, "accepted_at": accepted_at, "verifier_id": "synthetic-certifier", "production_evidence": False}
        review_path = external / "independent-review.json"
        write_json(review_path, review_raw)
        review_record = external_record(review_path, self.suite, evidence_id=review_raw["evidence_id"], accepted=True, independent=True, accepted_at=accepted_at, verifier_id="synthetic-certifier")
        domain_records = []
        for batch in range(38, 46):
            path = external / f"batch{batch}-gate.json"
            write_json(path, {"batch": batch, "status": "CERTIFIED", "eligible": True, "synthetic_gate_test": True})
            domain_records.append(external_record(path, self.suite, batch=batch, verifier_id="synthetic-certifier"))
        release = {
            "release_gate_version": 2,
            "suite_id": "batch38-45-strict",
            "required_design_partners": 2,
            "required_independent_reviews": 1,
            "required_domain_gates": list(range(38, 46)),
            "design_partner_evidence": customer_records,
            "independent_review_evidence": [review_record],
            "domain_gate_evidence": domain_records,
            "zero_tolerance_findings": [],
        }
        write_json(self.suite / "release-gate.json", release)
        subprocess.run([sys.executable, str(SCRIPTS / "generate_control_manifest.py"), "--suite", str(self.suite), "--schema-root", str(SCHEMAS)], check=True, capture_output=True, text=True)
        controls = load_json(self.suite / "cases/manifest.json")["control_digests"]
        case_bindings = []
        for case in catalog["cases"]:
            case_id = case["case_id"]
            result_path = self.suite / "results" / f"{case_id}.json"
            manifest_path = manifests / f"{case_id}.json"
            case_bindings.append({"case_id": case_id, "result_digest": sha256_file(result_path), "evidence_manifest_digests": [sha256_file(manifest_path)]})
        external_bindings = []
        for record in domain_records:
            external_bindings.append({"kind": "domain-gate", "id": str(record["batch"]), "digest": record["sha256"]})
        for record in customer_records:
            external_bindings.append({"kind": "design-partner", "id": record["evidence_id"], "digest": record["sha256"]})
        external_bindings.append({"kind": "independent-review", "id": review_record["evidence_id"], "digest": review_record["sha256"]})
        external_bindings.sort(key=lambda item: (item["kind"], item["id"]))
        request = {
            "request_version": 1,
            "suite_id": "batch38-45-strict",
            "requested_at": self.now.isoformat().replace("+00:00", "Z"),
            "expires_at": (self.now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "signer_id": "synthetic-certifier",
            "authorization_refs": ["synthetic-gate-test-only"],
            "control_digests": controls,
            "release_gate_digest": sha256_file(self.suite / "release-gate.json"),
            "case_bindings": case_bindings,
            "external_bindings": external_bindings,
        }
        write_json(self.request, request)
        private = self.trust / "private.pem"
        public = self.trust / "public.pem"
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private)], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)], check=True, capture_output=True)
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(private), "-out", str(self.signature), str(self.request)], check=True, capture_output=True)
        trust = {
            "store_version": 1,
            "authorities": [{
                "signer_id": "synthetic-certifier",
                "roles": ["independent-certifier"],
                "suites": ["batch38-45-strict"],
                "batches": list(range(38, 46)),
                "algorithm": "rsa-sha256",
                "revoked": False,
                "valid_from": (self.now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "valid_until": (self.now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                "public_key": "public.pem",
                "public_key_sha256": sha256_file(public),
            }],
        }
        write_json(self.trust_store, trust)


def run_gate(suite: Path, request: Path | None = None, signature: Path | None = None, trust: Path | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
    descriptor, output_name = tempfile.mkstemp(prefix="b38-45-gate-", suffix=".json")
    os.close(descriptor)
    output = Path(output_name)
    command = [sys.executable, str(SCRIPTS / "run_strict_gate.py"), str(suite), "--schema-root", str(SCHEMAS), "--skill-root", str(SKILLS), "--output", str(output)]
    if request is not None:
        command.extend(["--certification-request", str(request), "--signature", str(signature), "--trust-store", str(trust)])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    gate = load_json(output)
    output.unlink(missing_ok=True)
    return completed, gate


class ToolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory(prefix="b38-45-strict-tests-")
        cls.fixture = SyntheticFixture(Path(cls._temp.name) / "valid")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temp.cleanup()

    def clone_suite(self, name: str) -> Path:
        target = Path(self._temp.name) / name
        shutil.copytree(self.fixture.suite, target)
        return target

    def test_static_validators(self) -> None:
        commands = [
            [sys.executable, str(SCRIPTS / "validate_skill_bundle.py"), str(ROOT)],
            [sys.executable, str(SCRIPTS / "validate_test_catalog.py"), str(SUITE / "cases/catalog.json")],
            [sys.executable, str(SCRIPTS / "validate_coverage_matrix.py"), str(SUITE / "coverage-matrix.json")],
            [sys.executable, str(SCRIPTS / "generate_control_manifest.py"), "--check"],
        ]
        for command in commands:
            with self.subTest(command=command[1]):
                self.assertEqual(0, subprocess.run(command, check=False, capture_output=True, text=True).returncode)

    def test_default_suite_stays_not_run_and_blocked(self) -> None:
        completed, gate = run_gate(SUITE)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("BLOCKED", gate["decision"])
        self.assertEqual("NOT_RUN", gate["field_evidence_status"])
        self.assertEqual(400, gate["metrics"]["counts"]["not-run"])

    def test_complete_synthetic_signed_fixture_exercises_certified_path(self) -> None:
        completed, gate = run_gate(self.fixture.suite, self.fixture.request, self.fixture.signature, self.fixture.trust_store)
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertEqual("CERTIFIED", gate["decision"])
        self.assertEqual("PASSED", gate["field_evidence_status"])

    def test_unsigned_passed_results_are_rejected(self) -> None:
        completed, gate = run_gate(self.fixture.suite)
        self.assertEqual(2, completed.returncode)
        self.assertIn("externally trusted signed certification request", " ".join(gate["blockers"]))

    def test_raw_evidence_tamper_is_rejected(self) -> None:
        suite = self.clone_suite("tamper")
        (suite / "evidence/manifests/shared/artifact.json").write_text("tampered\n", encoding="utf-8")
        completed, gate = run_gate(suite, suite / "certification-request.json", suite / "certification-request.sig", self.fixture.trust_store)
        self.assertEqual(2, completed.returncode)
        self.assertIn("digest mismatch", " ".join(gate["blockers"]))

    def test_path_escape_is_rejected(self) -> None:
        suite = self.clone_suite("escape")
        manifest_path = next((suite / "evidence/manifests").glob("*.json"))
        manifest = load_json(manifest_path)
        manifest["files"][0]["path"] = "../../../../outside.json"
        write_json(manifest_path, manifest)
        completed, gate = run_gate(suite, suite / "certification-request.json", suite / "certification-request.sig", self.fixture.trust_store)
        self.assertEqual(2, completed.returncode)
        self.assertIn("path escapes allowed root", " ".join(gate["blockers"]))

    def test_self_verification_is_rejected(self) -> None:
        suite = self.clone_suite("self-verify")
        manifest_path = next((suite / "evidence/manifests").glob("*.json"))
        manifest = load_json(manifest_path)
        manifest["executor"]["id"] = "synthetic-certifier"
        write_json(manifest_path, manifest)
        completed, gate = run_gate(suite, suite / "certification-request.json", suite / "certification-request.sig", self.fixture.trust_store)
        self.assertEqual(2, completed.returncode)
        self.assertIn("self-verify", " ".join(gate["blockers"]))

    def test_stale_evidence_is_rejected(self) -> None:
        suite = self.clone_suite("stale")
        manifest_path = next((suite / "evidence/manifests").glob("*.json"))
        manifest = load_json(manifest_path)
        old = (datetime.now(timezone.utc) - timedelta(days=60)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        manifest["started_at"] = old
        manifest["finished_at"] = old
        write_json(manifest_path, manifest)
        result_path = suite / "results" / f"{manifest['case_id']}.json"
        result = load_json(result_path)
        result["started_at"] = old
        result["finished_at"] = old
        write_json(result_path, result)
        completed, gate = run_gate(suite, suite / "certification-request.json", suite / "certification-request.sig", self.fixture.trust_store)
        self.assertEqual(2, completed.returncode)
        self.assertIn("stale evidence", " ".join(gate["blockers"]))

    def test_in_suite_trust_anchor_is_rejected(self) -> None:
        suite = self.clone_suite("embedded-trust")
        embedded = suite / "embedded-trust"
        shutil.copytree(self.fixture.trust, embedded)
        completed, gate = run_gate(suite, suite / "certification-request.json", suite / "certification-request.sig", embedded / "trust-store.json")
        self.assertEqual(2, completed.returncode)
        self.assertIn("external to the evidence suite", " ".join(gate["blockers"]))

    def test_forged_signature_is_rejected(self) -> None:
        suite = self.clone_suite("forged-signature")
        signature = suite / "certification-request.sig"
        signature.write_bytes(b"forged")
        completed, gate = run_gate(suite, suite / "certification-request.json", signature, self.fixture.trust_store)
        self.assertEqual(2, completed.returncode)
        self.assertIn("signature verification failed", " ".join(gate["blockers"]))


if __name__ == "__main__":
    unittest.main()
