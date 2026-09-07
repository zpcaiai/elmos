from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/mature_product_toolkit.py"
METRICS = {
    38: {"editionConformanceRate": 1.0, "upgradeRollbackPassRate": 1.0, "recoveryPassRate": 1.0},
    39: {"sloPassRate": 1.0, "restorePassRate": 1.0, "incidentExercisePassRate": 1.0},
    40: {"supplyChainCoverageRate": 1.0, "signaturePassRate": 1.0, "criticalVulnerabilityCount": 0.0},
    41: {"knowledgeProvenanceCoverageRate": 1.0, "privacyIsolationPassRate": 1.0, "predictionCalibrationPassRate": 1.0},
    42: {"agentEvalPassRate": 1.0, "policyViolationCount": 0.0, "killSwitchPassRate": 1.0},
    43: {"compatibilityMatrixPassRate": 1.0, "upgradePassRate": 1.0, "unsupportedBreakingChangeCount": 0.0},
    44: {"meteringReconciliationRate": 1.0, "budgetGuardrailPassRate": 1.0, "grossMarginEvidenceCoverageRate": 1.0},
    45: {"maturityDimensionPassRate": 1.0, "independentReviewPassRate": 1.0, "unresolvedCriticalRiskCount": 0.0},
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def file_ref(pack: Path, relative: str) -> dict:
    path = pack / relative
    return {"path": relative, "sha256": digest(path), "bytes": path.stat().st_size}


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class MatureProductGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.trust_temp = tempfile.TemporaryDirectory()
        cls.trust_root = Path(cls.trust_temp.name)
        cls.private_key = cls.trust_root / "certifier-private.pem"
        cls.public_key = cls.trust_root / "certifier-public.pem"
        cls.trust_store = cls.trust_root / "trust-store.json"
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
        write_json(
            cls.trust_store,
            {
                "storeVersion": 1,
                "keys": [
                    {
                        "keyId": "independent-test-certifier",
                        "publicKeyPath": cls.public_key.name,
                        "revoked": False,
                        "authorizedBatches": list(range(38, 46)),
                    }
                ],
            },
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.trust_temp.cleanup()

    def scaffold(self, root: Path, batch: int) -> Path:
        result = run_tool(
            "scaffold",
            "--batch",
            str(batch),
            "--key",
            "signed-test-pack",
            "--owner",
            "test-owner",
            "--output-root",
            str(root),
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return root / f"batch{batch}" / "signed-test-pack"

    def sign_request(self, pack: Path) -> None:
        request_path = pack / "certification-request.json"
        request = {
            "requestVersion": 1,
            "batch": json.loads((pack / "program.json").read_text())["batch"],
            "packKey": "signed-test-pack",
            "requestedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "keyId": "independent-test-certifier",
            "approvedBy": ["test-owner"],
            "programDigest": digest(pack / "program.json"),
            "evidenceDigest": digest(pack / "evidence.json"),
            "certificationDigest": digest(pack / "certification.json"),
            "evidenceManifestDigest": digest(pack / "evidence-manifest.json"),
        }
        write_json(request_path, request)
        subprocess.run(
            [
                "openssl",
                "dgst",
                "-sha256",
                "-sign",
                str(self.private_key),
                "-out",
                str(pack / "certification-request.sig"),
                str(request_path),
            ],
            check=True,
            capture_output=True,
        )

    def materialize(self, root: Path, batch: int) -> Path:
        pack = self.scaffold(root, batch)
        program = json.loads((pack / "program.json").read_text())
        program["status"] = "COMPLETE"
        write_json(pack / "program.json", program)

        claim_id = "claim-1"
        role_files = [
            ("execution", "execution", "raw/execution.json"),
            ("provenance", "provenance", "raw/provenance.json"),
            ("verification", "verification", "raw/verification.json"),
        ]
        if batch == 45:
            role_files.extend(
                [
                    ("customer-1", "customer", "raw/customer-1.json"),
                    ("customer-2", "customer", "raw/customer-2.json"),
                    ("independent-review", "independent-review", "raw/independent-review.json"),
                ]
            )
        evidence_entries = []
        for identifier, role, relative in role_files:
            write_json(pack / relative, {"record": identifier, "batch": batch})
            evidence_entries.append(
                {
                    "id": identifier,
                    "role": role,
                    "claimIds": [claim_id],
                    **file_ref(pack, relative),
                }
            )
        write_json(pack / "artifact.json", {"artifact": f"batch-{batch}-artifact"})
        write_json(pack / "environment.json", {"environment": f"batch-{batch}-environment"})
        write_json(pack / "corpus/holdout.json", {"corpus": "holdout", "batch": batch})
        write_json(pack / "corpus/representative.json", {"corpus": "representative", "batch": batch})

        domain_gates = []
        if batch == 45:
            for domain_batch in range(38, 45):
                relative = f"domain-gates/batch{domain_batch}.json"
                write_json(
                    pack / relative,
                    {
                        "batch": domain_batch,
                        "packKey": f"domain-{domain_batch}",
                        "eligible": True,
                        "status": "CERTIFIED",
                        "failures": [],
                        "evidenceRefs": [f"domain-{domain_batch}-evidence"],
                        "externalOperationExecuted": False,
                    },
                )
                domain_gates.append({"batch": domain_batch, **file_ref(pack, relative)})

        now = datetime.now(timezone.utc).replace(microsecond=0)
        manifest = {
            "manifestVersion": 1,
            "batch": batch,
            "packKey": "signed-test-pack",
            "generatedAt": now.isoformat().replace("+00:00", "Z"),
            "artifact": file_ref(pack, "artifact.json"),
            "environment": file_ref(pack, "environment.json"),
            "execution": {
                "startedAt": (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
                "finishedAt": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "replayCommand": f"approved-runner replay batch-{batch}",
                "executorId": "fixture-executor",
                "verifierId": "independent-fixture-verifier",
                "verifierIndependent": True,
                "authorizationRefs": ["authorization://test-scope"],
            },
            "evidence": evidence_entries,
            "corpora": [
                {"kind": "holdout", "authoringAccess": False, **file_ref(pack, "corpus/holdout.json")},
                {"kind": "representative", "authoringAccess": False, **file_ref(pack, "corpus/representative.json")},
            ],
            "approvals": ["test-owner"],
            "domainGates": domain_gates,
        }
        write_json(pack / "evidence-manifest.json", manifest)

        evidence_ids = [entry["id"] for entry in evidence_entries]
        write_json(
            pack / "evidence.json",
            {
                "batch": batch,
                "packKey": "signed-test-pack",
                "claims": [
                    {
                        "claimId": claim_id,
                        "status": "PASS",
                        "evidenceRefs": evidence_ids,
                        "provenanceRefs": ["provenance"],
                        "externalOperationExecuted": False,
                        "authorizationRefs": [],
                    }
                ],
            },
        )
        write_json(
            pack / "certification.json",
            {
                "batch": batch,
                "packKey": "signed-test-pack",
                "status": "CERTIFIED",
                "evidenceRefs": evidence_ids,
                "holdoutPassRate": 1,
                "representativePassRate": 1,
                "criticalFindings": 0,
                "metrics": METRICS[batch],
            },
        )
        self.sign_request(pack)
        return pack

    def gate(self, batch: int, pack: Path) -> subprocess.CompletedProcess[str]:
        return run_tool(
            "gate",
            "--batch",
            str(batch),
            str(pack),
            "--trust-store",
            str(self.trust_store),
        )

    def test_complete_independently_signed_gate_path(self) -> None:
        for batch in range(38, 46):
            with self.subTest(batch=batch), tempfile.TemporaryDirectory() as tmp:
                pack = self.materialize(Path(tmp), batch)
                result = self.gate(batch, pack)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("status=CERTIFIED", result.stdout)

    def test_unsigned_certification_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 38)
            (pack / "certification-request.sig").unlink()
            result = self.gate(38, pack)
            self.assertEqual(2, result.returncode)
            self.assertIn("signature is missing", result.stdout)

    def test_self_verification_is_rejected_even_when_resigned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 42)
            manifest = json.loads((pack / "evidence-manifest.json").read_text())
            manifest["execution"]["verifierId"] = manifest["execution"]["executorId"]
            write_json(pack / "evidence-manifest.json", manifest)
            self.sign_request(pack)
            result = self.gate(42, pack)
            self.assertEqual(2, result.returncode)
            self.assertIn("executor and independent verifier must differ", result.stdout)

    def test_raw_evidence_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 40)
            (pack / "raw/execution.json").write_text("tampered\n")
            result = self.gate(40, pack)
            self.assertEqual(2, result.returncode)
            self.assertIn("digest does not match", result.stdout)

    def test_batch45_cannot_override_missing_domain_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 45)
            manifest = json.loads((pack / "evidence-manifest.json").read_text())
            manifest["domainGates"] = manifest["domainGates"][:-1]
            write_json(pack / "evidence-manifest.json", manifest)
            self.sign_request(pack)
            result = self.gate(45, pack)
            self.assertEqual(2, result.returncode)
            self.assertIn("requires exact certified domain gates", result.stdout)

    def test_certification_authority_cannot_be_the_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 39)
            manifest = json.loads((pack / "evidence-manifest.json").read_text())
            manifest["execution"]["executorId"] = "independent-test-certifier"
            write_json(pack / "evidence-manifest.json", manifest)
            self.sign_request(pack)
            result = self.gate(39, pack)
            self.assertEqual(2, result.returncode)
            self.assertIn("certification authority must differ from the executor", result.stdout)

    def test_malformed_pack_document_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.materialize(Path(tmp), 38)
            (pack / "program.json").write_text("not-json\n")
            result = self.gate(38, pack)
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertIn("status=BLOCKED", result.stdout)
            gate = json.loads((pack / "gate-result.json").read_text())
            self.assertFalse(gate["eligible"])


if __name__ == "__main__":
    unittest.main()
