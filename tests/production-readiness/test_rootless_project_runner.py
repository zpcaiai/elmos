from __future__ import annotations

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import tempfile
import threading
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


if __name__ == "__main__":
    unittest.main()
