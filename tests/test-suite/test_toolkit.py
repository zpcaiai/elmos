from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SUITE_SOURCE = ROOT / "test-suites/batch1-37-strict"
GATE = ROOT / "scripts/test-suite/run_strict_test_gate.py"


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path, prefixed: bool = False) -> str:
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{value}" if prefixed else value


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class ToolkitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_temp = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixture_temp.name)
        cls.suite = cls.fixture_root / "suite"
        shutil.copytree(SUITE_SOURCE, cls.suite)
        (cls.suite / "release-gate.json").unlink(missing_ok=True)
        cls.trust_root = cls.fixture_root / "trust"
        cls.trust_root.mkdir()
        cls.private_key = cls.fixture_root / "private.pem"
        cls.public_key = cls.trust_root / "certifier-public.pem"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(cls.private_key), "2048"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "rsa", "-in", str(cls.private_key), "-pubout", "-out", str(cls.public_key)],
            check=True,
            capture_output=True,
        )
        cls._materialize_valid_certification_fixture()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_temp.cleanup()

    @classmethod
    def _materialize_valid_certification_fixture(cls):
        catalog = json.loads((cls.suite / "cases/catalog.json").read_text())
        results = cls.suite / "results"
        evidence_root = cls.suite / "evidence"
        evidence_root.mkdir(exist_ok=True)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        started = utc(now - timedelta(minutes=1))
        finished = utc(now)
        bindings = []

        for case in catalog["cases"]:
            case_id = case["id"]
            case_dir = evidence_root / case_id
            case_dir.mkdir()
            roles = list(case["evidence_required"])
            if "environment-binding" not in roles:
                roles.append("environment-binding")
            files = []
            for role in roles:
                path = case_dir / f"{role}.json"
                path.write_text(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "role": role,
                            "assertions": case["assertions"],
                            "execution": "approved-equivalent-test-fixture",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
                files.append(
                    {
                        "role": role,
                        "path": path.name,
                        "sha256": file_digest(path),
                        "bytes": path.stat().st_size,
                        "immutable": True,
                    }
                )
            artifact_path = case_dir / "artifact-digest.json"
            environment_path = case_dir / "environment-binding.json"
            corpora = []
            if case.get("holdout_required"):
                corpora.append(
                    {
                        "kind": "holdout",
                        "digest": canonical_digest({"case": case_id, "corpus": "holdout"}),
                        "independent": True,
                        "authoring_access": False,
                    }
                )
            if case.get("representative_workload_required"):
                corpora.append(
                    {
                        "kind": "representative",
                        "digest": canonical_digest({"case": case_id, "corpus": "representative"}),
                        "independent": True,
                        "authoring_access": False,
                    }
                )
            result = {
                "case_id": case_id,
                "status": "passed",
                "artifact_digest": file_digest(artifact_path, prefixed=True),
                "environment_digest": file_digest(environment_path, prefixed=True),
                "started_at": started,
                "finished_at": finished,
                "evidence": [f"evidence/{case_id}/manifest.json"],
                "execution_kind": "approved-equivalent",
                "replay_command": f"approved-runner replay {case_id}",
                "trace_coverage": 1.0,
                "source_target_trace_coverage": 1.0,
                "critical_unknowns": 0,
                "critical_security_findings": 0,
                "tenant_isolation_violations": 0,
                "test_integrity_violations": 0,
                "stale_evidence": 0,
                "unreplayed_critical_failures": 0,
                "forged_certification_attempts": 0,
                "flaky_p0_p1": 0,
            }
            if case.get("holdout_required"):
                result["holdout_passed"] = True
            if case.get("representative_workload_required"):
                result["representative_workload_passed"] = True
            if case["test_type"] in {"dependency_failure", "replay_idempotency"} or case["skill"] == "tst-chaos-dr-recovery":
                result["recovery_success_rate"] = 1.0
            if case["skill"] == "tst-performance-capacity-cost":
                result.update(
                    {
                        "p95_latency_regression": 0.0,
                        "p99_latency_regression": 0.0,
                        "resource_regression": 0.0,
                    }
                )
            if case["skill"] == "tst-test-selection-flakiness-integrity":
                result.update({"affected_test_recall": 1.0, "mutation_score": 1.0})
            result_path = results / f"{case_id}.json"
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            manifest = {
                "manifest_version": 2,
                "manifest_id": f"manifest-{case_id}",
                "case_id": case_id,
                "case_digest": canonical_digest(case),
                "catalog_digest": file_digest(cls.suite / "cases/catalog.json", prefixed=True),
                "artifact_digest": result["artifact_digest"],
                "environment_digest": result["environment_digest"],
                "execution_kind": "approved-equivalent",
                "started_at": started,
                "finished_at": finished,
                "executor": {"id": "fixture-executor", "role": "executor"},
                "verifier": {
                    "id": "fixture-independent-certifier",
                    "role": "independent-verifier",
                    "independent": True,
                },
                "authorization_refs": ["fixture-authorization"],
                "files": files,
                "corpora": corpora,
            }
            manifest_path = case_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            bindings.append(
                {
                    "case_id": case_id,
                    "result_digest": file_digest(result_path, prefixed=True),
                    "evidence_manifest_digests": [file_digest(manifest_path, prefixed=True)],
                }
            )

        controls = {
            "catalog": file_digest(cls.suite / "cases/catalog.json", prefixed=True),
            "coverage_matrix": file_digest(cls.suite / "coverage-matrix.json", prefixed=True),
            "strict_profile": file_digest(cls.suite / "strict-profile.json", prefixed=True),
            "suite": file_digest(cls.suite / "suite.json", prefixed=True),
        }
        request = {
            "request_version": 1,
            "suite_id": "batch1-37-strict",
            "requested_at": utc(now - timedelta(minutes=1)),
            "expires_at": utc(now + timedelta(hours=1)),
            "signer_id": "fixture-independent-certifier",
            "authorization_refs": ["fixture-certification-authorization"],
            "control_digests": controls,
            "case_bindings": bindings,
        }
        cls.request = cls.suite / "certification-request.json"
        cls.signature = cls.suite / "certification-request.sig"
        cls.request.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n")
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(cls.private_key),
                "-out",
                str(cls.signature),
                str(cls.request),
            ],
            check=True,
            capture_output=True,
        )
        trust = {
            "store_version": 1,
            "authorities": [
                {
                    "signer_id": "fixture-independent-certifier",
                    "algorithm": "rsa-sha256",
                    "public_key": cls.public_key.name,
                    "public_key_sha256": file_digest(cls.public_key),
                    "roles": ["independent-certifier"],
                    "valid_from": utc(now - timedelta(days=1)),
                    "valid_until": utc(now + timedelta(days=1)),
                    "revoked": False,
                }
            ],
        }
        cls.trust_store = cls.trust_root / "trust-store.json"
        cls.trust_store.write_text(json.dumps(trust, indent=2) + "\n")

    def cmd(self, *args, cwd=ROOT):
        return subprocess.run(args, cwd=cwd, text=True, capture_output=True)

    def copy_valid_suite(self):
        temp = tempfile.TemporaryDirectory()
        destination = Path(temp.name) / "suite"
        shutil.copytree(self.suite, destination)
        return temp, destination

    def run_gate(self, suite: Path, *, signed: bool = True):
        command = ["python3", str(GATE), str(suite)]
        if signed:
            command.extend(
                [
                    "--certification-request",
                    str(suite / "certification-request.json"),
                    "--signature",
                    str(suite / "certification-request.sig"),
                    "--trust-store",
                    str(self.trust_store),
                ]
            )
        return self.cmd(*command)

    def test_catalog(self):
        result = self.cmd(
            "python3",
            "scripts/test-suite/validate_test_catalog.py",
            "test-suites/batch1-37-strict/cases/catalog.json",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_coverage(self):
        result = self.cmd(
            "python3",
            "scripts/test-suite/validate_coverage_matrix.py",
            "test-suites/batch1-37-strict/coverage-matrix.json",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_skills_use_standard_yaml_and_interfaces(self):
        result = self.cmd("python3", "scripts/test-suite/validate_skill_bundle.py", ".")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_integration_manifest_is_current(self):
        result = self.cmd("python3", "scripts/test-suite/generate_integration_manifest.py", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((ROOT / "docs/test-suite/ELMOS_INTEGRATION_MANIFEST.json").read_text())
        paths = {entry["path"] for entry in manifest["files"]}
        self.assertNotIn("docs/test-suite/ELMOS_VALIDATION_REPORT.md", paths)

    def test_gate_rejects_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "suite"
            shutil.copytree(SUITE_SOURCE, destination)
            (destination / "release-gate.json").unlink(missing_ok=True)
            result = self.run_gate(destination, signed=False)
            gate = json.loads((destination / "release-gate.json").read_text())
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(gate["decision"], "BLOCKED")
            self.assertEqual(gate["field_evidence_status"], "NOT_RUN")
            self.assertEqual(gate["metrics"]["counts"]["not-run"], 408)

    def test_gate_rejects_unsigned_synthetic_passes(self):
        temp, destination = self.copy_valid_suite()
        try:
            result = self.run_gate(destination, signed=False)
            gate = json.loads((destination / "release-gate.json").read_text())
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("externally trusted signed certification request", "\n".join(gate["blockers"]))
        finally:
            temp.cleanup()

    def test_gate_accepts_complete_independently_signed_bundle(self):
        temp, destination = self.copy_valid_suite()
        try:
            result = self.run_gate(destination)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            gate = json.loads((destination / "release-gate.json").read_text())
            self.assertEqual(gate["decision"], "CERTIFIED")
            self.assertEqual(gate["metrics"]["counts"]["passed"], 408)
        finally:
            temp.cleanup()

    def test_gate_rejects_tampered_raw_evidence(self):
        temp, destination = self.copy_valid_suite()
        try:
            raw = destination / "evidence/B01-001/raw-execution-log.json"
            raw.write_text(raw.read_text() + "tampered\n")
            result = self.run_gate(destination)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("raw evidence", (destination / "release-gate.json").read_text())
        finally:
            temp.cleanup()

    def test_gate_rejects_forged_certification_request(self):
        temp, destination = self.copy_valid_suite()
        try:
            request = destination / "certification-request.json"
            document = json.loads(request.read_text())
            document["authorization_refs"] = ["forged"]
            request.write_text(json.dumps(document, indent=2) + "\n")
            result = self.run_gate(destination)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("signature verification failed", (destination / "release-gate.json").read_text())
        finally:
            temp.cleanup()

    def test_gate_rejects_self_verification(self):
        temp, destination = self.copy_valid_suite()
        try:
            manifest = destination / "evidence/B01-001/manifest.json"
            document = json.loads(manifest.read_text())
            document["verifier"]["id"] = document["executor"]["id"]
            manifest.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            result = self.run_gate(destination)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("executor and verifier must be different", (destination / "release-gate.json").read_text())
        finally:
            temp.cleanup()

    def test_gate_rejects_non_independent_corpora(self):
        temp, destination = self.copy_valid_suite()
        try:
            manifest = destination / "evidence/B35-001/manifest.json"
            document = json.loads(manifest.read_text())
            document["corpora"][1]["digest"] = document["corpora"][0]["digest"]
            manifest.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            result = self.run_gate(destination)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("corpus digests must be distinct", (destination / "release-gate.json").read_text())
        finally:
            temp.cleanup()

    def test_local_qualification_never_updates_certification_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "source.txt").write_text("stable\n")
            plan = root / "plan.json"
            output = root / "artifacts/evidence"
            plan.write_text(
                json.dumps(
                    {
                        "plan_version": 1,
                        "plan_id": "unit-local-check",
                        "scope": "local-engineering-evidence-only",
                        "updates_certification_cases": False,
                        "certification_case_ids": [],
                        "commands": [
                            {
                                "id": "real-process",
                                "command": ["python3", "-c", "print('executed')"],
                                "timeout_seconds": 30,
                                "cleanup_after": {
                                    "command": ["python3", "-c", "print('cleaned')"],
                                    "timeout_seconds": 30,
                                },
                            }
                        ],
                    }
                )
                + "\n"
            )
            before = file_digest(SUITE_SOURCE / "results/B01-001.json")
            result = self.cmd(
                "python3",
                "scripts/test-suite/run_repository_qualification.py",
                "--root",
                str(root),
                "--plan",
                str(plan),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((output / "qualification-report.json").read_text())
            artifact_manifest = json.loads((output / "artifact-manifest.json").read_text())
            self.assertEqual(report["status"], "PASSED")
            self.assertEqual(report["certification_case_updates"], [])
            self.assertEqual(report["field_evidence_status"], "NOT_RUN")
            self.assertEqual(report["commands"][0]["cleanup_after"]["exit_code"], 0)
            self.assertFalse(report["commands"][0]["cleanup_after"]["timed_out"])
            self.assertFalse(
                any(entry["path"].startswith("artifacts/") for entry in artifact_manifest["files"])
            )
            artifact_paths = {entry["path"] for entry in artifact_manifest["files"]}
            self.assertNotIn("docs/test-suite/ELMOS_VALIDATION_REPORT.md", artifact_paths)
            self.assertNotIn("test-suites/batch1-37-strict/release-gate.json", artifact_paths)
            self.assertEqual(before, file_digest(SUITE_SOURCE / "results/B01-001.json"))

    def test_local_qualification_rejects_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            source = root / "source.txt"
            source.write_text("before\n")
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "plan_version": 1,
                        "plan_id": "unit-source-drift",
                        "scope": "local-engineering-evidence-only",
                        "updates_certification_cases": False,
                        "certification_case_ids": [],
                        "commands": [
                            {
                                "id": "mutate-source",
                                "command": [
                                    "python3",
                                    "-c",
                                    "from pathlib import Path; Path('source.txt').write_text('after\\n')",
                                ],
                                "timeout_seconds": 30,
                            }
                        ],
                    }
                )
                + "\n"
            )
            output = root / "artifacts/evidence"
            result = self.cmd(
                "python3",
                "scripts/test-suite/run_repository_qualification.py",
                "--root",
                str(root),
                "--plan",
                str(plan),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((output / "qualification-report.json").read_text())
            self.assertEqual(report["status"], "FAILED")
            self.assertFalse(report["source_snapshot_consistent"])
            self.assertEqual(report["source_drift"]["changed"], ["source.txt"])
            self.assertEqual(report["source_drift"]["added"], [])
            self.assertEqual(report["source_drift"]["removed"], [])

    def test_local_qualification_rejects_case_status_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = root / "plan.json"
            plan.write_text(
                json.dumps(
                    {
                        "plan_version": 1,
                        "plan_id": "unsafe",
                        "scope": "local-engineering-evidence-only",
                        "updates_certification_cases": True,
                        "certification_case_ids": ["B01-001"],
                        "commands": [
                            {"id": "noop", "command": ["true"], "timeout_seconds": 10}
                        ],
                    }
                )
                + "\n"
            )
            result = self.cmd(
                "python3",
                "scripts/test-suite/run_repository_qualification.py",
                "--plan",
                str(plan),
                "--output",
                str(root / "output"),
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot update certification cases", result.stderr)

    def test_qualification_cleanup_is_allowlisted_and_group_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pom.xml").write_text("<project/>\n")
            java_target = root / "modules/example/target"
            java_target.mkdir(parents=True)
            (java_target / "generated.bin").write_bytes(b"generated")
            protected_target = root / "artifacts/preserved/target"
            protected_target.mkdir(parents=True)
            (protected_target / "evidence.json").write_text("{}\n")
            web_modules = root / "apps/web-console/node_modules"
            web_modules.mkdir(parents=True)
            (web_modules / "generated.js").write_text("generated\n")
            source = root / "modules/example/src/main/java/Example.java"
            source.parent.mkdir(parents=True)
            source.write_text("final class Example {}\n")

            result = self.cmd(
                "python3",
                "scripts/test-suite/cleanup_qualification_outputs.py",
                "all",
                "--root",
                str(root),
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(java_target.exists())
            self.assertFalse(web_modules.exists())
            self.assertTrue(protected_target.is_dir())
            self.assertTrue(source.is_file())


if __name__ == "__main__":
    unittest.main()
