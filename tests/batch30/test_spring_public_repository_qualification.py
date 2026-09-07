import argparse
import importlib.util
import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/qualify_spring_public_repository.py"
LOCAL_SCRIPT = ROOT / "scripts/operations/replay_spring_public_repository_local.py"
LINUX_SCRIPT = ROOT / "scripts/operations/replay_retro_game_linux_baseline.py"
MANIFEST = (
    ROOT
    / "framework-packs/spring-boot-2-7-18-to-3-5-3/corpus/real-repository"
    / "public-qualification-manifest.json"
)
SPEC = importlib.util.spec_from_file_location("spring_public_qualification", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
QUALIFICATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = QUALIFICATION
SPEC.loader.exec_module(QUALIFICATION)
LOCAL_SPEC = importlib.util.spec_from_file_location(
    "spring_public_local_replay", LOCAL_SCRIPT
)
assert LOCAL_SPEC is not None and LOCAL_SPEC.loader is not None
LOCAL_REPLAY = importlib.util.module_from_spec(LOCAL_SPEC)
sys.modules[LOCAL_SPEC.name] = LOCAL_REPLAY
LOCAL_SPEC.loader.exec_module(LOCAL_REPLAY)
LINUX_SPEC = importlib.util.spec_from_file_location(
    "retro_game_linux_baseline_replay", LINUX_SCRIPT
)
assert LINUX_SPEC is not None and LINUX_SPEC.loader is not None
LINUX_REPLAY = importlib.util.module_from_spec(LINUX_SPEC)
sys.modules[LINUX_SPEC.name] = LINUX_REPLAY
LINUX_SPEC.loader.exec_module(LINUX_REPLAY)


class SpringPublicRepositoryQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="spring-public-qualification-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_checked_in_manifest_is_exact_non_customer_and_non_independent(self) -> None:
        manifest = QUALIFICATION.load_manifest(MANIFEST)
        retro = QUALIFICATION.repository_by_id(manifest, "retro-game")
        self.assertEqual(
            retro["commit_sha"], "3d08c4b2ca814acfd873fc7874f724089e5b1d85"
        )
        self.assertEqual(
            retro["tree_sha"], "0d1d5b20c725f559d9f996609ebbe11a56832a41"
        )
        self.assertEqual(retro["source_tuple"]["spring_boot"], "2.7.18")
        self.assertEqual(retro["source_tuple"]["java"], "17")
        self.assertFalse(retro["customer_repository"])
        self.assertFalse(retro["independent_verification"])
        policy = manifest["execution_policy"]
        self.assertEqual(
            policy["untrusted_build_execution"],
            QUALIFICATION.ROOTLESS_EXECUTION_STATUS,
        )
        self.assertEqual(
            policy["protected_rootless_runner_receipt_verifier"],
            "NOT_IMPLEMENTED",
        )
        self.assertFalse(policy["caller_supplied_attestation_accepted"])
        self.assertEqual(retro["test_inventory"]["total_tests"], 22)
        self.assertEqual(len(retro["service_images"]), 3)
        self.assertEqual(
            retro["service_images"][0]["resolved_reference"],
            "mirror.gcr.io/library/postgres@sha256:"
            "3119f20c52c059928a1f3455ef0c4ce57fa4f4c39562f0bf4c5ead414ad55b84",
        )
        self.assertEqual(
            retro["service_images"][1]["resolved_reference"],
            "mirror.gcr.io/library/redis@sha256:"
            "ef0234ae359f2550f773accc0b4207ae213475eccaa0b2dd17c2710abb8c1998",
        )
        self.assertEqual(
            retro["service_images"][2]["source_reference"],
            "testcontainers/ryuk:0.12.0",
        )
        for image in retro["service_images"]:
            self.assertEqual(image["execution_reference"], image["resolved_reference"])
            self.assertIn("@sha256:", image["execution_reference"])
            self.assertNotEqual(image["source_reference"], image["execution_reference"])
        self.assertEqual(retro["target"]["spring_boot"], "3.5.3")
        self.assertEqual(retro["target"]["java"], "21")
        self.assertEqual(retro["target"]["maven"], "3.9.11")
        contract = retro["toolchain_contract"]
        self.assertEqual(contract["platform_system"], "Darwin")
        self.assertEqual(contract["platform_machine"], "arm64")
        self.assertEqual(
            set(contract["executables"]), set(QUALIFICATION.EXACT_TOOLCHAIN_NAMES)
        )
        self.assertTrue(contract["maven_policy"]["strict_checksums"])
        for identity in contract["executables"].values():
            self.assertRegex(identity["sha256"], r"^[0-9a-f]{64}$")
            self.assertNotIn("\n", identity["version_line"])
        candidate = manifest["separate_public_candidates"][0]
        self.assertEqual(candidate["source_execution"], "NOT_RUN")
        self.assertEqual(candidate["target_execution"], "NOT_RUN")
        self.assertFalse(candidate["customer_repository"])
        self.assertFalse(candidate["independent_verification"])

    def test_linux_baseline_is_exact_explicit_and_non_certifying(self) -> None:
        with self.assertRaisesRegex(
            LINUX_REPLAY.protected.QualificationError,
            "LOCAL_LINUX_BASELINE_EXPLICIT_OPT_IN_REQUIRED",
        ):
            LINUX_REPLAY.require_opt_in(False)
        LINUX_REPLAY.require_opt_in(True)
        self.assertEqual(LINUX_REPLAY.LINUX_RUNNER_PLATFORM, "linux/amd64")
        self.assertEqual(LINUX_REPLAY.NESTED_DAEMON_PLATFORM, "linux/arm64")
        self.assertEqual(
            LINUX_REPLAY.PRIVILEGED_AUTHORIZATION_REQUIRED_STATUS,
            "BLOCKED_PRIVILEGED_RUNNER_AUTHORIZATION_REQUIRED",
        )
        self.assertIn(
            "@sha256:fa7aa19829157d299ff05f631b51697a388dcd2f6955e84249ecc652015f217b",
            LINUX_REPLAY.LINUX_RUNNER_BASE_REFERENCE,
        )
        self.assertIn(
            "@sha256:b7282888b57955edf6b213da6bf179039f09b8335526966f704566321945415a",
            LINUX_REPLAY.NESTED_DAEMON_REFERENCE,
        )
        dockerfile = LINUX_REPLAY.DEFAULT_RUNNER_DOCKERFILE.read_text(
            encoding="utf-8"
        )
        self.assertIn(
            f"FROM {LINUX_REPLAY.LINUX_RUNNER_BASE_REFERENCE}", dockerfile
        )
        self.assertIn('io.elmos.evidence-class="LOCAL_NON_CERTIFYING"', dockerfile)
        self.assertIn("https://archive.ubuntu.com", dockerfile)
        self.assertIn("https://security.ubuntu.com", dockerfile)
        self.assertIn("Acquire::Retries=5", dockerfile)

        implementation = LINUX_SCRIPT.read_text(encoding="utf-8")
        self.assertLess(
            implementation.index('receipt["runner"]["build"] = runner_build'),
            implementation.index('"LOCAL_LINUX_RUNNER_BUILD_FAILED"'),
        )
        self.assertIn('"overall_status"] = "FAILED_LOCAL_NON_CERTIFYING"', implementation)
        replay_body = implementation.split("def replay", 1)[1].split(
            "def parse_args", 1
        )[0]
        self.assertLess(
            replay_body.index("if not privileged_nested_daemon_authorized:"),
            replay_body.index("suffix = uuid.uuid4().hex[:10]"),
        )
        self.assertLess(
            replay_body.index("if not privileged_nested_daemon_authorized:"),
            replay_body.index('receipt["host_docker_runtime"]'),
        )
        build_segment = replay_body.split("runner_build = _run", 1)[1].split(
            "derived = derived_image_audit", 1
        )[0]
        self.assertLess(
            build_segment.index('receipt["runner"]["build"] = runner_build'),
            build_segment.index("protected.atomic_json(output, receipt)"),
        )
        self.assertLess(
            build_segment.index("protected.atomic_json(output, receipt)"),
            build_segment.index('"LOCAL_LINUX_RUNNER_BUILD_FAILED"'),
        )
        for stage in (
            "pull-linux-amd64-runner-base",
            "pull-rootless-dind-arm64",
            "build-linux-amd64-runner",
            "linux-amd64-source-native-and-tests",
        ):
            self.assertIn(f'operation="{stage}"', implementation)
        self.assertIn("cleanup_derived_runner(", replay_body)
        self.assertIn("cleanup_nested_daemon(", replay_body)
        self.assertIn('"--force", "--volumes"', implementation)
        self.assertIn("except (Exception, KeyboardInterrupt) as exc:", replay_body)
        self.assertIn("apply_cleanup_gate(receipt, cleanup)", replay_body)
        self.assertIn("--authorize-privileged-nested-daemon", implementation)
        self.assertIn('receipt["docker_operations_executed"] = False', replay_body)
        self.assertIn('receipt["cleanup"] = []', replay_body)

    def test_linux_baseline_failure_diagnostics_preserve_exact_float_delta(self) -> None:
        reports = self.root / "target/surefire-reports"
        reports.mkdir(parents=True)
        suite = QUALIFICATION.ET.Element(
            "testsuite",
            name="example.DifferentialTest",
            tests="1",
            failures="1",
            errors="0",
            skipped="0",
        )
        case = QUALIFICATION.ET.SubElement(
            suite, "testcase", classname="example.DifferentialTest", name="test"
        )
        failure = QUALIFICATION.ET.SubElement(
            case,
            "failure",
            type="org.opentest4j.AssertionFailedError",
            message=(
                "expected: <[numRemainingUnits=1, hullDamageDealt=39.366, "
                "shieldDamageDealt=7.282996E7]> but was: <[numRemainingUnits=1, "
                "hullDamageDealt=39.365997, shieldDamageDealt=7.2829936E7]>"
            ),
        )
        failure.text = "stack"
        QUALIFICATION.ET.ElementTree(suite).write(
            reports / "TEST-example.DifferentialTest.xml",
            encoding="utf-8",
            xml_declaration=True,
        )
        diagnostics = LINUX_REPLAY.numerical_failure_diagnostics(self.root)
        self.assertEqual(diagnostics["failure_count"], 1)
        record = diagnostics["failures"][0]
        self.assertEqual(record["compared_numeric_fields"], 3)
        self.assertEqual(record["exact_value_differences"], 2)
        self.assertEqual(record["integer_value_differences"], 0)
        self.assertEqual(
            record["first_differences"][0]["expected"], "39.366"
        )
        self.assertEqual(
            record["first_differences"][0]["actual"], "39.365997"
        )
        self.assertEqual(
            record["maximum_absolute_delta"]["absolute_delta"], 24.0
        )
        implementation = LINUX_SCRIPT.read_text(encoding="utf-8")
        diagnostics_body = implementation.split(
            "def numerical_failure_diagnostics", 1
        )[1].split("def _nested_command", 1)[0]
        self.assertEqual(
            diagnostics_body.count('"bytes": report.stat().st_size'), 1
        )

    def test_linux_toolchain_probe_is_structured_and_content_bound(self) -> None:
        lines = []
        for index, name in enumerate(
            ("java", "javac", "mvn", "cmake", "c++", "make"), start=1
        ):
            version = f"{name} version {index}\n"
            encoded = LINUX_REPLAY.base64.b64encode(version.encode()).decode()
            lines.append(
                "\t".join(
                    (
                        "ELMOS_TOOL",
                        name,
                        f"/usr/bin/{name}",
                        f"/usr/bin/{name}",
                        f"{index:x}" * 64,
                        str(index * 100),
                        encoded,
                    )
                )
            )
        lines.extend(
            [
                "ELMOS_DPKG\tbuild-essential\t12.10ubuntu1\tamd64",
                "ELMOS_DPKG\tcmake\t3.28.3-1build7\tamd64",
                "ELMOS_DPKG\tg++\t4:13.2.0-7ubuntu1\tamd64",
                "ELMOS_DPKG\tmake\t4.3-4.1build2\tamd64",
                "ELMOS_UNAME\tx86_64",
            ]
        )
        parsed = LINUX_REPLAY.parse_toolchain_probe("\n".join(lines))
        self.assertEqual(set(parsed["tools"]), {"java", "javac", "mvn", "cmake", "c++", "make"})
        self.assertEqual(parsed["tools"]["mvn"]["version_first_line"], "mvn version 3")
        self.assertEqual(len(parsed["tools"]["cmake"]["sha256"]), 64)
        self.assertEqual(len(parsed["dpkg_packages"]), 4)
        self.assertTrue(parsed["actual_bytes_bound_by_derived_image_id"])
        self.assertFalse(parsed["rebuild_inputs_fully_version_locked"])

    def test_linux_runner_command_drops_caps_and_uses_internal_network(self) -> None:
        with mock.patch.object(LINUX_REPLAY, "_docker", return_value="docker"):
            command = LINUX_REPLAY._runner_common_arguments(
                "sha256:runner",
                "elmos-internal",
                "elmos-dind",
                name="elmos-probe",
            )
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop=ALL", command)
        self.assertIn("no-new-privileges", command)
        self.assertEqual(command[command.index("--network") + 1], "elmos-internal")
        self.assertIn("DOCKER_HOST=tcp://elmos-dind:2375", command)
        self.assertEqual(command[-1], "sha256:runner")

    def test_archive_path_traversal_is_rejected(self) -> None:
        archive = self.root / "unsafe.tar.gz"
        with tarfile.open(archive, "w:gz") as handle:
            data = b"escape"
            member = tarfile.TarInfo("fixture-deadbeef/../../escape")
            member.size = len(data)
            handle.addfile(member, io.BytesIO(data))
        with self.assertRaisesRegex(
            QUALIFICATION.QualificationError, "ARCHIVE_PATH_TRAVERSAL"
        ):
            QUALIFICATION.validate_tar_members(archive, "fixture-deadbeef")

    def test_target_recipe_path_escape_is_rejected(self) -> None:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        payload["repositories"][0]["target"]["recipe_path"] = "../README.md"
        manifest = self.root / "unsafe-manifest.json"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(
            QUALIFICATION.QualificationError, "TARGET_RECIPE_PATH_ESCAPE"
        ):
            QUALIFICATION.load_manifest(manifest)

    def make_source(self) -> Path:
        source = self.root / "source"
        (source / "src/test/java/example").mkdir(parents=True)
        (source / "pom.xml").write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>2.7.18</version>
  </parent>
  <groupId>example</groupId><artifactId>fixture</artifactId><version>1</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
</project>
""",
            encoding="utf-8",
        )
        (source / "src/test/java/example/JupiterTest.java").write_text(
            """import org.junit.jupiter.api.Test;
class JupiterTest { @Test
void first() {} }
""",
            encoding="utf-8",
        )
        (source / "src/test/java/example/LegacyTest.java").write_text(
            """import org.junit.Test;
class LegacyTest { @Test(expected = RuntimeException.class)
public void legacy() { throw new RuntimeException(); } }
""",
            encoding="utf-8",
        )
        return source

    def make_fake_jdk(self, name: str = "jdk-17") -> Path:
        java_home = self.root / name
        include = java_home / "include"
        platform_include = include / "darwin"
        server = java_home / "lib/server"
        binaries = java_home / "bin"
        platform_include.mkdir(parents=True)
        server.mkdir(parents=True)
        binaries.mkdir(parents=True)
        (include / "jni.h").write_text("jni", encoding="utf-8")
        (platform_include / "jni_md.h").write_text("jni-md", encoding="utf-8")
        (server / "libjvm.dylib").write_bytes(b"jvm")
        (java_home / "lib/libjawt.dylib").write_bytes(b"awt")
        for binary in (binaries / "java", binaries / "javac"):
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
        return java_home

    def test_vintage_overlay_exposes_legacy_tests_without_editing_test_sources(self) -> None:
        source = self.make_source()
        repository = {
            "source_tuple": {"spring_boot": "2.7.18", "java": "17"},
            "test_inventory": {
                "test_source_files": 2,
                "junit_jupiter_tests": 1,
                "junit4_tests": 1,
                "total_tests": 2,
            },
            "test_discovery_overlay": {"version": "5.8.2"},
        }
        pom = QUALIFICATION.pom_audit(source, repository)
        self.assertFalse(pom["junit_vintage_declared"])
        inventory = QUALIFICATION.test_inventory(source, repository)
        self.assertEqual(inventory["total_tests"], 2)
        overlay = QUALIFICATION.create_vintage_overlay(source, repository)
        self.assertEqual(
            overlay["test_source_hashes_before_overlay"],
            overlay["test_source_hashes_after_overlay"],
        )
        self.assertIn(
            "junit-vintage-engine",
            (source / "qualification-pom.xml").read_text(encoding="utf-8"),
        )

        target_overlay = QUALIFICATION.create_vintage_overlay(
            source, repository, target_profile=True
        )
        target_pom = (source / "qualification-pom.xml").read_text(encoding="utf-8")
        self.assertEqual(
            target_overlay["version"], "MANAGED_BY_SPRING_BOOT_TARGET_BOM"
        )
        self.assertNotIn("<version>5.8.2</version>", target_pom)

    def test_service_image_audit_uses_only_resolved_digest_reference(self) -> None:
        resolved = "postgres@sha256:" + "1" * 64
        repository = {
            "service_images": [
                {
                    "role": "postgres",
                    "source_reference": "postgres:13-alpine",
                    "resolved_reference": resolved,
                    "execution_reference": resolved,
                    "platform": "linux/arm64",
                    "platform_digest": "sha256:" + "1" * 64,
                }
            ]
        }
        inspect = {
            "exit_code": 0,
            "output": json.dumps(
                [
                    {
                        "Id": "sha256:pinned",
                        "RepoDigests": [resolved],
                        "Os": "linux",
                        "Architecture": "arm64",
                    }
                ]
            ),
            "timed_out": False,
        }
        with (
            mock.patch.object(QUALIFICATION.shutil, "which", return_value="docker"),
            mock.patch.object(
                QUALIFICATION, "run_command", return_value=inspect
            ) as run,
        ):
            result = QUALIFICATION.service_image_audit(repository, self.root)[0]
        self.assertEqual(result["status"], "AVAILABLE_RESOLVED_DIGEST_LOCAL")
        self.assertFalse(result["source_reference_used_for_execution"])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["docker", "image", "inspect", resolved])
        self.assertNotIn("postgres:13-alpine", run.call_args.args[0])

    def test_service_image_audit_rejects_wrong_platform(self) -> None:
        resolved = "postgres@sha256:" + "1" * 64
        repository = {
            "service_images": [
                {
                    "role": "postgres",
                    "source_reference": "postgres:13-alpine",
                    "resolved_reference": resolved,
                    "execution_reference": resolved,
                    "platform": "linux/arm64",
                    "platform_digest": "sha256:" + "1" * 64,
                }
            ]
        }
        inspect = {
            "exit_code": 0,
            "output": json.dumps(
                [
                    {
                        "Id": "sha256:pinned",
                        "RepoDigests": [resolved],
                        "Os": "linux",
                        "Architecture": "amd64",
                    }
                ]
            ),
            "timed_out": False,
        }
        with (
            mock.patch.object(QUALIFICATION.shutil, "which", return_value="docker"),
            mock.patch.object(QUALIFICATION, "run_command", return_value=inspect),
        ):
            result = QUALIFICATION.service_image_audit(repository, self.root)[0]
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["reason"], "RESOLVED_DIGEST_PLATFORM_MISMATCH")

    def test_surefire_summary_counts_every_report_and_failure_class(self) -> None:
        reports = self.root / "target/surefire-reports"
        reports.mkdir(parents=True)
        first_cases = "".join(
            f'<testcase classname="example.One" name="case-{index}"/>'
            for index in range(2)
        )
        second_cases = "".join(
            f'<testcase classname="example.Two" name="case-{index}"/>'
            for index in range(20)
        )
        (reports / "TEST-one.xml").write_text(
            '<testsuite tests="2" failures="0" errors="0" skipped="0">'
            + first_cases
            + "</testsuite>",
            encoding="utf-8",
        )
        (reports / "TEST-two.xml").write_text(
            '<testsuite tests="20" failures="1" errors="2" skipped="3">'
            + second_cases
            + "</testsuite>",
            encoding="utf-8",
        )
        summary = QUALIFICATION.surefire_summary(self.root)
        self.assertEqual(summary["tests"], 22)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["errors"], 2)
        self.assertEqual(summary["skipped"], 3)
        self.assertEqual(len(summary["reports"]), 2)
        self.assertEqual(len(summary["test_cases"]), 22)

    def test_exact_jni_toolchain_resolves_every_input_below_declared_jdk(self) -> None:
        java_home = self.make_fake_jdk()
        include = java_home / "include"
        platform_include = include / "darwin"

        selected = QUALIFICATION.exact_jni_toolchain(java_home)

        self.assertEqual(selected["JAVA_HOME"], java_home.resolve())
        self.assertEqual(
            selected["Java_JAVA_EXECUTABLE"], (java_home / "bin/java").resolve()
        )
        self.assertEqual(
            selected["Java_JAVAC_EXECUTABLE"], (java_home / "bin/javac").resolve()
        )
        self.assertEqual(selected["JAVA_INCLUDE_PATH"], include.resolve())
        self.assertEqual(selected["JAVA_INCLUDE_PATH2"], platform_include.resolve())
        for path in selected.values():
            self.assertTrue(path.is_relative_to(java_home.resolve()))

    def test_cmake_jni_cache_rejects_homebrew_or_other_jdk_paths(self) -> None:
        java_home = self.make_fake_jdk()
        expected = QUALIFICATION.exact_jni_toolchain(java_home)
        foreign = self.root / "homebrew-openjdk-26/include"
        foreign.mkdir(parents=True)
        cache = self.root / "CMakeCache.txt"
        cache.write_text(
            "\n".join(
                f"{name}:PATH={foreign if name == 'JAVA_INCLUDE_PATH' else path}"
                for name, path in expected.items()
            ),
            encoding="utf-8",
        )

        audit = QUALIFICATION.audit_cmake_jni_cache(cache, expected)

        self.assertFalse(audit["matched"])
        self.assertEqual(audit["status"], "FAILED_JDK_PATH_MISMATCH")
        self.assertTrue(
            any(item.startswith("JAVA_INCLUDE_PATH:EXPECTED:") for item in audit["mismatches"])
        )

    def test_cmake_jni_cache_rejects_additional_foreign_jni_path(self) -> None:
        java_home = self.make_fake_jdk()
        expected = QUALIFICATION.exact_jni_toolchain(java_home)
        foreign = self.root / "homebrew-openjdk-26/include"
        foreign.mkdir(parents=True)
        (foreign / "jni.h").write_text("foreign", encoding="utf-8")
        cache = self.root / "CMakeCache.txt"
        cache.write_text(
            "\n".join(
                [*(f"{name}:PATH={path}" for name, path in expected.items()),
                 f"JNI_INCLUDE_DIRS:PATH={expected['JAVA_INCLUDE_PATH']};{foreign}"]
            ),
            encoding="utf-8",
        )

        audit = QUALIFICATION.audit_cmake_jni_cache(cache, expected)

        self.assertFalse(audit["matched"])
        self.assertIn(
            f"FOREIGN_JNI_PATH:JNI_INCLUDE_DIRS:{foreign.resolve()}",
            audit["mismatches"],
        )
        self.assertRegex(audit["cache_sha256"], r"^[0-9a-f]{64}$")

    def test_cmake_command_pins_jdk_compiler_and_make(self) -> None:
        java_home = self.make_fake_jdk()
        expected = QUALIFICATION.exact_jni_toolchain(java_home)
        cmake = self.root / "cmake"
        cxx = self.root / "c++"
        make = self.root / "make"
        command = QUALIFICATION.cmake_configure_command(
            cmake=cmake,
            cxx=cxx,
            make=make,
            source=self.root / "source",
            build=self.root / "build",
            jni_toolchain=expected,
        )

        self.assertEqual(command[0], str(cmake))
        self.assertIn(f"-DCMAKE_CXX_COMPILER={cxx}", command)
        self.assertIn(f"-DCMAKE_MAKE_PROGRAM={make}", command)
        for name, path in expected.items():
            self.assertIn(f"-D{name}={path}", command)

    def test_exact_executable_audit_requires_digest_and_exact_version_line(self) -> None:
        executable = self.root / "tool"
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        execution = {
            "exit_code": 0,
            "timed_out": False,
            "output": "tool version 17.0.11\n",
        }
        identity = {
            "sha256": QUALIFICATION.sha256_file(executable),
            "version_line": "tool version 17.0.11",
        }
        with mock.patch.object(QUALIFICATION, "run_command", return_value=execution):
            matched = QUALIFICATION.exact_executable_audit(
                name="source_java",
                executable=executable,
                identity=identity,
                cwd=self.root,
            )
            digest_mismatch = QUALIFICATION.exact_executable_audit(
                name="source_java",
                executable=executable,
                identity={**identity, "sha256": "0" * 64},
                cwd=self.root,
            )
            version_mismatch = QUALIFICATION.exact_executable_audit(
                name="source_java",
                executable=executable,
                identity={**identity, "version_line": "tool version 17"},
                cwd=self.root,
            )

        self.assertTrue(matched["matched"])
        self.assertFalse(digest_mismatch["matched"])
        self.assertFalse(version_mismatch["matched"])
        self.assertEqual(matched["sha256"], identity["sha256"])
        self.assertEqual(matched["bytes"], executable.stat().st_size)
        self.assertTrue(matched["identity_stable_during_audit"])
        self.assertEqual(
            matched["evidence_scope"],
            "LOCAL_TOOLCHAIN_ENGINEERING_AUDIT_NOT_ROOTLESS_ATTESTATION",
        )

        def mutate_during_version_check(*args: object, **kwargs: object) -> dict[str, object]:
            executable.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            return execution

        with mock.patch.object(
            QUALIFICATION,
            "run_command",
            side_effect=mutate_during_version_check,
        ):
            drift = QUALIFICATION.exact_executable_audit(
                name="source_java",
                executable=executable,
                identity=identity,
                cwd=self.root,
            )
        self.assertFalse(drift["matched"])
        self.assertFalse(drift["identity_stable_during_audit"])
        self.assertEqual(drift["status"], "FAILED_EXECUTABLE_DRIFT_DURING_AUDIT")
        self.assertIsNone(drift["execution_path"])

    def test_maven_commands_are_strict_and_workspace_isolated(self) -> None:
        workspace = self.root / "workspace"
        workspace.mkdir()
        isolation = QUALIFICATION.prepare_maven_isolation(workspace)
        arguments = QUALIFICATION.exact_maven_arguments(isolation)

        self.assertIn("--strict-checksums", arguments)
        self.assertIn(
            f"-Dmaven.repo.local={isolation['local_repository']}", arguments
        )
        self.assertIn(f"-Duser.home={isolation['user_home']}", arguments)
        for path in isolation.values():
            self.assertTrue(path.is_relative_to(workspace.resolve()))

        java_home = self.make_fake_jdk("maven-jdk")
        contaminated = {
            "MAVEN_ARGS": "--lax-checksums",
            "MAVEN_CONFIG": "/foreign",
            "MAVEN_OPTS": "-Dmaven.repo.local=/foreign",
            "JAVA_TOOL_OPTIONS": "-Duser.home=/foreign",
            "HOME": "/foreign",
        }
        with mock.patch.dict(QUALIFICATION.os.environ, contaminated, clear=False):
            environment = QUALIFICATION.exact_maven_environment(
                java_home, isolation
            )
        self.assertNotIn("MAVEN_ARGS", environment)
        self.assertNotIn("MAVEN_CONFIG", environment)
        self.assertNotIn("JAVA_TOOL_OPTIONS", environment)
        self.assertNotIn("/foreign", environment["MAVEN_OPTS"])
        self.assertEqual(environment["HOME"], str(isolation["user_home"]))

    def test_all_untrusted_execution_helpers_require_protected_rootless_runner(self) -> None:
        missing = Path("/missing")
        with mock.patch.object(QUALIFICATION, "run_command") as run:
            results = [
                QUALIFICATION.native_build(
                    self.root,
                    missing,
                    {},
                    cmake=missing,
                    cxx=missing,
                    make=missing,
                ),
                QUALIFICATION.source_test_command(
                    self.root,
                    missing,
                    missing,
                    {},
                    {},
                    {},
                ),
                QUALIFICATION.transform_target(
                    self.root,
                    self.root / "target",
                    {},
                    missing,
                    missing,
                    {},
                ),
                QUALIFICATION.qualify_target(
                    source=self.root,
                    workspace=self.root,
                    repository={},
                    maven=missing,
                    cmake=missing,
                    cxx=missing,
                    make=missing,
                    maven_isolation={},
                    target_java_home=None,
                    source_reports={"test_cases": []},
                    expected_tests=0,
                ),
            ]
        run.assert_not_called()
        self.assertTrue(all(result["status"] == QUALIFICATION.ROOTLESS_EXECUTION_STATUS for result in results))
        self.assertTrue(all(result["execution_enabled"] is False for result in results))
        self.assertTrue(
            all(result["caller_supplied_attestation_accepted"] is False for result in results)
        )

    def test_local_engineering_path_is_separate_and_never_certifying(self) -> None:
        self.assertEqual(LOCAL_REPLAY.LOCAL_EVIDENCE_CLASS, "LOCAL_NON_CERTIFYING")
        self.assertEqual(LOCAL_REPLAY.LOCAL_START_FREE_BYTES, 12 * 1024**3)
        self.assertEqual(LOCAL_REPLAY.LOCAL_HARD_STOP_FREE_BYTES, 8 * 1024**3)
        protected = QUALIFICATION.protected_execution_gate("source-tests")
        self.assertEqual(protected["status"], QUALIFICATION.ROOTLESS_EXECUTION_STATUS)
        self.assertFalse(protected["execution_enabled"])
        self.assertFalse(protected["caller_supplied_attestation_accepted"])

    def test_local_service_alias_refuses_to_overwrite_different_image(self) -> None:
        exact = {
            "available": True,
            "id": "sha256:exact",
            "repo_digests": ["postgres@sha256:" + "1" * 64],
            "platform": "linux/arm64",
        }
        occupied = {
            "available": True,
            "id": "sha256:different",
            "repo_digests": [],
            "platform": "linux/arm64",
        }
        repository = {
            "service_images": [
                {
                    "role": "postgresql-testcontainers",
                    "source_reference": "postgres:13-alpine",
                    "execution_reference": "postgres@sha256:" + "1" * 64,
                    "platform": "linux/arm64",
                }
            ]
        }
        with (
            mock.patch.object(LOCAL_REPLAY.shutil, "which", return_value="docker"),
            mock.patch.object(
                LOCAL_REPLAY, "_image_inspect", side_effect=[exact, occupied]
            ),
            mock.patch.object(LOCAL_REPLAY.protected, "run_command") as run,
            self.assertRaisesRegex(
                LOCAL_REPLAY.protected.QualificationError,
                "LOCAL_SOURCE_TAG_OCCUPIED_BY_DIFFERENT_IMAGE",
            ),
        ):
            LOCAL_REPLAY.prepare_service_aliases(repository, self.root)
        run.assert_not_called()

    def test_local_maven_binds_audited_docker_socket_and_supported_api(self) -> None:
        workspace = self.root / "local-maven-workspace"
        workspace.mkdir()
        isolation = LOCAL_REPLAY.protected.prepare_maven_isolation(workspace)
        java_home = self.make_fake_jdk("local-maven-jdk")
        repository = {
            "source_test_properties": {
                "spring.datasource.url": "jdbc:tc:postgresql:13-alpine:///db",
                "spring.datasource.driver-class-name": (
                    "org.testcontainers.jdbc.ContainerDatabaseDriver"
                ),
            },
            "timeouts_seconds": {"source_tests": 30},
        }
        completed = {
            "command": [],
            "started_at": "2026-08-11T00:00:00Z",
            "finished_at": "2026-08-11T00:00:01Z",
            "exit_code": 0,
            "timed_out": False,
            "output": "",
            "output_sha256": "0" * 64,
            "output_bytes": 0,
            "capacity_samples": [
                {
                    "operation": "source-maven-tests:start",
                    "free_bytes": 13 * 1024**3,
                    "status": "PASSED",
                }
            ],
        }
        with mock.patch.object(
            LOCAL_REPLAY, "run_capacity_bounded_command", return_value=completed
        ) as run:
            result = LOCAL_REPLAY.local_test_execution(
                workspace,
                self.root / "mvn",
                java_home,
                {"library_directory": str(self.root / "native")},
                repository,
                isolation,
                "testcontainers/ryuk@sha256:" + "2" * 64,
                {
                    "endpoint": "unix:///audited/docker.sock",
                    "server_minimum_api_version": "1.40",
                },
                timeout_key="source_tests",
                stage="source-maven-tests",
            )
        environment = run.call_args.kwargs["environment"]
        self.assertEqual(environment["DOCKER_HOST"], "unix:///audited/docker.sock")
        self.assertEqual(environment["DOCKER_API_VERSION"], "1.40")
        self.assertEqual(environment["api.version"], "1.40")
        self.assertEqual(
            environment["TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"],
            "/var/run/docker.sock",
        )
        self.assertEqual(result["docker_client_binding"]["rootless_attested"], False)
        self.assertTrue(
            any("-Dapi.version=1.40" in item for item in run.call_args.args[0])
        )

    def test_capacity_bounded_command_hard_stops_isolated_process_group(self) -> None:
        high = {
            "operation": "test:start",
            "observed_at": "2026-08-11T00:00:00Z",
            "free_bytes": 13 * 1024**3,
            "start_minimum_bytes": 12 * 1024**3,
            "hard_stop_bytes": 8 * 1024**3,
            "status": "PASSED",
        }
        low = {
            **high,
            "operation": "test:in-flight",
            "free_bytes": 8 * 1024**3,
            "status": "HARD_STOP",
        }
        final = {**low, "operation": "test:finished"}
        persisted: list[dict[str, object]] = []
        with mock.patch.object(
            LOCAL_REPLAY,
            "capacity_observation",
            side_effect=[high, low, final],
        ):
            execution = LOCAL_REPLAY.run_capacity_bounded_command(
                [
                    sys.executable,
                    "-c",
                    "import time; print('started', flush=True); time.sleep(30)",
                ],
                cwd=self.root,
                environment=None,
                timeout_seconds=10,
                capacity_path=self.root,
                operation="test",
                progress_callback=persisted.append,
                poll_interval_seconds=0.01,
            )
        self.assertTrue(execution["capacity_stopped"])
        self.assertFalse(execution["timed_out"])
        self.assertTrue(execution["process_group_isolated"])
        self.assertEqual(execution["termination"]["reason"], "CAPACITY_HARD_STOP")
        self.assertEqual(execution["capacity_poll_interval_seconds"], 0.01)
        self.assertTrue(persisted[-1]["capacity_stopped"])

    def test_capacity_bounded_command_persists_raw_output_on_success(self) -> None:
        high = {
            "operation": "test",
            "observed_at": "2026-08-11T00:00:00Z",
            "free_bytes": 13 * 1024**3,
            "start_minimum_bytes": 12 * 1024**3,
            "hard_stop_bytes": 8 * 1024**3,
            "status": "PASSED",
        }
        persisted: list[dict[str, object]] = []
        with mock.patch.object(
            LOCAL_REPLAY, "capacity_observation", return_value=high
        ):
            execution = LOCAL_REPLAY.run_capacity_bounded_command(
                [sys.executable, "-c", "print('raw-evidence')"],
                cwd=self.root,
                environment=None,
                timeout_seconds=10,
                capacity_path=self.root,
                operation="test",
                progress_callback=persisted.append,
                poll_interval_seconds=0.01,
            )
        self.assertEqual(execution["exit_code"], 0)
        self.assertEqual(execution["output"], "raw-evidence\n")
        self.assertEqual(execution["output_bytes"], len(b"raw-evidence\n"))
        self.assertRegex(execution["output_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(persisted[-1]["output"], "raw-evidence\n")

    def test_capacity_bounded_command_refuses_below_start_threshold(self) -> None:
        below_start = {
            "operation": "test:start",
            "observed_at": "2026-08-11T00:00:00Z",
            "free_bytes": 11 * 1024**3,
            "start_minimum_bytes": 12 * 1024**3,
            "hard_stop_bytes": 8 * 1024**3,
            "status": "BELOW_START_THRESHOLD",
        }
        persisted: list[dict[str, object]] = []
        with (
            mock.patch.object(
                LOCAL_REPLAY, "capacity_observation", return_value=below_start
            ),
            mock.patch.object(LOCAL_REPLAY.subprocess, "Popen") as popen,
            self.assertRaisesRegex(
                LOCAL_REPLAY.protected.QualificationError,
                "LOCAL_CAPACITY_BELOW_START_THRESHOLD",
            ),
        ):
            LOCAL_REPLAY.run_capacity_bounded_command(
                ["never-started"],
                cwd=self.root,
                environment=None,
                timeout_seconds=10,
                capacity_path=self.root,
                operation="test",
                progress_callback=persisted.append,
            )
        popen.assert_not_called()
        self.assertEqual(persisted[-1]["status"], "NOT_STARTED_CAPACITY_GATE")

    def test_capacity_bounded_command_persists_interrupted_stage(self) -> None:
        high = {
            "operation": "test",
            "observed_at": "2026-08-11T00:00:00Z",
            "free_bytes": 13 * 1024**3,
            "start_minimum_bytes": 12 * 1024**3,
            "hard_stop_bytes": 8 * 1024**3,
            "status": "PASSED",
        }
        persisted: list[dict[str, object]] = []
        first = True

        def interrupt_once(payload: dict[str, object]) -> None:
            nonlocal first
            if first:
                first = False
                raise KeyboardInterrupt
            persisted.append(payload)

        with (
            mock.patch.object(
                LOCAL_REPLAY, "capacity_observation", return_value=high
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            LOCAL_REPLAY.run_capacity_bounded_command(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=self.root,
                environment=None,
                timeout_seconds=10,
                capacity_path=self.root,
                operation="test",
                progress_callback=interrupt_once,
                poll_interval_seconds=0.01,
            )
        self.assertEqual(persisted[-1]["status"], "INTERRUPTED")
        self.assertEqual(
            persisted[-1]["termination"]["reason"], "CALLER_INTERRUPTED"
        )
        self.assertEqual(
            persisted[-1]["interruption"]["message"], "operation interrupted"
        )
        self.assertRegex(persisted[-1]["output_sha256"], r"^[0-9a-f]{64}$")

    def test_cleanup_failure_downgrades_overall_status(self) -> None:
        receipt = {"overall_status": "PASSED_LOCAL_NON_CERTIFYING"}
        passed = LOCAL_REPLAY.apply_cleanup_gate(
            receipt,
            [
                {
                    "resource": "runner",
                    "kind": "temporary-runner",
                    "removed": False,
                }
            ],
        )
        self.assertFalse(passed)
        self.assertEqual(receipt["overall_status"], "FAILED_CLEANUP")
        self.assertEqual(
            receipt["pre_cleanup_overall_status"],
            "PASSED_LOCAL_NON_CERTIFYING",
        )

    def test_nested_daemon_cleanup_removes_container_and_anonymous_volumes(self) -> None:
        name = "elmos-retro-dind-test"
        before = {
            "exit_code": 0,
            "timed_out": False,
            "output": json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "io.elmos.evidence-class": "LOCAL_NON_CERTIFYING"
                            }
                        },
                        "HostConfig": {"Privileged": True},
                        "Mounts": [
                            {"Type": "volume", "Name": "volume-b"},
                            {"Type": "bind", "Source": "/tmp/source"},
                            {"Type": "volume", "Name": "volume-a"},
                        ],
                    }
                ]
            ),
        }
        removed = {"exit_code": 0, "timed_out": False, "output": name + "\n"}
        absent_container = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: No such container: " + name + "\n"
            ),
        }
        absent_volume_a = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: get volume-a: no such volume\n"
            ),
        }
        absent_volume_b = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: get volume-b: no such volume\n"
            ),
        }
        with mock.patch.object(
            LINUX_REPLAY,
            "_run",
            side_effect=[
                before,
                removed,
                absent_container,
                absent_volume_a,
                absent_volume_b,
            ],
        ) as run:
            result = LINUX_REPLAY.cleanup_nested_daemon(
                name=name, run_attempted=True, cwd=self.root
            )
        self.assertTrue(result["removed"])
        self.assertEqual(result["status"], "REMOVED_WITH_VOLUMES")
        self.assertEqual(result["attached_volumes"], ["volume-a", "volume-b"])
        self.assertEqual(
            run.call_args_list[1].args[0][1:],
            ["container", "rm", "--force", "--volumes", name],
        )

    def test_nested_daemon_cleanup_handles_failed_run_without_container(self) -> None:
        name = "elmos-retro-dind-never-created"
        absent = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: No such container: " + name + "\n"
            ),
        }
        with mock.patch.object(
            LINUX_REPLAY, "_run", side_effect=[absent, absent, absent]
        ):
            result = LINUX_REPLAY.cleanup_nested_daemon(
                name=name, run_attempted=True, cwd=self.root
            )
        self.assertTrue(result["removed"])
        self.assertEqual(result["status"], "REMOVED_WITH_VOLUMES")
        self.assertEqual(result["attached_volumes"], [])

    def test_nested_daemon_cleanup_refuses_wrong_identity(self) -> None:
        name = "elmos-retro-dind-wrong-identity"
        before = {
            "exit_code": 0,
            "timed_out": False,
            "output": json.dumps(
                [
                    {
                        "Config": {"Labels": {}},
                        "HostConfig": {"Privileged": False},
                        "Mounts": [],
                    }
                ]
            ),
        }
        with (
            mock.patch.object(LINUX_REPLAY, "_run", return_value=before) as run,
            self.assertRaisesRegex(
                LINUX_REPLAY.protected.QualificationError,
                "LOCAL_NESTED_DAEMON_CLEANUP_IDENTITY_MISMATCH",
            ),
        ):
            LINUX_REPLAY.cleanup_nested_daemon(
                name=name, run_attempted=True, cwd=self.root
            )
        self.assertEqual(run.call_count, 1)

    def test_nested_daemon_cleanup_rejects_remaining_volume(self) -> None:
        name = "elmos-retro-dind-volume-remains"
        before = {
            "exit_code": 0,
            "timed_out": False,
            "output": json.dumps(
                [
                    {
                        "Config": {
                            "Labels": {
                                "io.elmos.evidence-class": "LOCAL_NON_CERTIFYING"
                            }
                        },
                        "HostConfig": {"Privileged": True},
                        "Mounts": [{"Type": "volume", "Name": "volume-a"}],
                    }
                ]
            ),
        }
        removed = {"exit_code": 0, "timed_out": False, "output": name + "\n"}
        absent_container = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: No such container: " + name + "\n"
            ),
        }
        remaining_volume = {
            "exit_code": 0,
            "timed_out": False,
            "output": json.dumps([{"Name": "volume-a"}]),
        }
        with mock.patch.object(
            LINUX_REPLAY,
            "_run",
            side_effect=[before, removed, absent_container, remaining_volume],
        ):
            result = LINUX_REPLAY.cleanup_nested_daemon(
                name=name, run_attempted=True, cwd=self.root
            )
        self.assertFalse(result["removed"])
        self.assertEqual(result["status"], "FAILED_ORPHAN_CHECK")

    def test_temporary_network_cleanup_removes_interrupted_create(self) -> None:
        name = "elmos-retro-internal-interrupted"
        before = {
            "exit_code": 0,
            "timed_out": False,
            "output": json.dumps(
                [
                    {
                        "Name": name,
                        "Driver": "bridge",
                        "Internal": True,
                        "Labels": {
                            "io.elmos.evidence-class": "LOCAL_NON_CERTIFYING"
                        },
                    }
                ]
            ),
        }
        removed = {"exit_code": 0, "timed_out": False, "output": name + "\n"}
        absent = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: network " + name + " not found\n"
            ),
        }
        with mock.patch.object(
            LINUX_REPLAY, "_run", side_effect=[before, removed, absent]
        ) as run:
            result = LINUX_REPLAY.cleanup_temporary_network(
                name=name,
                internal=True,
                create_attempted=True,
                cwd=self.root,
            )
        self.assertTrue(result["removed"])
        self.assertEqual(result["status"], "REMOVED")
        self.assertEqual(
            run.call_args_list[1].args[0][1:], ["network", "rm", name]
        )

    def test_temporary_network_cleanup_handles_create_without_object(self) -> None:
        name = "elmos-retro-stage-never-created"
        absent = {
            "exit_code": 1,
            "timed_out": False,
            "output": (
                "[]\nError response from daemon: network " + name + " not found\n"
            ),
        }
        with mock.patch.object(
            LINUX_REPLAY, "_run", side_effect=[absent, absent, absent]
        ):
            result = LINUX_REPLAY.cleanup_temporary_network(
                name=name,
                internal=False,
                create_attempted=True,
                cwd=self.root,
            )
        self.assertTrue(result["removed"])
        self.assertEqual(result["status"], "REMOVED")

    def test_linux_replay_main_returns_130_on_keyboard_interrupt(self) -> None:
        args = argparse.Namespace(
            manifest=self.root / "manifest.json",
            repository_id="retro-game",
            archive=self.root / "archive.tar.gz",
            workspace=self.root / "workspace",
            output=self.root / "receipt.json",
            maven_repository=self.root / "m2",
            runner_dockerfile=self.root / "Dockerfile",
            local_engineering_non_certifying=True,
            authorize_privileged_nested_daemon=True,
        )
        with (
            mock.patch.object(LINUX_REPLAY, "parse_args", return_value=args),
            mock.patch.object(LINUX_REPLAY, "replay", side_effect=KeyboardInterrupt),
            mock.patch.object(LINUX_REPLAY.sys, "stderr", io.StringIO()),
        ):
            self.assertEqual(LINUX_REPLAY.main(), 130)

    def test_linux_replay_installs_cleanup_signal_handlers(self) -> None:
        with mock.patch.object(LINUX_REPLAY.signal, "signal") as install:
            LINUX_REPLAY.install_termination_signal_handlers()
        self.assertEqual(
            install.call_args_list,
            [
                mock.call(
                    LINUX_REPLAY.signal.SIGTERM,
                    LINUX_REPLAY._termination_signal_handler,
                ),
                mock.call(
                    LINUX_REPLAY.signal.SIGHUP,
                    LINUX_REPLAY._termination_signal_handler,
                ),
            ],
        )
        with self.assertRaisesRegex(KeyboardInterrupt, "received SIGTERM"):
            LINUX_REPLAY._termination_signal_handler(
                LINUX_REPLAY.signal.SIGTERM, None
            )

    def test_linux_runner_cleanup_requires_exact_identity(self) -> None:
        candidate = {
            "available": True,
            "id": "sha256:" + "a" * 64,
            "repo_tags": ["elmos-local/retro-game-linux-amd64:test"],
            "repo_digests": [],
            "derived_identity_matched": False,
        }
        with (
            mock.patch.object(
                LINUX_REPLAY, "optional_image_audit", return_value=candidate
            ),
            mock.patch.object(LINUX_REPLAY, "_run") as run,
        ):
            cleanup = LINUX_REPLAY.cleanup_derived_runner(
                runner_tag="elmos-local/retro-game-linux-amd64:test",
                build_attempted=True,
                tag_preexisting=False,
                preexisting_image_ids=set(),
                expected_image_id="sha256:" + "a" * 64,
                cwd=self.root,
            )
        self.assertFalse(cleanup["removed"])
        self.assertEqual(cleanup["status"], "FAILED_RUNNER_IDENTITY_MISMATCH")
        run.assert_not_called()

    def test_linux_runner_cleanup_removes_only_new_exact_image(self) -> None:
        image_id = "sha256:" + "b" * 64
        candidate = {
            "available": True,
            "id": image_id,
            "repo_tags": ["elmos-local/retro-game-linux-amd64:test"],
            "repo_digests": [],
            "derived_identity_matched": True,
        }
        absent = {"available": False, "reference": image_id}
        removed = {
            "exit_code": 0,
            "timed_out": False,
            "output": "Deleted",
        }
        with (
            mock.patch.object(
                LINUX_REPLAY,
                "optional_image_audit",
                side_effect=[candidate, absent],
            ),
            mock.patch.object(LINUX_REPLAY, "_run", return_value=removed) as run,
        ):
            cleanup = LINUX_REPLAY.cleanup_derived_runner(
                runner_tag="elmos-local/retro-game-linux-amd64:test",
                build_attempted=True,
                tag_preexisting=False,
                preexisting_image_ids=set(),
                expected_image_id=image_id,
                cwd=self.root,
            )
        self.assertTrue(cleanup["removed"])
        self.assertEqual(
            cleanup["status"], "REMOVED_RUNNER_TAG_AND_DERIVED_IMAGE"
        )
        self.assertEqual(run.call_args.args[0][3], cleanup["resource"])

    def test_linux_runner_cleanup_does_not_delete_preexisting_only_reference(self) -> None:
        image_id = "sha256:" + "c" * 64
        candidate = {
            "available": True,
            "id": image_id,
            "repo_tags": ["elmos-local/retro-game-linux-amd64:test"],
            "repo_digests": [],
            "derived_identity_matched": True,
        }
        with (
            mock.patch.object(
                LINUX_REPLAY, "optional_image_audit", return_value=candidate
            ),
            mock.patch.object(LINUX_REPLAY, "_run") as run,
        ):
            cleanup = LINUX_REPLAY.cleanup_derived_runner(
                runner_tag="elmos-local/retro-game-linux-amd64:test",
                build_attempted=True,
                tag_preexisting=False,
                preexisting_image_ids={image_id},
                expected_image_id=image_id,
                cwd=self.root,
            )
        self.assertFalse(cleanup["removed"])
        self.assertEqual(
            cleanup["status"],
            "FAILED_PREEXISTING_IMAGE_HAS_ONLY_TEMPORARY_TAG",
        )
        run.assert_not_called()

    def test_target_pom_audit_requires_exact_boot_and_java(self) -> None:
        source = self.make_source()
        pom = source / "pom.xml"
        pom.write_text(
            pom.read_text(encoding="utf-8")
            .replace("<version>2.7.18</version>", "<version>3.5.3</version>")
            .replace("<java.version>17</java.version>", "<java.version>21</java.version>"),
            encoding="utf-8",
        )
        audit = QUALIFICATION.target_pom_audit(
            source, {"target": {"spring_boot": "3.5.3", "java": "21"}}
        )
        self.assertTrue(audit["matched"])
        self.assertRegex(audit["pom_sha256"], r"^[0-9a-f]{64}$")

    def test_atomic_evidence_replaces_without_temporary_residue(self) -> None:
        destination = self.root / "evidence.json"
        QUALIFICATION.atomic_json(destination, {"status": "NOT_RUN"})
        QUALIFICATION.atomic_json(destination, {"status": "BLOCKED"})
        self.assertEqual(
            json.loads(destination.read_text(encoding="utf-8")),
            {"status": "BLOCKED"},
        )
        self.assertEqual(list(self.root.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
