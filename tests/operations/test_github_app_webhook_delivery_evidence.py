from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "operations"
    / "collect_github_app_webhook_delivery_evidence.py"
)
SPEC = importlib.util.spec_from_file_location("github_webhook_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


GUID = "0b989ba4-242f-11e5-81e1-c7b6966d2516"
WEBHOOK_URL = "https://hooks.example.test/elmos/github"


def configuration(output: Path | None = None, **overrides: object):
    values = {
        "app_id": 101,
        "private_key_file": Path("/unused-in-collection"),
        "delivery_id": 12345678,
        "delivery_guid": GUID,
        "event": "issues",
        "action": "opened",
        "installation_id": 123,
        "repository_id": 456,
        "webhook_url": WEBHOOK_URL,
        "expected_status_code": 200,
        "change_ticket": "CHG-20260824-001",
        "pgservice": "elmos_prod_readonly",
        "tenant_id": "tenant-a",
        "expected_duplicate_count": 1,
        "expected_outbox_count": 1,
        "expected_processing_status": "RECEIVED",
        "output": output or Path("/tmp/not-written.json"),
        "http_timeout_seconds": 10.0,
        "poll_timeout_seconds": 1.0,
        "poll_interval_seconds": 0.01,
        "database_timeout_seconds": 10.0,
        "redeliver": True,
    }
    values.update(overrides)
    return MODULE.Configuration(**values)


def original_delivery(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 12345678,
        "guid": GUID,
        "delivered_at": "2026-08-24T00:00:00Z",
        "redelivery": False,
        "duration": 0.1,
        "status": "OK",
        "status_code": 200,
        "event": "issues",
        "action": "opened",
        "installation_id": 123,
        "repository_id": 456,
        "url": WEBHOOK_URL,
        "request": {
            "headers": {"X-Hub-Signature-256": "sha256=must-never-persist"},
            "payload": {"secret": "request-payload-must-never-persist"},
        },
        "response": {
            "headers": {"Set-Cookie": "must-never-persist"},
            "payload": "response-payload-must-never-persist",
        },
    }
    value.update(overrides)
    return value


def redelivery(**overrides: object) -> dict[str, object]:
    value = original_delivery(
        id=123456789,
        delivered_at="2026-08-24T00:00:02Z",
        redelivery=True,
        duration=0.2,
    )
    value.update(overrides)
    return value


def database_result(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "delivery_count": 1,
        "event_type": "issues",
        "action": "opened",
        "installation_external_id": 123,
        "repository_external_id": 456,
        "signature_valid": True,
        "processing_status": "RECEIVED",
        "duplicate_count": 1,
        "payload_digest_format_valid": True,
        "outbox_count": 1,
        "role_bypass_rls": False,
        "row_security_on": True,
    }
    value.update(overrides)
    return value


class FakeGithub:
    def __init__(
        self,
        *,
        before: dict[str, object] | None = None,
        attempt: dict[str, object] | None = None,
    ) -> None:
        self.before = before or original_delivery()
        self.attempt = attempt or redelivery()
        self.redelivered: list[int] = []
        self.detail_ids: list[int] = []

    def get_delivery(self, delivery_id: int):
        self.detail_ids.append(delivery_id)
        if delivery_id == self.before["id"]:
            return self.before
        if delivery_id == self.attempt["id"]:
            return self.attempt
        raise AssertionError("unexpected delivery id")

    def redeliver(self, delivery_id: int) -> None:
        self.redelivered.append(delivery_id)

    def list_deliveries(self):
        if not self.redelivered:
            return [self.before]
        return [self.attempt, self.before]


class FakeDatabase:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.result = result or database_result()
        self.calls = 0

    def query(self, _: object):
        self.calls += 1
        return self.result


class StepMonotonic:
    def __init__(self, step: float = 0.01) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class CollectionTests(unittest.TestCase):
    def test_success_binds_new_numeric_id_to_same_guid_and_drops_sensitive_bodies(self) -> None:
        github = FakeGithub()
        database = FakeDatabase()
        moments = iter(
            [
                dt.datetime(2026, 8, 24, 0, 0, 0, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 8, 24, 0, 0, 1, tzinfo=dt.timezone.utc),
                dt.datetime(2026, 8, 24, 0, 0, 3, tzinfo=dt.timezone.utc),
            ]
        )

        evidence = MODULE.collect_evidence(
            configuration(),
            github,
            database,
            wall_clock=lambda: next(moments),
            monotonic=StepMonotonic(),
            sleep=lambda _: None,
        )

        self.assertEqual([12345678], github.redelivered)
        self.assertEqual([12345678, 123456789], github.detail_ids)
        self.assertEqual(1, database.calls)
        self.assertEqual("PASS", evidence["result"])
        self.assertEqual("NOT_CERTIFIED", evidence["certification_status"])
        self.assertEqual(12345678, evidence["delivery_binding"]["original_delivery_id"])
        self.assertEqual(123456789, evidence["delivery_binding"]["redelivery_id"])
        serialized = json.dumps(evidence, sort_keys=True)
        for forbidden in (
            WEBHOOK_URL,
            "CHG-20260824-001",
            "elmos_prod_readonly",
            "tenant-a",
            "request-payload-must-never-persist",
            "response-payload-must-never-persist",
            "must-never-persist",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_initial_binding_mismatch_blocks_post(self) -> None:
        github = FakeGithub(before=original_delivery(repository_id=999))

        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_DELIVERY_BINDING_MISMATCH"):
            MODULE.collect_evidence(
                configuration(),
                github,
                FakeDatabase(),
                monotonic=StepMonotonic(),
                sleep=lambda _: None,
            )

        self.assertEqual([], github.redelivered)

    def test_redelivery_with_same_guid_but_different_resource_fails_closed(self) -> None:
        github = FakeGithub(attempt=redelivery(installation_id=999))

        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_DELIVERY_BINDING_MISMATCH"):
            MODULE.collect_evidence(
                configuration(),
                github,
                FakeDatabase(),
                monotonic=StepMonotonic(),
                sleep=lambda _: None,
            )

        self.assertEqual([12345678], github.redelivered)

    def test_concurrent_new_redeliveries_are_ambiguous_and_fail_closed(self) -> None:
        class ConcurrentGithub(FakeGithub):
            def list_deliveries(self):
                if not self.redelivered:
                    return [self.before]
                return [
                    self.attempt,
                    redelivery(id=123456790, delivered_at="2026-08-24T00:00:03Z"),
                    self.before,
                ]

        with self.assertRaisesRegex(
            MODULE.EvidenceError, "GITHUB_REDELIVERY_AMBIGUOUS"
        ):
            MODULE.collect_evidence(
                configuration(),
                ConcurrentGithub(),
                FakeDatabase(),
                wall_clock=lambda: dt.datetime(
                    2026, 8, 24, 0, 0, 1, tzinfo=dt.timezone.utc
                ),
                monotonic=StepMonotonic(),
                sleep=lambda _: None,
            )

    def test_database_mismatch_does_not_create_pass_evidence(self) -> None:
        clock = StepMonotonic(step=0.1)

        with self.assertRaisesRegex(MODULE.EvidenceError, "DATABASE_BINDING_NOT_OBSERVED"):
            MODULE.collect_evidence(
                configuration(poll_timeout_seconds=0.15),
                FakeGithub(),
                FakeDatabase(database_result(role_bypass_rls=True)),
                wall_clock=lambda: dt.datetime(
                    2026, 8, 24, 0, 0, 1, tzinfo=dt.timezone.utc
                ),
                monotonic=clock,
                sleep=lambda _: None,
            )

    def test_explicit_redelivery_flag_is_enforced_again_inside_collector(self) -> None:
        github = FakeGithub()

        with self.assertRaisesRegex(MODULE.EvidenceError, "REDELIVERY_EXPLICIT_FLAG_REQUIRED"):
            MODULE.collect_evidence(
                configuration(redeliver=False),
                github,
                FakeDatabase(),
            )

        self.assertEqual([], github.redelivered)

    def test_post_transport_failure_is_unknown_and_requires_reconciliation(self) -> None:
        class UncertainGithub(FakeGithub):
            def redeliver(self, delivery_id: int) -> None:
                self.redelivered.append(delivery_id)
                raise MODULE.EvidenceError("GITHUB_NETWORK_ERROR")

        progress = {
            "redelivery_post_attempted": False,
            "redelivery_post_accepted": False,
        }
        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_NETWORK_ERROR"):
            MODULE.collect_evidence(
                configuration(),
                UncertainGithub(),
                FakeDatabase(),
                progress=progress,
            )

        evidence = MODULE.failure_evidence(
            configuration(), "GITHUB_NETWORK_ERROR", progress
        )
        self.assertTrue(evidence["redelivery_post_attempted"])
        self.assertFalse(evidence["redelivery_post_accepted"])
        self.assertEqual(
            "UNKNOWN_RECONCILIATION_REQUIRED", evidence["side_effect_state"]
        )


class ApiClientTests(unittest.TestCase):
    def test_client_uses_only_bearer_jwt_and_exact_versioned_api(self) -> None:
        seen: list[tuple[str, str, dict[str, str]]] = []

        def transport(method: str, url: str, headers: dict[str, str], _: float):
            seen.append((method, url, dict(headers)))
            return MODULE.HttpResponse(
                200,
                {"Content-Type": "application/json"},
                json.dumps(original_delivery()).encode(),
                url,
            )

        client = MODULE.GitHubAppApi("header.payload.signature", 2.0, transport)
        client.get_delivery(12345678)

        method, url, headers = seen[0]
        self.assertEqual("GET", method)
        self.assertEqual(
            "https://api.github.com/app/hook/deliveries/12345678",
            url,
        )
        self.assertEqual("Bearer header.payload.signature", headers["Authorization"])
        self.assertEqual("2026-03-10", headers["X-GitHub-Api-Version"])
        self.assertNotIn("token", headers["Authorization"].lower())

    def test_final_url_change_is_rejected_even_if_transport_returns_200(self) -> None:
        def transport(_: str, __: str, ___: dict[str, str], ____: float):
            return MODULE.HttpResponse(
                200,
                {"Content-Type": "application/json"},
                b"{}",
                "https://redirect.example.test/",
            )

        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_FINAL_URL_MISMATCH"):
            MODULE.GitHubAppApi("a.b.c", 2.0, transport).get_delivery(1)

    def test_oversized_response_is_rejected_before_json_parsing(self) -> None:
        def transport(_: str, url: str, __: dict[str, str], ___: float):
            return MODULE.HttpResponse(
                200,
                {"Content-Type": "application/json"},
                b"x" * (MODULE.MAX_RESPONSE_BYTES + 1),
                url,
            )

        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_RESPONSE_TOO_LARGE"):
            MODULE.GitHubAppApi("a.b.c", 2.0, transport).get_delivery(1)

    def test_post_requires_exact_202(self) -> None:
        def transport(_: str, url: str, __: dict[str, str], ___: float):
            return MODULE.HttpResponse(200, {}, b"", url)

        with self.assertRaisesRegex(MODULE.EvidenceError, "GITHUB_HTTP_200"):
            MODULE.GitHubAppApi("a.b.c", 2.0, transport).redeliver(1)


class JwtAndInputTests(unittest.TestCase):
    def test_jwt_claims_are_short_lived_and_openssl_receives_fd_not_key_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            key = Path(temporary_directory).resolve() / "app.pem"
            key.write_bytes(b"k" * 512)
            key.chmod(0o600)
            captured: dict[str, object] = {}

            def runner(command: list[str], **kwargs: object):
                captured["command"] = command
                captured.update(kwargs)
                return subprocess.CompletedProcess(command, 0, b"s" * 256, b"")

            token = MODULE.build_github_app_jwt(101, key, 1_800_000_000, runner)

            encoded_header, encoded_payload, _ = token.split(".")
            decode = lambda value: json.loads(
                base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            )
            self.assertEqual({"alg": "RS256", "typ": "JWT"}, decode(encoded_header))
            claims = decode(encoded_payload)
            self.assertEqual("101", claims["iss"])
            self.assertEqual(600, claims["exp"] - claims["iat"])
            self.assertEqual(1_799_999_940, claims["iat"])
            self.assertNotIn(str(key), " ".join(captured["command"]))
            self.assertIn("/dev/fd/", " ".join(captured["command"]))
            self.assertEqual(1, len(captured["pass_fds"]))

    def test_private_key_must_be_absolute_owned_regular_and_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            key = Path(temporary_directory).resolve() / "app.pem"
            key.write_bytes(b"k" * 512)
            key.chmod(0o644)
            with self.assertRaisesRegex(
                MODULE.EvidenceError, "PRIVATE_KEY_PERMISSIONS_TOO_BROAD"
            ):
                MODULE._validate_private_key_path(key)
            key.chmod(0o600)
            MODULE._validate_private_key_path(key)

            symlink = Path(temporary_directory) / "link.pem"
            symlink.symlink_to(key)
            with self.assertRaisesRegex(MODULE.EvidenceError, "PRIVATE_KEY_NOT_REGULAR"):
                MODULE._validate_private_key_path(symlink)

            with self.assertRaisesRegex(MODULE.EvidenceError, "PRIVATE_KEY_PATH_NOT_ABSOLUTE"):
                MODULE._validate_private_key_path(Path("relative.pem"))

    def test_webhook_url_rejects_credentials_query_fragment_and_non_https(self) -> None:
        for value in (
            "http://hooks.example.test/path",
            "https://user@hooks.example.test/path",
            "https://hooks.example.test/path?token=secret",
            "https://hooks.example.test/path#fragment",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                MODULE.EvidenceError, "WEBHOOK_URL_INVALID"
            ):
                MODULE._validate_webhook_url(value)


class DatabaseVerifierTests(unittest.TestCase):
    def test_psql_uses_named_service_read_only_query_and_no_password_argument(self) -> None:
        observed: dict[str, object] = {}

        def runner(command: list[str], **kwargs: object):
            observed["command"] = command
            observed.update(kwargs)
            output = json.dumps(database_result()).encode() + b"\n"
            return subprocess.CompletedProcess(command, 0, output, b"")

        with mock.patch.dict(os.environ, {"PATH": "/usr/bin", "HOME": "/tmp"}, clear=True):
            result = MODULE.PsqlDatabaseVerifier(runner).query(configuration())

        self.assertEqual(1, result["delivery_count"])
        command = observed["command"]
        environment = observed["env"]
        self.assertIn("PGSERVICE", environment)
        self.assertEqual("elmos_prod_readonly", environment["PGSERVICE"])
        self.assertNotIn("PGPASSWORD", environment)
        self.assertNotIn("DATABASE_URL", environment)
        rendered = " ".join(command).lower()
        self.assertNotIn("password", rendered)
        self.assertIn("begin read only", rendered)
        self.assertIn("set local app.organization_id", rendered)
        self.assertIn("role_bypass_rls", rendered)

    def test_ambient_password_is_rejected_before_psql(self) -> None:
        runner = mock.Mock()
        with mock.patch.dict(
            os.environ, {"PGPASSWORD": "secret"}, clear=True
        ), self.assertRaisesRegex(
            MODULE.EvidenceError, "DATABASE_AMBIENT_PASSWORD_REJECTED"
        ):
            MODULE.PsqlDatabaseVerifier(runner).query(configuration())
        runner.assert_not_called()


class AtomicEvidenceTests(unittest.TestCase):
    def test_atomic_no_replace_creates_0600_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "evidence.json"
            MODULE.write_json_atomic_no_replace(destination, {"result": "PASS"})
            self.assertEqual({"result": "PASS"}, json.loads(destination.read_text()))
            self.assertEqual(0o600, stat.S_IMODE(destination.stat().st_mode))

            with self.assertRaisesRegex(MODULE.EvidenceError, "OUTPUT_ALREADY_EXISTS"):
                MODULE.write_json_atomic_no_replace(destination, {"result": "CHANGED"})
            self.assertEqual({"result": "PASS"}, json.loads(destination.read_text()))


if __name__ == "__main__":
    unittest.main()
