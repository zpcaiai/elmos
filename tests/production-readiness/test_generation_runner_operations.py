from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
BACKUP_TOOL = ROOT / "scripts" / "operations" / "generation_runner_backup.py"


class GenerationRunnerOperationsTests(unittest.TestCase):
    def command(self, *arguments: str, expected: int = 0) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(BACKUP_TOOL), *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(expected, result.returncode, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def fixture_root(self, base: Path, *, status: str = "COMPLETED") -> Path:
        root = base / "runner"
        job = root / "tenants" / "tenant-a" / "jobs" / "00000000-0000-0000-0000-000000000001"
        job.mkdir(parents=True, mode=0o700)
        (job / "job.json").write_text(
            json.dumps(
                {
                    "status": status,
                    "runtime": {"status": "STOPPED"},
                    "tenantId": "tenant-a",
                }
            ),
            encoding="utf-8",
        )
        (job / "generated-project.zip").write_bytes(b"immutable-artifact")
        return root

    def test_content_addressed_backup_verify_restore_and_resume(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-operations-") as temporary:
            base = Path(temporary)
            root = self.fixture_root(base)
            archive = base / "backup.zip"
            restored = base / "restored"
            actor = "user:operations"

            self.assertEqual(
                "QUIESCED",
                self.command("quiesce", "--root", str(root), "--actor", actor)["status"],
            )
            backup = self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            self.assertEqual("BACKUP_CREATED", backup["status"])
            self.assertEqual(
                backup["sha256"],
                self.command("verify", "--archive", str(archive))["sha256"],
            )
            recovery = self.command(
                "restore",
                "--archive",
                str(archive),
                "--destination",
                str(restored),
                "--actor",
                actor,
            )
            self.assertEqual("RESTORED_REQUIRES_RESUME", recovery["status"])
            self.assertEqual(
                b"immutable-artifact",
                (
                    restored
                    / "tenants"
                    / "tenant-a"
                    / "jobs"
                    / "00000000-0000-0000-0000-000000000001"
                    / "generated-project.zip"
                ).read_bytes(),
            )
            self.assertTrue((restored / ".maintenance.json").is_file())
            self.assertEqual(
                "RESUMED",
                self.command("resume", "--root", str(restored), "--actor", actor)["status"],
            )
            self.assertFalse((restored / ".maintenance.json").exists())

    def test_backup_rejects_active_job_and_undeclared_archive_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-negative-") as temporary:
            base = Path(temporary)
            root = self.fixture_root(base, status="GENERATING")
            archive = base / "backup.zip"
            actor = "user:operations"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            blocked = self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
                expected=2,
            )
            self.assertTrue(str(blocked["reason"]).startswith("RUNNER_NOT_DRAINED:"))

            (root / "tenants" / "tenant-a" / "jobs" / "00000000-0000-0000-0000-000000000001" / "job.json").write_text(
                json.dumps({"status": "COMPLETED", "runtime": {"status": "STOPPED"}}),
                encoding="utf-8",
            )
            self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            with zipfile.ZipFile(archive, "a") as backup:
                backup.writestr("undeclared.txt", "tamper")
            result = self.command("verify", "--archive", str(archive), expected=2)
            self.assertEqual("BACKUP_ARCHIVE_UNDECLARED_ENTRY", result["reason"])

    def test_container_and_secret_contracts_fail_closed(self) -> None:
        dockerfile = (ROOT / "apps" / "web-console" / "Dockerfile").read_text(encoding="utf-8")
        compose = yaml.safe_load(
            (ROOT / "deploy" / "compose" / "docker-compose.yml").read_text(encoding="utf-8")
        )
        runner_source = (
            ROOT / "apps" / "web-console" / "app" / "lib" / "server" / "generationRunner.ts"
        ).read_text(encoding="utf-8")
        health_route = (
            ROOT / "apps" / "web-console" / "app" / "api" / "health" / "route.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        for line in dockerfile.splitlines():
            if line.startswith("FROM "):
                self.assertRegex(line.split()[1], r"^[^@\s]+@sha256:[0-9a-f]{64}$")
        web = compose["services"]["web-console"]
        self.assertTrue(web["read_only"])
        self.assertEqual(["ALL"], web["cap_drop"])
        self.assertEqual("false", web["environment"]["ELMOS_LOCAL_RUNNER_ENABLED"])
        self.assertIn("healthcheck", web)
        self.assertIn("ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE", runner_source)
        self.assertIn("LOCAL_RUNNER_AUTH_FILE_UNSAFE", runner_source)
        self.assertIn("LOCAL_RUNNER_IDENTITY_LEASE_INVALID", runner_source)
        self.assertIn("LOCAL_RUNNER_QUIESCED", runner_source)
        self.assertIn("ROOTLESS_CONTAINER_ENGINE_NOT_CONFIGURED", runner_source)
        self.assertIn("HOST_EXECUTOR_FORBIDDEN_IN_PRODUCTION", runner_source)
        self.assertIn("RECOVERY_REQUEUED_AFTER_RESTART", runner_source)
        self.assertIn("RESTART_RECOVERY_LIMIT_EXCEEDED", runner_source)
        self.assertIn("reconcilePersistentQueue", runner_source)
        self.assertIn('probe === "liveness"', health_route)
        self.assertIn('runner.status === "BLOCKED" ? 503 : 200', health_route)


if __name__ == "__main__":
    unittest.main()
