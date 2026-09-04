import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

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
        ):
            environment.pop(name)
    return environment


def complete_environment(root: Path) -> dict[str, str]:
    workspace = root / "workspace"
    workspace.mkdir()
    secrets = []
    for index in range(4):
        secret = root / f"secret-{index}"
        secret.write_bytes(bytes([65 + index]) * 32)
        secret.chmod(0o600)
        secrets.append(secret)
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
        "ELMOS_SPRING_UPGRADE_VERIFIER_BASE_URL": "https://runner.example.test/verifier",
        "ELMOS_SPRING_TRANSFORMER_BROKER_BASE_URL": "https://runner.example.test/transformer",
        "ELMOS_SPRING_RUNTIME_RUNNER_BASE_URL": "https://runner.example.test/runtime",
        "ELMOS_JAVA_UPGRADE_WORKSPACE_HOST_PATH": str(workspace),
        "ELMOS_SPRING_ENGINE_HMAC_SECRET_HOST_PATH": str(secrets[0]),
        "ELMOS_VERIFIER_HMAC_SECRET_HOST_PATH": str(secrets[1]),
        "ELMOS_TRANSFORMER_HMAC_SECRET_HOST_PATH": str(secrets[2]),
        "ELMOS_SPRING_RUNTIME_HMAC_SECRET_HOST_PATH": str(secrets[3]),
    }


def write_environment_file(path: Path, values: dict[str, str], extra_lines: tuple[str, ...] = ()) -> None:
    lines = ["# Spring launch test environment"]
    lines.extend(f"{name}={value}" for name, value in values.items())
    lines.extend(extra_lines)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


class SpringLaunchReadinessTests(unittest.TestCase):
    def test_repository_contract_is_ready_only_for_external_gate(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SPRING_LAUNCH_GATE=READY_FOR_EXTERNAL_GATE", result.stdout)
        self.assertIn("EXTERNAL_EVIDENCE_INTAKE=NOT_RUN", result.stdout)
        self.assertIn("CERTIFICATION=NOT_CERTIFIED", result.stdout)

    def test_production_mode_fails_without_external_evidence(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--require-production-evidence"],
            text=True,
            capture_output=True,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("production evidence is required", result.stderr)

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

    def test_environment_preflight_rejects_unsafe_https_endpoints(self):
        cases = (
            "http://runner.production.example/verifier",
            "https://user:password@runner.production.example/verifier",
            "https://localhost/verifier",
            "https://127.0.0.1/verifier",
            "https://[::1]/verifier",
            "https://runner.production.example/verifier#mutable",
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

    def test_environment_file_rejects_identity_or_size_change_after_read(self):
        specification = importlib.util.spec_from_file_location("spring_launch_validator", SCRIPT)
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        validator = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(validator)
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

    def test_environment_file_rejects_relative_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for path, expected_error in (
                (Path("spring.env"), "path must be absolute"),
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
        self.assertIn('test -n "$(SPRING_ENV_FILE)"', makefile)
        self.assertIn('--environment-file "$(SPRING_ENV_FILE)"', makefile)
        self.assertIn('test -n "$(SPRING_TRUST_STORE)"', makefile)
        self.assertIn('--trust-store "$(SPRING_TRUST_STORE)"', makefile)
        self.assertIn('test -n "$(SPRING_TRUST_STORE_DIGEST)"', makefile)
        self.assertIn(
            '--expected-trust-store-digest "$(SPRING_TRUST_STORE_DIGEST)"',
            makefile,
        )
        self.assertIn('test -n "$(SPRING_EVIDENCE_ROOT)"', makefile)
        self.assertIn('--evidence-root "$(SPRING_EVIDENCE_ROOT)"', makefile)
        for variable, option in (
            ("SPRING_ENVIRONMENT_ID", "--expected-environment-id"),
            ("SPRING_DEPLOYMENT_ID", "--expected-deployment-id"),
            ("SPRING_PROVIDER", "--expected-provider"),
            ("SPRING_REGION", "--expected-region"),
            ("SPRING_ENVIRONMENT_CLASS", "--expected-environment-class"),
        ):
            self.assertIn(f'test -n "$({variable})"', makefile)
            self.assertIn(f'{option} "$({variable})"', makefile)
        self.assertIn("spring-launch-gate: spring-runner-validate", makefile)


if __name__ == "__main__":
    unittest.main()
