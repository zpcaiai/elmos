from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PACK = (
    ROOT / "mature-product-packs" / "batch40" / "elmos-platform-supply-chain"
)
SCRIPT = ROOT / "scripts" / "batch40_record_results.py"


class Batch40RecordResultsTest(unittest.TestCase):
    def test_refresh_clears_stale_certification_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory) / "pack"
            shutil.copytree(SOURCE_PACK, pack)

            metrics_path = pack / "metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            signature = next(
                item for item in metrics["metrics"]
                if item["name"] == "signaturePassRate"
            )
            signature.update({
                "measured": True,
                "value": 1.0,
                "evidenceRefs": ["fabricated-independent-result"],
                "note": "certified",
            })
            metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

            flags_path = pack / "zero-tolerance.json"
            flags = json.loads(flags_path.read_text(encoding="utf-8"))
            unsigned = next(
                item for item in flags["flags"]
                if item["name"] == "unsignedProductionArtifacts"
            )
            unsigned.update({
                "evaluated": True,
                "observed": 0,
                "evidenceRefs": ["fabricated-independent-result"],
                "note": "certified",
            })
            flags_path.write_text(json.dumps(flags), encoding="utf-8")

            pack_path = pack / "pack.json"
            pack_record = json.loads(pack_path.read_text(encoding="utf-8"))
            pack_record["evidenceRefs"].append("fabricated-independent-result")
            pack_path.write_text(json.dumps(pack_record), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(pack), "--skip-context-refresh"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

            refreshed_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            signature = next(
                item for item in refreshed_metrics["metrics"]
                if item["name"] == "signaturePassRate"
            )
            self.assertFalse(signature["measured"])
            self.assertIsNone(signature["value"])
            self.assertEqual([], signature["evidenceRefs"])

            refreshed_flags = json.loads(flags_path.read_text(encoding="utf-8"))
            unsigned = next(
                item for item in refreshed_flags["flags"]
                if item["name"] == "unsignedProductionArtifacts"
            )
            self.assertFalse(unsigned["evaluated"])
            self.assertIsNone(unsigned["observed"])
            self.assertEqual([], unsigned["evidenceRefs"])

            refreshed_pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertNotIn(
                "fabricated-independent-result", refreshed_pack["evidenceRefs"]
            )
            self.assertEqual("experimental", refreshed_pack["status"])


if __name__ == "__main__":
    unittest.main()
