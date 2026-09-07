from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.operations import run_spring_docker_smoke as smoke_runner


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = {
    "runtime": ROOT / "apps/java-runtime-runner/Dockerfile",
    "transformer": ROOT / "apps/java-engine-transformer/Dockerfile",
    "verifier": ROOT / "apps/java-engine-verifier/Dockerfile",
}


class SpringDockerBuildContractTest(unittest.TestCase):
    def assert_networked_maven_downloads_are_serial(
        self,
        dockerfile: str,
        *,
        expected_invocations: int,
    ) -> None:
        invocations = dockerfile.count("mvn -B --strict-checksums")
        serial_flags = re.findall(r"-Dmaven\.artifact\.threads=([^ \\\n]+)", dockerfile)
        self.assertEqual(expected_invocations, invocations)
        self.assertEqual(["1"] * expected_invocations, serial_flags)

    def test_every_base_image_is_digest_pinned_and_runtime_users_are_explicit(self) -> None:
        contents = {key: path.read_text(encoding="utf-8") for key, path in DOCKERFILES.items()}
        for key, dockerfile in contents.items():
            stage_aliases: set[str] = set()
            for line in dockerfile.splitlines():
                if line.startswith("FROM "):
                    fields = line.split()
                    image = fields[1]
                    if image != "scratch" and image not in stage_aliases:
                        self.assertRegex(
                            image, r"@sha256:[0-9a-f]{64}$", f"{key}: {line}"
                        )
                        self.assertNotIn(":latest", image, f"{key}: {line}")
                    if len(fields) == 4 and fields[2].upper() == "AS":
                        stage_aliases.add(fields[3])
        self.assertIn("USER 10003:10003", contents["runtime"])
        self.assertIn("USER 10001:10001", contents["transformer"])
        self.assertIn("USER 10002:10002", contents["verifier"])

    def test_networked_maven_builds_are_bounded_and_checksum_strict(self) -> None:
        expected_invocations = {"transformer": 4, "verifier": 4}
        for key in ("transformer", "verifier"):
            dockerfile = DOCKERFILES[key].read_text(encoding="utf-8")
            self.assertNotIn("maven.wagon.http.retryHandler.count=0", dockerfile)
            self.assertIn("--strict-checksums", dockerfile)
            self.assertIn("maven.wagon.http.retryHandler.count=5", dockerfile)
            self.assertIn("if [ \"$attempt\" -ge 3 ]; then exit 1; fi", dockerfile)
            self.assertIn("-name '*.part'", dockerfile)
            self.assert_networked_maven_downloads_are_serial(
                dockerfile,
                expected_invocations=expected_invocations[key],
            )

    def test_networked_maven_contract_rejects_parallel_artifact_downloads(self) -> None:
        dockerfile = DOCKERFILES["verifier"].read_text(encoding="utf-8")
        mutated = dockerfile.replace(
            "-Dmaven.artifact.threads=1",
            "-Dmaven.artifact.threads=5",
            1,
        )
        with self.assertRaises(AssertionError):
            self.assert_networked_maven_downloads_are_serial(
                mutated,
                expected_invocations=4,
            )

    def test_verifier_seed_cache_survives_a_failed_build_attempt(self) -> None:
        dockerfile = DOCKERFILES["verifier"].read_text(encoding="utf-8")
        cache_id = "id=elmos-java-engine-verifier-maven-3.9.11"
        self.assertEqual(4, dockerfile.count(cache_id))
        self.assertEqual(3, dockerfile.count("-Dmaven.repo.local=/opt/elmos/maven-cache"))
        self.assertIn(
            "cp -R /tmp/elmos-verifier-maven-cache/. /opt/elmos/maven-cache/",
            dockerfile,
        )

    def test_all_images_bind_the_authoritative_clean_source_contract(self) -> None:
        for key in ("runtime", "transformer", "verifier"):
            dockerfile = DOCKERFILES[key].read_text(encoding="utf-8")
            self.assertIn("AS source-context-digest", dockerfile)
            self.assertIn("/opt/elmos/source-context.sha256", dockerfile)
            self.assertIn("/opt/elmos/source-status.sha256", dockerfile)
            self.assertIn("ARG ELMOS_SOURCE_REVISION", dockerfile)
            self.assertIn("ARG ELMOS_SOURCE_CONTEXT_SHA256", dockerfile)
            self.assertIn("ARG ELMOS_SOURCE_STATUS_SHA256", dockerfile)
            self.assertIn("io.elmos.build.context-sha256", dockerfile)
            self.assertIn("io.elmos.build.context-status-sha256", dockerfile)
            self.assertIn('io.elmos.build.source-status="CLEAN_SOURCE"', dockerfile)
            self.assertIn('io.elmos.build.source-dirty="false"', dockerfile)

    def test_transformer_rewrite_retries_from_an_immutable_clean_seed(self) -> None:
        dockerfile = DOCKERFILES["transformer"].read_text(encoding="utf-8")
        self.assertIn("chmod -R a-w /tmp/elmos-seed-source", dockerfile)
        retry_loop = re.search(
            r"while :; do(?P<body>.*?)done; \\\n    attempt=1;",
            dockerfile,
            re.DOTALL,
        )
        self.assertIsNotNone(retry_loop)
        body = retry_loop.group("body") if retry_loop else ""
        remove = body.find("rm -rf /tmp/elmos-rewrite-project")
        copy = body.find("cp -R /tmp/elmos-seed-source /tmp/elmos-rewrite-project")
        rewrite = body.find("org.openrewrite.maven:rewrite-maven-plugin:6.44.0:run")
        self.assertGreaterEqual(remove, 0)
        self.assertGreater(copy, remove)
        self.assertGreater(rewrite, copy)
        self.assertIn("chmod -R u+w /tmp/elmos-rewrite-project", body)
        self.assertNotIn("-f /tmp/elmos-seed-project/pom.xml", dockerfile)

    def test_smoke_runner_enforces_hardened_container_options(self) -> None:
        smoke = (ROOT / "scripts/operations/run_spring_docker_smoke.py").read_text(
            encoding="utf-8"
        )
        for option in (
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--pids-limit=",
            "LOCAL_NON_CERTIFYING_CONTAINER_SMOKE",
            "docker",
            "network",
            "create",
            "--internal",
            "unique_internal_bridge",
            "io.elmos.build.context-sha256",
            "io.elmos.build.context-status-sha256",
            "io.elmos.build.source-status",
            "io.elmos.build.source-dirty",
            "LOCAL_NON_CERTIFYING",
            "CLEAN_SOURCE",
            "DIRTY_SOURCE",
            "expected_image_id",
            "runtime_context_digest",
            "/opt/elmos/source-status.sha256",
        ):
            self.assertIn(option, smoke)
        self.assertRegex(smoke, re.compile(r"docker.*,.*rm.*,.*--force", re.DOTALL))
        self.assertRegex(smoke, re.compile(r"docker.*,.*network.*,.*rm", re.DOTALL))
        self.assertNotIn('"--publish"', smoke)
        self.assertNotIn('["docker", "port"', smoke)
        self.assertIn('"host_port_published": False', smoke)
        self.assertIn(
            '"source": "generated_in_process_ephemeral_container_env"', smoke
        )
        self.assertIn('"container_removed_in_finally": True', smoke)
        self.assertIn('"value_recorded": False', smoke)
        self.assertIn('"digest_recorded": False', smoke)

    def test_service_command_keeps_secret_value_out_of_argv(self) -> None:
        spec = smoke_runner.ServiceImage(
            "transformer",
            "transformer:test",
            f"sha256:{'a' * 64}",
            "b" * 64,
            "c" * 64,
            "CLEAN_SOURCE",
            "10001:10001",
            8083,
            ("/workspace",),
            "ELMOS_TRANSFORMER_HMAC_SECRET_VALUE",
        )
        command = smoke_runner.service_run_command(
            spec,
            container="transformer-smoke",
            network="internal-smoke",
        )

        self.assertNotIn("--publish", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop=ALL", command)
        self.assertIn("--security-opt=no-new-privileges:true", command)
        self.assertEqual("internal-smoke", command[command.index("--network") + 1])
        self.assertEqual(
            "ELMOS_TRANSFORMER_HMAC_SECRET_VALUE",
            command[command.index("--env") + 1],
        )
        self.assertFalse(any("=" in item and "HMAC_SECRET" in item for item in command))

    def test_run_forwards_secret_via_process_environment_only(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["docker", "run"],
            returncode=0,
            stdout="container-id\n",
            stderr="",
        )
        with patch.object(smoke_runner.subprocess, "run", return_value=completed) as run:
            smoke_runner.run(
                ["docker", "run", "--env", "ELMOS_TEST_SECRET"],
                env={"ELMOS_TEST_SECRET": "memory-only-test-value"},
            )

        invoked_command = run.call_args.args[0]
        invoked_environment = run.call_args.kwargs["env"]
        self.assertNotIn("memory-only-test-value", invoked_command)
        self.assertEqual("memory-only-test-value", invoked_environment["ELMOS_TEST_SECRET"])

    def test_readiness_probe_is_loopback_only_and_bounded(self) -> None:
        command = smoke_runner.readiness_probe_command("transformer-smoke", 8083)
        self.assertEqual(("docker", "exec", "transformer-smoke"), tuple(command[:3]))
        self.assertIn("/usr/bin/curl", command)
        self.assertIn("--disable", command)
        self.assertIn("--connect-timeout", command)
        self.assertIn("--max-time", command)
        self.assertIn("--max-filesize", command)
        self.assertIn("=http", command)
        self.assertIn("=none", command)
        self.assertIn("--noproxy", command)
        self.assertEqual(
            "http://127.0.0.1:8083/actuator/health/readiness",
            command[-1],
        )

    def test_readiness_response_requires_200_json_object_and_top_level_up(self) -> None:
        valid = (
            '{"status":"UP","components":{"db":{"status":"UP"}}}'
            "\nELMOS_HTTP_META:200:application/vnd.spring-boot.actuator.v3+json\n"
        )
        self.assertEqual("UP", smoke_runner.parse_readiness_response(valid)["status"])

        invalid_responses = (
            '{"status":"UP"}\nELMOS_HTTP_META:503:application/json\n',
            '{"status":"UP"}\nELMOS_HTTP_META:200:text/plain\n',
            '[{"status":"UP"}]\nELMOS_HTTP_META:200:application/json\n',
            '{"component":{"status":"UP"}}\nELMOS_HTTP_META:200:application/json\n',
            'not-json\nELMOS_HTTP_META:200:application/json\n',
        )
        for response in invalid_responses:
            with self.subTest(response=response):
                with self.assertRaises(RuntimeError):
                    smoke_runner.parse_readiness_response(response)

    def test_readiness_failure_redacts_ephemeral_secret_from_service_logs(self) -> None:
        startup_secret = "memory-only-secret-value-with-more-than-32-bytes"
        stopped = subprocess.CompletedProcess(
            args=["docker", "inspect"],
            returncode=0,
            stdout="false\n",
            stderr="",
        )
        logs = subprocess.CompletedProcess(
            args=["docker", "logs"],
            returncode=0,
            stdout=f"startup rejected {startup_secret}\n",
            stderr="",
        )
        with (
            patch.object(smoke_runner, "run", side_effect=(stopped, logs)),
            patch.object(smoke_runner.time, "monotonic", side_effect=(0.0, 0.1)),
        ):
            with self.assertRaises(RuntimeError) as raised:
                smoke_runner.wait_for_readiness(
                    "transformer-smoke",
                    8083,
                    startup_secret=startup_secret,
                    timeout_seconds=1,
                )

        self.assertNotIn(startup_secret, str(raised.exception))
        self.assertIn("[REDACTED]", str(raised.exception))

    def test_docker_run_timeout_and_existing_container_report_orphan_risk(self) -> None:
        spec = smoke_runner.ServiceImage(
            "transformer",
            "transformer:test",
            f"sha256:{'a' * 64}",
            "b" * 64,
            "c" * 64,
            "CLEAN_SOURCE",
            "10001:10001",
            8083,
            ("/workspace",),
            "ELMOS_TRANSFORMER_HMAC_SECRET_VALUE",
        )
        successful = subprocess.CompletedProcess([], 0, "", "")
        internal = subprocess.CompletedProcess([], 0, "true\n", "")
        cleanup_failed = subprocess.CompletedProcess([], 1, "", "daemon unavailable")
        still_exists = subprocess.CompletedProcess([], 0, '[{"Id":"remaining"}]\n', "")
        network_absent = subprocess.CompletedProcess(
            [],
            1,
            "[]\n",
            "Error response from daemon: network "
            "elmos-spring-smoke-net-transformer-aaaaaaaaaa not found\n",
        )
        with (
            patch.object(
                smoke_runner.uuid,
                "uuid4",
                return_value=type("Uuid", (), {"hex": "a" * 32})(),
            ),
            patch.object(
                smoke_runner,
                "run",
                side_effect=(
                    successful,
                    internal,
                    subprocess.TimeoutExpired(["docker", "run"], 120),
                    cleanup_failed,
                    still_exists,
                    successful,
                    network_absent,
                ),
            ),
        ):
            with self.assertRaises(RuntimeError) as raised:
                smoke_runner.smoke_service(spec)

        message = str(raised.exception)
        self.assertIn("timed out", message)
        self.assertIn("cleanup/orphan risk", message)
        self.assertIn("container=elmos-spring-smoke-transformer-", message)
        self.assertIn("still exists after cleanup", message)

    def test_container_remove_exception_still_cleans_and_inspects_network(self) -> None:
        container_absent = subprocess.CompletedProcess(
            [],
            1,
            "[]\n",
            "Error response from daemon: No such container: smoke-container\n",
        )
        network_removed = subprocess.CompletedProcess([], 0, "smoke-network\n", "")
        network_absent = subprocess.CompletedProcess(
            [],
            1,
            "[]\n",
            "Error response from daemon: network smoke-network not found\n",
        )
        with patch.object(
            smoke_runner,
            "run",
            side_effect=(
                subprocess.TimeoutExpired(["docker", "rm"], 45),
                container_absent,
                network_removed,
                network_absent,
            ),
        ) as run:
            errors = smoke_runner.cleanup_smoke_resources(
                "smoke-container",
                "smoke-network",
            )

        self.assertTrue(any("container=smoke-container remove raised" in e for e in errors))
        self.assertEqual(4, run.call_count)
        self.assertEqual(
            ["docker", "network", "rm", "smoke-network"],
            run.call_args_list[2].args[0],
        )
        self.assertEqual(
            ["docker", "network", "inspect", "smoke-network"],
            run.call_args_list[3].args[0],
        )

    def test_clean_source_contract_is_explicit_and_fail_closed(self) -> None:
        image_id = f"sha256:{'a' * 64}"
        context_digest = "b" * 64
        status_digest = "c" * 64
        labels = {
            "org.opencontainers.image.revision": "revision",
            "io.elmos.evidence.scope": "spring-modernization-local",
            "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
            "io.elmos.build.source-status": "CLEAN_SOURCE",
            "io.elmos.build.source-dirty": "false",
            "io.elmos.build.context-sha256": context_digest,
            "io.elmos.build.context-status-sha256": status_digest,
        }
        record = {
            "Id": image_id,
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {"User": "10001:10001", "Labels": labels},
        }
        with patch.object(smoke_runner, "image_inspect", return_value=record):
            result = smoke_runner.assert_image_contract(
                "transformer:test",
                "10001:10001",
                image_id,
                "revision",
                expected_context_digest=context_digest,
                expected_source_status_digest=status_digest,
                expected_source_state="CLEAN_SOURCE",
            )
            self.assertEqual(
                "false",
                result["verified_labels"]["io.elmos.build.source-dirty"],
            )

            labels["io.elmos.build.source-dirty"] = "true"
            with self.assertRaisesRegex(RuntimeError, "source-dirty"):
                smoke_runner.assert_image_contract(
                    "transformer:test",
                    "10001:10001",
                    image_id,
                    "revision",
                    expected_context_digest=context_digest,
                    expected_source_status_digest=status_digest,
                    expected_source_state="CLEAN_SOURCE",
                )

    def test_dirty_source_contract_remains_compatible(self) -> None:
        image_id = f"sha256:{'d' * 64}"
        context_digest = "e" * 64
        status_digest = "f" * 64
        labels = {
            "org.opencontainers.image.revision": "revision",
            "io.elmos.evidence.scope": "spring-modernization-local",
            "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
            "io.elmos.build.source-status": "DIRTY_SOURCE",
            "io.elmos.build.source-dirty": "true",
            "io.elmos.build.context-sha256": context_digest,
            "io.elmos.build.context-status-sha256": status_digest,
        }
        record = {
            "Id": image_id,
            "Os": "linux",
            "Architecture": "arm64",
            "Config": {"User": "10002:10002", "Labels": labels},
        }
        with patch.object(smoke_runner, "image_inspect", return_value=record):
            result = smoke_runner.assert_image_contract(
                "verifier:test",
                "10002:10002",
                image_id,
                "revision",
                expected_context_digest=context_digest,
                expected_source_status_digest=status_digest,
                expected_source_state="DIRTY_SOURCE",
            )
        self.assertEqual(
            "true",
            result["verified_labels"]["io.elmos.build.source-dirty"],
        )

    def test_source_contract_rejects_partial_or_malformed_digests(self) -> None:
        image_id = f"sha256:{'1' * 64}"
        record = {
            "Id": image_id,
            "Os": "linux",
            "Config": {"User": "10001:10001", "Labels": {}},
        }
        with patch.object(smoke_runner, "image_inspect", return_value=record):
            with self.assertRaisesRegex(RuntimeError, "non-empty"):
                smoke_runner.assert_image_contract(
                    "transformer:test",
                    "10001:10001",
                    image_id,
                    "revision",
                    expected_context_digest="a" * 64,
                    expected_source_status_digest="",
                    expected_source_state="",
                )
            with self.assertRaisesRegex(RuntimeError, "context digest"):
                smoke_runner.assert_image_contract(
                    "transformer:test",
                    "10001:10001",
                    image_id,
                    "revision",
                    expected_context_digest="not-a-digest",
                    expected_source_status_digest="b" * 64,
                    expected_source_state="CLEAN_SOURCE",
                )


if __name__ == "__main__":
    unittest.main()
