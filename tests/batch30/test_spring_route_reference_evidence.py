import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/run_spring_route_reference.py"
SPEC = importlib.util.spec_from_file_location("spring_route_reference_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
REFERENCE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REFERENCE
SPEC.loader.exec_module(REFERENCE)

ROUTE_ID = "boot-2.7-maven-to-boot-3.5.3-java-21"
ROUTE_CONTRACT_SCRIPT = ROOT / "scripts/operations/validate_spring_route_contract.py"


class SpringRouteReferenceEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="spring-route-evidence-tests-"
        )
        self.repo = Path(self.temporary.name)
        self.workspace = self.repo / "workspace"
        self.route = REFERENCE.ROUTES[ROUTE_ID]
        self.canonical = (
            self.repo / "evidence/spring-routes" / f"{ROUTE_ID}.json"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_main(self) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        argv = [
            str(SCRIPT),
            "--route",
            ROUTE_ID,
            "--repo-root",
            str(self.repo),
            "--workspace",
            str(self.workspace),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = REFERENCE.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_existing_pass_survives_a_new_failed_attempt_byte_for_byte(self) -> None:
        self.canonical.parent.mkdir(parents=True)
        original = (
            b'{\n  "execution_status": "PASSED_LOCAL",\n'
            b'  "route_id": "boot-2.7-maven-to-boot-3.5.3-java-21",\n'
            b'  "schema_version": 1,\n  "sentinel": "keep-me"\n}\n'
        )
        self.canonical.write_bytes(original)

        with (
            mock.patch.object(
                REFERENCE,
                "execute",
                side_effect=REFERENCE.RunFailure("SIMULATED_NETWORK_FAILURE"),
            ),
            mock.patch.object(
                REFERENCE, "utc_now", return_value="2026-08-09T10:11:12Z"
            ),
        ):
            result, _, stderr = self.run_main()

        self.assertEqual(result, 1)
        self.assertEqual(self.canonical.read_bytes(), original)
        attempt = REFERENCE.failure_attempt_destination(self.repo, self.route)
        self.assertTrue(attempt.is_file())
        attempt_payload = json.loads(attempt.read_text(encoding="utf-8"))
        self.assertEqual(
            attempt_payload["canonical_evidence"]["execution_status_at_attempt"],
            "PASSED_LOCAL",
        )
        self.assertFalse(attempt_payload["canonical_evidence"]["updated"])
        self.assertIn("canonical evidence preserved", stderr)

    def test_failed_attempt_is_stable_auditable_and_explicitly_non_certifying(self) -> None:
        attempt = REFERENCE.failure_attempt_destination(self.repo, self.route)
        failures = (
            ("FIRST_FAILURE", "2026-08-09T10:11:12Z"),
            ("SECOND_FAILURE", "2026-08-09T10:12:13Z"),
        )
        for failure, attempted_at in failures:
            with (
                mock.patch.object(
                    REFERENCE,
                    "execute",
                    side_effect=REFERENCE.RunFailure(failure),
                ),
                mock.patch.object(
                    REFERENCE, "utc_now", return_value=attempted_at
                ),
            ):
                result, _, stderr = self.run_main()
            self.assertEqual(result, 1)
            self.assertIn("non-certifying attempt recorded", stderr)

        self.assertFalse(self.canonical.exists())
        self.assertEqual(
            list(attempt.parent.glob(f"{ROUTE_ID}*.json")),
            [attempt],
        )
        payload = json.loads(attempt.read_text(encoding="utf-8"))
        self.assertEqual(payload["record_type"], "NON_CERTIFYING_ROUTE_ATTEMPT")
        self.assertEqual(payload["evidence_scope"], "LOCAL_ATTEMPT_AUDIT_ONLY")
        self.assertEqual(payload["attempted_at"], "2026-08-09T10:12:13Z")
        self.assertEqual(payload["execution_status"], "FAILED")
        self.assertEqual(payload["failure"], "SECOND_FAILURE")
        self.assertFalse(payload["certification_eligible"])

    def test_failure_evidence_uses_portable_path_separators(self) -> None:
        REFERENCE.record_failure_attempt(
            self.repo,
            self.route,
            self.canonical,
            REFERENCE.RunFailure(r"COMMAND_FAILED:C:\work\source\pom.xml"),
        )

        attempt = REFERENCE.failure_attempt_destination(self.repo, self.route)
        payload = json.loads(attempt.read_text(encoding="utf-8"))
        self.assertEqual(payload["failure"], "COMMAND_FAILED:C:/work/source/pom.xml")
        self.assertEqual(payload["certification_status"], "NOT_CERTIFIED")
        self.assertEqual(payload["external_evidence_status"], "NOT_RUN")
        self.assertEqual(
            payload["canonical_evidence"],
            {
                "execution_status_at_attempt": "ABSENT",
                "path": f"evidence/spring-routes/{ROUTE_ID}.json",
                "updated": False,
            },
        )
        self.assertEqual(list(attempt.parent.glob("*.tmp")), [])

    def test_failed_attempt_preserves_primary_error_when_audit_write_fails(self) -> None:
        with (
            mock.patch.object(
                REFERENCE,
                "execute",
                side_effect=REFERENCE.RunFailure("PRIMARY_ROUTE_FAILURE"),
            ),
            mock.patch.object(
                REFERENCE,
                "record_failure_attempt",
                side_effect=OSError(28, "No space left on device"),
            ),
        ):
            result, _, stderr = self.run_main()

        self.assertEqual(result, 1)
        self.assertIn("PRIMARY_ROUTE_FAILURE", stderr)
        self.assertIn("ATTEMPT_AUDIT_WRITE_FAILED", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_success_atomically_replaces_the_canonical_record(self) -> None:
        success = {
            "schema_version": 1,
            "route_id": ROUTE_ID,
            "execution_status": "PASSED_LOCAL",
            "behavioral_parity": True,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        real_replace = os.replace
        with (
            mock.patch.object(REFERENCE, "execute", return_value=success),
            mock.patch.object(
                REFERENCE.os, "replace", wraps=real_replace
            ) as replace,
        ):
            result, stdout, _ = self.run_main()

        self.assertEqual(result, 0)
        self.assertIn(f"PASS: {ROUTE_ID}", stdout)
        self.assertEqual(
            json.loads(self.canonical.read_text(encoding="utf-8")), success
        )
        self.assertEqual(replace.call_count, 1)
        source, destination = replace.call_args.args
        self.assertEqual(Path(destination).resolve(), self.canonical.resolve())
        self.assertEqual(Path(source).parent.resolve(), self.canonical.parent.resolve())
        self.assertEqual(list(self.canonical.parent.glob("*.tmp")), [])
        self.assertFalse(
            REFERENCE.failure_attempt_destination(self.repo, self.route).exists()
        )

    def test_default_workspace_is_external_temporary_and_cleaned(self) -> None:
        success = {
            "schema_version": 1,
            "route_id": ROUTE_ID,
            "execution_status": "PASSED_LOCAL",
            "behavioral_parity": True,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        observed: list[Path] = []

        def execute(repo: Path, route: REFERENCE.Route, workspace: Path) -> dict:
            observed.append(workspace)
            self.assertEqual(repo, self.repo.resolve())
            self.assertEqual(route, self.route)
            self.assertTrue(workspace.is_dir())
            with self.assertRaises(ValueError):
                workspace.relative_to(repo)
            return success

        argv = [
            str(SCRIPT),
            "--route",
            ROUTE_ID,
            "--repo-root",
            str(self.repo),
        ]
        with (
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(REFERENCE, "execute", side_effect=execute),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = REFERENCE.main()

        self.assertEqual(result, 0)
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists())

    def test_boot_3_5_local_records_are_exact(self) -> None:
        expected = {
            "boot-1.5-java-8-maven-to-boot-3.5.3-java-21": ("1.5.22.RELEASE", "8"),
            "boot-2.0-2.6-maven-to-boot-3.5.3-java-21": ("2.3.12.RELEASE", "11"),
            "boot-2.7-maven-to-boot-3.5.3-java-21": ("2.7.18", "17"),
            "boot-3.0-3.4-maven-to-boot-3.5.3-java-21": ("3.4.1", "17"),
        }
        for route_id, (source_boot, source_java) in expected.items():
            record = json.loads(
                (ROOT / "evidence/spring-routes" / f"{route_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(record["execution_status"], "PASSED_LOCAL")
            self.assertTrue(record["behavioral_parity"])
            self.assertEqual(
                record["recorded_tuple"],
                {
                    "source_boot": source_boot,
                    "source_java": source_java,
                    "target_boot": "3.5.3",
                    "target_java": "21",
                },
            )
            self.assertEqual(record["external_evidence_status"], "NOT_RUN")
            self.assertEqual(record["independent_verification"], "NOT_RUN")
            self.assertEqual(record["certification_status"], "NOT_CERTIFIED")

    def test_boot_4_1_local_records_are_exact_and_contract_validated(self) -> None:
        expected = {
            "boot-1.5-maven-to-boot-4.1.0-java-21": ("1.5.22.RELEASE", "8"),
            "boot-2.0-2.6-maven-to-boot-4.1.0-java-21": ("2.3.12.RELEASE", "11"),
            "boot-2.7-maven-to-boot-4.1.0-java-21": ("2.7.18", "17"),
            "boot-3.0-3.4-maven-to-boot-4.1.0-java-21": ("3.4.1", "17"),
            "boot-3.5-maven-to-boot-4.1.0-java-21": ("3.5.3", "21"),
            "boot-2.x-gradle-to-boot-4.1.0-java-21": ("2.7.18", "17"),
            "spring-mvc-3.2-7.0-maven-to-boot-4.1.0-java-21": ("5.3.39", "11"),
        }
        for route_id, (source_boot, source_java) in expected.items():
            record = json.loads(
                (ROOT / "evidence/spring-routes" / f"{route_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(record["execution_status"], "PASSED_LOCAL")
            self.assertTrue(record["behavioral_parity"])
            self.assertEqual(
                record["recorded_tuple"],
                {
                    "source_boot": source_boot,
                    "source_java": source_java,
                    "target_boot": "4.1.0",
                    "target_java": "21",
                },
            )
            self.assertEqual(record["external_evidence_status"], "NOT_RUN")
            self.assertEqual(record["independent_verification"], "NOT_RUN")
            self.assertEqual(record["certification_status"], "NOT_CERTIFIED")

        result = subprocess.run(
            [sys.executable, str(ROUTE_CONTRACT_SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_tampered_boot_3_5_evidence_fails_contract_validator(self) -> None:
        target_evidence = ROOT / "evidence/spring-routes/boot-2.7-maven-to-boot-3.5.3-java-21.json"
        original = target_evidence.read_text(encoding="utf-8")
        tampered = json.loads(original)
        tampered["recorded_tuple"]["target_boot"] = "3.5.4"
        try:
            target_evidence.write_text(json.dumps(tampered), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROUTE_CONTRACT_SCRIPT)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BOOT_3_5_LOCAL_EVIDENCE", result.stdout + result.stderr)
        finally:
            target_evidence.write_text(original, encoding="utf-8")


    def test_gradle_route_fixture_declares_a_canonical_boot_gradle_build(self) -> None:
        route = REFERENCE.ROUTES["boot-2.x-gradle-to-boot-3.5.3-java-21"]
        self.assertEqual(route.build_tool, "gradle")
        build = REFERENCE.gradle_build(route)
        # The dependency-management plugin is what lets the starters resolve
        # without versions on Boot 2.x; a build.gradle that loses it fails at
        # compileJava with an empty version, far away from the real cause.
        self.assertIn(
            "id 'org.springframework.boot' version '2.7.18'", build
        )
        self.assertIn(
            "id 'io.spring.dependency-management' version '1.0.15.RELEASE'", build
        )
        # Regression lock: the dependencies block wrapper must be present, or
        # Gradle reads `implementation` as an unknown root-project method.
        self.assertIn("dependencies {", build)
        self.assertIn(
            "implementation 'org.springframework.boot:spring-boot-starter-web'", build
        )
        self.assertIn(
            "testImplementation 'org.springframework.boot:spring-boot-starter-test'",
            build,
        )
        self.assertIn("sourceCompatibility = '17'", build)
        self.assertIn("useJUnitPlatform()", build)
        self.assertEqual(
            REFERENCE.gradle_settings(route),
            "rootProject.name = 'spring-reference-2-7-18'\n",
        )

    def test_gradle_route_recipe_matches_the_catalog_route_id(self) -> None:
        route = REFERENCE.ROUTES["boot-2.x-gradle-to-boot-3.5.3-java-21"]
        recipe = (
            ROOT
            / "apps/java-engine-worker/src/main/resources/rewrite"
            / route.recipe_file
        )
        self.assertTrue(recipe.is_file())
        text = recipe.read_text(encoding="utf-8")
        self.assertIn(f"name: {route.recipe_id}", text)
        self.assertIn("pluginIdPattern: org.springframework.boot", text)
        self.assertIn("newVersion: 3.5.3", text)
        # The harness drives the same init-script mechanism the Java Worker
        # ships, so the recipe must pin the boot plugin for Gradle builds.
        self.assertIn("org.openrewrite.gradle.plugins.ChangePluginVersion", text)

    def test_priority_route_exercises_all_declared_local_capabilities(self) -> None:
        route = REFERENCE.ROUTES[ROUTE_ID]
        self.assertIn("security", route.extra_starters)
        self.assertIn("data-jpa", route.extra_starters)
        self.assertIn("cache", route.extra_starters)
        self.assertIn("antMatchers", route.security)
        self.assertIn("javax.persistence.Entity", route.persistence)
        self.assertIn("rollsBackTransactionalWrites", route.test)
        self.assertIn("preservesConstructorDependencyInjection", route.test)
        self.assertIn("preservesApplicationEventDelivery", route.test)
        self.assertIn("preservesCacheHitSemantics", route.test)
        self.assertIn("schedulerExecutesInTheApplicationContext", route.test)
        self.assertIn("public void createThenRollback", REFERENCE._PERSISTENCE_SERVICE)
        self.assertIn("@EventListener", route.capabilities)
        self.assertIn("@Cacheable", route.capabilities)
        self.assertIn("@Scheduled", route.capabilities)

        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "source"
            REFERENCE.materialize(project, route)
            entity = (project / "src/main/java/io/elmos/reference/PersistedOrder.java")
            capabilities = (
                project / "src/main/java/io/elmos/reference/CapabilityContracts.java"
            )
            security = (
                project / "src/main/java/io/elmos/reference/SecurityConfiguration.java"
            )
            generated_test = (
                project / "src/test/java/io/elmos/reference/OrderControllerTest.java"
            ).read_text(encoding="utf-8")
            self.assertIn("javax.persistence.Entity", entity.read_text(encoding="utf-8"))
            self.assertIn("@EnableScheduling", capabilities.read_text(encoding="utf-8"))
            self.assertIn("antMatchers", security.read_text(encoding="utf-8"))
            self.assertIn("private CapabilityContracts capabilities;", generated_test)
            self.assertIn(
                "org.junit.jupiter.api.Assertions.assertEquals", generated_test
            )
            pom = (project / "pom.xml").read_text(encoding="utf-8")
            self.assertIn("spring-boot-starter-security", pom)
            self.assertIn("spring-boot-starter-data-jpa", pom)
            self.assertIn("spring-boot-starter-cache", pom)
            self.assertIn("com.h2database", pom)

    def test_local_reference_projection_never_promotes_external_evidence(self) -> None:
        runtime = {
            "health": {"status": "UP"},
            "responses": {"42": {"id": 42}},
            "security": {"authenticated_order_status": 200},
            "persistence": {"count_response": {"count": 0}},
            "dependency_injection": {"injected": True},
            "messaging": {"status": 200, "response": {"deliveries": 1}},
            "cache": {"first": 1, "second": 1, "loads": 1},
            "scheduler": {"active": True},
        }
        evidence = {
            "route_id": ROUTE_ID,
            "execution_status": "PASSED_LOCAL",
            "behavioral_parity": True,
            "source": {"boot": "2.7.18", "java": "17", "build": "PASSED", "runtime": runtime},
            "target": {"boot": "3.5.3", "java": "21", "build": "PASSED", "runtime": runtime},
            "transformation": {
                "recipe_id": "recipe",
                "recipe_sha256": "0" * 64,
                "maven": "Apache Maven 3.9.11",
            },
        }

        projected = REFERENCE.pack_local_reference_evidence(evidence, "pack")

        self.assertFalse(projected["certification_eligible"])
        self.assertEqual(projected["external_certification"], "NOT_RUN")
        for capability in (
            "dependency_injection", "persistence", "messaging", "cache", "scheduler"
        ):
            self.assertEqual(projected[capability]["status"], "PASSED_LOCAL")
            self.assertEqual(projected[capability]["production_status"], "NOT_RUN")

    def test_composite_recipe_loads_repository_owned_recipe_artifact(self) -> None:
        boot_3_recipe = (
            ROOT
            / "apps/java-engine-worker/src/main/resources/rewrite"
            / REFERENCE.ROUTES[ROUTE_ID].recipe_file
        )
        boot_4_recipe = (
            ROOT
            / "apps/java-engine-worker/src/main/resources/rewrite"
            / REFERENCE.ROUTES[
                "boot-3.5-maven-to-boot-4.1.0-java-21"
            ].recipe_file
        )
        self.assertNotIn(
            REFERENCE.ELMOS_RECIPE_COORDINATE,
            REFERENCE.rewrite_recipe_artifact_coordinates(boot_3_recipe),
        )
        self.assertIn(
            REFERENCE.ELMOS_RECIPE_COORDINATE,
            REFERENCE.rewrite_recipe_artifact_coordinates(boot_4_recipe),
        )

    def test_built_boot_jar_rejects_missing_and_plain_jars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            with self.assertRaises(REFERENCE.RunFailure):
                REFERENCE.built_boot_jar(project, "maven")
            with self.assertRaises(REFERENCE.RunFailure):
                REFERENCE.built_boot_jar(project, "gradle")
            maven_target = project / "target"
            maven_target.mkdir()
            (maven_target / "app.jar.original").write_bytes(b"original")
            with self.assertRaises(REFERENCE.RunFailure):
                REFERENCE.built_boot_jar(project, "maven")
            (maven_target / "app.jar").write_bytes(b"boot")
            self.assertEqual(
                REFERENCE.built_boot_jar(project, "maven"),
                maven_target / "app.jar",
            )
            gradle_libs = project / "build" / "libs"
            gradle_libs.mkdir(parents=True)
            (gradle_libs / "app-1.0.0-plain.jar").write_bytes(b"plain")
            with self.assertRaises(REFERENCE.RunFailure):
                REFERENCE.built_boot_jar(project, "gradle")
            (gradle_libs / "app-1.0.0.jar").write_bytes(b"boot")
            self.assertEqual(
                REFERENCE.built_boot_jar(project, "gradle"),
                gradle_libs / "app-1.0.0.jar",
            )

    def test_java_executable_uses_the_native_windows_suffix(self) -> None:
        with mock.patch.object(REFERENCE.os, "name", "nt"):
            self.assertEqual(
                REFERENCE.java_executable(Path("C:/jdk-21")),
                Path("C:/jdk-21/bin/java.exe"),
            )

    def test_run_prepends_java_bin_with_platform_path_separator(self) -> None:
        completed = subprocess.CompletedProcess(["java"], 0, "", "")
        with (
            mock.patch.dict(REFERENCE.os.environ, {"PATH": "existing-path"}, clear=True),
            mock.patch.object(
                REFERENCE.subprocess, "run", return_value=completed
            ) as invoked,
        ):
            REFERENCE.run(
                ["java", "-version"], cwd=self.repo, home=Path("C:/jdk-21")
            )

        environment = invoked.call_args.kwargs["env"]
        self.assertEqual(
            environment["PATH"],
            REFERENCE.os.pathsep.join((str(Path("C:/jdk-21/bin")), "existing-path")),
        )


if __name__ == "__main__":
    unittest.main()
