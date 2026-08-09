from __future__ import annotations

import re
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
        for key in ("transformer", "verifier"):
            dockerfile = DOCKERFILES[key].read_text(encoding="utf-8")
            self.assertNotIn("maven.wagon.http.retryHandler.count=0", dockerfile)
            self.assertIn("--strict-checksums", dockerfile)
            self.assertIn("maven.wagon.http.retryHandler.count=5", dockerfile)
            self.assertIn("if [ \"$attempt\" -ge 3 ]; then exit 1; fi", dockerfile)
            self.assertIn("-name '*.part'", dockerfile)

    def test_verifier_seed_cache_survives_a_failed_build_attempt(self) -> None:
        dockerfile = DOCKERFILES["verifier"].read_text(encoding="utf-8")
        cache_id = "id=elmos-java-engine-verifier-maven-3.9.11"
        self.assertEqual(4, dockerfile.count(cache_id))
        self.assertEqual(3, dockerfile.count("-Dmaven.repo.local=/opt/elmos/maven-cache"))
        self.assertIn(
            "cp -R /tmp/elmos-verifier-maven-cache/. /opt/elmos/maven-cache/",
            dockerfile,
        )

    def test_service_images_bind_the_docker_filtered_source_context(self) -> None:
        for key in ("transformer", "verifier"):
            dockerfile = DOCKERFILES[key].read_text(encoding="utf-8")
            self.assertIn("AS source-context-digest", dockerfile)
            self.assertIn("/opt/elmos/source-context.sha256", dockerfile)
            self.assertIn("ELMOS_EXPECTED_SOURCE_CONTEXT_SHA256", dockerfile)
            self.assertIn("xargs -0 sha256sum", dockerfile)

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
        ):
            self.assertIn(option, smoke)
        self.assertRegex(smoke, re.compile(r"docker.*,.*rm.*,.*--force", re.DOTALL))
        self.assertRegex(smoke, re.compile(r"docker.*,.*network.*,.*rm", re.DOTALL))

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
