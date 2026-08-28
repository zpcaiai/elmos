from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/production-runtime"))

from external_provider_adapter import (  # noqa: E402
    ProviderAdapterError,
    build_provider_request,
    execute_provider_probe,
    validate_provider_binding,
)
from hosted_pitr_adapter import (  # noqa: E402
    PitrAdapterError,
    cleanup_command,
    describe_command,
    restore_command,
    restored_endpoint,
    validate_pitr_binding,
    wait_command,
)
from independent_verifier import issue_receipt  # noqa: E402
from independent_verifier_service import (  # noqa: E402
    VerificationService,
    VerifierServiceError,
)
from external_verifier_crypto import validate_external_report  # noqa: E402


class FakeResponse:
    def __init__(self, status: int, body: dict[str, object], headers: dict[str, str] | None = None):
        self.status = status
        self.body = json.dumps(body).encode()
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self) -> int:
        return self.status

    def read(self, maximum: int) -> bytes:
        return self.body[:maximum]


class ExternalProviderAdapterTest(unittest.TestCase):
    def binding(self, adapter: str) -> dict[str, object]:
        provider, model = {
            "openai-responses-v1": ("openai", "gpt-test"),
            "anthropic-messages-2023-06-01": ("anthropic", "claude-test"),
            "gemini-generate-content-v1beta": ("gemini", "gemini-test"),
        }[adapter]
        return {
            "adapter": adapter,
            "provider": provider,
            "model": model,
            "credential_env": "PROVIDER_KEY",
            "probe_input": "Return ELMOS_PROVIDER_RUNTIME_OK.",
            "max_output_tokens": 32,
        }

    def test_exact_provider_profiles_have_no_generic_endpoint_override(self) -> None:
        openai = build_provider_request(self.binding("openai-responses-v1"), "secret", "request-id")
        self.assertEqual("https://api.openai.com/v1/responses", openai.full_url)
        self.assertEqual("Bearer secret", openai.get_header("Authorization"))
        self.assertEqual("request-id", openai.get_header("X-client-request-id"))

        anthropic = build_provider_request(
            self.binding("anthropic-messages-2023-06-01"), "secret", "request-id"
        )
        self.assertEqual("https://api.anthropic.com/v1/messages", anthropic.full_url)
        self.assertEqual("2023-06-01", anthropic.get_header("Anthropic-version"))

        gemini = build_provider_request(
            self.binding("gemini-generate-content-v1beta"), "secret", "request-id"
        )
        self.assertTrue(gemini.full_url.endswith("/v1beta/models/gemini-test:generateContent"))
        self.assertEqual("secret", gemini.get_header("X-goog-api-key"))

    def test_probe_is_one_attempt_and_content_addressed(self) -> None:
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return FakeResponse(200, {"id": "resp_123", "status": "completed"})

        with tempfile.TemporaryDirectory() as temporary:
            result = execute_provider_probe(
                self.binding("openai-responses-v1"),
                Path(temporary),
                {"PROVIDER_KEY": "secret"},
                opener,
            )
            self.assertEqual("PASS", result["status"])
            self.assertEqual(1, result["attempts"])
            artifact = Path(temporary) / result["response_artifact"]
            self.assertTrue(artifact.is_file())
            import hashlib

            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), result["response_sha256"])
        self.assertEqual(1, len(calls))

    def test_uncertain_provider_error_is_not_retried(self) -> None:
        calls = 0

        def opener(_request, timeout):
            nonlocal calls
            calls += 1
            self.assertEqual(120, timeout)
            raise urllib.error.URLError("timeout after send")

        with tempfile.TemporaryDirectory() as temporary:
            result = execute_provider_probe(
                self.binding("openai-responses-v1"),
                Path(temporary),
                {"PROVIDER_KEY": "secret"},
                opener,
            )
        self.assertEqual("UNKNOWN", result["status"])
        self.assertEqual(1, calls)

    def test_profile_provider_mismatch_is_rejected(self) -> None:
        binding = self.binding("openai-responses-v1")
        binding["provider"] = "anthropic"
        with self.assertRaises(ProviderAdapterError):
            validate_provider_binding(binding)


class HostedPitrAdapterTest(unittest.TestCase):
    def binding(self, driver: str) -> dict[str, object]:
        value: dict[str, object] = {
            "driver": driver,
            "source_instance": "elmos-source",
            "restore_target": "elmos-pitr-verify",
            "restore_database": "elmos",
            "restore_username_env": "PITR_USER",
            "restore_password_env": "PITR_PASSWORD",
            "source_database_url_env": "PITR_SOURCE_URL",
            "marker_tenant_id": "11111111-1111-4111-8111-111111111111",
            "marker_id": "22222222-2222-4222-8222-222222222222",
            "marker_sha256": "a" * 64,
            "archive_delay_seconds": 60,
            "cleanup_after_verification": True,
        }
        if driver == "aws-rds-postgresql-v1":
            value["region"] = "us-east-1"
        elif driver == "gcp-cloudsql-postgresql-v1":
            value["project"] = "elmos-project"
        else:
            value["subscription"] = "sub-123"
            value["resource_group"] = "elmos-rg"
        return value

    def test_all_hosted_drivers_use_fixed_command_vectors(self) -> None:
        restore_time = "2026-08-28T01:02:03Z"
        aws = self.binding("aws-rds-postgresql-v1")
        self.assertEqual("aws", restore_command(aws, restore_time)[0])
        self.assertIn("--no-publicly-accessible", restore_command(aws, restore_time))
        self.assertEqual("aws", wait_command(aws)[0])
        self.assertIn("--skip-final-snapshot", cleanup_command(aws))

        gcp = self.binding("gcp-cloudsql-postgresql-v1")
        self.assertEqual(["gcloud", "sql", "instances", "clone"], restore_command(gcp, restore_time)[:4])
        self.assertIsNone(wait_command(gcp))
        self.assertIn("--quiet", cleanup_command(gcp))

        azure = self.binding("azure-postgresql-flexible-v1")
        self.assertEqual(["az", "postgres", "flexible-server", "restore"], restore_command(azure, restore_time)[:4])
        self.assertIn("--yes", cleanup_command(azure))

    def test_provider_describe_outputs_are_strictly_parsed(self) -> None:
        aws = self.binding("aws-rds-postgresql-v1")
        self.assertEqual(
            ("private.rds.example", 5432),
            restored_endpoint(aws, json.dumps({"DBInstances": [{"Endpoint": {"Address": "private.rds.example", "Port": 5432}}]})),
        )
        gcp = self.binding("gcp-cloudsql-postgresql-v1")
        self.assertEqual(
            ("10.0.0.5", 5432),
            restored_endpoint(gcp, json.dumps({"ipAddresses": [{"type": "PRIVATE", "ipAddress": "10.0.0.5"}]})),
        )
        azure = self.binding("azure-postgresql-flexible-v1")
        self.assertEqual(
            ("restore.postgres.database.azure.com", 5432),
            restored_endpoint(azure, json.dumps({"fullyQualifiedDomainName": "restore.postgres.database.azure.com"})),
        )
        with self.assertRaises(PitrAdapterError):
            restored_endpoint(aws, json.dumps({"DBInstances": [{"Endpoint": {"Address": "bad/host"}}]}))

    def test_restore_time_and_resource_injection_fail_closed(self) -> None:
        binding = self.binding("aws-rds-postgresql-v1")
        binding["restore_target"] = "target; rm -rf"
        with self.assertRaises(PitrAdapterError):
            validate_pitr_binding(binding)
        binding = self.binding("aws-rds-postgresql-v1")
        with self.assertRaises(PitrAdapterError):
            restore_command(binding, "2026-08-28 01:02:03")
        self.assertEqual("aws", describe_command(binding)[0])


class IndependentVerifierTest(unittest.TestCase):
    def report(self) -> dict[str, object]:
        passing = {
            name: {"status": "PASS"}
            for name in (
                "provider_runtime",
                "target_cluster_load",
                "chaos",
                "worker_process_kill",
                "redis_loss",
                "backup_pitr",
                "production_deployment",
            )
        }
        passing["independent_verification"] = {"status": "NOT_RUN"}
        return {
            "schema_version": 1,
            "mode": "EXECUTE",
            "source_archive_sha256": "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37",
            "operations": passing,
            "external_evidence": {
                name: value["status"] for name, value in passing.items()
            },
            "production_certification": "NOT_CERTIFIED",
        }

    def test_verifier_refuses_failed_operation(self) -> None:
        report = self.report()
        report["operations"]["chaos"]["status"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            validate_external_report(report)

    def test_separate_key_issues_digest_bound_receipt(self) -> None:
        if shutil.which("openssl") is None:
            self.skipTest("openssl is required")
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private.pem"
            public = Path(temporary) / "public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private)],
                check=True, capture_output=True,
            )
            private.chmod(0o600)
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                check=True, capture_output=True,
            )
            report_bytes = (json.dumps(self.report(), sort_keys=True) + "\n").encode()
            receipt = issue_receipt(
                report_bytes, "PRODUCTION_RUNTIME_EXECUTOR", "INDEPENDENT_VERIFIER",
                private, public,
            )
            self.assertEqual("PASS", receipt["status"])
            self.assertEqual(hashlib.sha256(report_bytes).hexdigest(), receipt["report_sha256"])
            self.assertEqual(hashlib.sha256(public.read_bytes()).hexdigest(), receipt["signing_key_sha256"])
            self.assertTrue(receipt["signature"])

    def test_verifier_service_is_persistent_idempotent_and_actor_bound(self) -> None:
        if shutil.which("openssl") is None:
            self.skipTest("openssl is required")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private.pem"
            public = root / "public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "RSA",
                 "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(private)],
                check=True, capture_output=True,
            )
            private.chmod(0o600)
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout",
                 "-out", str(public)],
                check=True, capture_output=True,
            )
            service = VerificationService(
                bearer_token="t" * 48,
                producer_actor="PRODUCTION_RUNTIME_EXECUTOR",
                verifier_actor="INDEPENDENT_VERIFIER",
                private_key=private,
                public_key=public,
                receipt_store=root / "receipts",
                maximum_report_bytes=1024 * 1024,
            )
            report_bytes = (json.dumps(self.report(), sort_keys=True) + "\n").encode()
            digest = hashlib.sha256(report_bytes).hexdigest()
            service.authenticate("Bearer " + "t" * 48)
            first = service.verify(
                report_bytes, digest, "PRODUCTION_RUNTIME_EXECUTOR")
            second = service.verify(
                report_bytes, digest, "PRODUCTION_RUNTIME_EXECUTOR")
            self.assertEqual(first, second)
            self.assertEqual(
                1, len(list((root / "receipts").glob("*.json"))))
            with self.assertRaises(VerifierServiceError):
                service.authenticate("Bearer wrong")
            with self.assertRaises(VerifierServiceError):
                service.verify(report_bytes, "0" * 64, "PRODUCTION_RUNTIME_EXECUTOR")
            with self.assertRaises(VerifierServiceError):
                service.verify(report_bytes, digest, "INDEPENDENT_VERIFIER")


if __name__ == "__main__":
    unittest.main()
