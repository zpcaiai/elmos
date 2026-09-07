from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "mature_product_toolkit.py"
BATCH = 43
METRICS = {'compatibilityMatrixPassRate': 1.0, 'upgradePassRate': 1.0, 'unsupportedBreakingChangeCount': 0.0}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=ROOT, text=True, capture_output=True)


class Batch43ToolkitTest(unittest.TestCase):
    def scaffold(self, root: Path) -> Path:
        result = run("scaffold", "--batch", str(BATCH), "--key", "acceptance-pack", "--owner", "test-owner", "--output-root", str(root))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return root / f"batch{BATCH}" / "acceptance-pack"

    def test_bundle(self) -> None:
        result = run("validate", "--batch", str(BATCH))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            self.assertTrue((pack / "program.json").is_file())
            self.assertEqual("NOT_RUN", json.loads((pack / "certification.json").read_text())["status"])

    def test_fake_certification_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            certification = json.loads((pack / "certification.json").read_text())
            certification["status"] = "CERTIFIED"
            (pack / "certification.json").write_text(json.dumps(certification))
            result = run("gate", "--batch", str(BATCH), str(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("BLOCKED", result.stdout)

    def test_unauthorized_external_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = self.scaffold(Path(tmp))
            certification = json.loads((pack / "certification.json").read_text())
            certification.update({"status": "CERTIFIED", "evidenceRefs": ["evidence://test"], "holdoutPassRate": 1, "representativePassRate": 1, "criticalFindings": 0, "metrics": METRICS})
            (pack / "certification.json").write_text(json.dumps(certification))
            evidence = {"batch": BATCH, "packKey": "acceptance-pack", "claims": [{"claimId": "external", "status": "PASS", "evidenceRefs": ["evidence://external"], "provenanceRefs": ["run://1"], "externalOperationExecuted": True, "authorizationRefs": []}]}
            (pack / "evidence.json").write_text(json.dumps(evidence))
            result = run("gate", "--batch", str(BATCH), str(pack))
            self.assertEqual(2, result.returncode)
            self.assertIn("authorizationRefs", result.stdout)


if __name__ == "__main__":
    unittest.main()
