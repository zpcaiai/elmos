from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import importlib.util
import hashlib
import io
import json
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "operations" / "generation_runtime_reaper.py"
SPEC = importlib.util.spec_from_file_location("generation_runtime_reaper", MODULE_PATH)
assert SPEC and SPEC.loader
reaper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reaper)
PODMAN = Path("/usr/bin/podman")


class GenerationRuntimeReaperTests(unittest.TestCase):
    def fixture(self, base: Path, *, expires_at: str, lease_id: str = "a" * 32) -> tuple[Path, str]:
        root = base / "runner"
        job_id = "123e4567-e89b-42d3-a456-426614174000"
        job_root = root / "tenants" / "tenant-a" / "jobs" / job_id
        job_root.mkdir(parents=True, mode=0o700)
        (job_root / "job.json").write_text(
            json.dumps(
                {
                    "id": job_id,
                    "tenantId": "tenant-a",
                    "runtime": {
                        "status": "RUNNING",
                        "executor": "ROOTLESS_CONTAINER",
                        "language": "python",
                        "leaseId": lease_id,
                        "leaseExpiresAt": expires_at,
                    },
                }
            ),
            encoding="utf-8",
        )
        expires_epoch = int(datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp())
        state = job_root / "runtime-state"
        state.mkdir(mode=0o700)
        marker = state / "lease.json"
        marker.write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "language": "python",
                    "lease_id": lease_id,
                    "phase": "RUNNING",
                    "lease_started_epoch": expires_epoch - 600,
                    "lease_expires_epoch": expires_epoch,
                }
            ),
            encoding="utf-8",
        )
        marker.chmod(0o600)
        return root, job_id

    def test_expired_lease_is_cleaned_with_a_durable_receipt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-") as temporary:
            root, job_id = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            with patch.object(reaper, "_invoke_helper", return_value={"status": "STOPPED"}) as invoke:
                result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("REAPER_SWEEP_COMPLETE", result["status"])
            self.assertEqual(1, result["cleaned"])
            self.assertEqual(1, invoke.call_count)
            receipt = json.loads(
                (root / "tenants" / "tenant-a" / "runtime-reaper" / f"{job_id}-{'a' * 32}.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual("CLEANUP_VERIFIED", receipt["outcome"])
            self.assertEqual("LEASE_EXPIRED", receipt["trigger"])

    def test_old_receipt_cannot_delete_a_newer_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-superseded-") as temporary:
            root, job_id = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            with patch.object(
                reaper,
                "_invoke_helper",
                return_value={"status": "SUPERSEDED"},
            ) as invoke:
                result = reaper.sweep(root, ROOT, PODMAN)
                receipt_path = (
                    root
                    / "tenants"
                    / "tenant-a"
                    / "runtime-reaper"
                    / f"{job_id}-{'a' * 32}.json"
                )
                original = receipt_path.read_bytes()
                repeated = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual(0, result["cleaned"])
            self.assertEqual("BLOCKED", result["status"])
            self.assertEqual(0, repeated["cleaned"])
            self.assertEqual("BLOCKED", repeated["status"])
            self.assertEqual(1, invoke.call_count)
            self.assertEqual(original, receipt_path.read_bytes())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual("NEWER_LEASE_PRESERVED", receipt["outcome"])

    def test_unexpired_marker_is_not_touched_and_invalid_marker_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-boundary-") as temporary:
            base = Path(temporary)
            root, _ = self.fixture(
                base,
                expires_at=(datetime.now(timezone.utc) + timedelta(seconds=500)).isoformat(),
            )
            with patch.object(reaper, "_invoke_helper") as invoke:
                result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual(0, result["cleaned"])
            invoke.assert_not_called()

            marker = next((root / "tenants" / "tenant-a" / "jobs").glob("*/runtime-state/lease.json"))
            value = json.loads(marker.read_text(encoding="utf-8"))
            value["lease_expires_epoch"] = value["lease_started_epoch"] + 599
            marker.write_text(json.dumps(value), encoding="utf-8")
            blocked = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("BLOCKED", blocked["status"])
            self.assertEqual(1, blocked["blocked"])

    def test_provisioning_marker_is_bounded_but_cannot_back_a_running_job(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-provisioning-") as temporary:
            root, job_id = self.fixture(
                Path(temporary),
                expires_at=(datetime.now(timezone.utc) + timedelta(seconds=200)).isoformat(),
            )
            job_file = root / "tenants" / "tenant-a" / "jobs" / job_id / "job.json"
            marker_file = job_file.parent / "runtime-state" / "lease.json"
            job = json.loads(job_file.read_text(encoding="utf-8"))
            marker = json.loads(marker_file.read_text(encoding="utf-8"))
            marker["lease_started_epoch"] = marker["lease_expires_epoch"] - 300
            marker_file.write_text(json.dumps(marker), encoding="utf-8")
            job["runtime"]["status"] = "STOPPED"
            job_file.write_text(json.dumps(job), encoding="utf-8")
            with patch.object(reaper, "_invoke_helper") as invoke:
                waiting = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual(0, waiting["cleaned"])
            invoke.assert_not_called()

            job["runtime"]["status"] = "RUNNING"
            job_file.write_text(json.dumps(job), encoding="utf-8")
            with patch.object(reaper, "_invoke_helper", return_value={"status": "STOPPED"}):
                cleaned = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual(1, cleaned["cleaned"])
            receipt = json.loads(
                (
                    root
                    / "tenants"
                    / "tenant-a"
                    / "runtime-reaper"
                    / f"{job_id}-{'a' * 32}.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual("LEASE_STATE_DIVERGED", receipt["trigger"])

    def test_marker_expiry_overrides_a_tampered_future_job_expiry_and_receipt_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-marker-") as temporary:
            root, _ = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            job_file = next((root / "tenants" / "tenant-a" / "jobs").glob("*/job.json"))
            job = json.loads(job_file.read_text(encoding="utf-8"))
            job["runtime"]["leaseExpiresAt"] = "2099-01-01T00:00:00+00:00"
            job_file.write_text(json.dumps(job), encoding="utf-8")
            with patch.object(reaper, "_invoke_helper", return_value={"status": "STOPPED"}) as invoke:
                first = reaper.sweep(root, ROOT, PODMAN)
                receipt_path = next((root / "tenants" / "tenant-a" / "runtime-reaper").glob("*.json"))
                original = receipt_path.read_bytes()
                second = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual(1, first["cleaned"])
            self.assertEqual(0, second["cleaned"])
            self.assertEqual(1, invoke.call_count)
            self.assertEqual(original, receipt_path.read_bytes())

    def test_invalid_tenant_is_isolated_and_does_not_starve_a_valid_expired_job(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-tenant-") as temporary:
            root, _ = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            (root / "tenants" / "000-invalid").write_text("unsafe", encoding="utf-8")
            with patch.object(reaper, "_invoke_helper", return_value={"status": "STOPPED"}) as invoke:
                result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("BLOCKED", result["status"])
            self.assertEqual(1, result["cleaned"])
            self.assertEqual(1, result["blocked"])
            self.assertEqual(1, invoke.call_count)

    def test_tenant_io_failure_is_isolated_from_valid_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-tenant-io-") as temporary:
            root, _ = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            (root / "tenants" / "tenant-b" / "jobs").mkdir(parents=True)
            original = reaper._safe_receipt_directory

            def safe_receipt_directory(scan_root: Path, destination: Path) -> None:
                if destination == root / "tenants" / "tenant-b" / "runtime-reaper":
                    raise OSError("injected tenant storage failure")
                original(scan_root, destination)

            with (
                patch.object(reaper, "_safe_receipt_directory", side_effect=safe_receipt_directory),
                patch.object(reaper, "_invoke_helper", return_value={"status": "STOPPED"}) as invoke,
            ):
                result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("BLOCKED", result["status"])
            self.assertEqual(1, result["cleaned"])
            self.assertEqual(1, result["blocked"])
            self.assertEqual(1, invoke.call_count)
            error_receipts = list((root / "runtime-reaper-errors").glob("tenant-*.json"))
            self.assertEqual(1, len(error_receipts))
            error = json.loads(error_receipts[0].read_text(encoding="utf-8"))
            self.assertEqual("RUNTIME_REAPER_TENANT_ACCESS_FAILED", error["reason"])

    def test_atomic_receipt_is_no_clobber_and_cleans_failed_temporary_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-atomic-") as temporary:
            root = Path(temporary)
            destination = root / "receipt.json"
            barrier = threading.Barrier(2)

            def write(value: int) -> bool:
                barrier.wait(timeout=2)
                return reaper._atomic_json(destination, {"value": value}, replace=False)

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(write, (1, 2)))
            self.assertEqual([False, True], sorted(results))
            self.assertIn(json.loads(destination.read_text(encoding="utf-8"))["value"], {1, 2})
            self.assertEqual(0, destination.stat().st_mode & 0o077)
            self.assertEqual([], list(root.glob(".*.tmp")))

            failed = root / "failed.json"
            with (
                patch.object(reaper.os, "write", side_effect=OSError("injected write failure")),
                self.assertRaisesRegex(OSError, "injected write failure"),
            ):
                reaper._atomic_json(failed, {"value": 3}, replace=False)
            self.assertFalse(failed.exists())
            self.assertEqual([], list(root.glob(".*.tmp")))

    def test_scan_limits_bound_directory_enumeration_and_total_job_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-scan-limit-") as temporary:
            root, _ = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            (root / "tenants" / "tenant-b").mkdir()
            with patch.object(reaper, "MAX_TENANT_SCAN_ENTRIES", 1):
                tenant_limited = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("BLOCKED", tenant_limited["status"])
            self.assertEqual(0, tenant_limited["examined"])
            self.assertEqual(1, tenant_limited["blocked"])

            with (
                patch.object(reaper, "MAX_TOTAL_JOB_SCAN_ENTRIES", 0),
                patch.object(reaper, "_invoke_helper") as invoke,
            ):
                result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("BLOCKED", result["status"])
            self.assertEqual(0, result["examined"])
            self.assertEqual(0, result["cleaned"])
            self.assertEqual(1, result["blocked"])
            invoke.assert_not_called()

    def test_quiesce_pauses_cleanup_and_heartbeat_is_durable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-quiesce-") as temporary:
            root, _ = self.fixture(Path(temporary), expires_at="2026-01-01T00:00:00+00:00")
            (root / ".maintenance.json").write_text(
                json.dumps({"status": "QUIESCED", "actor": "user:operations"}),
                encoding="utf-8",
            )
            result = reaper.sweep(root, ROOT, PODMAN)
            self.assertEqual("REAPER_QUIESCED", result["status"])
            reaper._write_heartbeat(root, result, "b" * 64)
            heartbeat = json.loads((root / ".runtime-reaper-heartbeat.json").read_text(encoding="utf-8"))
            self.assertEqual(reaper.HEARTBEAT_SCHEMA, heartbeat["schema_version"])
            self.assertEqual("b" * 64, heartbeat["engine_context_sha256"])
            self.assertEqual("REAPER_QUIESCED", heartbeat["sweep_status"])

    def test_engine_environment_is_sanitized_and_bound_to_the_shared_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="erc-", dir="/tmp") as temporary:
            base = Path(temporary).resolve()
            root = base / "runner"
            root.mkdir(mode=0o700)
            engine = base / "docker"
            engine.write_text("test fixture", encoding="utf-8")
            xdg_runtime = base / "xdg-runtime"
            xdg_runtime.mkdir(mode=0o700)
            docker_socket = xdg_runtime / "docker.sock"
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(docker_socket))
                docker_socket.chmod(0o660)
                source = {
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                    "HOME": "/untrusted/home",
                    "DOCKER_HOST": "tcp://127.0.0.1:2375",
                    "DOCKER_CONTEXT": "untrusted-context",
                    "ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR": str(xdg_runtime),
                    "ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET": str(docker_socket),
                    "ELMOS_LOCAL_RUNNER_AUTH_TOKEN": "must-not-reach-helper",
                }
                environment, digest = reaper._engine_environment(root, engine, source)

                self.assertEqual(str((root / "home").resolve()), environment["HOME"])
                self.assertEqual(str(xdg_runtime), environment["XDG_RUNTIME_DIR"])
                self.assertEqual(f"unix://{docker_socket}", environment["DOCKER_HOST"])
                self.assertNotIn("DOCKER_CONTEXT", environment)
                self.assertNotIn("ELMOS_LOCAL_RUNNER_AUTH_TOKEN", environment)
                expected = hashlib.sha256()
                for value in (
                    str(engine),
                    str((root / "home").resolve()),
                    str(xdg_runtime),
                    str(docker_socket),
                ):
                    expected.update(value.encode("utf-8"))
                    expected.update(b"\0")
                self.assertEqual(expected.hexdigest(), digest)

                job_id = "123e4567-e89b-42d3-a456-426614174000"
                lease_id = "a" * 32
                completed = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "status": "STOPPED",
                            "job_id": job_id,
                            "language": "python",
                            "requested_lease_id": lease_id,
                        }
                    ),
                    stderr="",
                )
                with patch.object(reaper.subprocess, "run", return_value=completed) as run:
                    reaper._invoke_helper(
                        ROOT / "scripts" / "operations" / "rootless_project_runner.py",
                        engine,
                        root / "job",
                        job_id,
                        "python",
                        lease_id,
                        environment,
                    )
                self.assertEqual(environment, run.call_args.kwargs["env"])

    def test_engine_environment_rejects_tcp_relative_and_mismatched_socket_configuration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ern-", dir="/tmp") as temporary:
            base = Path(temporary).resolve()
            root = base / "runner"
            root.mkdir(mode=0o700)
            docker = base / "docker"
            docker.write_text("test fixture", encoding="utf-8")
            podman = base / "podman"
            podman.write_text("test fixture", encoding="utf-8")
            with self.assertRaisesRegex(
                reaper.ReaperError,
                "RUNTIME_REAPER_DOCKER_UNIX_SOCKET_NOT_CONFIGURED",
            ):
                reaper._engine_environment(root, docker, {})
            with self.assertRaisesRegex(
                reaper.ReaperError,
                "RUNTIME_REAPER_DOCKER_UNIX_SOCKET_INVALID",
            ):
                reaper._engine_environment(
                    root,
                    docker,
                    {"ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET": "tcp://127.0.0.1:2375"},
                )
            with self.assertRaisesRegex(
                reaper.ReaperError,
                "RUNTIME_REAPER_ENGINE_XDG_RUNTIME_DIR_INVALID",
            ):
                reaper._engine_environment(
                    root,
                    podman,
                    {"ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR": "relative/runtime"},
                )

            unix_socket = base / "podman-mismatch.sock"
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(unix_socket))
                unix_socket.chmod(0o660)
                with self.assertRaisesRegex(
                    reaper.ReaperError,
                    "RUNTIME_REAPER_DOCKER_UNIX_SOCKET_ENGINE_MISMATCH",
                ):
                    reaper._engine_environment(
                        root,
                        podman,
                        {"ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET": str(unix_socket)},
                    )

    def test_main_once_writes_heartbeat_and_rejects_a_symlink_lock(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-runtime-reaper-main-") as temporary:
            base = Path(temporary)
            root = base / "runner"
            root.mkdir(mode=0o700)
            engine = base / "podman"
            engine.write_text("test fixture", encoding="utf-8")
            arguments = [
                str(MODULE_PATH),
                "--root",
                str(root),
                "--repository-root",
                str(ROOT),
                "--engine",
                str(engine),
                "--once",
            ]
            output = io.StringIO()
            with patch.object(reaper.sys, "argv", arguments), redirect_stdout(output):
                self.assertEqual(0, reaper.main())
            heartbeat = json.loads((root / ".runtime-reaper-heartbeat.json").read_text(encoding="utf-8"))
            self.assertEqual("REAPER_IDLE", heartbeat["sweep_status"])

            lock = root / ".runtime-reaper.lock"
            lock.unlink()
            lock.symlink_to(engine)
            output = io.StringIO()
            with patch.object(reaper.sys, "argv", arguments), redirect_stdout(output):
                self.assertEqual(2, reaper.main())
            blocked = json.loads(output.getvalue())
            self.assertEqual("BLOCKED", blocked["status"])

    def test_node_helper_uses_the_same_explicit_engine_context_contract(self) -> None:
        source = (
            ROOT / "apps" / "web-console" / "app" / "lib" / "server" / "generationRunner.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("HOME: runner.engineHome", source)
        self.assertIn("ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR", source)
        self.assertIn("ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET", source)
        self.assertIn("environment.XDG_RUNTIME_DIR = runner.engineXdgRuntimeDir", source)
        self.assertIn("environment.DOCKER_HOST = `unix://${runner.dockerUnixSocket}`", source)
        self.assertIn('value.schema_version !== "elmos.generation-runtime-reaper-heartbeat.v2"', source)
        self.assertIn("value.engine_context_sha256 !== runner.engineContextDigest", source)


if __name__ == "__main__":
    unittest.main()
