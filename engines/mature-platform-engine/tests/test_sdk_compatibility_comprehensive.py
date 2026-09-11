"""Comprehensive test suite for SdkCompatibilityEngine (Batch 43 - Skill 1439)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.sdk_compatibility_engine import SdkCompatibilityEngine
from elmos_mature_platform.types import (
    SdkCompatibilityAssessment,
    SdkCompatibilityLevel,
    SdkLanguage,
    SdkPackageRelease,
)


class TestSdkCompatibilityComprehensive(unittest.TestCase):
    """Rigorous unit testing for SdkCompatibilityEngine."""

    def setUp(self) -> None:
        self.engine = SdkCompatibilityEngine()

    def test_register_sdk_release_success(self) -> None:
        release = SdkPackageRelease(
            sdk_id="sdk-py-v1",
            language=SdkLanguage.PYTHON,
            version="1.0.0",
            supported_server_versions=["v1.0", "v1.1"],
            min_runtime_version="3.10",
            checksum_sha256="abcdef123456",
        )
        sdk_id = self.engine.register_sdk_release(release)
        self.assertEqual(sdk_id, "sdk-py-v1")
        fetched = self.engine.get_sdk_release(sdk_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.language, SdkLanguage.PYTHON)
        self.assertEqual(fetched.version, "1.0.0")

    def test_register_sdk_release_auto_generates_id_and_date(self) -> None:
        release = SdkPackageRelease(
            sdk_id="",
            language=SdkLanguage.TYPESCRIPT,
            version="2.1.0",
        )
        sdk_id = self.engine.register_sdk_release(release)
        self.assertEqual(sdk_id, "sdk-typescript-2.1.0")
        self.assertTrue(len(release.published_at) > 0)

    def test_register_sdk_release_missing_version_or_language(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_sdk_release(
                SdkPackageRelease(sdk_id="1", language=SdkLanguage.JAVA, version="")
            )

    def test_assess_compatibility_fully_compatible(self) -> None:
        release = SdkPackageRelease(
            sdk_id="sdk-go-v1",
            language=SdkLanguage.GOLANG,
            version="1.0.0",
            supported_server_versions=["v2.0"],
        )
        self.engine.register_sdk_release(release)

        assessment = self.engine.assess_compatibility(
            sdk_id="sdk-go-v1",
            target_server_version="v2.1",
            broken_methods=[],
            deprecated_methods=[],
            notes="All contract tests passed with zero failures",
        )
        self.assertEqual(assessment.level, SdkCompatibilityLevel.FULLY_COMPATIBLE)
        self.assertIn("v2.1", release.supported_server_versions)

    def test_assess_compatibility_with_deprecations(self) -> None:
        release = SdkPackageRelease(
            sdk_id="sdk-cs-v1",
            language=SdkLanguage.CSHARP,
            version="1.0.0",
        )
        self.engine.register_sdk_release(release)

        assessment = self.engine.assess_compatibility(
            sdk_id="sdk-cs-v1",
            target_server_version="v2.2",
            deprecated_methods=["ExecuteLegacyPipeline"],
            broken_methods=[],
            notes="Uses deprecated endpoint",
        )
        self.assertEqual(assessment.level, SdkCompatibilityLevel.COMPATIBLE_WITH_DEPRECATIONS)
        self.assertIn("v2.2", release.supported_server_versions)

    def test_assess_compatibility_incompatible(self) -> None:
        release = SdkPackageRelease(
            sdk_id="sdk-java-v1",
            language=SdkLanguage.JAVA,
            version="1.0.0",
        )
        self.engine.register_sdk_release(release)

        assessment = self.engine.assess_compatibility(
            sdk_id="sdk-java-v1",
            target_server_version="v3.0",
            broken_methods=["AuthenticateTokenV1", "StreamEvents"],
            deprecated_methods=[],
            notes="Breaking payload protocol changes",
        )
        self.assertEqual(assessment.level, SdkCompatibilityLevel.INCOMPATIBLE)
        self.assertNotIn("v3.0", release.supported_server_versions)

    def test_assess_compatibility_missing_sdk_or_server_version(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.assess_compatibility("nonexistent-sdk", "v1.0")

        self.engine.register_sdk_release(
            SdkPackageRelease(sdk_id="s1", language=SdkLanguage.PYTHON, version="1.0")
        )
        with self.assertRaises(ValueError):
            self.engine.assess_compatibility("s1", "")

    def test_get_compatible_sdks(self) -> None:
        py_sdk = SdkPackageRelease(
            sdk_id="py-1",
            language=SdkLanguage.PYTHON,
            version="1.0.0",
            supported_server_versions=["v1.0", "v1.1"],
        )
        ts_sdk = SdkPackageRelease(
            sdk_id="ts-1",
            language=SdkLanguage.TYPESCRIPT,
            version="1.0.0",
            supported_server_versions=["v1.1"],
        )
        go_sdk = SdkPackageRelease(
            sdk_id="go-1",
            language=SdkLanguage.GOLANG,
            version="1.0.0",
            supported_server_versions=["v2.0"],
        )
        self.engine.register_sdk_release(py_sdk)
        self.engine.register_sdk_release(ts_sdk)
        self.engine.register_sdk_release(go_sdk)

        res_v11 = self.engine.get_compatible_sdks("v1.1")
        self.assertEqual(len(res_v11), 2)
        res_v11_py = self.engine.get_compatible_sdks("v1.1", language=SdkLanguage.PYTHON)
        self.assertEqual(len(res_v11_py), 1)
        self.assertEqual(res_v11_py[0].sdk_id, "py-1")

        res_v20 = self.engine.get_compatible_sdks("v2.0")
        self.assertEqual(len(res_v20), 1)
        self.assertEqual(res_v20[0].sdk_id, "go-1")

        res_v99 = self.engine.get_compatible_sdks("v9.9")
        self.assertEqual(len(res_v99), 0)

    def test_get_sdk_matrix_report(self) -> None:
        report_empty = self.engine.get_sdk_matrix_report()
        self.assertEqual(report_empty["total_sdk_releases"], 0)
        self.assertEqual(report_empty["total_assessments_recorded"], 0)

        # Add releases and assessments
        r1 = SdkPackageRelease(sdk_id="r1", language=SdkLanguage.PYTHON, version="1.0")
        r2 = SdkPackageRelease(sdk_id="r2", language=SdkLanguage.PYTHON, version="2.0")
        r3 = SdkPackageRelease(sdk_id="r3", language=SdkLanguage.JAVA, version="1.0")
        self.engine.register_sdk_release(r1)
        self.engine.register_sdk_release(r2)
        self.engine.register_sdk_release(r3)

        self.engine.assess_compatibility("r1", "v1.0")
        self.engine.assess_compatibility("r3", "v2.0", broken_methods=["fail"])

        rep = self.engine.get_sdk_matrix_report()
        self.assertEqual(rep["total_sdk_releases"], 3)
        self.assertEqual(rep["by_language"]["python"], 2)
        self.assertEqual(rep["by_language"]["java"], 1)
        self.assertEqual(rep["total_assessments_recorded"], 2)
        self.assertEqual(rep["incompatible_evaluations_count"], 1)


if __name__ == "__main__":
    unittest.main()
