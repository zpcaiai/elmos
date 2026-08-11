from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
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

    def rewrite_manifest(self, archive_path: Path, mutation) -> None:
        with zipfile.ZipFile(archive_path, "r") as source:
            members = [(info, source.read(info.filename)) for info in source.infolist()]
        manifest = json.loads(
            next(payload for info, payload in members if info.filename == "MANIFEST.json")
        )
        mutation(manifest)
        rewritten = archive_path.with_name(f".{archive_path.name}.rewritten")
        with zipfile.ZipFile(rewritten, "w") as target:
            for info, payload in members:
                target.writestr(
                    info,
                    (
                        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                    ).encode("utf-8")
                    if info.filename == "MANIFEST.json"
                    else payload,
                )
        rewritten.replace(archive_path)

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

    def test_backup_manifest_schema_rejects_invalid_mode_duplicate_path_and_types(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-manifest-negative-") as temporary:
            base = Path(temporary)
            root = self.fixture_root(base)
            archive = base / "backup.zip"
            actor = "user:operations"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            original = archive.read_bytes()

            def invalid_mode(manifest: dict[str, object]) -> None:
                manifest["entries"][0]["mode"] = "not-octal"  # type: ignore[index]

            def duplicate_path(manifest: dict[str, object]) -> None:
                entries = manifest["entries"]  # type: ignore[assignment]
                entries.append(dict(entries[0]))  # type: ignore[union-attr,index]
                manifest["entry_count"] = len(entries)  # type: ignore[arg-type]

            def boolean_entry_count(manifest: dict[str, object]) -> None:
                manifest["entry_count"] = True

            def extra_entry_property(manifest: dict[str, object]) -> None:
                manifest["entries"][0]["unexpected"] = True  # type: ignore[index]

            for name, mutation, reason in (
                ("invalid-mode", invalid_mode, "BACKUP_MANIFEST_ENTRY_INVALID"),
                ("duplicate-logical-path", duplicate_path, "BACKUP_MANIFEST_ENTRY_INVALID"),
                ("boolean-entry-count", boolean_entry_count, "BACKUP_MANIFEST_INVALID"),
                ("extra-entry-property", extra_entry_property, "BACKUP_MANIFEST_ENTRY_INVALID"),
            ):
                with self.subTest(name=name):
                    archive.write_bytes(original)
                    self.rewrite_manifest(archive, mutation)
                    result = self.command("verify", "--archive", str(archive), expected=2)
                    self.assertEqual(reason, result["reason"])

            archive.write_bytes(original)
            self.rewrite_manifest(archive, invalid_mode)
            restored = base / "invalid-mode-restore"
            blocked_restore = self.command(
                "restore",
                "--archive",
                str(archive),
                "--destination",
                str(restored),
                "--actor",
                actor,
                expected=2,
            )
            self.assertEqual("BACKUP_MANIFEST_ENTRY_INVALID", blocked_restore["reason"])
            self.assertFalse(restored.exists())

    def test_quiesced_gc_requires_digest_bound_backup_and_writes_verified_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-gc-") as temporary:
            base = Path(temporary)
            root = base / "runner"
            job_id = "123e4567-e89b-42d3-a456-426614174000"
            tenant = "tenant-a"
            job = root / "tenants" / tenant / "jobs" / job_id
            job.mkdir(parents=True, mode=0o700)
            (job / "job.json").write_text(
                json.dumps(
                    {
                        "id": job_id,
                        "tenantId": tenant,
                        "actor": "user:operations",
                        "status": "COMPLETED",
                        "runtime": {"status": "STOPPED"},
                        "retentionPolicyVersion": "generation-storage-v1",
                        "retentionExpiresAt": "2026-01-01T00:00:00+00:00",
                        "legalHold": False,
                        "artifactSha256": "a" * 64,
                        "artifactSize": 18,
                    }
                ),
                encoding="utf-8",
            )
            (job / "generated-project.zip").write_bytes(b"immutable-artifact")
            actor = "user:operations"
            archive = base / "gc-backup.zip"

            self.command("quiesce", "--root", str(root), "--actor", actor)
            plan = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
            )
            self.assertEqual("GC_PLAN_READY", plan["status"])
            self.assertEqual([job_id], [item["job_id"] for item in plan["candidates"]])
            blocked = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
                "--apply",
                expected=2,
            )
            self.assertEqual("GC_BACKUP_ARCHIVE_REQUIRED", blocked["reason"])
            self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            applied = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
                "--apply",
                "--backup-archive",
                str(archive),
            )
            self.assertEqual("GC_VERIFIED_PURGED", applied["status"])
            self.assertEqual([job_id], applied["deleted_job_ids"])
            self.assertFalse(job.exists())
            audits = list((root / "tenants" / tenant / "storage-gc" / "audit").glob("*.json"))
            self.assertEqual(1, len(audits))
            receipt = json.loads(audits[0].read_text(encoding="utf-8"))
            self.assertEqual("VERIFIED_PURGED", receipt["status"])
            self.assertEqual(applied["backup_sha256"], receipt["backup_sha256"])

    def test_gc_fails_closed_while_a_durable_lease_is_active(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-gc-lease-") as temporary:
            root = Path(temporary) / "runner"
            root.mkdir(parents=True)
            actor = "user:operations"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            lease = root / ".durable-queue" / "leases" / "generation" / ("a" * 64) / "lease.json"
            lease.parent.mkdir(parents=True)
            lease.write_text(json.dumps({"expiresAt": "2099-01-01T00:00:00+00:00"}), encoding="utf-8")
            blocked = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                "tenant-a",
                "--actor",
                actor,
                expected=2,
            )
            self.assertTrue(str(blocked["reason"]).startswith("DURABLE_LEASE_ACTIVE:"))

    def test_gc_recovers_a_job_moved_to_trash_with_the_original_backup_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-gc-recovery-") as temporary:
            base = Path(temporary)
            root = base / "runner"
            tenant = "tenant-a"
            actor = "user:operations"
            job_id = "123e4567-e89b-42d3-a456-426614174000"
            deletion_id = "223e4567-e89b-42d3-a456-426614174000"
            job = root / "tenants" / tenant / "jobs" / job_id
            job.mkdir(parents=True, mode=0o700)
            job_record = {
                "id": job_id,
                "tenantId": tenant,
                "status": "COMPLETED",
                "runtime": {"status": "STOPPED"},
                "retentionPolicyVersion": "generation-storage-v1",
                "retentionExpiresAt": "2026-01-01T00:00:00+00:00",
                "legalHold": False,
            }
            (job / "job.json").write_text(json.dumps(job_record), encoding="utf-8")
            (job / "generated-project.zip").write_bytes(b"immutable-artifact")
            archive = base / "gc-backup.zip"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            backup = self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            maintenance_created_at = json.loads(
                (root / ".maintenance.json").read_text(encoding="utf-8")
            )["created_at"]
            files = sorted(item for item in job.iterdir() if item.is_file())
            job_bytes = sum(item.stat().st_size for item in files)
            job_file_count = len(files)
            trash = (
                root
                / "tenants"
                / tenant
                / "storage-trash"
                / "jobs"
                / f"{job_id}-{deletion_id}"
            )
            trash.parent.mkdir(parents=True, mode=0o700)
            audit_path = (
                root / "tenants" / tenant / "storage-gc" / "audit" / f"{deletion_id}.json"
            )
            audit_path.parent.mkdir(parents=True, mode=0o700)
            job_digest = hashlib.sha256((job / "job.json").read_bytes()).hexdigest()
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "elmos.generation-storage-gc.v1",
                        "status": "PREPARED",
                        "tenant_id": tenant,
                        "job_id": job_id,
                        "actor": actor,
                        "job_record_sha256": job_digest,
                        "backup_sha256": backup["sha256"],
                        "maintenance_created_at": maintenance_created_at,
                        "bytes": job_bytes,
                        "file_count": job_file_count,
                        "backup_bytes": job_bytes,
                        "backup_file_count": job_file_count,
                        "trash_bytes": job_bytes,
                        "trash_file_count": job_file_count,
                        "original_path": f"tenants/{tenant}/jobs/{job_id}",
                        "trash_path": trash.relative_to(root).as_posix(),
                    }
                ),
                encoding="utf-8",
            )
            job.rename(trash)

            plan = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
            )
            self.assertEqual("GC_PLAN_RECOVERY_REQUIRED", plan["status"])
            blocked_resume = self.command(
                "resume",
                "--root",
                str(root),
                "--actor",
                actor,
                expected=2,
            )
            self.assertEqual("GC_RECOVERY_REQUIRED_BEFORE_RESUME", blocked_resume["reason"])
            applied = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
                "--apply",
                "--backup-archive",
                str(archive),
            )
            self.assertEqual("GC_VERIFIED_PURGED", applied["status"])
            self.assertEqual([job_id], applied["deleted_job_ids"])
            self.assertFalse(trash.exists())
            receipt = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual("VERIFIED_PURGED", receipt["status"])
            self.assertTrue(receipt["recovered_after_interruption"])

    def test_gc_recovery_preserves_backup_and_post_cleanup_trash_statistics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-gc-rootless-recovery-") as temporary:
            base = Path(temporary)
            root = base / "runner"
            tenant = "tenant-a"
            actor = "user:operations"
            job_id = "323e4567-e89b-42d3-a456-426614174000"
            deletion_id = "423e4567-e89b-42d3-a456-426614174000"
            job = root / "tenants" / tenant / "jobs" / job_id
            runtime_state = job / "runtime-state"
            runtime_state.mkdir(parents=True, mode=0o700)
            job_record = {
                "id": job_id,
                "tenantId": tenant,
                "status": "COMPLETED",
                "runtime": {
                    "status": "STOPPED",
                    "executor": "ROOTLESS_CONTAINER",
                    "language": "python",
                    "leaseId": "a" * 32,
                },
                "retentionPolicyVersion": "generation-storage-v1",
                "retentionExpiresAt": "2026-01-01T00:00:00+00:00",
                "legalHold": False,
            }
            (job / "job.json").write_text(json.dumps(job_record), encoding="utf-8")
            (job / "generated-project.zip").write_bytes(b"immutable-artifact")
            (runtime_state / "lease.json").write_text("rootless lease", encoding="utf-8")
            (runtime_state / "jwt-hmac-secret").write_text("ephemeral secret", encoding="utf-8")
            original_files = sorted(path for path in job.rglob("*") if path.is_file())
            backup_bytes = sum(path.stat().st_size for path in original_files)
            backup_file_count = len(original_files)
            archive = base / "gc-backup.zip"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            backup = self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            maintenance_created_at = json.loads(
                (root / ".maintenance.json").read_text(encoding="utf-8")
            )["created_at"]

            # Simulate the successful rootless cleanup followed by interruption
            # after the job directory was atomically moved to trash.
            shutil.rmtree(runtime_state)
            trash_files = sorted(path for path in job.rglob("*") if path.is_file())
            trash_bytes = sum(path.stat().st_size for path in trash_files)
            trash_file_count = len(trash_files)
            self.assertLess(trash_bytes, backup_bytes)
            self.assertLess(trash_file_count, backup_file_count)
            trash = (
                root
                / "tenants"
                / tenant
                / "storage-trash"
                / "jobs"
                / f"{job_id}-{deletion_id}"
            )
            trash.parent.mkdir(parents=True, mode=0o700)
            audit_path = (
                root / "tenants" / tenant / "storage-gc" / "audit" / f"{deletion_id}.json"
            )
            audit_path.parent.mkdir(parents=True, mode=0o700)
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "elmos.generation-storage-gc.v1",
                        "status": "MOVED_TO_TRASH",
                        "tenant_id": tenant,
                        "job_id": job_id,
                        "actor": actor,
                        "job_record_sha256": hashlib.sha256(
                            (job / "job.json").read_bytes()
                        ).hexdigest(),
                        "backup_sha256": backup["sha256"],
                        "maintenance_created_at": maintenance_created_at,
                        "bytes": backup_bytes,
                        "file_count": backup_file_count,
                        "backup_bytes": backup_bytes,
                        "backup_file_count": backup_file_count,
                        "trash_bytes": trash_bytes,
                        "trash_file_count": trash_file_count,
                        "original_path": f"tenants/{tenant}/jobs/{job_id}",
                        "trash_path": trash.relative_to(root).as_posix(),
                        "rootless_cleanup_receipt": {
                            "status": "STOPPED",
                            "job_id": job_id,
                            "language": "python",
                            "requested_lease_id": "a" * 32,
                        },
                        "prepared_at": "2026-08-10T00:00:00+00:00",
                        "moved_at": "2026-08-10T00:00:01+00:00",
                    }
                ),
                encoding="utf-8",
            )
            job.rename(trash)

            applied = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
                "--apply",
                "--backup-archive",
                str(archive),
            )
            self.assertEqual("GC_VERIFIED_PURGED", applied["status"])
            self.assertEqual(backup_bytes, applied["bytes"])
            self.assertFalse(trash.exists())
            receipt = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual("VERIFIED_PURGED", receipt["status"])
            self.assertEqual(backup_bytes, receipt["backup_bytes"])
            self.assertEqual(trash_bytes, receipt["trash_bytes"])

    def test_gc_recovers_purge_completed_before_final_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runner-gc-purge-receipt-") as temporary:
            base = Path(temporary)
            root = base / "runner"
            tenant = "tenant-a"
            actor = "user:operations"
            job_id = "523e4567-e89b-42d3-a456-426614174000"
            deletion_id = "623e4567-e89b-42d3-a456-426614174000"
            job = root / "tenants" / tenant / "jobs" / job_id
            job.mkdir(parents=True, mode=0o700)
            job_record = {
                "id": job_id,
                "tenantId": tenant,
                "status": "COMPLETED",
                "runtime": {"status": "STOPPED"},
                "retentionPolicyVersion": "generation-storage-v1",
                "retentionExpiresAt": "2026-01-01T00:00:00+00:00",
                "legalHold": False,
            }
            (job / "job.json").write_text(json.dumps(job_record), encoding="utf-8")
            (job / "generated-project.zip").write_bytes(b"immutable-artifact")
            files = sorted(path for path in job.rglob("*") if path.is_file())
            job_bytes = sum(path.stat().st_size for path in files)
            job_file_count = len(files)
            job_digest = hashlib.sha256((job / "job.json").read_bytes()).hexdigest()
            archive = base / "gc-backup.zip"
            self.command("quiesce", "--root", str(root), "--actor", actor)
            backup = self.command(
                "backup",
                "--root",
                str(root),
                "--actor",
                actor,
                "--output",
                str(archive),
            )
            maintenance_created_at = json.loads(
                (root / ".maintenance.json").read_text(encoding="utf-8")
            )["created_at"]
            audit_path = (
                root / "tenants" / tenant / "storage-gc" / "audit" / f"{deletion_id}.json"
            )
            audit_path.parent.mkdir(parents=True, mode=0o700)
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "elmos.generation-storage-gc.v1",
                        "status": "MOVED_TO_TRASH",
                        "tenant_id": tenant,
                        "job_id": job_id,
                        "actor": actor,
                        "job_record_sha256": job_digest,
                        "backup_sha256": backup["sha256"],
                        "maintenance_created_at": maintenance_created_at,
                        "bytes": job_bytes,
                        "file_count": job_file_count,
                        "backup_bytes": job_bytes,
                        "backup_file_count": job_file_count,
                        "trash_bytes": job_bytes,
                        "trash_file_count": job_file_count,
                        "original_path": f"tenants/{tenant}/jobs/{job_id}",
                        "trash_path": (
                            f"tenants/{tenant}/storage-trash/jobs/{job_id}-{deletion_id}"
                        ),
                        "rootless_cleanup_receipt": None,
                        "prepared_at": "2026-08-10T00:00:00+00:00",
                        "moved_at": "2026-08-10T00:00:01+00:00",
                    }
                ),
                encoding="utf-8",
            )
            shutil.rmtree(job)

            plan = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
            )
            self.assertEqual("GC_PLAN_RECOVERY_REQUIRED", plan["status"])
            applied = self.command(
                "gc",
                "--root",
                str(root),
                "--tenant",
                tenant,
                "--actor",
                actor,
                "--apply",
                "--backup-archive",
                str(archive),
            )
            self.assertEqual("GC_VERIFIED_PURGED", applied["status"])
            self.assertEqual([job_id], applied["deleted_job_ids"])
            self.assertEqual(job_bytes, applied["bytes"])
            receipt = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual("VERIFIED_PURGED", receipt["status"])
            self.assertTrue(receipt["recovered_after_interruption"])

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
