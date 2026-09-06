from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "batch40_local_assurance.py"
SPEC = importlib.util.spec_from_file_location("batch40_local_assurance", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Batch40LocalAssuranceTest(unittest.TestCase):
    def fixture(self) -> tuple[Path, Path, Path, Path]:
        root = Path(tempfile.mkdtemp())
        repo = root / "repo"
        pack = repo / "pack"
        workflow = repo / ".github/workflows/ci.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(
            """name: CI
on: [push, pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
""",
            encoding="utf-8",
        )
        threat_model = repo / "threat-model.json"
        threat_model.write_text(json.dumps({
            "id": "fixture-threat-model",
            "owner": "test-owner",
            "scope": "fixture",
            "expectedThreatIds": ["T1"],
            "threats": [{
                "threatId": "T1",
                "owner": "test-owner",
                "assets": ["artifact"],
                "trustBoundaries": ["builder to verifier"],
                "controls": ["digest verification"],
                "evidenceRequirement": "verification receipt",
                "residualRisk": "independent verification not run",
            }],
        }), encoding="utf-8")
        (pack / "evidence/execution").mkdir(parents=True)
        (pack / "evidence/provenance").mkdir(parents=True)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        (pack / "evidence/execution/run.json").write_text(
            json.dumps({"check": "run", "finishedAt": now}), encoding="utf-8"
        )
        (pack / "evidence/provenance/run-provenance.json").write_text(
            json.dumps({
                "recordType": "provenance",
                "evidenceId": "run",
                "runReport": {
                    "path": "evidence/execution/run.json",
                    "sha256": MODULE.sha256_file(pack / "evidence/execution/run.json"),
                },
            }),
            encoding="utf-8",
        )
        (pack / "evidence.json").write_text(json.dumps({
            "claims": [{
                "claimId": "claim",
                "status": "PASS",
                "evidenceRefs": ["run"],
                "provenanceRefs": ["run-provenance"],
                "externalOperationExecuted": False,
                "authorizationRefs": [],
            }],
        }), encoding="utf-8")
        (pack / "claims.json").write_text(json.dumps({
            "claims": [{"claimId": "claim", "limitations": ["bounded fixture"]}],
        }), encoding="utf-8")
        return repo, pack, workflow, threat_model

    def analyze(self, repo: Path, pack: Path, workflow: Path, threat_model: Path) -> dict:
        with mock.patch.object(MODULE, "git_revision", return_value="a" * 40):
            return MODULE.analyze(repo, pack, workflow, threat_model, 30)

    def test_complete_local_scope_passes_without_claiming_certification(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertEqual("PASS", report["status"])
        self.assertEqual("NOT_RUN", report["independentVerification"])
        self.assertEqual("NOT_CERTIFIED", report["certificationStatus"])
        self.assertEqual(1.0, report["metrics"]["secureSdlcControlCoverage"])
        self.assertEqual(1.0, report["metrics"]["evidenceTraceCoverage"])
        self.assertEqual(1.0, report["metrics"]["threatModelCoverage"])

    def test_unpinned_action_and_persisted_checkout_token_fail_closed(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        body = workflow.read_text(encoding="utf-8")
        body = body.replace(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/checkout@v7",
        ).replace("persist-credentials: false", "persist-credentials: true")
        workflow.write_text(body, encoding="utf-8")
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("B40-CI-ACTION-PINS", report["failedControls"])
        self.assertIn("B40-CI-CHECKOUT-CREDENTIALS", report["failedControls"])

    def test_missing_provenance_and_evidence_refs_fail_closed(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        evidence = json.loads((pack / "evidence.json").read_text(encoding="utf-8"))
        evidence["claims"][0]["evidenceRefs"] = ["missing-run"]
        evidence["claims"][0]["provenanceRefs"] = ["missing-provenance"]
        (pack / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertEqual("BLOCKED", report["status"])
        self.assertEqual(0.0, report["metrics"]["evidenceTraceCoverage"])
        self.assertEqual(0.0, report["metrics"]["provenanceCoverage"])

    def test_external_operation_without_authorization_fails_closed(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        evidence = json.loads((pack / "evidence.json").read_text(encoding="utf-8"))
        evidence["claims"][0]["externalOperationExecuted"] = True
        (pack / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertIn("B40-EXTERNAL-AUTHORITY", report["failedControls"])

    def test_stale_evidence_is_not_counted_as_fresh(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        (pack / "evidence/execution/run.json").write_text(
            json.dumps({"check": "run", "finishedAt": "2020-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertIn("B40-EVIDENCE-FRESHNESS", report["failedControls"])
        self.assertEqual(0.0, report["metrics"]["auditEvidenceFreshnessRate"])

    def test_incomplete_threat_model_fails_closed(self) -> None:
        repo, pack, workflow, threat_model = self.fixture()
        payload = json.loads(threat_model.read_text(encoding="utf-8"))
        payload["threats"][0]["controls"] = []
        threat_model.write_text(json.dumps(payload), encoding="utf-8")
        report = self.analyze(repo, pack, workflow, threat_model)
        self.assertIn("B40-THREAT-MODEL-COVERAGE", report["failedControls"])
        self.assertEqual(0.0, report["metrics"]["threatModelCoverage"])

    def test_evidence_target_refreshes_provenance_before_assurance(self) -> None:
        makefile = (ROOT / "Makefile.batch40").read_text(encoding="utf-8")
        target = makefile.split("batch40-evidence:", 1)[1].split(
            "batch40-local-assurance:", 1
        )[0]
        record = "python3 scripts/batch40_record_results.py"
        assurance = "$(MAKE) batch40-local-assurance PACK=$(PACK)"
        self.assertEqual(2, target.count(record))
        self.assertLess(target.index(record), target.index(assurance))
        self.assertLess(target.index(assurance), target.rindex(record))


if __name__ == "__main__":
    unittest.main()
