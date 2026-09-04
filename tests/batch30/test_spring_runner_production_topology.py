from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = (
    ROOT / "deploy/production/runner/validate_spring_runner_topology.py"
)
SPEC = importlib.util.spec_from_file_location("spring_runner_topology", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
TOPOLOGY = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOPOLOGY
SPEC.loader.exec_module(TOPOLOGY)


class SpringRunnerProductionTopologyTests(TestCase):
    def test_repository_static_contract_is_ready_only_for_external_gate(self) -> None:
        self.assertEqual([], TOPOLOGY.validate_static())

    def test_host_mode_refuses_ambient_environment_without_data_file(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--check-host", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(1, completed.returncode)
        self.assertEqual("ENVIRONMENT_FILE_REQUIRED", payload["mode"])
        self.assertTrue(any("shell sourcing is forbidden" in item for item in payload["errors"]))

    def test_runner_is_separate_and_never_receives_engine_hmac(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        runner = TOPOLOGY.read_yaml(paths.runner_compose)
        application = TOPOLOGY.read_yaml(paths.application_compose)
        serialized_runner = paths.runner_compose.read_text(encoding="utf-8")

        self.assertNotIn("ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH", serialized_runner)
        self.assertIn(
            "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH",
            paths.application_spring_overlay.read_text(encoding="utf-8"),
        )
        socket_holders = [
            name
            for name, service in runner["services"].items()
            if TOPOLOGY.volume_for_target(service, "/run/docker.sock")
        ]
        self.assertEqual(["spring-runner-broker"], socket_holders)
        self.assertIsNone(
            TOPOLOGY.volume_for_target(
                application["services"]["java-engine-worker"],
                "/run/docker.sock",
            )
        )

    def test_non_spring_baseline_does_not_require_engine_secret_file(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        application = TOPOLOGY.read_yaml(paths.application_compose)
        overlay = TOPOLOGY.read_yaml(paths.application_spring_overlay)
        target = "/run/secrets/elmos-spring-engine-hmac"

        self.assertIsNone(
            TOPOLOGY.volume_for_target(application["services"]["web-console"], target)
        )
        self.assertEqual(
            "${ELMOS_SPRING_ENGINE_AUTH_ENABLED:-false}",
            application["services"]["web-console"]["environment"][
                "ELMOS_SPRING_ENGINE_AUTH_ENABLED"
            ],
        )
        web_mount = TOPOLOGY.volume_for_target(
            overlay["services"]["web-console"], target
        )
        worker_mount = TOPOLOGY.volume_for_target(
            overlay["services"]["java-engine-worker"], target
        )
        self.assertIsNotNone(web_mount)
        self.assertIsNotNone(worker_mount)
        assert web_mount is not None and worker_mount is not None
        self.assertEqual(web_mount["source"], worker_mount["source"])
        self.assertTrue(
            web_mount["source"].startswith(
                "${ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH:?"
            )
        )
        self.assertEqual(
            {"condition": "service_started"},
            overlay["services"]["web-console"]["depends_on"][
                "java-engine-worker"
            ],
        )
        self.assertEqual(
            ["spring"],
            application["services"]["java-engine-worker"]["profiles"],
        )

    def test_static_contract_rejects_overlay_without_worker_dependency(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        with tempfile.TemporaryDirectory(prefix="spring-app-overlay-") as directory:
            mutated = Path(directory) / "spring-application.yml"
            source = paths.application_spring_overlay.read_text(encoding="utf-8")
            marker = (
                "    depends_on:\n"
                "      java-engine-worker: { condition: service_started }\n"
            )
            self.assertIn(marker, source)
            mutated.write_text(source.replace(marker, "", 1), encoding="utf-8")
            errors = TOPOLOGY.validate_static(
                TOPOLOGY.ContractPaths(application_spring_overlay=mutated)
            )

        self.assertTrue(
            any(
                "must depend on the profile-gated Java worker" in item
                for item in errors
            ),
            errors,
        )

    def test_runner_services_do_not_receive_host_preflight_environment(self) -> None:
        runner = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)

        for name, service in runner["services"].items():
            with self.subTest(service=name):
                self.assertNotIn("env_file", service)

    def test_replay_state_uses_required_role_specific_host_binds(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        runner = TOPOLOGY.read_yaml(paths.runner_compose)
        application = TOPOLOGY.read_yaml(paths.application_compose)
        overlay = TOPOLOGY.read_yaml(paths.application_spring_overlay)
        broker = runner["services"]["spring-runner-broker"]
        runner_target = "/var/lib/elmos/spring-auth-replay"
        runner_mount = TOPOLOGY.volume_for_target(broker, runner_target)
        self.assertIsNotNone(runner_mount)
        assert runner_mount is not None
        self.assertTrue(
            runner_mount["source"].startswith(
                "${ELMOS_SPRING_RUNNER_REPLAY_HOST_PATH:?"
            )
        )
        self.assertFalse(runner_mount["read_only"])
        self.assertIs(False, runner_mount["bind"]["create_host_path"])
        self.assertEqual(
            {
                "ELMOS_SPRING_RUNTIME_REPLAY_ROOT": runner_target + "/runtime",
                "ELMOS_SPRING_VERIFIER_REPLAY_ROOT": runner_target + "/verifier",
                "ELMOS_SPRING_TRANSFORMER_REPLAY_ROOT": runner_target + "/transformer",
            },
            {
                key: broker["environment"][key]
                for key in (
                    "ELMOS_SPRING_RUNTIME_REPLAY_ROOT",
                    "ELMOS_SPRING_VERIFIER_REPLAY_ROOT",
                    "ELMOS_SPRING_TRANSFORMER_REPLAY_ROOT",
                )
            },
        )

        engine_target = "/var/lib/elmos/spring-engine-auth-replay"
        worker = application["services"]["java-engine-worker"]
        self.assertEqual(
            engine_target,
            worker["environment"]["ELMOS_SPRING_ENGINE_AUTH_REPLAY_ROOT"],
        )
        engine_mount = TOPOLOGY.volume_for_target(
            overlay["services"]["java-engine-worker"], engine_target
        )
        self.assertIsNotNone(engine_mount)
        assert engine_mount is not None
        self.assertTrue(
            engine_mount["source"].startswith(
                "${ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH:?"
            )
        )
        self.assertFalse(engine_mount["read_only"])
        self.assertIs(False, engine_mount["bind"]["create_host_path"])

    def test_application_env_excludes_runner_security_domain_configuration(self) -> None:
        environment = TOPOLOGY.ContractPaths().environment_example.read_text(
            encoding="utf-8"
        )
        application_keys = {
            line.split("=", 1)[0]
            for line in environment.splitlines()
            if line and not line.startswith("#") and "=" in line
        }
        shared_contract_keys = {
            "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
            "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
        }

        self.assertEqual(
            set(),
            (TOPOLOGY.RUNNER_ENVIRONMENT_ALLOWLIST - shared_contract_keys)
            & application_keys,
        )

    def test_spring_worker_clears_path_overrides_and_excludes_broad_env_file(self) -> None:
        application = TOPOLOGY.read_yaml(
            TOPOLOGY.ContractPaths().application_compose
        )
        worker = application["services"]["java-engine-worker"]

        self.assertEqual([], worker["env_file"])
        for name in TOPOLOGY.WORKER_PATH_OVERRIDE_ENVIRONMENTS:
            with self.subTest(name=name):
                self.assertEqual("", worker["environment"][name])

    def test_static_contract_rejects_servlet_path_override_or_broad_env_file(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        cases = {
            "servlet-path": (
                '      SERVER_SERVLET_CONTEXT_PATH: ""',
                '      SERVER_SERVLET_CONTEXT_PATH: "/hidden"',
                "must clear dangerous path override SERVER_SERVLET_CONTEXT_PATH",
            ),
            "broad-env-file": (
                "    env_file: []",
                '    env_file: ["${ELMOS_ENV_FILE:-../elmos-commercial.env}"]',
                "must not receive the broad application env_file",
            ),
        }
        for label, (before, after, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"spring-worker-{label}-"
            ) as directory:
                mutated = Path(directory) / "application.yml"
                source = paths.application_compose.read_text(encoding="utf-8")
                self.assertIn(before, source)
                mutated.write_text(source.replace(before, after, 1), encoding="utf-8")
                errors = TOPOLOGY.validate_static(
                    TOPOLOGY.ContractPaths(application_compose=mutated)
                )
            self.assertTrue(any(expected in item for item in errors), errors)

    def test_static_contract_rejects_runner_service_env_file_injection(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        with tempfile.TemporaryDirectory(
            prefix="spring-runner-env-injection-"
        ) as directory:
            mutated = Path(directory) / "runner.yml"
            source = paths.runner_compose.read_text(encoding="utf-8")
            marker = '    image: "${ELMOS_SPRING_INGRESS_IMAGE:?'
            self.assertIn(marker, source)
            mutated.write_text(
                source.replace(marker, "    env_file: [runner.env]\n" + marker, 1),
                encoding="utf-8",
            )
            errors = TOPOLOGY.validate_static(
                TOPOLOGY.ContractPaths(runner_compose=mutated)
            )

        self.assertTrue(
            any(
                "must not receive the host-only Runner environment file" in item
                for item in errors
            ),
            errors,
        )

    def test_ingress_and_broker_networks_are_internal_default_deny(self) -> None:
        runner = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)

        self.assertIs(True, runner["networks"]["spring-runner-edge"]["internal"])
        self.assertIs(True, runner["networks"]["spring-runner-broker"]["internal"])

    def test_ingress_exposes_only_exact_hmac_post_routes(self) -> None:
        config = TOPOLOGY.ContractPaths().ingress_config.read_text(encoding="utf-8")
        errors: list[str] = []
        TOPOLOGY.validate_ingress(errors, config)
        self.assertEqual([], errors)
        self.assertEqual(3, config.count("location = /internal/v1/spring-"))
        self.assertNotIn("listen 8082", config)

    def test_ingress_body_limits_match_controller_allocation_bounds(self) -> None:
        config = TOPOLOGY.ContractPaths().ingress_config.read_text(encoding="utf-8")

        self.assertIn("client_max_body_size 1k;", config)
        for path, limit in TOPOLOGY.BROKER_BODY_LIMITS.items():
            with self.subTest(path=path):
                location = TOPOLOGY.re.search(
                    rf"location = {TOPOLOGY.re.escape(path)} \{{(?P<body>.*?)\n    \}}",
                    config,
                    flags=TOPOLOGY.re.DOTALL,
                )
                self.assertIsNotNone(location)
                assert location is not None
                self.assertIn(f"client_max_body_size {limit};", location.group("body"))

        weakened = config.replace("client_max_body_size 64k;", "client_max_body_size 8m;", 1)
        errors: list[str] = []
        TOPOLOGY.validate_ingress(errors, weakened)
        self.assertTrue(
            any("request-body limit must remain 64k" in item for item in errors),
            errors,
        )

    def test_static_contract_rejects_non_internal_ingress_or_broker_network(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        cases = {
            "edge": (
                "    name: elmos-spring-runner-edge\n    driver: bridge\n    internal: true",
                "ingress edge network must be internal",
            ),
            "broker": (
                "    name: elmos-spring-runner-broker\n    driver: bridge\n    internal: true",
                "broker network must be internal",
            ),
        }
        for label, (marker, expected) in cases.items():
            with self.subTest(network=label), tempfile.TemporaryDirectory(
                prefix="spring-runner-static-"
            ) as directory:
                mutated = Path(directory) / "runner.yml"
                source = paths.runner_compose.read_text(encoding="utf-8")
                self.assertIn(marker, source)
                mutated.write_text(
                    source.replace(marker, marker.replace("true", "false"), 1),
                    encoding="utf-8",
                )
                custom = TOPOLOGY.ContractPaths(
                    runner_compose=mutated,
                    application_compose=paths.application_compose,
                    ingress_config=paths.ingress_config,
                    environment_example=paths.environment_example,
                    rootless_readme=paths.rootless_readme,
                    production_readme=paths.production_readme,
                )
                errors = TOPOLOGY.validate_static(custom)
            self.assertTrue(any(expected in item for item in errors), errors)

    def test_owner_only_secret_rejects_world_readable_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-secret-") as directory:
            secret = Path(directory).resolve() / "secret"
            secret.write_bytes(b"x" * 32)
            secret.chmod(0o444)
            errors: list[str] = []
            TOPOLOGY.owner_only_file(
                errors,
                secret,
                label="test secret",
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                minimum_size=32,
            )
        self.assertTrue(any("mode must be 0400 or 0600" in item for item in errors))

    def test_hmac_secret_rejects_ascii_and_unicode_boundary_whitespace(self) -> None:
        for suffix in (b"\n", "\u00a0".encode("utf-8")):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory(
                prefix="spring-runner-hmac-whitespace-"
            ) as directory:
                secret = Path(directory).resolve() / "secret"
                secret.write_bytes(b"x" * 32 + suffix)
                secret.chmod(0o600)
                errors: list[str] = []
                record = TOPOLOGY.owner_only_file(
                    errors,
                    secret,
                    label="test HMAC",
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                    minimum_size=32,
                    canonical_hmac_secret=True,
                )
            self.assertIsNone(record)
            self.assertTrue(any("HMAC whitespace" in item for item in errors), errors)

    def test_protected_replay_directory_rejects_permissive_mode_and_symlink_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-replay-") as directory:
            root = Path(directory).resolve()
            permissive = root / "permissive"
            permissive.mkdir(mode=0o755)
            permissive_errors: list[str] = []
            TOPOLOGY.protected_directory(
                permissive_errors,
                permissive,
                label="replay",
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

            real_parent = root / "real"
            real_parent.mkdir(mode=0o700)
            replay = real_parent / "replay"
            replay.mkdir(mode=0o700)
            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            symlink_errors: list[str] = []
            TOPOLOGY.protected_directory(
                symlink_errors,
                linked_parent / "replay",
                label="replay",
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

        self.assertTrue(any("mode must equal 0700" in item for item in permissive_errors))
        self.assertTrue(any("symbolic-link" in item for item in symlink_errors))

    def test_environment_file_is_inert_allowlisted_data_with_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-env-") as directory:
            parent = Path(directory).resolve()
            parent.chmod(0o700)
            path = parent / "runner.env"
            values = self.valid_environment_values(path)
            original_image = values["ELMOS_SPRING_INGRESS_IMAGE"]
            replacement = f"registry.example/ingress@sha256:{'f' * 64}"
            path.write_text(
                "\n".join(f"{name}={values[name]}" for name in sorted(values)) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)

            parsed, errors = TOPOLOGY.load_environment_file(
                path,
                {"ELMOS_SPRING_INGRESS_IMAGE": replacement},
            )

        self.assertEqual([], errors)
        self.assertNotEqual(original_image, replacement)
        self.assertEqual(replacement, parsed["ELMOS_SPRING_INGRESS_IMAGE"])

    def test_environment_file_rejects_unknown_duplicate_interpolation_and_command(self) -> None:
        cases = {
            "unknown": ("ELMOS_UNDECLARED_RUNNER_FLAG=true", "unknown variable"),
            "duplicate": ("ELMOS_ROOTLESS_UID=123", "duplicates ELMOS_ROOTLESS_UID"),
            "interpolation": (
                "ELMOS_SPRING_RUNNER_DATABASE_PASSWORD=${SECRET}",
                "unsafe or empty value",
            ),
            "command": (
                "ELMOS_SPRING_RUNNER_DATABASE_PASSWORD=$(touch/tmp/pwned)",
                "unsafe or empty value",
            ),
        }
        for label, (bad_line, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"spring-runner-env-{label}-"
            ) as directory:
                parent = Path(directory).resolve()
                parent.chmod(0o700)
                path = parent / "runner.env"
                values = self.valid_environment_values(path)
                lines = [f"{name}={values[name]}" for name in sorted(values)]
                if label in {"interpolation", "command"}:
                    key = "ELMOS_SPRING_RUNNER_DATABASE_PASSWORD"
                    lines = [line for line in lines if not line.startswith(key + "=")]
                lines.append(bad_line)
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                path.chmod(0o600)
                _, errors = TOPOLOGY.load_environment_file(path, {})
            self.assertTrue(any(expected in item for item in errors), errors)

    def test_environment_file_rejects_symlink_and_permissive_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-env-files-") as directory:
            parent = Path(directory).resolve()
            parent.chmod(0o700)
            real = parent / "real.env"
            values = self.valid_environment_values(real)
            real.write_text(
                "\n".join(f"{name}={values[name]}" for name in sorted(values)) + "\n",
                encoding="utf-8",
            )
            real.chmod(0o644)
            _, permissive_errors = TOPOLOGY.load_environment_file(real, {})

            link = parent / "linked.env"
            link.symlink_to(real)
            _, symlink_errors = TOPOLOGY.load_environment_file(link, {})

        self.assertTrue(any("mode must be 0400 or 0600" in item for item in permissive_errors))
        self.assertTrue(any("symbolic link" in item for item in symlink_errors))

    def test_environment_file_rejects_symlink_parent_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-env-path-") as directory:
            root = Path(directory).resolve()
            real_parent = root / "real"
            real_parent.mkdir(mode=0o700)
            real = real_parent / "runner.env"
            values = self.valid_environment_values(real)
            real.write_text(
                "\n".join(f"{name}={values[name]}" for name in sorted(values)) + "\n",
                encoding="utf-8",
            )
            real.chmod(0o600)

            linked_parent = root / "linked"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            _, parent_errors = TOPOLOGY.load_environment_file(
                linked_parent / "runner.env", {}
            )

            hardlink = real_parent / "runner-hardlink.env"
            os.link(real, hardlink)
            _, hardlink_errors = TOPOLOGY.load_environment_file(hardlink, {})

        self.assertTrue(any("symbolic-link parent" in item for item in parent_errors))
        self.assertTrue(any("hard-linked" in item for item in hardlink_errors))

    def test_environment_file_rejects_metadata_race(self) -> None:
        real_fstat = TOPOLOGY.os.fstat
        calls = 0

        def changing_fstat(descriptor: int):
            nonlocal calls
            calls += 1
            details = real_fstat(descriptor)
            if calls == 2:
                fields = list(details)
                fields[1] += 1
                return os.stat_result(fields)
            return details

        with tempfile.TemporaryDirectory(prefix="spring-runner-env-race-") as directory:
            parent = Path(directory).resolve()
            parent.chmod(0o700)
            path = parent / "runner.env"
            values = self.valid_environment_values(path)
            path.write_text(
                "\n".join(f"{name}={values[name]}" for name in sorted(values)) + "\n",
                encoding="utf-8",
            )
            path.chmod(0o600)
            with mock.patch.object(TOPOLOGY.os, "fstat", side_effect=changing_fstat):
                parsed, errors = TOPOLOGY.load_environment_file(path, {})

        self.assertEqual({}, parsed)
        self.assertTrue(any("changed while it was being read" in item for item in errors))

    @staticmethod
    def valid_environment_values(path: Path) -> dict[str, str]:
        values = {name: "VALUE" for name in TOPOLOGY.RUNNER_ENVIRONMENT_ALLOWLIST}
        for index, name in enumerate(TOPOLOGY.IMAGE_ENVIRONMENTS):
            values[name] = f"registry.example/image-{index}@sha256:{str(index + 1) * 64}"
        for index, name in enumerate(TOPOLOGY.CHILD_IMAGE_DIGEST_ENVIRONMENTS):
            values[name] = f"sha256:{str(index + 4) * 64}"
        values.update(
            {
                "ELMOS_ROOTLESS_UID": str(os.getuid()),
                "ELMOS_ROOTLESS_GID": str(os.getgid()),
                "ELMOS_SPRING_BROKER_SECRET_MAPPED_UID": str(os.getuid()),
                "ELMOS_SPRING_BROKER_SECRET_MAPPED_GID": str(os.getgid()),
                "ELMOS_SPRING_INGRESS_SECRET_MAPPED_UID": str(os.getuid()),
                "ELMOS_SPRING_INGRESS_SECRET_MAPPED_GID": str(os.getgid()),
                "ELMOS_SPRING_RUNNER_ENV_FILE": str(path),
                "ELMOS_SPRING_RUNNER_HTTPS_PORT": "8443",
                "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS": "127.0.0.1",
                "ELMOS_SPRING_RUNNER_DATABASE_URL": "jdbc:postgresql://db:5432/elmos?sslmode=require",
                "ELMOS_SPRING_RUNNER_DATABASE_USER": "elmos_runner",
                "ELMOS_SPRING_RUNNER_DATABASE_PASSWORD": "base64safevalue1234567890+/=",
            }
        )
        return values


if __name__ == "__main__":
    main()
