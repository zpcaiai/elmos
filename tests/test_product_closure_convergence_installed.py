from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tooling/validate_product_closure_convergence_installed.py"
SPEC = importlib.util.spec_from_file_location("validate_product_closure_convergence_installed", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ProductClosureConvergenceInstalledTests(unittest.TestCase):
    def test_tracked_distribution_matches_manifest_without_certifying(self) -> None:
        result = VALIDATOR.validate(ROOT)
        self.assertEqual("INSTALLED_ARTIFACTS_VERIFIED", result["decision"])
        self.assertEqual(16, result["batch56a_skills"])
        self.assertEqual(32, result["convergence_skills"])
        self.assertEqual(69, result["integrated_assets"])
        self.assertFalse(result["source_packages_validated"])
        self.assertEqual("NOT_RUN", result["external_evidence"])
        self.assertEqual("NOT_CERTIFIED", result["certification"])

    def test_modified_integrated_artifact_fails_digest_binding(self) -> None:
        manifest = json.loads((ROOT / "docs/product-closure-convergence/installed-manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="elmos-product-closure-") as temporary:
            checkout = Path(temporary)
            target_manifest = checkout / "docs/product-closure-convergence/installed-manifest.json"
            target_manifest.parent.mkdir(parents=True)
            target_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            paths = []
            for family in ("batch56a", "convergence"):
                for entry in manifest[family]["skills"]:
                    paths.extend(
                        [
                            entry["installed_path"],
                            str(Path(entry["installed_path"]).parent / "agents/openai.yaml"),
                        ]
                    )
            paths.extend(entry["installed_path"] for entry in manifest["integrated_assets"])
            for relative in paths:
                source = ROOT / relative
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            first = checkout / manifest["integrated_assets"][0]["installed_path"]
            first.write_bytes(first.read_bytes() + b"\nmodified\n")
            with self.assertRaisesRegex(VALIDATOR.ValidationError, "digest mismatch"):
                VALIDATOR.validate(checkout)


if __name__ == "__main__":
    unittest.main()
