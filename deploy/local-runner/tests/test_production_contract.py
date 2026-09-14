from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import datetime as dt
import os
import unittest


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "deploy/local-runner/validate_production_contract.py"
CONTRACT = ROOT / "deploy/local-runner/production-contract.json"


def load_validator():
    spec = importlib.util.spec_from_file_location("runner_production_contract", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductionRunnerContractTest(unittest.TestCase):
    def test_static_contract_is_digest_bound_and_keeps_external_evidence_not_run(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["runtime_validation"], "NOT_RUN")
        self.assertEqual(result["linux_systemd_evidence"], "NOT_RUN")
        self.assertEqual(result["rootless_engine_evidence"], "NOT_RUN")
        self.assertEqual(result["certification"], "NOT_CERTIFIED")

    def test_contract_covers_isolation_restart_cancel_timeout_and_tenant_cleanup(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        isolation = contract["job_isolation"]
        self.assertEqual(isolation["executor"], "ROOTLESS_CONTAINER")
        self.assertEqual(isolation["root_filesystem"], "read-only")
        self.assertEqual(isolation["runtime_network"], "internal-only-no-external-egress")
        self.assertEqual(isolation["capabilities"], "drop-all")
        self.assertTrue(isolation["no_new_privileges"])
        self.assertEqual(isolation["limits"], {
            "cpus": 0.5,
            "memory": "512m",
            "pids": 256,
            "tmpfs": "/tmp:rw,noexec,nosuid,size=64m",
        })
        lifecycle = contract["lifecycle"]
        self.assertEqual(lifecycle["recovery"]["maximum_job_requeues"], 2)
        self.assertTrue(lifecycle["cancellation"]["termination_must_be_observed"])
        self.assertEqual(lifecycle["timeouts"]["runtime_lease_max_seconds"], 600)
        self.assertEqual(lifecycle["tenant_cleanup"]["superseded_lease"], "preserve-and-block")

    def test_runtime_preflight_fails_closed_before_reading_secret_content(self) -> None:
        module = load_validator()
        marker = "super-secret-token-value-must-not-leak"
        environment = {
            "ELMOS_LOCAL_RUNNER_SERVICE_UID": "0",
            "ELMOS_LOCAL_RUNNER_AUTH_SIGNING_KEY_FILE": marker,
        }
        with self.assertRaisesRegex(module.ContractError, "RUNNER_SERVICE_UID_INVALID") as raised:
            module.validate_runtime_environment(environment)
        self.assertNotIn(marker, str(raised.exception))

    def test_units_bind_same_non_root_identity_and_reaper_dependency(self) -> None:
        runner = (ROOT / "deploy/local-runner/systemd/elmos-generation-runner.service").read_text(
            encoding="utf-8"
        )
        reaper = (ROOT / "deploy/local-runner/systemd/elmos-generation-runtime-reaper.service").read_text(
            encoding="utf-8"
        )
        for unit in (runner, reaper):
            self.assertIn("User=elmos-runner", unit)
            self.assertIn("Group=elmos-runner", unit)
            self.assertIn("CapabilityBoundingSet=\n", unit)
            self.assertIn("NoNewPrivileges=true", unit)
            self.assertIn("ProtectSystem=full", unit)
            self.assertIn("ReadOnlyPaths=/opt/elmos", unit)
            self.assertIn("ReadWritePaths=/var/lib/elmos-generation-runner", unit)
        self.assertIn("Requires=elmos-generation-runtime-reaper.service", runner)
        self.assertIn("Restart=on-failure", runner)
        self.assertIn("Restart=always", reaper)
        self.assertIn("IPAddressDeny=any", reaper)
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            contract["systemd"]["runner_exec_start"],
            "/usr/bin/env ${ELMOS_LOCAL_RUNNER_PNPM_PATH} --dir "
            "${ELMOS_REPOSITORY_ROOT}/apps/web-console start --hostname 127.0.0.1 --port 3000",
        )
        self.assertEqual(
            contract["systemd"]["reaper_exec_start"],
            "/usr/bin/python3 ${ELMOS_REPOSITORY_ROOT}/scripts/operations/"
            "generation_runtime_reaper.py --root ${ELMOS_LOCAL_RUNNER_ROOT} "
            "--repository-root ${ELMOS_REPOSITORY_ROOT} "
            "--engine ${ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE} --interval-seconds 1",
        )

    def test_authentication_contract_forbids_static_bearer_and_binds_one_time_request(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        auth = contract["authentication"]
        self.assertEqual(auth["mode"], "ONE_TIME_HS256_SERVICE_CREDENTIAL")
        self.assertTrue(auth["static_bearer_forbidden_in_production"])
        self.assertEqual(auth["maximum_credential_seconds"], 300)
        self.assertTrue(auth["replay_rejected"])
        self.assertEqual(
            set(auth["exact_bindings"]),
            {"tenant_id", "actor_id", "permission", "method", "path", "kid", "jti"},
        )

    def test_auth_lease_requires_timezone_safety_margin_and_24_hour_maximum(self) -> None:
        module = load_validator()
        now = dt.datetime(2026, 9, 4, 12, 0, tzinfo=dt.timezone.utc)
        module._validate_lease_expiry("2026-09-04T12:05:00Z", now=now)
        for value, expected in (
            ("2026-09-04T12:04:59Z", "RUNNER_AUTH_LEASE_SAFETY_MARGIN_REQUIRED"),
            ("2026-09-05T12:00:01Z", "RUNNER_AUTH_LEASE_EXCEEDS_MAXIMUM"),
            ("2026-09-04T12:30:00", "RUNNER_AUTH_LEASE_TIMEZONE_REQUIRED"),
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(module.ContractError, expected):
                    module._validate_lease_expiry(value, now=now)

    def test_executable_integrity_contract_rejects_hardlinks(self) -> None:
        module = load_validator()
        directory = ROOT / ".elmos-test-runner-contract"
        directory.mkdir(exist_ok=True)
        first = directory / "tool"
        second = directory / "tool-hardlink"
        try:
            first.write_bytes(self._testMethodName.encode())
            first.chmod(0o555)
            os.link(first, second)
            with self.assertRaisesRegex(module.ContractError, "RUNNER_EXECUTABLE_HARDLINK_FORBIDDEN"):
                module._executable_immutable_to_service(
                    first,
                    os.geteuid(),
                    os.getegid(),
                    name="TEST",
                )
        finally:
            second.unlink(missing_ok=True)
            first.unlink(missing_ok=True)
            directory.rmdir()


if __name__ == "__main__":
    unittest.main()
