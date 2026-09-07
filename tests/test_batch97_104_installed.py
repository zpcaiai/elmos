from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tooling" / "validate_batch97_104_installed.py"
SPEC = importlib.util.spec_from_file_location("validate_batch97_104_installed", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class Batch97104InstalledDistributionTests(unittest.TestCase):
    def test_tracked_distribution_matches_immutable_manifest(self) -> None:
        result = VALIDATOR.validate(ROOT)
        self.assertEqual("INSTALLED_ARTIFACTS_VERIFIED", result["decision"])
        self.assertEqual(128, result["skills"])
        self.assertEqual(128, result["interfaces"])
        self.assertFalse(result["source_package_validated"])
        self.assertEqual("NOT_RUN", result["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])

    def test_modified_installed_skill_fails_digest_binding(self) -> None:
        manifest = json.loads((ROOT / "docs/batch97-104/installed-manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="elmos-b97-104-") as temporary:
            checkout = Path(temporary)
            target_manifest = checkout / "docs/batch97-104/installed-manifest.json"
            target_manifest.parent.mkdir(parents=True)
            target_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            for entry in manifest["skills"]:
                for key in ("installed_path", "interface_path"):
                    source = ROOT / entry[key]
                    target = checkout / entry[key]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            first = checkout / manifest["skills"][0]["installed_path"]
            first.write_text(first.read_text(encoding="utf-8") + "\nmodified\n", encoding="utf-8")
            with self.assertRaisesRegex(VALIDATOR.ValidationError, "digest mismatch"):
                VALIDATOR.validate(checkout)


if __name__ == "__main__":
    unittest.main()
