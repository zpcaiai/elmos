import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/run_spring_route_reference.py"
SPEC = importlib.util.spec_from_file_location("spring_route_reference_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)

ROUTE_ID = "boot-2.7-maven-to-boot-3.5.3-java-21"
ROUTE_CONTRACT_SCRIPT = ROOT / "scripts/operations/validate_spring_route_contract.py"


class SpringRouteReferenceEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="spring-route-evidence-tests-"
        )
        self.repo = Path(self.temporary.name)
        self.workspace = self.repo / "workspace"
        self.route = REFERENCE.ROUTES[ROUTE_ID]
        self.canonical = (
            self.repo / "evidence/spring-routes" / f"{ROUTE_ID}.json"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_main(self) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            str(SCRIPT),
            "--route",
            ROUTE_ID,
            "--repo-root",
            str(self.repo),
            "--workspace",
            str(self.workspace),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = REFERENCE.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_existing_pass_survives_a_new_failed_attempt_byte_for_byte(self) -> None:
        self.canonical.parent.mkdir(parents=True)
        original = (
            b'{\n  "execution_status": "PASSED_LOCAL",\n'
            b'  "route_id": "boot-2.7-maven-to-boot-3.5.3-java-21",\n'
            b'  "schema_version": 1,\n  "sentinel": "keep-me"\n}\n'
        )
        self.canonical.write_bytes(original)

        with (
            mock.patch.object(
                REFERENCE,
                "execute",
                side_effect=REFERENCE.RunFailure("SIMULATED_NETWORK_FAILURE"),
            ),
            mock.patch.object(
                REFERENCE, "utc_now", return_value="2026-08-09T10:11:12Z"
            ),
        ):
            result, _, stderr = self.run_main()

        self.assertEqual(result, 1)
        self.assertEqual(self.canonical.read_bytes(), original)
        attempt = REFERENCE.failure_attempt_destination(self.repo, self.route)
        self.assertTrue(attempt.is_file())
        attempt_payload = json.loads(attempt.read_text(encoding="utf-8"))
        self.assertEqual(
            attempt_payload["canonical_evidence"]["execution_status_at_attempt"],
            "PASSED_LOCAL",
        )
        self.assertFalse(attempt_payload["canonical_evidence"]["updated"])
        self.assertIn("canonical evidence preserved", stderr)

    def test_failed_attempt_is_stable_auditable_and_explicitly_non_certifying(self) -> None:
        attempt = REFERENCE.failure_attempt_destination(self.repo, self.route)
        failures = (
            ("FIRST_FAILURE", "2026-08-09T10:11:12Z"),
            ("SECOND_FAILURE", "2026-08-09T10:12:13Z"),
        )
        for failure, attempted_at in failures:
            with (
                mock.patch.object(
                    REFERENCE,
                    "execute",
                    side_effect=REFERENCE.RunFailure(failure),
                ),
                mock.patch.object(
                    REFERENCE, "utc_now", return_value=attempted_at
                ),
            ):
                result, _, stderr = self.run_main()
            self.assertEqual(result, 1)
            self.assertIn("non-certifying attempt recorded", stderr)

        self.assertFalse(self.canonical.exists())
        self.assertEqual(
            list(attempt.parent.glob(f"{ROUTE_ID}*.json")),
            [attempt],
        )
        payload = json.loads(attempt.read_text(encoding="utf-8"))
        self.assertEqual(payload["record_type"], "NON_CERTIFYING_ROUTE_ATTEMPT")
        self.assertEqual(payload["evidence_scope"], "LOCAL_ATTEMPT_AUDIT_ONLY")
        self.assertEqual(payload["attempted_at"], "2026-08-09T10:12:13Z")
        self.assertEqual(payload["execution_status"], "FAILED")
        self.assertEqual(payload["failure"], "SECOND_FAILURE")
        self.assertFalse(payload["certification_eligible"])
        self.assertEqual(payload["certification_status"], "NOT_CERTIFIED")
        self.assertEqual(payload["external_evidence_status"], "NOT_RUN")
        self.assertEqual(
            payload["canonical_evidence"],
            {
                "execution_status_at_attempt": "ABSENT",
                "path": f"evidence/spring-routes/{ROUTE_ID}.json",
                "updated": False,
            },
        )
        self.assertEqual(list(attempt.parent.glob("*.tmp")), [])

    def test_success_atomically_replaces_the_canonical_record(self) -> None:
        success = {
            "schema_version": 1,
            "route_id": ROUTE_ID,
            "execution_status": "PASSED_LOCAL",
            "behavioral_parity": True,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        real_replace = os.replace
        with (
            mock.patch.object(REFERENCE, "execute", return_value=success),
            mock.patch.object(
                REFERENCE.os, "replace", wraps=real_replace
            ) as replace,
        ):
            result, stdout, _ = self.run_main()

        self.assertEqual(result, 0)
        self.assertIn(f"PASS: {ROUTE_ID}", stdout)
        self.assertEqual(
            json.loads(self.canonical.read_text(encoding="utf-8")), success
        )
        self.assertEqual(replace.call_count, 1)
        source, destination = replace.call_args.args
        self.assertEqual(Path(destination).resolve(), self.canonical.resolve())
        self.assertEqual(Path(source).parent.resolve(), self.canonical.parent.resolve())
        self.assertEqual(list(self.canonical.parent.glob("*.tmp")), [])
        self.assertFalse(
            REFERENCE.failure_attempt_destination(self.repo, self.route).exists()
        )

    def test_boot_3_5_local_records_are_exact(self) -> None:
        expected = {
            "boot-1.5-java-8-maven-to-boot-3.5.3-java-21": ("1.5.22.RELEASE", "8"),
            "boot-2.0-2.6-maven-to-boot-3.5.3-java-21": ("2.3.12.RELEASE", "11"),
            "boot-2.7-maven-to-boot-3.5.3-java-21": ("2.7.18", "17"),
            "boot-3.0-3.4-maven-to-boot-3.5.3-java-21": ("3.4.1", "17"),
        }
        for route_id, (source_boot, source_java) in expected.items():
            record = json.loads(
                (ROOT / "evidence/spring-routes" / f"{route_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(record["execution_status"], "PASSED_LOCAL")
            self.assertTrue(record["behavioral_parity"])
            self.assertEqual(
                record["recorded_tuple"],
                {
                    "source_boot": source_boot,
                    "source_java": source_java,
                    "target_boot": "3.5.3",
                    "target_java": "21",
                },
            )
            self.assertEqual(record["external_evidence_status"], "NOT_RUN")
            self.assertEqual(record["independent_verification"], "NOT_RUN")
            self.assertEqual(record["certification_status"], "NOT_CERTIFIED")

    def test_boot_4_1_local_records_are_exact_and_contract_validated(self) -> None:
        expected = {
            "boot-2.7-maven-to-boot-4.1.0-java-21": ("2.7.18", "17"),
            "boot-3.5-maven-to-boot-4.1.0-java-21": ("3.5.3", "21"),
        }
        for route_id, (source_boot, source_java) in expected.items():
            record = json.loads(
                (ROOT / "evidence/spring-routes" / f"{route_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(record["execution_status"], "PASSED_LOCAL")
            self.assertTrue(record["behavioral_parity"])
            self.assertEqual(
                record["recorded_tuple"],
                {
                    "source_boot": source_boot,
                    "source_java": source_java,
                    "target_boot": "4.1.0",
                    "target_java": "21",
                },
            )
            self.assertEqual(record["external_evidence_status"], "NOT_RUN")
            self.assertEqual(record["independent_verification"], "NOT_RUN")
            self.assertEqual(record["certification_status"], "NOT_CERTIFIED")

        result = subprocess.run(
            [sys.executable, str(ROUTE_CONTRACT_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tampered_boot_3_5_evidence_fails_contract_validator(self) -> None:
        target_evidence = ROOT / "evidence/spring-routes/boot-2.7-maven-to-boot-3.5.3-java-21.json"
        original = target_evidence.read_text(encoding="utf-8")
        tampered = json.loads(original)
        tampered["recorded_tuple"]["target_boot"] = "3.5.4"
        try:
            target_evidence.write_text(json.dumps(tampered), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROUTE_CONTRACT_SCRIPT)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BOOT_3_5_LOCAL_EVIDENCE", result.stdout + result.stderr)
        finally:
            target_evidence.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
