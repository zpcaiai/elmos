import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/batch30/validate_spring_launch_readiness.py"
ENV_TEMPLATE = ROOT / "deploy/production/spring-launch.env.example"
MAKEFILE = ROOT / "Makefile.batch30"

SPRING_ENVIRONMENT_KEYS = (
    "ELMOS_SPRING_PROXY_ENABLED",
    "ELMOS_SPRING_PROXY_MULTI_TENANT",
    "ELMOS_SPRING_ENGINE_AUTH_ENABLED",
    "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED",
    "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED",
    "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED",
    "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED",
    "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED",
    "ELMOS_SPRING_CODING_AGENT_ENABLED",
    "ELMOS_SPRING_UPGRADE_VERIFIER_ID",
    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
    "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH",
    "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH",
    "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH",
    "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH",
    "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH",
)
DANGEROUS_DEPLOYMENT_KEYS = (
    "SPRING_APPLICATION_JSON",
    "JAVA_TOOL_OPTIONS",
    "_JAVA_OPTIONS",
    "JAVA_OPTS",
    "JDK_JAVA_OPTIONS",
    "SERVER_SERVLET_CONTEXT_PATH",
    "SERVER_SERVLET_PATH",
    "SPRING_MVC_SERVLET_PATH",
    "SPRING_CONFIG_LOCATION",
    "SPRING_CONFIG_ADDITIONAL_LOCATION",
    "SPRING_CONFIG_IMPORT",
    "SPRING_PROFILES_ACTIVE",
    "SPRING_PROFILES_INCLUDE",
)


def sanitized_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in tuple(environment):
        if (
            name.startswith("ELMOS_SPRING_")
            or name.startswith("ELMOS_JAVA_UPGRADE_")
            or name.startswith("ELMOS_VERIFIER_")
            or name.startswith("ELMOS_TRANSFORMER_")
            or name == "ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID"
            or name == "ELMOS_ENV_FILE"
            or name in DANGEROUS_DEPLOYMENT_KEYS
        ):
            environment.pop(name)
    return environment


def complete_environment(root: Path) -> dict[str, str]:
    root.chmod(0o700)
    workspace = root / "workspace"
    workspace.mkdir(mode=0o700)
    replay = root / "engine-replay"
    replay.mkdir(mode=0o700)
    secrets = []
    for index in range(4):
        secret = root / f"secret-{index}"
        secret.write_bytes(bytes([65 + index]) * 32)
        secret.chmod(0o600)
        secrets.append(secret)
    resend_secret = root / "resend-api-key"
    resend_secret.write_bytes(b"E" * 32)
    resend_secret.chmod(0o600)
    return {
        "ELMOS_SPRING_PROXY_ENABLED": "true",
        "ELMOS_SPRING_PROXY_MULTI_TENANT": "true",
        "ELMOS_SPRING_ENGINE_AUTH_ENABLED": "true",
        "ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED": "true",
        "ELMOS_SPRING_UPGRADE_NETWORK_POLICY_ATTESTED": "true",
        "ELMOS_SPRING_UPGRADE_VERIFIER_ENABLED": "true",
        "ELMOS_SPRING_TRANSFORMER_BROKER_ENABLED": "true",
        "ELMOS_SPRING_RUNTIME_RUNNER_ENABLED": "true",
        "ELMOS_SPRING_UPGRADE_EXPERIMENTAL_ROUTES_ENABLED": "false",
        "ELMOS_SPRING_CODING_AGENT_ENABLED": "false",
        "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "independent-verifier-1",
        "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL": "https://runner.example.test",
        "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL": "https://runner.example.test",
        "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL": "https://runner.example.test",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH": str(workspace),
        "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH": str(secrets[0]),
        "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH": str(secrets[1]),
        "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH": str(secrets[2]),
        "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH": str(secrets[3]),
        "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH": str(replay),
    }


def write_environment_file(path: Path, values: dict[str, str], extra_lines: tuple[str, ...] = ()) -> None:
    lines = ["# Spring launch test environment"]
    lines.extend(f"{name}={value}" for name, value in values.items())
    lines.extend(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_compose_environment_file(
    path: Path,
    spring_values: dict[str, str],
    extra_lines: tuple[str, ...] = (),
) -> None:
    values = {
        "ELMOS_ENV_FILE": str(path),
        "ELMOS_SECRET_ROOT": str(path.parent),
        "NODE_ENV": "production",
        "ELMOS_DATABASE_URL": "jdbc:postgresql://database.example/elmos?sslmode=require",
    }
    write_environment_file(path, values, extra_lines)


class SpringLaunchReadinessTests(unittest.TestCase):
    @staticmethod
    def load_validator(name: str):
        specification = importlib.util.spec_from_file_location(name, SCRIPT)
        if specification is None or specification.loader is None:
            raise RuntimeError(f"Cannot load spec for {name}")
        validator = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = validator
        specification.loader.exec_module(validator)
        return validator

    def test_repository_contract_is_ready_only_for_external_gate(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SPRING_LAUNCH_GATE=READY_FOR_EXTERNAL_GATE", result.stdout)
        self.assertIn("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN", result.stdout)
        self.assertIn("CERTIFICATION=NOT_CERTIFIED", result.stdout)

    def test_worker_management_endpoint_allowlist_is_exact(self):
        validator = self.load_validator("spring_launch_endpoint_allowlist")
        original = validator.WORKER_CONFIG.read_text(encoding="utf-8")
        cases = (
            original.replace("health,info,prometheus", "health,info"),
            original.replace("health,info,prometheus", "health,info,prometheus,env"),
        )
        for index, worker_config in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                candidate = Path(temporary) / "application.yml"
                candidate.write_text(worker_config, encoding="utf-8")
                with mock.patch.object(validator, "WORKER_CONFIG", candidate):
                    errors: list[str] = []
                    validator.validate_code(errors)
                self.assertIn(
                    "Spring worker must expose only the minimal internal health, info, and Prometheus endpoints",
                    errors,
                )

    def test_production_mode_fails_without_external_evidence(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--require-production-evidence"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("production evidence is required", result.stderr)
        self.assertIn(
            "production evidence requires --compose-environment-file", result.stderr
        )
        self.assertIn(
            "production evidence requires --expected-revision", result.stderr
        )
        self.assertIn(
            "production evidence requires --expected-worker-application-artifact-digest",
            result.stderr,
        )

    def test_template_cannot_masquerade_as_external_evidence(self):
        template = ROOT / "deploy/production/spring-external-evidence.example.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--external-evidence",
                str(template),
                "--trust-store",
                str(template),
                "--evidence-root",
                str(ROOT),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("must be mounted from outside the repository", result.stderr)

    def test_external_evidence_requires_explicit_trust_and_content_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary).resolve() / "receipt.json"
            receipt.write_text("{}\n", encoding="utf-8")
            receipt.chmod(0o600)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--external-evidence", str(receipt)],
                text=True,
                capture_output=True,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("--trust-store is required", result.stderr)
        self.assertIn("at least one --evidence-root is required", result.stderr)
        self.assertIn("external evidence intake requires --environment-file", result.stderr)
        self.assertIn(
            "external evidence intake requires --expected-trust-store-digest",
            result.stderr,
        )
        self.assertIn(
            "external evidence intake requires --expected-revision", result.stderr
        )
        self.assertIn(
            "external evidence intake requires --expected-worker-application-artifact-digest",
            result.stderr,
        )

    def test_environment_preflight_fails_closed_without_attestations(self):
        environment = sanitized_environment()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-environment"],
            text=True,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("ELMOS_SPRING_UPGRADE_ROOTLESS_ATTESTED must equal true", result.stderr)
        self.assertIn("shared Spring workspace", result.stderr)

    def test_environment_preflight_accepts_complete_nonsecret_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment = sanitized_environment()
            environment.update(complete_environment(root))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check-environment"],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN", result.stdout)
            self.assertRegex(
                result.stdout,
                r"SPRING_CONFIGURATION_DIGEST=sha256:[0-9a-f]{64}",
            )
            self.assertRegex(
                result.stdout,
                r"EXPECTED_SPRING_WORKER_CONFIGURATION_DIGEST=sha256:[0-9a-f]{64}",
            )

    def test_environment_preflight_rejects_unsafe_https_endpoints(self):
        cases = (
            "http://runner.production.example/verifier",
            "https://user:password@runner.production.example/verifier",
            "https://localhost/verifier",
            "https://127.0.0.1/verifier",
            "https://[::1]/verifier",
            "https://runner.production.example/verifier#mutable",
            "https://runner.production.example/internal-prefix",
            "https://runner.production.example/?route=mutable",
            "https://bad_host",
            "https://bad..host",
            "https://-bad.example.com",
            "https://runner.example.com.",
        )
        for index, endpoint in enumerate(cases):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                environment = sanitized_environment()
                environment.update(complete_environment(root))
                environment["ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL"] = endpoint
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )
                self.assertEqual(2, result.returncode, f"case {index} unexpectedly passed")
                self.assertIn(
                    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL must use a non-local absolute https URL",
                    result.stderr,
                )

    def test_production_https_origin_rejects_reserved_names_and_addresses(self):
        validator = self.load_validator("spring_launch_validator_https")

        for endpoint in (
            "https://runner.example.test",
            "https://runner.production.example",
            "https://example.com",
            "https://192.0.2.10",
            "https://198.51.100.10",
            "https://203.0.113.10",
            "https://[2001:db8::10]",
            "https://[::ffff:127.0.0.1]",
            "https://[::ffff:169.254.1.1]",
            "https://[::ffff:192.0.2.10]",
            "https://[::ffff:8.8.8.8]",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIsNone(
                    validator.https_endpoint_origin(endpoint, production=True)
                )
        self.assertEqual(
            ("https", "runner.production.company.com", 443),
            validator.https_endpoint_origin(
                "https://runner.production.company.com", production=True
            ),
        )

    def test_environment_preflight_requires_one_runner_https_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment = sanitized_environment()
            environment.update(complete_environment(root))
            environment["ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL"] = (
                "https://other-runner.example.test"
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--check-environment"],
                text=True,
                capture_output=True,
                env=environment,
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("must use one exact Runner HTTPS origin", result.stderr)

    def test_hmac_secret_permissions_must_be_exactly_owner_only(self):
        for mode in (0o000, 0o440, 0o640, 0o644):
            with self.subTest(mode=oct(mode)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                secret = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
                secret.chmod(mode)
                environment = sanitized_environment()
                environment.update(values)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(
                    "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH must be an owner-only regular",
                    result.stderr,
                )

    def test_owner_only_environment_file_is_parsed_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment_file = root / "spring.env"
            write_environment_file(environment_file, complete_environment(root))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("ENVIRONMENT_PRECEDENCE=PROCESS_ENVIRONMENT_OVER_FILE", result.stdout)
            self.assertIn("CERTIFICATION=NOT_CERTIFIED", result.stdout)

    def test_actual_compose_environment_is_verified_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            spring_file = root / "spring.env"
            compose_file = root / "elmos.env"
            write_environment_file(spring_file, values)
            write_compose_environment_file(compose_file, values)
            command = [
                sys.executable,
                str(SCRIPT),
                "--environment-file",
                str(spring_file),
                "--compose-environment-file",
                str(compose_file),
            ]

            first = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            self.assertIn(
                "COMPOSE_ENVIRONMENT_BINDING=ELMOS_ENV_FILE_VERIFIED", first.stdout
            )
            first_digest = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("SPRING_CONFIGURATION_DIGEST=")
            )
            first_application_environment_commitment = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST=")
            )
            first_worker_digest = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("EXPECTED_SPRING_WORKER_CONFIGURATION_DIGEST=")
            )
            first_web_digest = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("EXPECTED_WEB_CONSOLE_CONFIGURATION_DIGEST=")
            )
            first_web_names_digest = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("EXPECTED_WEB_CONSOLE_ENVIRONMENT_NAMES_DIGEST=")
            )
            first_mounts_digest = next(
                line
                for line in first.stdout.splitlines()
                if line.startswith("EXPECTED_APPLICATION_MOUNT_SOURCES_DIGEST=")
            )

            write_compose_environment_file(
                compose_file,
                values,
                ("ELMOS_DEPLOYMENT_MARKER=second-revision",),
            )
            second = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(0, second.returncode, second.stdout + second.stderr)
            second_digest = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("SPRING_CONFIGURATION_DIGEST=")
            )
            second_application_environment_commitment = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST=")
            )
            second_worker_digest = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("EXPECTED_SPRING_WORKER_CONFIGURATION_DIGEST=")
            )
            second_web_digest = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("EXPECTED_WEB_CONSOLE_CONFIGURATION_DIGEST=")
            )
            second_web_names_digest = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("EXPECTED_WEB_CONSOLE_ENVIRONMENT_NAMES_DIGEST=")
            )
            second_mounts_digest = next(
                line
                for line in second.stdout.splitlines()
                if line.startswith("EXPECTED_APPLICATION_MOUNT_SOURCES_DIGEST=")
            )
            self.assertNotEqual(first_digest, second_digest)
            self.assertNotEqual(
                first_application_environment_commitment,
                second_application_environment_commitment,
            )
            self.assertEqual(first_worker_digest, second_worker_digest)
            self.assertEqual(first_web_digest, second_web_digest)
            self.assertNotEqual(first_web_names_digest, second_web_names_digest)
            self.assertEqual(first_mounts_digest, second_mounts_digest)

    def test_application_environment_commitment_never_hashes_secret_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            spring_file = root / "spring.env"
            compose_file = root / "elmos.env"
            write_environment_file(spring_file, values)
            command = [
                sys.executable,
                str(SCRIPT),
                "--environment-file",
                str(spring_file),
                "--compose-environment-file",
                str(compose_file),
            ]

            commitments = []
            for secret in ("guessable-secret-one", "guessable-secret-two"):
                write_compose_environment_file(
                    compose_file,
                    values,
                    (f"ELMOS_DATABASE_PASSWORD={secret}",),
                )
                result = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    env=sanitized_environment(),
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertNotIn(secret, result.stdout + result.stderr)
                commitments.append(
                    next(
                        line
                        for line in result.stdout.splitlines()
                        if line.startswith(
                            "APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST="
                        )
                    )
                )
            self.assertEqual(commitments[0], commitments[1])

            write_compose_environment_file(
                compose_file,
                values,
                (
                    "ELMOS_DATABASE_PASSWORD=guessable-secret-two",
                    "ELMOS_DATABASE_SQL_PREFLIGHT_ENABLED=true",
                ),
            )
            changed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(0, changed.returncode, changed.stdout + changed.stderr)
            changed_commitment = next(
                line
                for line in changed.stdout.splitlines()
                if line.startswith("APPLICATION_ENVIRONMENT_COMMITMENT_DIGEST=")
            )
            self.assertNotEqual(commitments[1], changed_commitment)

    def test_actual_compose_environment_must_match_spring_file_and_self_bind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            spring_file = root / "spring.env"
            compose_file = root / "elmos.env"
            write_environment_file(spring_file, values)
            write_compose_environment_file(
                compose_file,
                values,
                ("ELMOS_SPRING_PROXY_ENABLED=false",),
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--environment-file",
                    str(spring_file),
                    "--compose-environment-file",
                    str(compose_file),
                ],
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(2, result.returncode)
            self.assertIn(
                "must not leak Spring launch key ELMOS_SPRING_PROXY_ENABLED",
                result.stderr,
            )

            write_environment_file(
                compose_file,
                {
                    "ELMOS_ENV_FILE": "/different/deployment.env",
                    "NODE_ENV": "production",
                    **values,
                },
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--environment-file",
                    str(spring_file),
                    "--compose-environment-file",
                    str(compose_file),
                ],
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(2, result.returncode)
            self.assertIn(
                "must set ELMOS_ENV_FILE to its exact validated path", result.stderr
            )

    def test_application_environment_rejects_spring_key_aliases_and_future_keys(self):
        for name in (
            "elmos_spring_proxy_enabled",
            "ELMOS_SPRING_FUTURE_OVERRIDE",
            "elmos_java_upgrade_workspace_host_path",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                spring_file = root / "spring.env"
                compose_file = root / "elmos.env"
                write_environment_file(spring_file, values)
                write_compose_environment_file(
                    compose_file,
                    values,
                    (f"{name}=attacker",),
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--environment-file",
                        str(spring_file),
                        "--compose-environment-file",
                        str(compose_file),
                    ],
                    text=True,
                    capture_output=True,
                    env=sanitized_environment(),
                )

            self.assertEqual(2, result.returncode)
            self.assertIn(
                f"must not leak Spring launch key {name}", result.stderr
            )

    def test_actual_compose_environment_rejects_dangerous_or_equivalent_overrides(self):
        keys = DANGEROUS_DEPLOYMENT_KEYS + (
            "SERVER_SERVLET_CONTEXTPATH",
            "spring_mvc_servletpath",
        )
        for key in keys:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                spring_file = root / "spring.env"
                compose_file = root / "elmos.env"
                write_environment_file(spring_file, values)
                write_compose_environment_file(compose_file, values, (f"{key}=attacker",))
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--environment-file",
                        str(spring_file),
                        "--compose-environment-file",
                        str(compose_file),
                    ],
                    text=True,
                    capture_output=True,
                    env=sanitized_environment(),
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(
                    f"must not define dangerous override {key}", result.stderr
                )

    def test_process_environment_rejects_dangerous_overrides_and_config_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            spring_file = root / "spring.env"
            compose_file = root / "elmos.env"
            write_environment_file(spring_file, values)
            write_compose_environment_file(compose_file, values)
            command = [
                sys.executable,
                str(SCRIPT),
                "--environment-file",
                str(spring_file),
                "--compose-environment-file",
                str(compose_file),
            ]

            environment = sanitized_environment()
            environment["JAVA_TOOL_OPTIONS"] = "-Dserver.servlet.context-path=/hidden"
            result = subprocess.run(
                command, text=True, capture_output=True, env=environment
            )
            self.assertEqual(2, result.returncode)
            self.assertIn(
                "process environment must not define dangerous override JAVA_TOOL_OPTIONS",
                result.stderr,
            )

            environment = sanitized_environment()
            environment["ELMOS_SPRING_PROXY_ENABLED"] = "false"
            result = subprocess.run(
                command, text=True, capture_output=True, env=environment
            )
            self.assertEqual(2, result.returncode)
            self.assertIn(
                "process environment Spring value differs from SPRING_ENV_FILE for ELMOS_SPRING_PROXY_ENABLED",
                result.stderr,
            )

            for name, expected in (
                (
                    "elmos_spring_proxy_enabled",
                    "process environment uses relaxed Spring launch alias",
                ),
                (
                    "ELMOS_SPRING_FUTURE_OVERRIDE",
                    "process environment defines unsupported Spring launch key",
                ),
            ):
                environment = sanitized_environment()
                environment[name] = "true"
                result = subprocess.run(
                    command, text=True, capture_output=True, env=environment
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(expected, result.stderr)

    def test_process_environment_cannot_supply_a_missing_spring_file_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            spring_file = root / "spring.env"
            compose_file = root / "elmos.env"
            missing = dict(values)
            missing.pop("ELMOS_SPRING_PROXY_ENABLED")
            write_environment_file(spring_file, missing)
            write_compose_environment_file(compose_file, values)
            environment = sanitized_environment()
            environment["ELMOS_SPRING_PROXY_ENABLED"] = "true"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--environment-file",
                    str(spring_file),
                    "--compose-environment-file",
                    str(compose_file),
                ],
                text=True,
                capture_output=True,
                env=environment,
            )

        self.assertEqual(2, result.returncode)
        self.assertIn(
            "SPRING_ENV_FILE is missing required key ELMOS_SPRING_PROXY_ENABLED",
            result.stderr,
        )
        self.assertIn(
            "process environment must not supply missing SPRING_ENV_FILE key ELMOS_SPRING_PROXY_ENABLED",
            result.stderr,
        )

    def test_explicit_process_environment_overrides_file_and_empty_override_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            values["ELMOS_SPRING_PROXY_ENABLED"] = "false"
            environment_file = root / "spring.env"
            write_environment_file(environment_file, values)

            environment = sanitized_environment()
            environment["ELMOS_SPRING_PROXY_ENABLED"] = "true"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

            environment["ELMOS_SPRING_PROXY_ENABLED"] = ""
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("ELMOS_SPRING_PROXY_ENABLED must equal true", result.stderr)

    def test_environment_file_rejects_duplicate_unknown_interpolation_and_commands(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            cases = (
                (
                    "duplicate",
                    values,
                    ("ELMOS_SPRING_PROXY_ENABLED=true",),
                    "duplicates ELMOS_SPRING_PROXY_ENABLED",
                ),
                (
                    "unknown",
                    values,
                    ("ELMOS_UNRELATED_DATABASE_PASSWORD=secret",),
                    "uses unknown key ELMOS_UNRELATED_DATABASE_PASSWORD",
                ),
                (
                    "forbidden-single-tenant",
                    values,
                    ("ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID=tenant-1",),
                    "uses unknown key ELMOS_TRUSTED_SINGLE_TENANT_ORGANIZATION_ID",
                ),
                (
                    "interpolation",
                    {**values, "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "${VERIFIER_ID}"},
                    (),
                    "forbidden interpolation",
                ),
                (
                    "command",
                    {**values, "ELMOS_SPRING_UPGRADE_VERIFIER_ID": "verifier;touch"},
                    (),
                    "command syntax",
                ),
            )
            for name, case_values, extra_lines, expected_error in cases:
                with self.subTest(name=name):
                    environment_file = root / f"{name}.env"
                    write_environment_file(environment_file, case_values, extra_lines)
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                        text=True,
                        capture_output=True,
                        env=sanitized_environment(),
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn(expected_error, result.stderr)

    def test_environment_file_command_substitution_is_data_and_never_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            sentinel = root / "must-not-exist"
            values = complete_environment(root)
            values["ELMOS_SPRING_UPGRADE_VERIFIER_ID"] = f"$(touch {sentinel})"
            environment_file = root / "command-substitution.env"
            write_environment_file(environment_file, values)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                text=True,
                capture_output=True,
                env=sanitized_environment(),
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("forbidden interpolation", result.stderr)
            self.assertFalse(sentinel.exists())

    def test_environment_file_rejects_unsafe_location_type_and_permissions(self):
        environment = sanitized_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            valid_file = root / "valid.env"
            write_environment_file(valid_file, values)

            unsafe_file = root / "unsafe.env"
            write_environment_file(unsafe_file, values)
            unsafe_file.chmod(0o644)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(unsafe_file)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("permissions must be 0400 or 0600", result.stderr)

            symlink = root / "spring-link.env"
            symlink.symlink_to(valid_file)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(symlink)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must not be a symbolic link", result.stderr)

            hardlink = root / "spring-hardlink.env"
            os.link(valid_file, hardlink)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(hardlink)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must not be hard-linked", result.stderr)

            real_directory = root / "real-environment-directory"
            real_directory.mkdir()
            parent_environment_file = real_directory / "spring.env"
            write_environment_file(parent_environment_file, values)
            symlink_directory = root / "environment-directory-link"
            symlink_directory.symlink_to(real_directory, target_is_directory=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--environment-file",
                    str(symlink_directory / parent_environment_file.name),
                ],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must not traverse symbolic-link parent directories", result.stderr)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(root)],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("must be a regular file", result.stderr)

        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--environment-file", str(ENV_TEMPLATE)],
            text=True,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("must be mounted from outside the repository", result.stderr)

    def test_environment_file_requires_a_private_stable_parent_chain(self):
        environment = sanitized_environment()
        for mode in (0o770, 0o777):
            with self.subTest(parent_mode=oct(mode)), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                parent = root / "unsafe-parent"
                parent.mkdir(mode=0o700)
                environment_file = parent / "spring.env"
                write_environment_file(environment_file, values)
                parent.chmod(mode)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                    text=True,
                    capture_output=True,
                    env=environment,
                )
            self.assertEqual(2, result.returncode)
            self.assertIn("parent directory must be mode 0700", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            ancestor = root / "unsafe-ancestor"
            ancestor.mkdir(mode=0o700)
            parent = ancestor / "private-parent"
            parent.mkdir(mode=0o700)
            environment_file = parent / "spring.env"
            write_environment_file(environment_file, values)
            ancestor.chmod(0o777)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                text=True,
                capture_output=True,
                env=environment,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("group/other-writable non-sticky ancestors", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            child = root / "child"
            child.mkdir(mode=0o700)
            environment_file = root / "spring.env"
            write_environment_file(environment_file, values)
            non_normalized = child / ".." / environment_file.name
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--environment-file", str(non_normalized)],
                text=True,
                capture_output=True,
                env=environment,
            )
        self.assertEqual(2, result.returncode)
        self.assertIn("normalized absolute non-root path", result.stderr)

        secondary_groups = [group for group in os.getgroups() if group != os.getgid()]
        if secondary_groups:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                environment_file = root / "wrong-group.env"
                write_environment_file(environment_file, values)
                os.chown(environment_file, -1, secondary_groups[0])
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--environment-file", str(environment_file)],
                    text=True,
                    capture_output=True,
                    env=environment,
                )
            self.assertEqual(2, result.returncode)
            self.assertIn("must be owned by the current UID/GID", result.stderr)

    def test_environment_file_rejects_identity_or_size_change_after_read(self):
        validator = self.load_validator("spring_launch_validator")
        real_fstat = os.fstat

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment_file = root / "spring.env"
            write_environment_file(environment_file, complete_environment(root))
            for changed_field, field_index in (("identity", 1), ("size", 6)):
                with self.subTest(changed_field=changed_field):
                    calls = 0

                    def changing_fstat(descriptor):
                        nonlocal calls
                        calls += 1
                        details = real_fstat(descriptor)
                        if calls == 2:
                            fields = list(details)
                            fields[field_index] += 1
                            return os.stat_result(fields)
                        return details

                    errors = []
                    with mock.patch.object(validator.os, "fstat", side_effect=changing_fstat):
                        values = validator.parse_environment_file(errors, environment_file)
                    self.assertEqual({}, values)
                    self.assertIn("Spring environment file identity or size changed while it was being read", errors)

    def test_environment_file_rejects_ancestor_identity_change_during_read(self):
        validator = self.load_validator("spring_launch_validator_ancestor_race")
        real_lstat = Path.lstat

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment_file = root / "spring.env"
            write_environment_file(environment_file, complete_environment(root))
            parent_calls = 0

            def changing_parent_identity(path):
                nonlocal parent_calls
                details = real_lstat(path)
                if path == environment_file.parent:
                    parent_calls += 1
                    if parent_calls >= 3:
                        fields = list(details)
                        fields[1] += 1
                        return os.stat_result(fields)
                return details

            errors: list[str] = []
            with mock.patch.object(
                validator.Path,
                "lstat",
                autospec=True,
                side_effect=changing_parent_identity,
            ):
                raw = validator.secure_environment_file_bytes(
                    errors,
                    environment_file,
                    label="Spring environment file",
                )

        self.assertIsNone(raw)
        self.assertIn(
            "Spring environment file identity or size changed while it was being read",
            errors,
        )

    def test_four_hmac_roles_require_distinct_paths_inodes_and_values(self):
        cases = (
            ("path", "Spring HMAC secrets must use four distinct paths"),
            ("hardlink", "must not be hard-linked"),
            ("parent-symlink", "must not traverse symbolic-link parent directories"),
            ("content", "Spring HMAC secrets must use four distinct secret values"),
        )
        for case, expected_error in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                engine_secret = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
                verifier_secret = Path(values["ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH"])
                if case == "path":
                    values["ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH"] = str(engine_secret)
                elif case == "hardlink":
                    outside_secret = root / "outside-role-secret"
                    outside_secret.write_bytes(b"Z" * 32)
                    outside_secret.chmod(0o600)
                    verifier_secret.unlink()
                    os.link(outside_secret, verifier_secret)
                elif case == "parent-symlink":
                    real_parent = root / "real-secret-parent"
                    real_parent.mkdir()
                    parent_secret = real_parent / "engine-secret"
                    parent_secret.write_bytes(b"Y" * 32)
                    parent_secret.chmod(0o600)
                    linked_parent = root / "linked-secret-parent"
                    linked_parent.symlink_to(real_parent, target_is_directory=True)
                    values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"] = str(linked_parent / parent_secret.name)
                else:
                    verifier_secret.write_bytes(engine_secret.read_bytes())
                    verifier_secret.chmod(0o600)
                environment = sanitized_environment()
                environment.update(values)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )
                self.assertEqual(2, result.returncode)
                self.assertIn(expected_error, result.stderr)

    def test_hmac_secret_rejects_ascii_and_unicode_boundary_whitespace(self):
        for suffix in (
            b"\n",
            "\u0085".encode("utf-8"),
            "\u00a0".encode("utf-8"),
            "\ufeff".encode("utf-8"),
        ):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                secret = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
                secret.write_bytes(b"A" * 32 + suffix)
                secret.chmod(0o600)
                environment = sanitized_environment()
                environment.update(values)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )

                self.assertEqual(2, result.returncode)
                self.assertIn("must not have leading or trailing whitespace", result.stderr)

    def test_runtime_paths_bind_owner_group_and_secret_parent_contract(self):
        validator = self.load_validator("spring_launch_validator_runtime_owner")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            secret = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
            replay = Path(values["ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH"])

            valid_secret, _, _, secret_failure = validator.inspect_secret_file(
                secret,
                expected_uid=os.getuid() + 1,
                expected_gid=os.getgid(),
            )
            valid_replay, _, replay_failure = validator.inspect_owner_only_directory(
                replay,
                expected_uid=os.getuid(),
                expected_gid=os.getgid() + 1,
            )
            root.chmod(0o755)
            valid_parent, _, _, parent_failure = validator.inspect_secret_file(
                secret,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
            )

        self.assertFalse(valid_secret)
        self.assertIn("UID/GID", secret_failure or "")
        self.assertFalse(valid_replay)
        self.assertIn("UID/GID", replay_failure or "")
        self.assertFalse(valid_parent)
        self.assertIn("parent directory", parent_failure or "")

    def test_runtime_paths_reject_writable_non_sticky_ancestors(self):
        validator = self.load_validator("spring_launch_validator_runtime_ancestors")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            unsafe_ancestor = root / "unsafe"
            unsafe_ancestor.mkdir(mode=0o700)
            secret_parent = unsafe_ancestor / "secrets"
            secret_parent.mkdir(mode=0o700)
            secret = secret_parent / "engine-hmac"
            secret.write_bytes(b"A" * 32)
            secret.chmod(0o600)
            workspace = unsafe_ancestor / "workspace"
            workspace.mkdir(mode=0o700)
            unsafe_ancestor.chmod(0o777)

            valid_secret, _, _, secret_failure = validator.inspect_secret_file(secret)
            valid_workspace, _, workspace_failure = (
                validator.inspect_owner_only_directory(workspace)
            )

        self.assertFalse(valid_secret)
        self.assertIn("group/other-writable non-sticky ancestors", secret_failure or "")
        self.assertFalse(valid_workspace)
        self.assertIn(
            "group/other-writable non-sticky ancestors", workspace_failure or ""
        )

    def test_security_sensitive_paths_reject_foreign_owned_ancestors(self):
        validator = self.load_validator("spring_launch_validator_foreign_ancestors")
        real_lstat = Path.lstat
        foreign_uid = max(os.getuid(), 0) + 20_000

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            root.chmod(0o700)
            foreign_ancestor = root / "foreign"
            foreign_ancestor.mkdir(mode=0o755)
            private_parent = foreign_ancestor / "private"
            private_parent.mkdir(mode=0o700)
            secret = private_parent / "engine-hmac"
            secret.write_bytes(b"A" * 32)
            secret.chmod(0o600)
            environment_file = private_parent / "spring.env"
            environment_file.write_text("ELMOS_SPRING_PROXY_ENABLED=true\n")
            environment_file.chmod(0o600)
            workspace = foreign_ancestor / "workspace"
            workspace.mkdir(mode=0o700)

            def foreign_owner(path):
                details = real_lstat(path)
                if path == foreign_ancestor:
                    fields = list(details)
                    fields[4] = foreign_uid
                    return os.stat_result(fields)
                return details

            environment_errors: list[str] = []
            with mock.patch.object(
                validator.Path,
                "lstat",
                autospec=True,
                side_effect=foreign_owner,
            ):
                environment_bytes = validator.secure_environment_file_bytes(
                    environment_errors,
                    environment_file,
                    label="Spring environment file",
                )
                valid_secret, _, _, secret_failure = validator.inspect_secret_file(
                    secret
                )
                valid_workspace, _, workspace_failure = (
                    validator.inspect_owner_only_directory(workspace)
                )

        self.assertIsNone(environment_bytes)
        self.assertTrue(
            any("owned outside root/current UID" in error for error in environment_errors),
            environment_errors,
        )
        self.assertFalse(valid_secret)
        self.assertIn("owned outside root/runtime UID", secret_failure or "")
        self.assertFalse(valid_workspace)
        self.assertIn("owned outside root/runtime UID", workspace_failure or "")

    def test_hmac_secrets_are_isolated_from_workspace_and_replay_state(self):
        for location, expected in (
            ("workspace", "shared Spring workspace"),
            ("replay", "Spring replay state"),
        ):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                old_secret = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
                protected = Path(
                    values[
                        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH"
                        if location == "workspace"
                        else "ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH"
                    ]
                )
                nested = protected / "engine-secret"
                nested.write_bytes(old_secret.read_bytes())
                nested.chmod(0o600)
                old_secret.unlink()
                values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"] = str(nested)
                environment = sanitized_environment()
                environment.update(values)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )

            self.assertEqual(2, result.returncode)
            self.assertIn(f"Spring HMAC secrets must be isolated from {expected}", result.stderr)

    def test_web_console_resend_secret_is_owner_only_and_not_reused(self):
        cases = {
            "missing": "web-console Resend secret",
            "permissions": "web-console Resend secret",
            "same_value": "must not reuse a Spring HMAC value",
            "workspace": "must be isolated from shared Spring workspace",
        }
        for case, expected in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                spring_file = root / "spring.env"
                compose_file = root / "elmos.env"
                resend = root / "resend-api-key"
                secret_root = root
                if case == "missing":
                    resend.unlink()
                elif case == "permissions":
                    resend.chmod(0o644)
                elif case == "same_value":
                    resend.write_bytes((root / "secret-0").read_bytes())
                elif case == "workspace":
                    secret_root = Path(
                        values["ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH"]
                    )
                    resend = secret_root / "resend-api-key"
                    resend.write_bytes(b"E" * 32)
                    resend.chmod(0o600)
                write_environment_file(spring_file, values)
                write_environment_file(
                    compose_file,
                    {
                        "ELMOS_ENV_FILE": str(compose_file),
                        "ELMOS_SECRET_ROOT": str(secret_root),
                        "NODE_ENV": "production",
                        "ELMOS_DATABASE_URL": (
                            "jdbc:postgresql://database.example/elmos?sslmode=require"
                        ),
                    },
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--environment-file",
                        str(spring_file),
                        "--compose-environment-file",
                        str(compose_file),
                    ],
                    text=True,
                    capture_output=True,
                    env=sanitized_environment(),
                )

                self.assertEqual(2, result.returncode)
                self.assertIn(expected, result.stderr)

    def test_cross_file_secret_rotation_cannot_escape_the_group_snapshot(self):
        validator = self.load_validator("spring_launch_validator_secret_group")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = complete_environment(root)
            first = Path(values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"])
            second = Path(values["ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH"])
            original = validator.inspect_secret_file
            rotated = False

            def inspect_then_rotate(path, **kwargs):
                nonlocal rotated
                result = original(path, **kwargs)
                if path == first and result[0] and not rotated:
                    first.write_bytes(second.read_bytes())
                    first.chmod(0o600)
                    rotated = True
                return result

            errors: list[str] = []
            with mock.patch.object(
                validator,
                "inspect_secret_file",
                side_effect=inspect_then_rotate,
            ):
                validator.validate_environment(errors, values)

        self.assertTrue(rotated)
        self.assertTrue(
            any("secret group" in error or "secret set changed" in error for error in errors),
            errors,
        )

    def test_persistent_replay_directory_is_owner_only_and_workspace_isolated(self):
        cases = ("mode", "symlink", "workspace", "missing")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                replay = Path(values["ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH"])
                if case == "mode":
                    replay.chmod(0o755)
                elif case == "symlink":
                    target = root / "real-replay"
                    target.mkdir(mode=0o700)
                    replay.rmdir()
                    replay.symlink_to(target, target_is_directory=True)
                elif case == "workspace":
                    replay.rmdir()
                    values["ELMOS_SPRING_ENGINE_REPLAY_HOST_PATH"] = values[
                        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH"
                    ]
                    Path(values["ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH"]).chmod(0o700)
                else:
                    replay.rmdir()
                environment = sanitized_environment()
                environment.update(values)

                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--check-environment"],
                    text=True,
                    capture_output=True,
                    env=environment,
                )

                self.assertEqual(2, result.returncode)
                self.assertIn("replay", result.stderr.lower())

    def test_environment_file_rejects_relative_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for path, expected_error in (
                (Path("spring.env"), "normalized absolute non-root path"),
                (root / "missing.env", "missing or unreadable"),
            ):
                with self.subTest(path=path):
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "--environment-file", str(path)],
                        text=True,
                        capture_output=True,
                        env=sanitized_environment(),
                    )
                    self.assertEqual(2, result.returncode)
                    self.assertIn(expected_error, result.stderr)

    def test_template_and_make_target_are_wired_to_the_strict_loader(self):
        template_keys = {
            line.split("=", 1)[0]
            for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        }
        self.assertEqual(set(SPRING_ENVIRONMENT_KEYS), template_keys)
        makefile = MAKEFILE.read_text(encoding="utf-8")
        self.assertIn('test -n "$${SPRING_ENV_FILE}"', makefile)
        self.assertIn('--environment-file "$${SPRING_ENV_FILE}"', makefile)
        self.assertIn('test -n "$${ELMOS_ENV_FILE}"', makefile)
        self.assertIn('--compose-environment-file "$${ELMOS_ENV_FILE}"', makefile)
        self.assertIn('test -n "$${SPRING_TRUST_STORE}"', makefile)
        self.assertIn('--trust-store "$${SPRING_TRUST_STORE}"', makefile)
        self.assertIn('test -n "$${SPRING_TRUST_STORE_DIGEST}"', makefile)
        self.assertIn(
            '--expected-trust-store-digest "$${SPRING_TRUST_STORE_DIGEST}"',
            makefile,
        )
        self.assertIn('test -n "$${SPRING_EVIDENCE_ROOT}"', makefile)
        self.assertIn('--evidence-root "$${SPRING_EVIDENCE_ROOT}"', makefile)
        self.assertIn('test -n "$${SPRING_EXPECTED_REVISION}"', makefile)
        self.assertIn('--expected-revision "$${SPRING_EXPECTED_REVISION}"', makefile)
        self.assertIn(
            'test -n "$${SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST}"', makefile
        )
        self.assertIn(
            '--expected-worker-application-artifact-digest "$${SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST}"',
            makefile,
        )
        self.assertIn('--worker-container "$${SPRING_WORKER_CONTAINER}"', makefile)
        self.assertIn(
            '--expected-worker-image-digest "$${SPRING_WORKER_IMAGE_DIGEST}"',
            makefile,
        )
        for variable, option in (
            ("SPRING_ENVIRONMENT_ID", "--expected-environment-id"),
            ("SPRING_DEPLOYMENT_ID", "--expected-deployment-id"),
            ("SPRING_PROVIDER", "--expected-provider"),
            ("SPRING_REGION", "--expected-region"),
            ("SPRING_ENVIRONMENT_CLASS", "--expected-environment-class"),
        ):
            self.assertIn(f'test -n "$${{{variable}}}"', makefile)
            self.assertIn(f'{option} "$${{{variable}}}"', makefile)
        self.assertIn("spring-launch-gate: spring-runner-validate", makefile)

    def test_make_targets_do_not_shell_interpolate_external_parameters(self):
        launch_values = {
            "SPRING_EXTERNAL_EVIDENCE": "/evidence/receipt.json",
            "SPRING_ENV_FILE": "/config/spring.env",
            "ELMOS_ENV_FILE": "/config/elmos.env",
            "SPRING_TRUST_STORE": "/evidence/trust.json",
            "SPRING_TRUST_STORE_DIGEST": "sha256:" + "a" * 64,
            "SPRING_EVIDENCE_ROOT": "/evidence",
            "SPRING_ENVIRONMENT_ID": "production-1",
            "SPRING_DEPLOYMENT_ID": "deployment-1",
            "SPRING_PROVIDER": "provider-1",
            "SPRING_REGION": "region-1",
            "SPRING_ENVIRONMENT_CLASS": "PRODUCTION",
            "SPRING_EXPECTED_REVISION": "b" * 40,
            "SPRING_WORKER_APPLICATION_ARTIFACT_DIGEST": "sha256:" + "c" * 64,
        }
        web_values = {
            "SPRING_WEB_CONTAINER": "elmos-web-1",
            "SPRING_WEB_IMAGE_DIGEST": "sha256:" + "d" * 64,
            "SPRING_WORKER_CONTAINER": "elmos-worker-1",
            "SPRING_WORKER_IMAGE_DIGEST": "sha256:" + "e" * 64,
            "SPRING_WEB_COLLECTOR_ID": "collector-1",
            "SPRING_WEB_RUNTIME_ATTESTATION_OUTPUT": "/evidence/web-runtime.json",
        }
        for target, values in (
            ("spring-launch-gate", launch_values),
            ("spring-web-runtime-attestation", web_values),
        ):
            for attacked in values:
                for attack_kind in ("shell", "make"):
                    with (
                        self.subTest(
                            target=target,
                            attacked=attacked,
                            attack_kind=attack_kind,
                        ),
                        tempfile.TemporaryDirectory() as temporary,
                    ):
                        marker = Path(temporary) / "injection-marker"
                        supplied = dict(values)
                        supplied[attacked] = (
                            f'"; touch {marker}; #'
                            if attack_kind == "shell"
                            else f"$(shell touch {marker})"
                        )
                        result = subprocess.run(
                            [
                                "make",
                                "--no-print-directory",
                                "-f",
                                str(MAKEFILE),
                                target,
                                "BATCH30_PYTHON=true",
                                *(f"{name}={value}" for name, value in supplied.items()),
                            ],
                            cwd=ROOT,
                            text=True,
                            capture_output=True,
                        )
                        self.assertEqual(
                            0, result.returncode, result.stdout + result.stderr
                        )
                        self.assertFalse(
                            marker.exists(),
                            f"{attacked} executed {attack_kind} input",
                        )

    def test_external_verification_rechecks_environment_and_mount_snapshots(self):
        specification = importlib.util.spec_from_file_location(
            "spring_launch_validator_post_external_snapshot", SCRIPT
        )
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        validator = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = validator
        specification.loader.exec_module(validator)

        for rotated in ("environment", "secret"):
            with self.subTest(rotated=rotated), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = complete_environment(root)
                for name in (
                    "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL",
                    "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL",
                    "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL",
                ):
                    values[name] = "https://runner.spring.acme"
                spring_file = root / "spring.env"
                compose_file = root / "elmos.env"
                write_environment_file(spring_file, values)
                write_compose_environment_file(compose_file, values)
                engine_secret = Path(
                    values["ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH"]
                )

                def rotate_during_external_verification(*_args, **_kwargs):
                    if rotated == "environment":
                        replacement = root / "replacement-spring.env"
                        write_environment_file(replacement, values)
                        os.replace(replacement, spring_file)
                    else:
                        replacement = root / "replacement-engine-hmac"
                        replacement.write_bytes(b"Z" * 32)
                        replacement.chmod(0o600)
                        os.replace(replacement, engine_secret)
                    return {
                        "evidence_status": "VERIFIED_EXTERNAL_RECEIPT",
                        "external_evidence_intake": "VALIDATED_NOT_CERTIFIED",
                        "certification": "NOT_CERTIFIED",
                        "certification_promoted": False,
                    }

                arguments = [
                    str(SCRIPT),
                    "--environment-file",
                    str(spring_file),
                    "--compose-environment-file",
                    str(compose_file),
                    "--external-evidence",
                    str(root / "receipt.json"),
                    "--trust-store",
                    str(root / "trust-store.json"),
                    "--evidence-root",
                    str(root),
                    "--expected-revision",
                    "a" * 40,
                    "--expected-trust-store-digest",
                    "sha256:" + "b" * 64,
                    "--expected-environment-id",
                    "production-1",
                    "--expected-deployment-id",
                    "deployment-1",
                    "--expected-provider",
                    "provider-1",
                    "--expected-region",
                    "region-1",
                    "--expected-environment-class",
                    "PRODUCTION",
                    "--expected-worker-application-artifact-digest",
                    "sha256:" + "c" * 64,
                ]
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    mock.patch.object(sys, "argv", arguments),
                    mock.patch.dict(os.environ, sanitized_environment(), clear=True),
                    mock.patch.object(
                        validator, "APPLICATION_RUNTIME_UID", os.getuid()
                    ),
                    mock.patch.object(
                        validator, "APPLICATION_RUNTIME_GID", os.getgid()
                    ),
                    mock.patch.object(
                        validator,
                        "validate_external",
                        side_effect=rotate_during_external_verification,
                    ),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    result = validator.main()

                self.assertEqual(2, result, stdout.getvalue() + stderr.getvalue())
                self.assertIn(
                    "launch environment or mount binding changed during external evidence verification",
                    stderr.getvalue(),
                )
                self.assertNotIn("EXTERNAL_GATE_VERIFIED", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
