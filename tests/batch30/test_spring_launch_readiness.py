import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/validate_spring_launch_readiness.py"


class SpringLaunchReadinessTests(unittest.TestCase):
    def test_repository_contract_is_ready_only_for_external_gate(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SPRING_LAUNCH_GATE=READY_FOR_EXTERNAL_GATE", result.stdout)
        self.assertIn("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN", result.stdout)
        self.assertIn("CERTIFICATION=NOT_CERTIFIED", result.stdout)

    def test_production_mode_fails_without_external_evidence(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--require-production-evidence"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("production evidence is required", result.stderr)

    def test_template_cannot_masquerade_as_external_evidence(self):
        template = ROOT / "deploy/production/spring-external-evidence.example.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--external-evidence", str(template)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("artifact_sha256 must be 64 lowercase hex", result.stderr)
        self.assertIn("is not PASSED_EXTERNAL", result.stderr)

    def test_environment_preflight_fails_closed_without_attestations(self):
        environment = dict(os.environ)
        for name in tuple(environment):
            if name.startswith("ELMOS_SPRING_") or name.startswith("ELMOS_JAVA_UPGRADE_") or name.startswith("ELMOS_VERIFIER_") or name.startswith("ELMOS_TRANSFORMER_"):
                environment.pop(name)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-environment"],
            text=True,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED must equal true", result.stderr)
        self.assertIn("shared Spring workspace", result.stderr)

    def test_environment_preflight_accepts_complete_nonsecret_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            secrets = []
            for index in range(3):
                secret = root / f"secret-{index}"
                secret.write_bytes(bytes([65 + index]) * 32)
                secret.chmod(0o600)
                secrets.append(secret)
            environment = dict(os.environ)
            environment.update({
                "ELMOS_SPRING_PROXY_ENABLED": "true",
                "ELMOS_SPRING_PROXY_MULTI_TENANT": "true",
                "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED": "true",
                "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED": "true",
                "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED": "true",
                "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED": "true",
                "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED": "true",
                "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED": "false",
                "ELMOS_SPRING_CODING_AGENT_ENABLED": "false",
                "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "independent-verifier-1",
                "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL": "https://runner.example.test/verifier",
                "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL": "https://runner.example.test/transformer",
                "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL": "https://runner.example.test/runtime",
                "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH": str(workspace),
                "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH": str(secrets[0]),
                "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH": str(secrets[1]),
                "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH": str(secrets[2]),
            })
            environment.pop("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID", None)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check-environment"],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN", result.stdout)


if __name__ == "__main__":
    unittest.main()
