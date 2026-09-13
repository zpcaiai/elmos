import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/legacy-web-modernization-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_legacy_web_modernization.gradle_build_migrator import GradleBuildMigrator


class TestGradleModernizationBenchmarks(unittest.TestCase):
    def setUp(self):
        self.migrator = GradleBuildMigrator(target_boot="3.5.3", target_java="21")
        self.corpus_root = ROOT / "framework-packs/spring-boot-2-x-gradle-to-3-5-3/corpus"

    def test_tier1_starter_benchmark_migration(self):
        build_file = self.corpus_root / "tier1-starter/build.gradle"
        self.assertTrue(build_file.is_file(), f"Missing Tier 1 build file: {build_file}")
        content = build_file.read_text(encoding="utf-8")

        result = self.migrator.migrate(content)
        self.assertIn("3.5.3", result.migrated_content)
        self.assertIn("JavaLanguageVersion.of(21)", result.migrated_content)
        self.assertTrue(any("org.springframework.boot:3.5.3" in p for p in result.plugins_updated))
        self.assertIn("1.1.7", result.migrated_content)

    def test_tier2_security_jpa_benchmark_migration(self):
        build_file = self.corpus_root / "tier2-security-jpa/build.gradle"
        self.assertTrue(build_file.is_file(), f"Missing Tier 2 build file: {build_file}")
        content = build_file.read_text(encoding="utf-8")

        result = self.migrator.migrate(content)
        self.assertIn("3.5.3", result.migrated_content)
        self.assertIn("jakarta.persistence:jakarta.persistence-api:3.1.0", result.migrated_content)
        self.assertNotIn("javax.persistence:javax.persistence-api", result.migrated_content)
        self.assertIn("jakarta.persistence:jakarta.persistence-api:3.1.0", result.dependencies_migrated)

    def test_tier3_multimodule_benchmark_migration(self):
        root_build = self.corpus_root / "tier3-multimodule/build.gradle"
        common_build = self.corpus_root / "tier3-multimodule/common-domain/build.gradle"
        web_build = self.corpus_root / "tier3-multimodule/web-app/build.gradle"

        self.assertTrue(root_build.is_file())
        self.assertTrue(common_build.is_file())
        self.assertTrue(web_build.is_file())

        root_result = self.migrator.migrate(root_build.read_text(encoding="utf-8"))
        self.assertIn("3.5.3", root_result.migrated_content)
        self.assertIn("1.1.7", root_result.migrated_content)

        common_result = self.migrator.migrate(common_build.read_text(encoding="utf-8"))
        self.assertIn("jakarta.annotation:jakarta.annotation-api:2.1.1", common_result.migrated_content)
        self.assertNotIn("javax.annotation:javax.annotation-api", common_result.migrated_content)


if __name__ == "__main__":
    unittest.main()
