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
        self.assertEqual(retro["target"]["spring_boot"], "3.5.3")
        self.assertEqual(retro["target"]["java"], "21")
        self.assertEqual(retro["target"]["maven"], "3.9.11")
        candidate = manifest["separate_public_candidates"][0]
        self.assertEqual(candidate["source_execution"], "NOT_RUN")
        self.assertEqual(candidate["target_execution"], "NOT_RUN")
        self.assertFalse(candidate["customer_repository"])
        self.assertFalse(candidate["independent_verification"])

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

    def test_service_image_requires_source_tag_to_match_pinned_digest(self) -> None:
        repository = {
            "service_images": [
                {
                    "role": "postgres",
                    "source_reference": "postgres:13-alpine",
                    "resolved_reference": "postgres@sha256:" + "1" * 64,
                    "platform": "linux/arm64",
                    "platform_digest": "sha256:" + "1" * 64,
                }
            ]
        }
        records = [
            {
                "exit_code": 0,
                "output": json.dumps([{"Id": "sha256:pinned"}]),
                "timed_out": False,
            },
            {
                "exit_code": 0,
                "output": json.dumps([{"Id": "sha256:other"}]),
                "timed_out": False,
            },
        ]
        with (
            mock.patch.object(QUALIFICATION.shutil, "which", return_value="docker"),
            mock.patch.object(QUALIFICATION, "run_command", side_effect=records),
        ):
            result = QUALIFICATION.service_image_audit(repository, self.root)[0]
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertEqual(result["reason"], "SOURCE_TAG_NOT_BOUND_TO_PINNED_IMAGE")

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
        java_home = self.root / "jdk-17"
        include = java_home / "include"
        platform_include = include / "darwin"
        server = java_home / "lib/server"
        platform_include.mkdir(parents=True)
        server.mkdir(parents=True)
        (include / "jni.h").write_text("jni", encoding="utf-8")
        (platform_include / "jni_md.h").write_text("jni-md", encoding="utf-8")
        (server / "libjvm.dylib").write_bytes(b"jvm")
        (java_home / "lib/libjawt.dylib").write_bytes(b"awt")

        selected = QUALIFICATION.exact_jni_toolchain(java_home)

        self.assertEqual(selected["JAVA_HOME"], java_home.resolve())
        self.assertEqual(selected["JAVA_INCLUDE_PATH"], include.resolve())
        self.assertEqual(selected["JAVA_INCLUDE_PATH2"], platform_include.resolve())
        for path in selected.values():
            self.assertTrue(path.is_relative_to(java_home.resolve()))

    def test_cmake_jni_cache_rejects_homebrew_or_other_jdk_paths(self) -> None:
        java_home = self.root / "jdk-17"
        include = java_home / "include"
        platform_include = include / "darwin"
        server = java_home / "lib/server"
        platform_include.mkdir(parents=True)
        server.mkdir(parents=True)
        (include / "jni.h").write_text("jni", encoding="utf-8")
        (platform_include / "jni_md.h").write_text("jni-md", encoding="utf-8")
        (server / "libjvm.dylib").write_bytes(b"jvm")
        (java_home / "lib/libjawt.dylib").write_bytes(b"awt")
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

    def test_target_execution_remains_blocked_without_java_21(self) -> None:
        result = QUALIFICATION.qualify_target(
            source=self.root,
            workspace=self.root,
            repository={},
            maven=Path("/missing/mvn"),
            target_java_home=None,
            source_reports={"test_cases": []},
            expected_tests=0,
        )
        self.assertEqual(result["status"], "NOT_RUN_TARGET_TOOLCHAIN_NOT_DECLARED")

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
