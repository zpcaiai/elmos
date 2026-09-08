from __future__ import annotations

import copy
import importlib.util
import json
import os
import socket
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

    def test_host_mode_requires_independent_owner_binding_and_root_observer(self) -> None:
        missing_binding = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--check-host",
                "--environment-file",
                "/does/not/exist/runner.env",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(missing_binding.stdout)
        self.assertEqual(1, missing_binding.returncode)
        self.assertEqual("ROOTLESS_OWNER_BINDING_REQUIRED", payload["mode"])

        if os.geteuid() != 0:
            unprivileged = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR_PATH),
                    "--check-host",
                    "--environment-file",
                    "/does/not/exist/runner.env",
                    "--rootless-owner-uid",
                    str(os.getuid()),
                    "--rootless-owner-gid",
                    str(os.getgid()),
                    "--json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            payload = json.loads(unprivileged.stdout)
            self.assertEqual(1, unprivileged.returncode)
            self.assertEqual("PRIVILEGED_OBSERVER_REQUIRED", payload["mode"])

    def test_docker_inspection_uses_fixed_cli_and_sanitized_environment(self) -> None:
        command = TOPOLOGY.docker_command(
            Path("/run/user/1001/docker.sock"), "info", "--format", "{{json .}}"
        )
        self.assertEqual("/usr/bin/docker", command[0])
        self.assertNotIn("docker", command[:1])

        completed = subprocess.CompletedProcess(command, 0, stdout='{"ok":true}\n', stderr="")
        with mock.patch.object(
            TOPOLOGY, "validate_trusted_system_executable"
        ) as trusted, mock.patch.object(
            TOPOLOGY.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual({"ok": True}, TOPOLOGY.command_json(command))
        trusted.assert_called_once_with(
            TOPOLOGY.TRUSTED_DOCKER_CLI, label="Docker CLI"
        )
        self.assertEqual(
            {
                "HOME": "/nonexistent",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
            },
            run.call_args.kwargs["env"],
        )
        with self.assertRaisesRegex(RuntimeError, "fixed trusted"):
            TOPOLOGY.command_json(["docker", "info"])

    def test_daemon_and_socket_binding_reject_identity_switch(self) -> None:
        socket_identity = (1, 2, 3, 4, 5, 1, 6, 7)
        changed_socket = (1, 99, 3, 4, 5, 1, 6, 8)
        errors: list[str] = []
        with mock.patch.object(
            TOPOLOGY,
            "trusted_unix_socket",
            side_effect=(socket_identity, changed_socket),
        ), mock.patch.object(
            TOPOLOGY, "docker_daemon_identity", return_value=("ID=daemon",)
        ):
            binding = TOPOLOGY.observe_docker_endpoint(
                errors,
                Path("/run/user/1001/docker.sock"),
                expected_uid=1001,
                expected_gid=1001,
            )
        self.assertIsNone(binding)
        self.assertTrue(any("socket changed" in item for item in errors), errors)

    def test_running_rejects_endpoint_switch_after_host_phase(self) -> None:
        socket_identity = (1, 2, 3, 1001, 1001, 1, 4, 5)
        host_binding = TOPOLOGY.DockerEndpointBinding(
            socket_identity, ("ID=daemon-a",)
        )
        changed_binding = TOPOLOGY.DockerEndpointBinding(
            socket_identity, ("ID=daemon-b",)
        )
        control_identity = ("Id=control",)

        def host(
            _paths,
            _environment,
            *,
            _docker_binding_out,
            _control_network_out,
        ):
            _docker_binding_out.append(host_binding)
            _control_network_out.append(control_identity)
            return []

        environment = self.valid_environment_values(Path("/secure/runner.env"))
        environment["ELMOS_ROOTLESS_DOCKER_SOCKET"] = "/run/user/1001/docker.sock"
        with mock.patch.object(TOPOLOGY, "validate_host", side_effect=host), mock.patch.object(
            TOPOLOGY, "observe_docker_endpoint", return_value=changed_binding
        ):
            errors = TOPOLOGY.validate_running(environment=environment)
        self.assertTrue(
            any("between host and running validation" in item for item in errors),
            errors,
        )

    def test_daemon_identity_binds_rootless_installation_fields(self) -> None:
        record = {
            "ID": "daemon-a",
            "Name": "runner-host",
            "DockerRootDir": "/home/runner/.local/share/docker",
            "Driver": "overlay2",
            "ServerVersion": "28.0.0",
            "CgroupDriver": "systemd",
            "CgroupVersion": "2",
            "OperatingSystem": "Linux",
            "OSType": "linux",
            "Architecture": "x86_64",
            "KernelVersion": "6.8.0",
            "SecurityOptions": ["name=seccomp,profile=builtin", "name=rootless"],
        }
        with mock.patch.object(TOPOLOGY, "command_json", return_value=record):
            first = TOPOLOGY.docker_daemon_identity(Path("/run/docker.sock"))
        with mock.patch.object(
            TOPOLOGY,
            "command_json",
            return_value={**record, "ServerVersion": "28.0.1"},
        ):
            second = TOPOLOGY.docker_daemon_identity(Path("/run/docker.sock"))
        self.assertNotEqual(first, second)
        with mock.patch.object(
            TOPOLOGY,
            "command_json",
            return_value={**record, "SecurityOptions": ["name=seccomp"]},
        ), self.assertRaisesRegex(ValueError, "name=rootless"):
            TOPOLOGY.docker_daemon_identity(Path("/run/docker.sock"))

    def test_network_identity_binds_id_policy_and_membership(self) -> None:
        record = {
            "Id": "a" * 64,
            "Name": "elmos-spring-runner-broker",
            "Created": "2026-09-05T00:00:00Z",
            "Scope": "local",
            "Driver": "bridge",
            "EnableIPv6": False,
            "Internal": True,
            "Attachable": False,
            "Ingress": False,
            "IPAM": {"Driver": "default", "Config": [{"Subnet": "172.30.0.0/24"}]},
            "Options": {},
            "Labels": {"io.elmos.network.default-deny": "true"},
            "Containers": {"b" * 64: {"Name": "spring-runner-broker"}},
        }
        baseline = TOPOLOGY.network_identity(record, label="broker")
        changed = copy.deepcopy(record)
        changed["Containers"]["c" * 64] = {"Name": "unexpected"}
        self.assertNotEqual(
            baseline, TOPOLOGY.network_identity(changed, label="broker")
        )
        missing = dict(record)
        missing.pop("Internal")
        with self.assertRaisesRegex(ValueError, "fields are incomplete"):
            TOPOLOGY.network_identity(missing, label="broker")

    def test_observer_contract_requires_exact_revision_digest_and_root(self) -> None:
        self.assertTrue(
            any(
                "40-character" in item
                for item in TOPOLOGY.validate_observer_execution(
                    revision="main", expected_digest="sha256:" + "a" * 64
                )
            )
        )
        errors = TOPOLOGY.validate_observer_execution(
            revision="a" * 40, expected_digest="invalid"
        )
        self.assertTrue(any("sha256" in item for item in errors), errors)

    def test_observer_bundle_mode_checks_immutable_root_without_runner_owner_args(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--check-observer-bundle",
                "--observer-revision",
                "a" * 40,
                "--observer-bundle-digest",
                "sha256:" + "b" * 64,
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(1, completed.returncode)
        self.assertEqual("OBSERVER_BUNDLE_REJECTED", payload["mode"])
        self.assertTrue(
            any("/opt/elmos-spring-gate" in item for item in payload["errors"]),
            payload,
        )
        self.assertFalse(
            any("rootless-owner" in item for item in payload["errors"]),
            payload,
        )

    def test_observer_bundle_digest_commits_every_file_byte(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-observer-") as directory:
            root = Path(directory).resolve()
            first = root / "first"
            second = root / "second"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            with mock.patch.object(TOPOLOGY, "ROOT", root), mock.patch.object(
                TOPOLOGY, "observer_bundle_files", return_value=(first, second)
            ):
                before = TOPOLOGY.observer_bundle_digest()
                second.write_bytes(b"three")
                after = TOPOLOGY.observer_bundle_digest()
        self.assertRegex(before, r"^sha256:[0-9a-f]{64}$")
        self.assertNotEqual(before, after)

    def test_show_observer_bundle_digest_mode_has_no_false_argument_conflict(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "--show-observer-bundle-digest"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertRegex(completed.stdout.strip(), r"^sha256:[0-9a-f]{64}$")

    def test_observer_bundle_covers_application_launch_gate_inputs(self) -> None:
        relative = {
            path.relative_to(TOPOLOGY.ROOT).as_posix()
            for path in TOPOLOGY.observer_bundle_files()
        }
        self.assertTrue(set(TOPOLOGY.APPLICATION_GATE_BUNDLE_PATHS) <= relative)

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
                (
                    "    # The Spring worker consumes only the explicit allowlist below and never\n"
                    "    # receives any service runtime env file.\n"
                    "    env_file: []"
                ),
                (
                    "    # The Spring worker consumes only the explicit allowlist below and never\n"
                    "    # receives any service runtime env file.\n"
                    '    env_file: ["${ELMOS_ENV_FILE:-../elmos-commercial.env}"]'
                ),
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

    def test_static_contract_rejects_process_environment_and_mount_expansion(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        source = paths.runner_compose.read_text(encoding="utf-8")
        cases = {
            "process": (
                '    image: "${ELMOS_SPRING_INGRESS_IMAGE:?',
                (
                    '    command: ["/bin/sh"]\n'
                    '    image: "${ELMOS_SPRING_INGRESS_IMAGE:?'
                ),
                "inherit its digest-pinned image command",
            ),
            "environment": (
                ("    environment:\n" "      ELMOS_DATABASE_URL:"),
                (
                    "    environment:\n"
                    "      ELMOS_UNDECLARED_RUNTIME_FLAG: true\n"
                    "      ELMOS_DATABASE_URL:"
                ),
                "environment contract drift",
            ),
            "mount": (
                (
                    "    networks: [spring-runner-broker, spring-runner-control]\n"
                    "    expose: [\"8082\"]"
                ),
                (
                    "      - type: bind\n"
                    "        source: /host/escape\n"
                    "        target: /escape\n"
                    "        read_only: false\n"
                    "        bind: { create_host_path: false }\n"
                    "    networks: [spring-runner-broker, spring-runner-control]\n"
                    "    expose: [\"8082\"]"
                ),
                "mount inventory drift",
            ),
        }
        for label, (before, after, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"spring-runner-static-{label}-"
            ) as directory:
                self.assertIn(before, source)
                mutated = Path(directory) / "runner.yml"
                mutated.write_text(source.replace(before, after, 1), encoding="utf-8")
                errors = TOPOLOGY.validate_static(
                    TOPOLOGY.ContractPaths(runner_compose=mutated)
                )
            self.assertTrue(any(expected in item for item in errors), errors)

    def test_static_contract_rejects_interpolation_suffix_bypass(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        source = paths.runner_compose.read_text(encoding="utf-8")
        cases = {
            "image": (
                "digest-pinned ingress image is required}",
                "digest-pinned ingress image is required}-suffix",
                "image must be supplied by required ELMOS_SPRING_INGRESS_IMAGE",
            ),
            "mount": (
                "ingress config is required}",
                "ingress config is required}-suffix",
                "mount /etc/nginx/nginx.conf must use ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH",
            ),
            "network": (
                "internal control network is required}",
                "internal control network is required}-suffix",
                "control network name must be explicitly supplied",
            ),
        }
        for label, (before, after, expected) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"spring-runner-interpolation-{label}-"
            ) as directory:
                mutated = Path(directory) / "runner.yml"
                mutated.write_text(source.replace(before, after, 1), encoding="utf-8")
                errors = TOPOLOGY.validate_static(
                    TOPOLOGY.ContractPaths(runner_compose=mutated)
                )
            self.assertTrue(any(expected in item for item in errors), errors)

    def test_ingress_and_broker_networks_are_internal_default_deny(self) -> None:
        runner = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)

        self.assertIs(True, runner["networks"]["spring-runner-edge"]["internal"])
        self.assertIs(True, runner["networks"]["spring-runner-broker"]["internal"])

    def test_control_network_cannot_collapse_into_another_runner_network(self) -> None:
        compose = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)
        environment = self.valid_environment_values(Path("/secure/runner.env"))
        environment["ELMOS_SPRING_RUNNER_CONTROL_NETWORK"] = (
            "elmos-spring-runner-broker"
        )
        errors: list[str] = []
        TOPOLOGY.validate_resolved_network_isolation(errors, compose, environment)
        self.assertTrue(any("distinct actual names" in item for item in errors), errors)
        with self.assertRaisesRegex(ValueError, "distinct actual network names"):
            TOPOLOGY.expected_service_networks(
                compose,
                compose["services"]["spring-runner-broker"],
                environment,
            )

    def test_ingress_exposes_only_exact_hmac_post_routes(self) -> None:
        config = TOPOLOGY.ContractPaths().ingress_config.read_text(encoding="utf-8")
        errors: list[str] = []
        TOPOLOGY.validate_ingress(errors, config)
        self.assertEqual([], errors)
        self.assertEqual(3, config.count("location = /internal/v1/spring-"))
        self.assertNotIn("listen 8082", config)

        malicious = config.replace(
            "    location / {",
            "    location = /tls-key { alias /run/secrets/tls/tls.key; }\n\n    location / {",
            1,
        )
        errors = []
        TOPOLOGY.validate_ingress(errors, malicious)
        self.assertTrue(any("byte-for-byte" in item for item in errors), errors)

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

    def test_static_contract_rejects_wildcard_or_additional_ingress_binding(self) -> None:
        paths = TOPOLOGY.ContractPaths()
        source = paths.runner_compose.read_text(encoding="utf-8")
        cases = {
            "wildcard": (
                '        host_ip: "${ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS:?private bind address is required}"',
                '        host_ip: "0.0.0.0"',
            ),
            "additional": (
                "        protocol: tcp\n    volumes:",
                (
                    "        protocol: tcp\n"
                    "      - target: 9443\n"
                    "        published: 9443\n"
                    "        host_ip: 127.0.0.1\n"
                    "        protocol: tcp\n"
                    "    volumes:"
                ),
            ),
        }
        for label, (before, after) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix=f"spring-runner-port-{label}-"
            ) as directory:
                self.assertIn(before, source)
                mutated = Path(directory) / "runner.yml"
                mutated.write_text(source.replace(before, after, 1), encoding="utf-8")
                errors = TOPOLOGY.validate_static(
                    TOPOLOGY.ContractPaths(runner_compose=mutated)
                )
            self.assertTrue(
                any("publish only its exact configured private 8443 binding" in item for item in errors),
                errors,
            )

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
        for suffix in (b"\n", "\u00a0".encode("utf-8"), "\ufeff".encode("utf-8")):
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

    def test_runner_bind_sources_reject_unsafe_ancestors_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-bind-source-") as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            unsafe = root / "unsafe"
            unsafe.mkdir(mode=0o700)
            private = unsafe / "private"
            private.mkdir(mode=0o700)
            config = private / "nginx.conf"
            config.write_bytes(b"reviewed")
            config.chmod(0o600)
            workspace = unsafe / "workspace"
            workspace.mkdir(mode=0o700)
            unsafe.chmod(0o777)

            config_errors: list[str] = []
            TOPOLOGY.trusted_regular_file(
                config_errors,
                config,
                label="config",
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                expected_parent_uid=os.getuid(),
                expected_parent_gid=os.getgid(),
                expected_sha256=TOPOLOGY.hashlib.sha256(b"reviewed").hexdigest(),
            )
            directory_errors: list[str] = []
            TOPOLOGY.ordinary_directory(
                directory_errors,
                workspace,
                label="workspace",
                allowed_uids={os.getuid()},
                allowed_gids={os.getgid()},
            )

        self.assertTrue(
            any("group/other-writable non-sticky ancestors" in item for item in config_errors),
            config_errors,
        )
        self.assertTrue(
            any("group/other-writable non-sticky ancestors" in item for item in directory_errors),
            directory_errors,
        )

    def test_runner_sensitive_bind_sources_reject_foreign_owned_ancestors(self) -> None:
        real_lstat = Path.lstat
        foreign_uid = os.getuid() + 20_000
        with tempfile.TemporaryDirectory(prefix="spring-runner-foreign-owner-") as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            foreign = root / "foreign"
            foreign.mkdir(mode=0o755)
            private = foreign / "private"
            private.mkdir(mode=0o700)
            secret = private / "secret"
            secret.write_bytes(b"x" * 32)
            secret.chmod(0o600)

            def foreign_owner(path: Path) -> os.stat_result:
                details = real_lstat(path)
                if path == foreign:
                    fields = list(details)
                    fields[4] = foreign_uid
                    return os.stat_result(fields)
                return details

            errors: list[str] = []
            with mock.patch.object(
                TOPOLOGY.Path,
                "lstat",
                autospec=True,
                side_effect=foreign_owner,
            ):
                TOPOLOGY.owner_only_file(
                    errors,
                    secret,
                    label="secret",
                    expected_uid=os.getuid(),
                    expected_gid=os.getgid(),
                    minimum_size=32,
                )

        self.assertTrue(any("foreign-owned ancestors" in item for item in errors), errors)

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

    def test_https_bind_requires_canonical_private_unicast_and_valid_port(self) -> None:
        valid = {
            "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS": "10.20.30.40",
            "ELMOS_SPRING_RUNNER_HTTPS_PORT": "8443",
        }
        self.assertEqual(("10.20.30.40", 8443), TOPOLOGY.private_https_endpoint(valid))
        self.assertEqual(
            ("127.0.0.1", 8443),
            TOPOLOGY.private_https_endpoint(
                {**valid, "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS": "127.0.0.1"}
            ),
        )
        cases = (
            ("0.0.0.0", "8443"),
            ("::", "8443"),
            ("8.8.8.8", "8443"),
            ("169.254.1.1", "8443"),
            ("10.20.30.40", "0"),
            ("10.20.30.40", "65536"),
            ("10.20.30.40", "08443"),
        )
        for address, port in cases:
            with self.subTest(address=address, port=port), self.assertRaises(ValueError):
                TOPOLOGY.private_https_endpoint(
                    {
                        "ELMOS_SPRING_RUNNER_HTTPS_BIND_ADDRESS": address,
                        "ELMOS_SPRING_RUNNER_HTTPS_PORT": port,
                    }
                )

    def test_sensitive_paths_cannot_overlap_mutable_runtime_roots(self) -> None:
        cases = (
            (Path("/srv/secrets/key"), Path("/srv/secrets")),
            (Path("/srv/runtime"), Path("/srv/runtime/evidence")),
            (Path("/srv/shared"), Path("/srv/shared")),
        )
        for secret, root in cases:
            with self.subTest(secret=secret, root=root):
                errors: list[str] = []
                TOPOLOGY.validate_sensitive_path_isolation(
                    errors,
                    {"SECRET_PATH": secret},
                    {"MUTABLE_ROOT": root},
                )
                self.assertTrue(any("must not equal, contain" in item for item in errors))

        errors = []
        TOPOLOGY.validate_sensitive_path_isolation(
            errors,
            {"SECRET_PATH": Path("/srv/secrets/key")},
            {"MUTABLE_ROOT": Path("/srv/runtime")},
        )
        self.assertEqual([], errors)

        with tempfile.TemporaryDirectory(prefix="spring-runner-overlap-") as directory:
            base = Path(directory).resolve()
            mutable = base / "mutable"
            mutable.mkdir()
            secret = mutable / "secret"
            secret.write_bytes(b"x" * 32)
            alias = base / "alias"
            alias.symlink_to(mutable, target_is_directory=True)
            errors = []
            TOPOLOGY.validate_sensitive_path_isolation(
                errors,
                {"SECRET_PATH": secret},
                {"MUTABLE_ROOT": alias},
            )
        self.assertTrue(any("must not equal, contain" in item for item in errors), errors)

    def test_operational_roots_are_pairwise_path_and_inode_isolated(self) -> None:
        cases = (
            (Path("/srv/workspace"), Path("/srv/workspace")),
            (Path("/srv/workspace"), Path("/srv/workspace/replay")),
            (Path("/srv/evidence/archive"), Path("/srv/evidence")),
        )
        for left, right in cases:
            with self.subTest(left=left, right=right):
                errors: list[str] = []
                TOPOLOGY.validate_operational_root_isolation(
                    errors,
                    {"LEFT_ROOT": left, "RIGHT_ROOT": right},
                )
                self.assertTrue(any("must not equal, contain" in item for item in errors))

        errors = []
        TOPOLOGY.validate_operational_root_isolation(
            errors,
            {
                "WORKSPACE_ROOT": Path("/srv/workspace"),
                "REPLAY_ROOT": Path("/srv/replay"),
            },
        )
        self.assertEqual([], errors)

        with tempfile.TemporaryDirectory(prefix="spring-runner-root-alias-") as directory:
            base = Path(directory).resolve()
            first = base / "first"
            first.write_bytes(b"identity")
            second = base / "second"
            os.link(first, second)
            errors = []
            TOPOLOGY.validate_operational_root_isolation(
                errors,
                {"FIRST_ROOT": first, "SECOND_ROOT": second},
            )
        self.assertTrue(any("or alias" in item for item in errors), errors)

    def test_compose_ps_rejects_duplicate_missing_extra_and_reused_ids(self) -> None:
        environment = {
            "ELMOS_SPRING_RUNNER_ENV_FILE": "/secure/runner.env",
        }
        valid_rows = [
            {"Service": service, "ID": f"{index + 1}" * 64}
            for index, service in enumerate(sorted(TOPOLOGY.EXPECTED_RUNNER_SERVICES))
        ]
        cases = {
            "duplicate-service": [valid_rows[0], valid_rows[0], valid_rows[2]],
            "extra-record": valid_rows
            + [{"Service": "spring-runner-broker", "ID": "4" * 64}],
            "missing-record": valid_rows[:2],
            "reused-id": [
                valid_rows[0],
                valid_rows[1],
                {**valid_rows[2], "ID": valid_rows[0]["ID"]},
            ],
        }
        for label, rows in cases.items():
            with self.subTest(label=label), mock.patch.object(
                TOPOLOGY, "command_json", return_value=rows
            ), self.assertRaises(ValueError):
                TOPOLOGY.compose_container_ids(Path("/run/user/1000/docker.sock"), environment)

        with mock.patch.object(
            TOPOLOGY, "command_json", return_value=valid_rows
        ) as command_json:
            identifiers = TOPOLOGY.compose_container_ids(
                Path("/run/user/1000/docker.sock"), environment
            )
        self.assertEqual(TOPOLOGY.EXPECTED_RUNNER_SERVICES, set(identifiers))
        command = command_json.call_args.args[0]
        self.assertIn("--all", command)
        self.assertIn("--no-trunc", command)
        self.assertEqual(
            "elmos-spring-runner",
            command[command.index("--project-name") + 1],
        )

    def test_live_inspect_contract_binds_every_service_to_compose_and_image(self) -> None:
        for service in sorted(TOPOLOGY.EXPECTED_RUNNER_SERVICES):
            with self.subTest(service=service):
                fixture = self.runtime_fixture(service)
                errors: list[str] = []
                TOPOLOGY.validate_runtime_service(errors, **fixture)
                self.assertEqual([], errors)

    def test_live_inspect_rejects_image_process_hardening_namespace_and_port_drift(self) -> None:
        mutations = {
            "image-ref": (
                lambda record: record["Config"].__setitem__("Image", "registry.invalid/image@sha256:" + "f" * 64),
                "image reference drift",
            ),
            "image-id": (
                lambda record: record.__setitem__("Image", "sha256:" + "e" * 64),
                "image ID drift",
            ),
            "user": (
                lambda record: record["Config"].__setitem__("User", "0:0"),
                "runtime user drift",
            ),
            "environment": (
                lambda record: record["Config"]["Env"].append("UNDECLARED=value"),
                "runtime environment drift",
            ),
            "entrypoint": (
                lambda record: record["Config"].__setitem__("Entrypoint", ["/bin/sh"]),
                "Entrypoint drift",
            ),
            "cmd": (
                lambda record: record["Config"].__setitem__("Cmd", ["sleep", "infinity"]),
                "Cmd drift",
            ),
            "privileged": (
                lambda record: record["HostConfig"].__setitem__("Privileged", True),
                "must not be privileged",
            ),
            "writable-root": (
                lambda record: record["HostConfig"].__setitem__("ReadonlyRootfs", False),
                "must be read-only",
            ),
            "capabilities": (
                lambda record: record["HostConfig"].__setitem__("CapDrop", []),
                "drop exactly all capabilities",
            ),
            "security-opt": (
                lambda record: record["HostConfig"].__setitem__("SecurityOpt", []),
                "security options drift",
            ),
            "memory": (
                lambda record: record["HostConfig"].__setitem__("Memory", 0),
                "Memory resource limit drift",
            ),
            "cpu": (
                lambda record: record["HostConfig"].__setitem__("NanoCpus", 0),
                "NanoCpus resource limit drift",
            ),
            "logging": (
                lambda record: record["HostConfig"]["LogConfig"].__setitem__(
                    "Type", "none"
                ),
                "logging contract drift",
            ),
            "healthcheck": (
                lambda record: record["Config"]["Healthcheck"].__setitem__(
                    "Retries", 1
                ),
                "healthcheck configuration drift",
            ),
            "tmpfs-size": (
                lambda record: record["HostConfig"]["Tmpfs"].__setitem__(
                    "/tmp", "rw,noexec,nosuid,size=1g"
                ),
                "tmpfs /tmp hardening drift",
            ),
            "restarting": (
                lambda record: record["State"].__setitem__("Restarting", True),
                "must be stably running",
            ),
            "pid-namespace": (
                lambda record: record["HostConfig"].__setitem__("PidMode", "host"),
                "PidMode runtime namespace drift",
            ),
            "network-mode": (
                lambda record: record["HostConfig"].__setitem__("NetworkMode", "host"),
                "primary network must select a controlled network",
            ),
            "extra-network": (
                lambda record: record["NetworkSettings"]["Networks"].__setitem__("outside", {}),
                "network membership drift",
            ),
            "wildcard-port": (
                lambda record: record["NetworkSettings"]["Ports"]["8443/tcp"][0].__setitem__("HostIp", "0.0.0.0"),
                "runtime published ports drift",
            ),
            "extra-port": (
                lambda record: record["HostConfig"]["PortBindings"].__setitem__(
                    "8080/tcp", [{"HostIp": "127.0.0.1", "HostPort": "8080"}]
                ),
                "HostConfig port bindings drift",
            ),
        }
        for label, (mutate, expected) in mutations.items():
            with self.subTest(label=label):
                fixture = self.runtime_fixture("spring-runner-ingress")
                mutate(fixture["record"])
                errors: list[str] = []
                TOPOLOGY.validate_runtime_service(errors, **fixture)
                self.assertTrue(any(expected in item for item in errors), errors)

    def test_live_inspect_rejects_tls_config_socket_hmac_replay_and_extra_mounts(self) -> None:
        cases = (
            ("spring-runner-ingress", "/etc/nginx/nginx.conf"),
            ("spring-runner-ingress", "/run/secrets/tls/tls.crt"),
            ("spring-runner-ingress", "/run/secrets/tls/tls.key"),
            ("spring-runner-broker", "/run/docker.sock"),
            ("spring-runner-broker", "/run/secrets/elmos-runtime-hmac"),
            ("spring-runner-broker", "/run/secrets/elmos-verifier-hmac"),
            ("spring-runner-broker", "/run/secrets/elmos-transformer-hmac"),
            ("spring-runner-broker", "/var/lib/elmos/spring-auth-replay"),
        )
        for service, target in cases:
            with self.subTest(service=service, target=target):
                fixture = self.runtime_fixture(service)
                mount = next(
                    item for item in fixture["record"]["Mounts"]
                    if item["Destination"] == target
                )
                mount["Source"] += "-drift"
                errors: list[str] = []
                TOPOLOGY.validate_runtime_service(errors, **fixture)
                self.assertTrue(any(f"mount {target} source drift" in item for item in errors), errors)

        for field, value, expected in (
            ("RW", False, "access mode drift"),
            ("Mode", "ro", "mode drift"),
            ("Propagation", "shared", "propagation drift"),
        ):
            with self.subTest(field=field):
                fixture = self.runtime_fixture("spring-runner-broker")
                mount = next(
                    item
                    for item in fixture["record"]["Mounts"]
                    if item["Destination"] == "/run/docker.sock"
                )
                mount[field] = value
                errors = []
                TOPOLOGY.validate_runtime_service(errors, **fixture)
                self.assertTrue(any(expected in item for item in errors), errors)

        fixture = self.runtime_fixture("spring-runner-egress-proxy")
        fixture["record"]["Mounts"].append(
            {
                "Type": "bind",
                "Source": "/host/escape",
                "Destination": "/escape",
                "RW": True,
            }
        )
        errors = []
        TOPOLOGY.validate_runtime_service(errors, **fixture)
        self.assertTrue(any("runtime mount inventory drift" in item for item in errors), errors)

    def test_live_mount_identities_cover_zero_mount_service_and_reject_stale_inode(self) -> None:
        compose = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)
        environment = self.valid_environment_values(Path("/secure/runner.env"))
        records: dict[str, dict[str, object]] = {}
        for index, service in enumerate(sorted(TOPOLOGY.EXPECTED_RUNNER_SERVICES), start=10):
            record = self.runtime_fixture(service)["record"]
            assert isinstance(record, dict)
            record["State"]["Pid"] = index
            records[service] = record

        calls: list[tuple[str, int, str]] = []

        def process_observer(process_id: int, _label: str) -> tuple[int, int, int, str, int, int]:
            return (process_id, 1, process_id, "100", 2, process_id)

        def matching_observer(
            source: str, process_id: int, destination: str, _label: str
        ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
            calls.append((source, process_id, destination))
            identity = (1, process_id, 0o100000, 0o600, os.getuid(), os.getgid())
            process = process_observer(process_id, "")
            return identity, identity, process, process

        errors: list[str] = []
        identities = TOPOLOGY.validate_live_mount_identities(
            errors,
            records=records,
            compose=compose,
            environment=environment,
            observer=matching_observer,
            process_observer=process_observer,
        )
        self.assertEqual([], errors)
        self.assertEqual(TOPOLOGY.EXPECTED_RUNNER_SERVICES, set(identities))
        self.assertEqual(
            sum(
                len(TOPOLOGY.expected_service_mounts(compose["services"][name], environment))
                for name in TOPOLOGY.EXPECTED_RUNNER_SERVICES
            ),
            len(calls),
        )

        def stale_observer(
            source: str, process_id: int, destination: str, label: str
        ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
            host, target, before, after = matching_observer(
                source, process_id, destination, label
            )
            return host, (target[0], target[1] + 1, *target[2:]), before, after

        stale_errors: list[str] = []
        TOPOLOGY.validate_live_mount_identities(
            stale_errors,
            records=records,
            compose=compose,
            environment=environment,
            observer=stale_observer,
            process_observer=process_observer,
        )
        self.assertTrue(
            any("does not expose the current host source object" in item for item in stale_errors),
            stale_errors,
        )

    def test_live_mount_identities_reject_process_generation_or_namespace_change(self) -> None:
        compose = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)
        environment = self.valid_environment_values(Path("/secure/runner.env"))
        records: dict[str, dict[str, object]] = {}
        for index, service in enumerate(sorted(TOPOLOGY.EXPECTED_RUNNER_SERVICES), start=20):
            record = self.runtime_fixture(service)["record"]
            assert isinstance(record, dict)
            record["State"]["Pid"] = index
            records[service] = record
        calls: dict[int, int] = {}

        def changing_process(process_id: int, _label: str) -> tuple[int, int, int, str, int, int]:
            calls[process_id] = calls.get(process_id, 0) + 1
            return (process_id, 1, process_id, "100", 2, process_id + calls[process_id] - 1)

        def stable_mount(
            _source: str, process_id: int, _destination: str, _label: str
        ) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
            identity = (1, process_id, 0o100000, 0o600, os.getuid(), os.getgid())
            process = (process_id, 1, process_id, "100", 2, process_id)
            return identity, identity, process, process

        errors: list[str] = []
        TOPOLOGY.validate_live_mount_identities(
            errors,
            records=records,
            compose=compose,
            environment=environment,
            observer=stable_mount,
            process_observer=changing_process,
        )
        self.assertTrue(any("mount namespace changed" in item for item in errors), errors)

    def test_runtime_generation_binds_restart_and_mount_inventory(self) -> None:
        fixture = self.runtime_fixture("spring-runner-ingress")
        record = fixture["record"]
        assert isinstance(record, dict)
        baseline = TOPOLOGY.runtime_generation(record, label="ingress")
        for field, mutate in (
            ("pid", lambda value: value["State"].__setitem__("Pid", 99999)),
            ("started", lambda value: value["State"].__setitem__("StartedAt", "later")),
            ("restart", lambda value: value.__setitem__("RestartCount", 1)),
            ("id", lambda value: value.__setitem__("Id", "f" * 64)),
            ("bind", lambda value: value["HostConfig"]["Binds"].append("/x:/y:rw")),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(record)
                mutate(changed)
                self.assertNotEqual(
                    baseline,
                    TOPOLOGY.runtime_generation(changed, label="ingress"),
                )

    def test_ingress_materials_must_predate_container_start_and_remain_exact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="spring-runner-startup-material-") as directory:
            root = Path(directory).resolve()
            config = root / "nginx.conf"
            certificate = root / "tls.crt"
            key = root / "tls.key"
            config.write_bytes(
                TOPOLOGY.ContractPaths().ingress_config.read_bytes()
            )
            certificate.write_bytes(b"certificate")
            key.write_bytes(b"k" * 32)
            environment = {
                "ELMOS_SPRING_INGRESS_CONFIG_HOST_PATH": str(config),
                "ELMOS_SPRING_INGRESS_TLS_CERT_HOST_PATH": str(certificate),
                "ELMOS_SPRING_INGRESS_TLS_KEY_HOST_PATH": str(key),
            }
            future_record = {"State": {"StartedAt": "2099-01-01T00:00:00.123456789Z"}}
            materials = TOPOLOGY.ingress_startup_materials(
                environment, future_record
            )
            self.assertEqual(
                TOPOLOGY.EXPECTED_INGRESS_CONFIG_SHA256,
                materials["installed Spring ingress config"][7],
            )

            # Models an in-place overwrite after nginx loaded an older object:
            # the current bytes are reviewed, but ctime/mtime postdate StartedAt.
            stale_process_record = {
                "State": {"StartedAt": "2000-01-01T00:00:00Z"}
            }
            with self.assertRaisesRegex(
                RuntimeError, "modified after the ingress container StartedAt"
            ):
                TOPOLOGY.ingress_startup_materials(
                    environment, stale_process_record
                )

    def test_docker_started_at_parser_rejects_noncanonical_or_invalid_time(self) -> None:
        self.assertEqual(
            1_000_000_001,
            TOPOLOGY.parse_docker_started_at_ns(
                "1970-01-01T00:00:01.000000001Z", label="ingress"
            ),
        )
        for value in (
            "2026-09-05T00:00:00+00:00",
            "2026-09-05 00:00:00Z",
            "2026-13-05T00:00:00Z",
            "later",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                TOPOLOGY.parse_docker_started_at_ns(value, label="ingress")

    def test_linux_live_mount_observer_detects_atomic_source_replacement_and_socket(self) -> None:
        if sys.platform != "linux" or not hasattr(os, "O_PATH"):
            self.skipTest("Linux O_PATH and /proc are required")
        with tempfile.TemporaryDirectory(prefix="spring-runner-live-bind-") as directory:
            root = Path(directory).resolve()
            source = root / "source"
            stale_target = root / "stale-target"
            source.write_bytes(b"old")
            os.link(source, stale_target)
            replacement = root / "replacement"
            replacement.write_bytes(b"new")
            os.replace(replacement, source)
            host, target, before, after = TOPOLOGY.observe_live_bind_mount(
                str(source), os.getpid(), str(stale_target), "stale file"
            )
            self.assertNotEqual(host, target)
            self.assertEqual(before, after)

            socket_path = root / "docker.sock"
            endpoint = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                endpoint.bind(str(socket_path))
                host, target, before, after = TOPOLOGY.observe_live_bind_mount(
                    str(socket_path), os.getpid(), str(socket_path), "socket"
                )
                self.assertEqual(host, target)
                self.assertEqual(before, after)
            finally:
                endpoint.close()

    @classmethod
    def runtime_fixture(cls, service_name: str) -> dict[str, object]:
        compose = TOPOLOGY.read_yaml(TOPOLOGY.ContractPaths().runner_compose)
        service = compose["services"][service_name]
        environment = cls.valid_environment_values(Path("/secure/runner.env"))
        image_reference = environment[TOPOLOGY.SERVICE_IMAGE_ENVIRONMENTS[service_name]]
        image_id = "sha256:" + {
            "spring-runner-ingress": "a",
            "spring-runner-broker": "b",
            "spring-runner-egress-proxy": "c",
        }[service_name] * 64
        image_record = {
            "Id": image_id,
            "RepoDigests": [image_reference],
            "Config": {
                "Env": ["PATH=/usr/local/bin:/usr/bin:/bin"],
                "Entrypoint": ["/usr/local/bin/entrypoint"],
                "Cmd": ["serve"],
                "WorkingDir": "/opt/elmos",
                "ExposedPorts": {},
            },
        }
        expectation_errors: list[str] = []
        expected_environment = TOPOLOGY.expected_service_environment(
            service,
            image_record,
            environment,
            expectation_errors,
            label=service_name,
        )
        if expectation_errors or expected_environment is None:
            raise AssertionError(expectation_errors)
        networks = TOPOLOGY.expected_service_networks(compose, service, environment)
        mounts = TOPOLOGY.expected_service_mounts(service, environment)
        bindings = (
            {"8443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}]}
            if service_name == "spring-runner-ingress"
            else {}
        )
        record = {
            "Id": {
                "spring-runner-ingress": "d",
                "spring-runner-broker": "e",
                "spring-runner-egress-proxy": "f",
            }[service_name]
            * 64,
            "Image": image_id,
            "Path": "/usr/local/bin/entrypoint",
            "Args": ["serve"],
            "Config": {
                "Image": image_reference,
                "User": TOPOLOGY.SERVICE_USERS[service_name],
                "Env": [f"{name}={value}" for name, value in expected_environment.items()],
                "Entrypoint": image_record["Config"]["Entrypoint"],
                "Cmd": image_record["Config"]["Cmd"],
                "WorkingDir": "/opt/elmos",
                "ExposedPorts": {
                    name: {}
                    for name in TOPOLOGY.expected_exposed_ports(service, image_record)
                },
                "Healthcheck": TOPOLOGY.expected_runtime_healthcheck(
                    service_name, image_record
                ),
                "Labels": {
                    "com.docker.compose.project": "elmos-spring-runner",
                    "com.docker.compose.service": service_name,
                },
            },
            "HostConfig": {
                "Privileged": False,
                "ReadonlyRootfs": True,
                "AutoRemove": False,
                "Init": True,
                "PidsLimit": service["pids_limit"],
                **TOPOLOGY.RUNNER_SERVICE_RUNTIME_RESOURCE_CONTRACT[service_name],
                "CapAdd": None,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "PublishAllPorts": False,
                "GroupAdd": ["0"] if service_name == "spring-runner-broker" else [],
                "PidMode": "",
                "IpcMode": "private",
                "UTSMode": "",
                "UsernsMode": "",
                "CgroupnsMode": "private",
                "NetworkMode": networks[0],
                "PortBindings": copy.deepcopy(bindings),
                "Tmpfs": {
                    "/tmp": "rw,noexec,nosuid,size="
                    + {
                        "spring-runner-ingress": "33554432",
                        "spring-runner-broker": "268435456",
                        "spring-runner-egress-proxy": "33554432",
                    }[service_name]
                },
                "Binds": [
                    f"{source}:{target}:{'rw' if read_write else 'ro'}"
                    for target, (source, read_write) in mounts.items()
                ],
                "RestartPolicy": {
                    "Name": "unless-stopped",
                    "MaximumRetryCount": 0,
                },
                "LogConfig": {
                    "Type": "json-file",
                    "Config": {"max-size": "20m", "max-file": "5"},
                },
            },
            "NetworkSettings": {
                "Networks": {name: {} for name in networks},
                "Ports": {
                    **{
                        name: None
                        for name in TOPOLOGY.expected_exposed_ports(service, image_record)
                    },
                    **copy.deepcopy(bindings),
                },
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": source,
                    "Destination": target,
                    "RW": read_write,
                    "Mode": "rw" if read_write else "ro",
                    "Propagation": "rprivate",
                }
                for target, (source, read_write) in mounts.items()
            ],
            "State": {
                "Pid": 1000,
                "StartedAt": "2026-09-05T00:00:00Z",
                "Running": True,
                "Restarting": False,
                "Paused": False,
                "Dead": False,
                "OOMKilled": False,
                **(
                    {"Health": {"Status": "healthy"}}
                    if TOPOLOGY.expected_runtime_healthcheck(service_name, image_record)
                    is not None
                    else {}
                ),
            },
            "RestartCount": 0,
        }
        return {
            "service_name": service_name,
            "service": service,
            "compose": compose,
            "record": record,
            "image_record": image_record,
            "environment": environment,
            "bind_address": "127.0.0.1",
            "bind_port": 8443,
        }

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
