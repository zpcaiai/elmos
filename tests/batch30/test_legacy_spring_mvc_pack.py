import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "framework-packs" / "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
VALIDATOR = ROOT / "scripts" / "batch30" / "validate_legacy_spring_mvc_pack.py"


class LegacySpringMvcPackTests(unittest.TestCase):
    def run_validator(self, pack: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--pack-dir", str(pack)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_checked_in_pack_is_exact_and_fail_closed(self):
        completed = self.run_validator(PACK)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("status=experimental decision=NOT_CERTIFIED execution=NOT_RUN", completed.stdout)

    def test_source_test_dependencies_are_exactly_pinned(self):
        pom = (PACK / "corpus/development/legacy-spring-mvc/pom.xml").read_text(
            encoding="utf-8"
        )
        self.assertIn("<hamcrest.version>2.2</hamcrest.version>", pom)
        self.assertIn("<json-path.version>2.7.0</json-path.version>", pom)
        self.assertIn("<artifactId>hamcrest</artifactId>", pom)
        self.assertIn("<artifactId>json-path</artifactId>", pom)

    def mutated_pack(self, temporary: str) -> tuple[Path, Path]:
        copied = Path(temporary) / PACK.name
        shutil.copytree(PACK, copied)
        pom_path = copied / "corpus/development/legacy-spring-mvc/pom.xml"
        return copied, pom_path

    def test_commented_property_token_does_not_satisfy_xml_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom = pom.replace(
                "    <hamcrest.version>2.2</hamcrest.version>",
                "    <!-- <hamcrest.version>2.2</hamcrest.version> -->",
            )
            pom_path.write_text(pom, encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property hamcrest.version must appear exactly once",
                completed.stderr,
            )

    def test_duplicate_property_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            token = "    <json-path.version>2.7.0</json-path.version>"
            pom_path.write_text(pom.replace(token, f"{token}\n{token}"), encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property json-path.version must appear exactly once",
                completed.stderr,
            )

    def test_wrong_property_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(
                pom.replace(
                    "<hamcrest.version>2.2</hamcrest.version>",
                    "<hamcrest.version>2.1</hamcrest.version>",
                ),
                encoding="utf-8",
            )

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM property hamcrest.version must equal 2.2",
                completed.stderr,
            )

    def test_literal_dependency_version_cannot_replace_locked_expression(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied, pom_path = self.mutated_pack(temporary)
            pom = pom_path.read_text(encoding="utf-8")
            pom_path.write_text(
                pom.replace("<version>${json-path.version}</version>", "<version>2.7.0</version>"),
                encoding="utf-8",
            )

            completed = self.run_validator(copied)
            self.assertEqual(1, completed.returncode)
            self.assertIn(
                "fixture POM dependency com.jayway.jsonpath:json-path version "
                "must equal ${json-path.version}",
                completed.stderr,
            )

    def test_unearned_behavior_pass_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            certification_path = copied / "certification" / "certification.json"
            certification = json.loads(certification_path.read_text(encoding="utf-8"))
            certification["gate_results"]["behavior_equivalence"] = "PASSED"
            certification_path.write_text(json.dumps(certification, indent=2) + "\n", encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("runtime gate must remain NOT_RUN: behavior_equivalence", completed.stderr)

    def test_unearned_supported_capability_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / PACK.name
            shutil.copytree(PACK, copied)
            support_path = copied / "support-matrix.json"
            support = json.loads(support_path.read_text(encoding="utf-8"))
            support["capabilities"][0]["status"] = "supported"
            support_path.write_text(json.dumps(support, indent=2) + "\n", encoding="utf-8")

            completed = self.run_validator(copied)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("cannot contain supported/certified capabilities", completed.stderr)


if __name__ == "__main__":
    unittest.main()
