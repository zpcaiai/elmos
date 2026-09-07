from __future__ import annotations

import importlib.util
from contextlib import nullcontext
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "operations" / "rootless_project_runner.py"
SPEC = importlib.util.spec_from_file_location("rootless_project_runner", MODULE_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RootlessProjectRunnerTests(unittest.TestCase):
    def test_exact_profiles_and_host_health_paths_cover_all_emitters(self) -> None:
        self.assertEqual(set(runner.LANGUAGE_DIRECTORIES), set(runner.PORTS))
        self.assertEqual(set(runner.LANGUAGE_DIRECTORIES), set(runner.HEALTH_PATHS))
        self.assertEqual(len(runner.LANGUAGE_DIRECTORIES), 8)
        self.assertEqual(set(runner.HEALTH_PATHS.values()), {"/health"})
        self.assertRegex(
            runner.POSTGRES_IMAGE,
            r"^postgres:17\.5-alpine@sha256:[0-9a-f]{64}$",
        )

    def test_database_administrator_and_runtime_secrets_are_separate(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"postgres-admin-password"', source)
        self.assertIn('"postgres-runtime-password"', source)
        self.assertNotIn('"postgres-password"', source)
        self.assertIn("ALTER ROLE app_runtime PASSWORD", source)

    def test_dynamic_host_port_accepts_one_loopback_mapping_and_rejects_unsafe_receipts(self) -> None:
        valid = subprocess.CompletedProcess(
            ["docker", "port"],
            0,
            stdout="127.0.0.1:49152\n",
            stderr="",
        )
        with patch.object(runner, "_run", return_value=valid):
            self.assertEqual(
                runner._published_loopback_port(Path("/usr/bin/docker"), "app", 8082),
                49_152,
            )

        invalid_receipts = (
            "0.0.0.0:49152\n",
            ":::49152\n",
            "127.0.0.1:80\n",
            "127.0.0.1:49152\n127.0.0.1:49153\n",
            "127.0.0.1:70000\n",
        )
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt), patch.object(
                runner,
                "_run",
                return_value=subprocess.CompletedProcess(
                    ["docker", "port"],
                    0,
                    stdout=receipt,
                    stderr="",
                ),
            ):
                with self.assertRaisesRegex(
                    runner.RunnerError,
                    "RUNTIME_LOOPBACK_PORT_INVALID",
                ):
                    runner._published_loopback_port(Path("/usr/bin/docker"), "app", 8082)

    def test_host_probe_does_not_depend_on_tools_inside_the_image(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                payload = json.dumps({"status": "UP", "service": "test-service"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(runner.PORTS, {"test": server.server_port}, clear=True):
                runner._probe_loopback(
                    server.server_port,
                    "test-service",
                    path="/health",
                    timeout=1,
                )
                with self.assertRaisesRegex(
                    runner.RunnerError,
                    "RUNTIME_HEALTH_IDENTITY_TIMEOUT",
                ):
                    runner._probe_loopback(
                        server.server_port,
                        "wrong-service",
                        path="/health",
                        timeout=0.05,
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_workspace_confinement_and_exact_dockerfile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-runner-") as temporary:
            workspace = Path(temporary).resolve()
            target = workspace / "python"
            target.mkdir()
            (target / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            resolved, exact_target = runner._validated_workspace(str(workspace), "python")
            self.assertEqual(workspace, resolved)
            self.assertEqual(target, exact_target)
            with self.assertRaisesRegex(runner.RunnerError, "TARGET_DOCKERFILE_MISSING"):
                runner._validated_workspace(str(workspace), "java")

    def test_rejects_unallowlisted_engine_and_invalid_identifiers(self) -> None:
        with self.assertRaisesRegex(runner.RunnerError, "CONTAINER_ENGINE_NOT_ALLOWLISTED"):
            runner._engine_kind(Path("/usr/bin/sh"))
        with self.assertRaisesRegex(runner.RunnerError, "JOB_ID_INVALID"):
            runner._container_name("../../escape", "python")

    def test_build_egress_requires_exact_approval_labels(self) -> None:
        runner._validate_build_network(Path("/usr/bin/docker"), "none")
        with patch.object(
            runner,
            "_run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"io.elmos.network-purpose":"approved-build-egress","io.elmos.approved":"true"}',
                stderr="",
            ),
        ):
            runner._validate_build_network(Path("/usr/bin/docker"), "elmos-build-egress")
        with patch.object(
            runner,
            "_run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"io.elmos.network-purpose":"approved-build-egress"}',
                stderr="",
            ),
        ):
            with self.assertRaisesRegex(runner.RunnerError, "BUILD_NETWORK_NOT_APPROVED"):
                runner._validate_build_network(Path("/usr/bin/docker"), "elmos-build-egress")

    def test_toolchain_image_inventory_requires_digest_pins(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-images-") as temporary:
            target = Path(temporary)
            (target / "Dockerfile").write_text(
                "FROM example.invalid/build@sha256:" + ("a" * 64) + " AS build\n"
                "FROM scratch\n",
                encoding="utf-8",
            )
            self.assertEqual(
                runner._required_images(target),
                ("example.invalid/build@sha256:" + ("a" * 64),),
            )
            (target / "Dockerfile").write_text("FROM example.invalid/build:latest\n", encoding="utf-8")
            with self.assertRaisesRegex(runner.RunnerError, "TOOLCHAIN_IMAGE_NOT_IMMUTABLE"):
                runner._required_images(target)

    def test_offline_diagnosis_reports_missing_exact_toolchain_images(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-diagnose-") as temporary:
            workspace = Path(temporary)
            target = workspace / "python"
            target.mkdir()
            image = "example.invalid/python@sha256:" + ("b" * 64)
            (target / "Dockerfile").write_text(f"FROM {image}\n", encoding="utf-8")
            arguments = type(
                "Arguments",
                (),
                {
                    "engine": "/usr/bin/docker",
                    "workspace": str(workspace),
                    "language": "python",
                    "build_network": "none",
                },
            )()
            with (
                patch.object(runner, "_preflight", return_value={"status": "READY"}),
                patch.object(runner, "_validate_build_network"),
                patch.object(runner, "_image_cache_status", return_value=(image,)),
                self.assertRaisesRegex(
                    runner.RunnerError,
                    "TOOLCHAIN_IMAGES_NOT_AVAILABLE_OFFLINE",
                ),
            ):
                runner._diagnose(arguments)

    def test_diagnosis_distinguishes_approved_pull_from_cached_images(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-diagnose-") as temporary:
            workspace = Path(temporary)
            target = workspace / "go"
            target.mkdir()
            image = "example.invalid/go@sha256:" + ("c" * 64)
            (target / "Dockerfile").write_text(f"FROM {image}\n", encoding="utf-8")
            arguments = type(
                "Arguments",
                (),
                {
                    "engine": "/usr/bin/docker",
                    "workspace": str(workspace),
                    "language": "go",
                    "build_network": "elmos-build-egress",
                },
            )()
            with (
                patch.object(
                    runner,
                    "_preflight",
                    return_value={"status": "READY", "engine": "docker", "rootless": True},
                ),
                patch.object(runner, "_validate_build_network"),
                patch.object(runner, "_image_cache_status", return_value=(image,)),
            ):
                result = runner._diagnose(arguments)
            self.assertEqual(result["toolchain_cache"], "APPROVED_BUILD_EGRESS_REQUIRED")
            self.assertEqual(result["missing_images"], [image])

    def test_runtime_lease_is_bounded_to_ten_minutes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-lease-") as temporary:
            workspace = Path(temporary)
            target = workspace / "python"
            target.mkdir()
            arguments = type(
                "Arguments",
                (),
                {
                    "engine": "/usr/bin/docker",
                    "workspace": str(workspace),
                    "language": "python",
                    "port": 8082,
                    "job_id": "123e4567-e89b-42d3-a456-426614174000",
                    "service": "lease-service",
                    "state": str(workspace.parent / "runtime-state"),
                    "persistence": "in-memory",
                    "auth_mode": "none",
                    "build_network": "none",
                    "lease_seconds": 601,
                },
            )()
            with (
                patch.object(runner, "_diagnose"),
                patch.object(runner, "_validated_workspace", return_value=(workspace, target)),
                patch.object(runner, "_state_directory", return_value=workspace.parent),
                patch.object(runner, "_ensure_runtime_absent"),
                patch.object(runner, "_resource_labels", return_value=None),
                self.assertRaisesRegex(runner.RunnerError, "RUNTIME_LEASE_INVALID"),
            ):
                runner._start(arguments)

    def test_status_cleans_an_expired_rootless_runtime(self) -> None:
        arguments = type(
            "Arguments",
            (),
            {
                "engine": "/usr/bin/docker",
                "language": "python",
                "job_id": "123e4567-e89b-42d3-a456-426614174000",
                "state": None,
                "lease_id": "a" * 32,
            },
        )()
        state = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"Running":true,"ExitCode":0}', stderr="",
        )
        labels = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({
                "io.elmos.service": "lease-service",
                "io.elmos.port": "8082",
                "io.elmos.persistence": "in-memory",
                "io.elmos.lease-seconds": "600",
                "io.elmos.lease-started-epoch": str(int(time.time()) - 601),
                "io.elmos.expires-epoch": str(int(time.time()) - 1),
                "io.elmos.lease-id": "a" * 32,
                "io.elmos.job": "123e4567-e89b-42d3-a456-426614174000",
                "io.elmos.language": "python",
            }),
            stderr="",
        )
        with (
            patch.object(runner, "_preflight"),
            patch.object(runner, "_run", side_effect=[state, labels]),
            patch.object(
                runner,
                "_read_lease_marker",
                return_value={
                    "job_id": arguments.job_id,
                    "language": arguments.language,
                    "lease_id": arguments.lease_id,
                    "phase": "RUNNING",
                    "lease_started_epoch": int(time.time()) - 601,
                    "lease_expires_epoch": int(time.time()) - 1,
                },
            ),
            patch.object(
                runner,
                "_stop_locked",
                return_value={"status": "STOPPED", "container_name": "expired"},
            ) as stop,
        ):
            result = runner._status_locked(arguments)
        self.assertEqual(result["status"], "EXPIRED")
        self.assertEqual(result["health"], "lease-expired-cleaned")
        stop.assert_called_once_with(arguments)

    def test_slow_build_and_health_probe_do_not_consume_the_runtime_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-build-lease-") as temporary:
            workspace = Path(temporary)
            target = workspace / "python"
            target.mkdir()
            arguments = type(
                "Arguments",
                (),
                {
                    "engine": "/usr/bin/docker",
                    "workspace": str(workspace),
                    "language": "python",
                    "port": 8082,
                    "job_id": "123e4567-e89b-42d3-a456-426614174000",
                    "service": "lease-service",
                    "state": str(workspace.parent / "runtime-state"),
                    "persistence": "in-memory",
                    "auth_mode": "none",
                    "build_network": "none",
                    "lease_seconds": 600,
                },
            )()
            clock = {"now": 1_000}
            commands: list[list[str]] = []

            def run(command: list[str], *, timeout: int = 1_200) -> subprocess.CompletedProcess[str]:
                del timeout
                commands.append(command)
                if "build" in command:
                    clock["now"] += 3_600
                stdout = (
                    "127.0.0.1:49152\n"
                    if "port" in command
                    else "container-id\n" if "run" in command else ""
                )
                return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

            def probe(*_: object, **__: object) -> None:
                clock["now"] += 60

            with (
                patch.object(runner, "_diagnose"),
                patch.object(runner, "_validated_workspace", return_value=(workspace, target)),
                patch.object(runner, "_state_directory", return_value=workspace.parent),
                patch.object(runner, "_ensure_runtime_absent"),
                patch.object(runner, "_resource_labels", return_value=None),
                patch.object(runner, "_write_lease_marker") as write_marker,
                patch.object(runner, "_create_internal_network"),
                patch.object(runner, "_authentication_arguments", return_value=[]),
                patch.object(runner, "_start_expiry_watchdog", return_value=4321),
                patch.object(runner, "_probe_loopback", side_effect=probe),
                patch.object(runner, "_run", side_effect=run),
                patch.object(runner.secrets, "token_hex", return_value="a" * 32),
                patch.object(runner.time, "time", side_effect=lambda: clock["now"]),
            ):
                result = runner._start(arguments)

        start_command = next(command for command in commands if "run" in command)
        self.assertNotIn("io.elmos.lease-started-epoch=4600", start_command)
        self.assertNotIn("io.elmos.expires-epoch=5200", start_command)
        self.assertIn(f"io.elmos.lease-id={'a' * 32}", start_command)
        self.assertEqual(result["lease_started_epoch"], 4_661)
        self.assertEqual(result["lease_expires_epoch"], 5_261)
        self.assertEqual(result["lease_seconds"], 600)
        self.assertEqual(result["lease_id"], "a" * 32)
        self.assertEqual(result["watchdog_pid"], 4_321)
        self.assertEqual(result["host_port"], 49_152)
        final_marker = write_marker.call_args_list[-1]
        self.assertEqual(final_marker.kwargs["lease_started_epoch"], 4_661)
        self.assertEqual(final_marker.kwargs["lease_expires_epoch"], 5_261)

    def test_expiry_watchdog_is_detached_and_bound_to_exact_runtime(self) -> None:
        process = type("Process", (), {"pid": 4_321})()
        with patch.object(runner.subprocess, "Popen", return_value=process) as popen:
            pid = runner._start_expiry_watchdog(
                Path("/usr/bin/docker"),
                "python",
                "123e4567-e89b-42d3-a456-426614174000",
                1_700_000_600,
                "a" * 32,
                Path("/private/tmp/elmos-runtime-state"),
            )
        self.assertEqual(pid, 4_321)
        command = popen.call_args.args[0]
        self.assertEqual(command[2], "expire")
        self.assertIn("/usr/bin/docker", command)
        self.assertIn("123e4567-e89b-42d3-a456-426614174000", command)
        self.assertIn("1700000600", command)
        self.assertIn("a" * 32, command)
        self.assertIn("/private/tmp/elmos-runtime-state", command)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertTrue(popen.call_args.kwargs["close_fds"])

    def test_old_watchdog_cannot_stop_a_new_runtime_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-rootless-old-watchdog-") as temporary:
            arguments = type(
                "Arguments",
                (),
                {
                    "engine": "/usr/bin/docker",
                    "language": "python",
                    "job_id": "123e4567-e89b-42d3-a456-426614174000",
                    "state": str(Path(temporary) / "runtime-state"),
                    "lease_id": "a" * 32,
                },
            )()
            with (
                patch.object(runner, "_preflight"),
                patch.object(
                    runner,
                    "_read_lease_marker",
                    return_value={
                        "job_id": arguments.job_id,
                        "language": arguments.language,
                        "lease_id": "b" * 32,
                    },
                ),
                patch.object(runner, "_run") as run,
            ):
                result = runner._stop(arguments)
            self.assertEqual(result["status"], "SUPERSEDED")
            run.assert_not_called()

    def test_expiry_reports_superseded_without_relabeling_it_expired(self) -> None:
        arguments = type(
            "Arguments",
            (),
            {
                "expires_epoch": 1_000,
                "lease_id": "a" * 32,
                "state": "/private/tmp/elmos-runtime-state",
            },
        )()
        with (
            patch.object(runner.time, "time", return_value=1_000),
            patch.object(runner, "_runtime_operation_lock", return_value=nullcontext()),
            patch.object(
                runner,
                "_stop_locked",
                return_value={"status": "SUPERSEDED", "container_name": "new-runtime"},
            ) as stop,
        ):
            result = runner._expire(arguments)
        self.assertEqual(result["status"], "SUPERSEDED")
        stop.assert_called_once_with(arguments)


if __name__ == "__main__":
    unittest.main()
