import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import modernization_proof_release_state as release_state
import run_modernization_proof_release_gate as subject


class ModernizationProofReleaseGateTest(unittest.TestCase):
    def write_json(self, path: Path, document):
        path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")

    def image_fixture(self, root: Path, *, local=True, scan_status="BLOCKED"):
        repository = (
            "localhost:5000/elmos/modernization-proof-worker"
            if local
            else "registry.example.test/elmos/modernization-proof-worker"
        )
        immutable_reference = repository + "@sha256:" + "a" * 64
        environment = root / "modernization-proof-worker.env"
        environment.write_text(
            f"ELMOS_RUNNER_IMAGE_MODERNIZATION_PROOF={immutable_reference}\n",
            encoding="utf-8",
        )
        environment.chmod(0o600)
        smoke = root / "container-smoke-result.json"
        self.write_json(
            smoke,
            {
                "externalOperationExecuted": False,
                "productionApproved": False,
                "certified": False,
            },
        )
        if scan_status == "PASSED":
            report = root / "vulnerabilities-test.sarif.json"
            self.write_json(report, {"runs": [{"results": []}]})
            scan = {
                "status": "PASSED",
                "exit_code": 0,
                "finding_count": 0,
                "report_path": str(report),
                "report_sha256": subject.sha256_file(report),
                "reason": None,
            }
        else:
            scan = {
                "status": "BLOCKED",
                "exit_code": 1,
                "finding_count": None,
                "report_path": str(root / "missing.sarif.json"),
                "report_sha256": None,
                "reason": "DOCKER_SCOUT_AUTHENTICATION_REQUIRED",
            }
        return {
            "schema_version": 2,
            "source_commit": "b" * 40,
            "source_worktree_clean": True,
            "source_worktree_clean_before": True,
            "source_worktree_clean_after": True,
            "immutable_reference": immutable_reference,
            "image_contract": {"status": "PASSED"},
            "container_smoke": {
                "status": "PASSED",
                "result_sha256": subject.sha256_file(smoke),
            },
            "runtime_environment": {
                "path": str(environment),
                "sha256": subject.sha256_file(environment),
                "mode": "0600",
                "status": "CONFIGURED",
            },
            "vulnerability_scan": scan,
            "external_boundaries": release_state.initial_external_boundaries(),
            "production_ready": False,
            "certified": False,
        }

    def write_image(self, root: Path, image):
        path = root / "image-build-receipt.json"
        self.write_json(path, image)
        return path

    def closure_fixture(self, image, image_path: Path):
        observation = {
            "provider": "github",
            "repository": "zpcaiai/elmos",
            "number": 25,
            "url": "https://github.com/zpcaiai/elmos/pull/25",
            "state": "open",
            "draft": True,
            "head_sha": image["source_commit"],
            "head_ref": "codex/batch105-108-release-evidence",
            "base_ref": "main",
            "author": "release-engineer",
            "observed_at": "2026-08-06T00:00:00+00:00",
        }
        observation["observation_sha256"] = subject.sha256_bytes(
            subject.canonical_json(observation)
        )
        boundaries = release_state.record_observed_execution(
            image["external_boundaries"], boundary="SCM_DRAFT_PULL_REQUEST"
        )
        return {
            "schema_version": 2,
            "image_receipt": {
                "path": str(image_path),
                "sha256": subject.sha256_file(image_path),
                "source_commit": image["source_commit"],
                "immutable_reference": image["immutable_reference"],
            },
            "scm_draft_pull_request": observation,
            "external_evidence": {
                "SCM_DRAFT_PULL_REQUEST": {
                    "state": release_state.EXECUTED_AWAITING_VERIFICATION,
                    "source_commit": image["source_commit"],
                    "immutable_reference": image["immutable_reference"],
                    "executor": "release-engineer",
                    "observer": "github-rest-api",
                    "observation_sha256": observation["observation_sha256"],
                    "independent_verifier": None,
                    "authorization_reference": None,
                }
            },
            "external_boundaries": boundaries,
            "production_ready": False,
            "certified": False,
            "independently_verified": False,
        }

    def test_blocked_scan_local_registry_and_not_run_boundaries_stay_false(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root)
            image_path = self.write_image(root, image)
            result = subject.evaluate_release_gate(image, image_receipt_path=image_path)
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])
        self.assertIn("DOCKER_SCOUT_AUTHENTICATION_REQUIRED", result["blockers"])
        self.assertIn("EXTERNAL_REGISTRY_NOT_CONFIGURED", result["blockers"])
        self.assertIn("REAL_CLOUD_PROVIDER_NOT_RUN", result["blockers"])

    def test_real_pr_observation_updates_only_scm_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root)
            image_path = self.write_image(root, image)
            closure = self.closure_fixture(image, image_path)
            closure_path = root / "release-closure-receipt.json"
            self.write_json(closure_path, closure)
            result = subject.evaluate_release_gate(
                image,
                image_receipt_path=image_path,
                closure=closure,
                closure_path=closure_path,
            )
        self.assertEqual(
            release_state.EXECUTED_AWAITING_VERIFICATION,
            result["effective_external_boundaries"]["SCM_DRAFT_PULL_REQUEST"],
        )
        self.assertEqual(
            release_state.NOT_RUN,
            result["effective_external_boundaries"]["REAL_CLOUD_PROVIDER"],
        )
        self.assertIn(
            "SCM_DRAFT_PULL_REQUEST_EXECUTED_AWAITING_INDEPENDENT_VERIFICATION",
            result["blockers"],
        )
        self.assertNotIn("SCM_DRAFT_PULL_REQUEST_NOT_RUN", result["blockers"])

    def test_caller_status_flags_cannot_promote_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root, local=False, scan_status="PASSED")
            image["production_ready"] = True
            image["certified"] = True
            image_path = self.write_image(root, image)
            result = subject.evaluate_release_gate(image, image_receipt_path=image_path)
        self.assertIn("IMAGE_RECEIPT_ASSERTED_PRODUCTION_READY", result["blockers"])
        self.assertIn("IMAGE_RECEIPT_ASSERTED_CERTIFIED", result["blockers"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])

    def test_missing_boundary_is_rejected_instead_of_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root)
            image["external_boundaries"].pop("CUSTOMER_ACCEPTANCE")
            image_path = self.write_image(root, image)
            result = subject.evaluate_release_gate(image, image_receipt_path=image_path)
        self.assertIn("IMAGE_EXTERNAL_BOUNDARIES_INVALID", result["blockers"])
        self.assertIn("CUSTOMER_ACCEPTANCE_INVALID", result["blockers"])

    def test_image_receipt_cannot_claim_an_external_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root)
            image["external_boundaries"]["SCM_DRAFT_PULL_REQUEST"] = (
                release_state.EXECUTED_AWAITING_VERIFICATION
            )
            image_path = self.write_image(root, image)
            result = subject.evaluate_release_gate(image, image_receipt_path=image_path)
        self.assertIn("IMAGE_BUILD_BOUNDARIES_NOT_ALL_NOT_RUN", result["blockers"])

    def test_tampered_closure_receipt_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = self.image_fixture(root)
            image_path = self.write_image(root, image)
            closure = self.closure_fixture(image, image_path)
            closure["image_receipt"]["sha256"] = "0" * 64
            closure_path = root / "release-closure-receipt.json"
            self.write_json(closure_path, closure)
            result = subject.evaluate_release_gate(
                image,
                image_receipt_path=image_path,
                closure=closure,
                closure_path=closure_path,
            )
        self.assertIn("CLOSURE_IMAGE_RECEIPT_SHA256_MISMATCH", result["blockers"])

    def test_self_verification_is_never_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.json"
            verified = root / "verified.json"
            raw.write_text("raw\n", encoding="utf-8")
            verified.write_text("verified\n", encoding="utf-8")
            blockers = []
            subject.validate_independent_evidence(
                "REAL_CLOUD_PROVIDER",
                {
                    "state": release_state.INDEPENDENTLY_VERIFIED,
                    "source_commit": "b" * 40,
                    "immutable_reference": "registry.example.test/elmos/worker@sha256:"
                    + "a" * 64,
                    "executor": "same-person",
                    "independent_verifier": "same-person",
                    "authorization_reference": "approved-change-42",
                    "evidence_refs": [
                        {
                            "role": "RAW_EXECUTION",
                            "path": str(raw),
                            "sha256": subject.sha256_file(raw),
                            "byte_count": raw.stat().st_size,
                        },
                        {
                            "role": "INDEPENDENT_VERIFICATION",
                            "path": str(verified),
                            "sha256": subject.sha256_file(verified),
                            "byte_count": verified.stat().st_size,
                        },
                    ],
                },
                source_commit="b" * 40,
                immutable_reference="registry.example.test/elmos/worker@sha256:"
                + "a" * 64,
                evidence_root=root,
                blockers=blockers,
            )
        self.assertIn(
            "REAL_CLOUD_PROVIDER_INDEPENDENT_VERIFICATION_SELF_VERIFICATION",
            blockers,
        )


if __name__ == "__main__":
    unittest.main()
