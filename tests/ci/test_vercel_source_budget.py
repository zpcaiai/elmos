from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tooling" / "validate_vercel_source_budget.py"
SPEC = importlib.util.spec_from_file_location(
    "validate_vercel_source_budget", MODULE_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Vercel source budget validator could not be loaded")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class VercelSourceBudgetTest(unittest.TestCase):
    def test_repository_context_is_bounded_and_route_complete(self) -> None:
        report = validator.validate(ROOT)

        self.assertEqual("PASSED", report["status"])
        self.assertEqual("SOURCE_CONTEXT_ONLY", report["claim_scope"])
        self.assertEqual(72, report["route_count"])
        self.assertEqual(0, report["passed_route_evidence_count"])
        self.assertEqual("NOT_RUN", report["runtime_status"])
        self.assertEqual("NOT_CERTIFIED", report["certification_status"])

    def test_budget_is_conservative_and_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "FILE_BUDGET_EXCEEDED"):
            validator.enforce_budget(
                (f"file-{index}", 0) for index in range(validator.MAX_SOURCE_FILES + 1)
            )
        with self.assertRaisesRegex(ValueError, "BYTE_BUDGET_EXCEEDED"):
            validator.enforce_budget([("large.bin", validator.MAX_SOURCE_BYTES + 1)])

    def test_root_policy_cannot_be_shadowed_by_an_app_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".vercelignore").write_text(
                "\n".join(validator.EXPECTED_IGNORE_PATTERNS) + "\n", encoding="utf-8"
            )
            validator.validate_ignore_policy(root)
            app_root = root / "apps" / "web-console"
            app_root.mkdir(parents=True)
            (app_root / ".vercelignore").write_text("/*\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "MUST_NOT_OVERRIDE"):
                validator.validate_ignore_policy(root)

    def test_root_policy_must_be_part_of_the_tracked_source(self) -> None:
        validator.validate_policy_is_tracked([".vercelignore", "pom.xml"])
        with self.assertRaisesRegex(ValueError, "NOT_TRACKED"):
            validator.validate_policy_is_tracked(["pom.xml"])

    def test_passed_route_evidence_is_route_relative_and_content_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            route_root = root / "routes" / "java-to-go"
            evidence_path = route_root / "certification" / "repository-evidence.json"
            evidence_path.parent.mkdir(parents=True)
            evidence = b'{"status":"PASSED"}\n'
            evidence_path.write_bytes(evidence)
            (route_root / "route.json").write_text("{}\n", encoding="utf-8")
            route = {
                "route_key": "java-to-go",
                "repository_execution_status": "PASSED",
                "repository_profile": "repository-v1",
                "repository_evidence_ref": "certification/repository-evidence.json",
                "repository_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
                "repository_evidence_bytes": len(evidence),
            }
            (root / "routes" / "inventory.json").write_text(
                json.dumps({"route_count": 1, "routes": [route]}) + "\n",
                encoding="utf-8",
            )
            deployed = {
                "routes/inventory.json",
                "routes/java-to-go/route.json",
                "routes/java-to-go/certification/repository-evidence.json",
            }

            self.assertEqual((1, 1), validator.validate_route_contracts(root, deployed))
            with self.assertRaisesRegex(ValueError, "NOT_DEPLOYED"):
                validator.validate_route_contracts(
                    root,
                    {
                        "routes/inventory.json",
                        "routes/java-to-go/route.json",
                        "certification/repository-evidence.json",
                    },
                )
            route["repository_evidence_sha256"] = "0" * 64
            (root / "routes" / "inventory.json").write_text(
                json.dumps({"route_count": 1, "routes": [route]}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "DIGEST_MISMATCH"):
                validator.validate_route_contracts(root, deployed)

    def test_deployment_source_predicate_is_exact(self) -> None:
        self.assertTrue(validator.is_deployment_source("pom.xml"))
        self.assertTrue(validator.is_deployment_source("routes/java-to-go/route.json"))
        self.assertTrue(validator.is_deployment_source(validator.PRICING_CONTRACT))
        self.assertTrue(validator.is_deployment_source("apps/web-console/app/page.tsx"))
        self.assertFalse(
            validator.is_deployment_source("verification-packs/large.json")
        )
        self.assertFalse(validator.is_deployment_source("contracts/secret.json"))
        self.assertFalse(validator.is_deployment_source("apps/runner-agent/Dockerfile"))


if __name__ == "__main__":
    unittest.main()
