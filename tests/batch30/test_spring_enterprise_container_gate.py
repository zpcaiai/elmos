from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/run_spring_enterprise_container_gate.py"
SPEC = importlib.util.spec_from_file_location("spring_enterprise_container_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


class SpringEnterpriseContainerGateTest(unittest.TestCase):
    def test_exact_enterprise_fixture_tuple_and_shared_contract(self) -> None:
        subject._verify_fixture_metadata()
        source_pom = (subject.FIXTURES["source"]["directory"] / "pom.xml").read_text()
        target_pom = (subject.FIXTURES["target"]["directory"] / "pom.xml").read_text()
        test_source = (
            subject.FIXTURES["source"]["directory"]
            / "src/test/java/io/elmos/enterprise/EnterpriseContractIT.java"
        ).read_text()

        self.assertIn("<version>2.7.18</version>", source_pom)
        self.assertIn("<java.version>17</java.version>", source_pom)
        self.assertIn("<version>3.5.3</version>", target_pom)
        self.assertIn("<java.version>21</java.version>", target_pom)
        self.assertIn("../enterprise-source/src/test/java", target_pom)
        self.assertIn(subject.IMAGES["postgres"], test_source)
        self.assertIn(subject.IMAGES["rabbitmq"], test_source)

    def test_report_requires_all_four_contracts_without_waiver(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-enterprise-report-") as directory:
            report = Path(directory) / "report.xml"
            report.write_text(
                '<testsuite tests="4" failures="0" errors="0" skipped="0"/>',
                encoding="utf-8",
            )
            self.assertEqual(
                subject._parse_report(report),
                {"tests": 4, "failures": 0, "errors": 0, "skipped": 0},
            )
            report.write_text(
                '<testsuite tests="4" failures="0" errors="0" skipped="1"/>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(subject.EnterpriseGateError, "unexpected"):
                subject._parse_report(report)

    def test_staging_requires_exact_main_rootless_runner_identity(self) -> None:
        environment = {
            "CI": "true",
            "GITHUB_ACTIONS": "true",
            "GITHUB_REF": "refs/heads/main",
            "ELMOS_SPRING_RUNNER_CLASS": "DEDICATED_ROOTLESS",
            "ELMOS_SPRING_RUNNER_ID": "spring-staging-arm64-01",
            "ELMOS_SPRING_RUNNER_ATTESTATION_DIGEST": "sha256:" + "a" * 64,
            "ELMOS_SPRING_ENVIRONMENT_ID": "spring-enterprise-staging",
            "ELMOS_SPRING_DEPLOYMENT_ID": "deployment-20260914-01",
            "ELMOS_SPRING_EXPECTED_REVISION": "b" * 40,
        }
        docker = {"rootless": True}
        with tempfile.TemporaryDirectory(prefix="spring-enterprise-evidence-") as directory:
            output = Path(directory) / "evidence.json"
            identity = subject._require_staging_context(
                environment, docker, "b" * 40, output
            )
        self.assertEqual(identity["runner_id"], "spring-staging-arm64-01")

        with tempfile.TemporaryDirectory(prefix="spring-enterprise-evidence-") as directory:
            with self.assertRaisesRegex(subject.EnterpriseGateError, "rootless"):
                subject._require_staging_context(
                    environment, {"rootless": False}, "b" * 40, Path(directory) / "evidence.json"
                )


if __name__ == "__main__":
    unittest.main()
