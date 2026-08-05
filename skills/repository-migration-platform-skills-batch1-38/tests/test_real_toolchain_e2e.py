from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import real_toolchain_e2e as e2e  # noqa: E402


class RealToolchainE2ETest(unittest.TestCase):
    def test_only_unique_ephemeral_resource_names_are_allowed(self) -> None:
        self.assertEqual("rmp-e2e-deadbeef", e2e.safe_resource("rmp-e2e-deadbeef"))
        self.assertEqual("rmp-e2e-deadbeef-source", e2e.safe_resource("rmp-e2e-deadbeef-source"))
        for unsafe in ("postgres", "rmp-e2e-*", "rmp-e2e-deadbeef/target", "rmp-e2e-DEADBEEF"):
            with self.subTest(unsafe=unsafe), self.assertRaises(e2e.E2EFailure):
                e2e.safe_resource(unsafe)

    def test_fixture_fingerprint_is_content_addressed(self) -> None:
        observed = e2e.fixture_digest()
        self.assertRegex(observed, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(observed, e2e.fixture_digest())

    def test_real_report_can_materialize_exact_claim_subjects(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rmp-e2e-unit-") as directory:
            output = Path(directory)
            report = output / "report.json"
            report.write_text(json.dumps({"decision": "PASS"}), encoding="utf-8")
            obligation = e2e.claim(7, "output", 0)
            result = output / "domain-result.json"
            tools = [
                e2e.tool("pg_dump", "pg_dump 16.9", ["pg_dump", "-Fc", "rmp"]),
                e2e.tool("pg_restore", "pg_restore 17.5", ["pg_restore", "rmp"]),
                e2e.tool("psql", "psql 17.5", ["psql", "rollback-check"]),
            ]
            e2e.emit_domain_result(
                result, report, obligation, tools,
                "detail reconciliation and rollback passed",
                e2e.digest_bytes(b"environment"),
            )
            subject = json.loads((output / "domain-result-oracle-subject.json").read_text(encoding="utf-8"))
            self.assertEqual(obligation["oracle_id"], subject["oracle_id"])
            self.assertEqual("PASS", subject["decision"])
            self.assertEqual("development", subject["corpus_role"])

    def test_migration_template_has_fail_closed_checksum_guard(self) -> None:
        template = (e2e.FIXTURES / "target-expand-contract.sql").read_text(encoding="utf-8")
        self.assertEqual(2, template.count("__CHECKSUM__"))
        self.assertIn("migration checksum drift", template)
        self.assertIn("BEGIN;", template)
        self.assertIn("COMMIT;", template)

    def test_minio_pipe_attaches_stdin_only_when_bytes_are_present(self) -> None:
        provider = e2e.ProviderRuntime(
            "rmp-e2e-deadbeef-minio", "rmp-e2e-deadbeef",
            e2e.MINIO_IMAGE, e2e.MC_IMAGE,
        )
        completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(e2e, "run", return_value=completed) as invoke:
            provider.mc(["pipe", "e2e/bucket/object"], input_bytes=b"payload")
            with_stdin = invoke.call_args.args[0]
            self.assertIn("-i", with_stdin)
            provider.mc(["ls", "e2e"])
            without_stdin = invoke.call_args.args[0]
            self.assertNotIn("-i", without_stdin)


if __name__ == "__main__":
    unittest.main()
