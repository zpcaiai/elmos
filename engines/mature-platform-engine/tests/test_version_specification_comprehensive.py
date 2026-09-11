"""Comprehensive test suite for VersionSpecificationEngine (Batch 43 - Skill 1436)."""

import unittest

from elmos_mature_platform.version_specification_engine import (
    VersionSpecificationEngine,
)
from elmos_mature_platform.types import (
    VersionChangeType,
)


class TestVersionSpecificationComprehensive(unittest.TestCase):
    """Rigorous tests covering SemVer 2.0.0 parsing, comparison, range matching, and compatibility resolution."""

    def setUp(self) -> None:
        self.engine = VersionSpecificationEngine()

    def test_parse_version_valid(self) -> None:
        v = self.engine.parse_version("1.2.3")
        self.assertEqual((v.major, v.minor, v.patch), (1, 2, 3))
        self.assertEqual(v.prerelease, "")
        self.assertEqual(v.build_metadata, "")

        v_pre = self.engine.parse_version("2.0.0-rc.1+build.123")
        self.assertEqual((v_pre.major, v_pre.minor, v_pre.patch), (2, 0, 0))
        self.assertEqual(v_pre.prerelease, "rc.1")
        self.assertEqual(v_pre.build_metadata, "build.123")

    def test_parse_version_invalid(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.parse_version("not-a-version")

        with self.assertRaises(ValueError):
            self.engine.parse_version("1.2")

    def test_compare_versions(self) -> None:
        self.assertEqual(self.engine.compare_versions("1.0.0", "1.0.0"), 0)
        self.assertEqual(self.engine.compare_versions("1.0.0", "2.0.0"), -1)
        self.assertEqual(self.engine.compare_versions("2.1.0", "2.0.9"), 1)
        self.assertEqual(self.engine.compare_versions("1.0.0", "1.0.1"), -1)

        # Prerelease precedence: 1.0.0-alpha < 1.0.0
        self.assertEqual(self.engine.compare_versions("1.0.0-alpha", "1.0.0"), -1)
        self.assertEqual(self.engine.compare_versions("1.0.0", "1.0.0-alpha"), 1)

    def test_classify_change(self) -> None:
        self.assertEqual(
            self.engine.classify_change("1.0.0", "2.0.0"), VersionChangeType.MAJOR
        )
        self.assertEqual(
            self.engine.classify_change("1.0.0", "1.1.0"), VersionChangeType.MINOR
        )
        self.assertEqual(
            self.engine.classify_change("1.0.0", "1.0.1"), VersionChangeType.PATCH
        )
        self.assertEqual(
            self.engine.classify_change("1.0.0-alpha", "1.0.0-beta"), VersionChangeType.PRERELEASE
        )
        self.assertEqual(
            self.engine.classify_change("1.0.0", "1.0.0"), VersionChangeType.NO_CHANGE
        )

    def test_matches_range_caret(self) -> None:
        # ^1.2.3 allows >=1.2.3 <2.0.0
        self.assertTrue(self.engine.matches_range("1.2.3", "^1.2.3"))
        self.assertTrue(self.engine.matches_range("1.5.0", "^1.2.3"))
        self.assertFalse(self.engine.matches_range("1.2.0", "^1.2.3"))
        self.assertFalse(self.engine.matches_range("2.0.0", "^1.2.3"))

        # ^0.2.3 allows >=0.2.3 <0.3.0
        self.assertTrue(self.engine.matches_range("0.2.5", "^0.2.3"))
        self.assertFalse(self.engine.matches_range("0.3.0", "^0.2.3"))

    def test_matches_range_tilde_and_wildcard(self) -> None:
        # ~1.2.3 allows >=1.2.3 <1.3.0
        self.assertTrue(self.engine.matches_range("1.2.4", "~1.2.3"))
        self.assertFalse(self.engine.matches_range("1.3.0", "~1.2.3"))

        # Wildcards
        self.assertTrue(self.engine.matches_range("1.2.9", "1.2.*"))
        self.assertFalse(self.engine.matches_range("1.3.0", "1.2.*"))
        self.assertTrue(self.engine.matches_range("9.9.9", "*"))

    def test_get_highest_compatible(self) -> None:
        candidates = ["1.0.0", "1.2.0", "1.2.5", "1.3.0", "2.0.0"]
        highest = self.engine.get_highest_compatible(candidates, "^1.2.0")
        self.assertEqual(highest, "1.3.0")

        none_match = self.engine.get_highest_compatible(candidates, "^3.0.0")
        self.assertIsNone(none_match)

    def test_version_report(self) -> None:
        vers = ["1.0.0", "1.1.0", "2.0.0-rc.1", "2.0.0"]
        rep = self.engine.get_version_report(vers)
        self.assertEqual(rep["total_versions_analyzed"], 4)
        self.assertEqual(rep["breakdown_by_major"][1], 2)
        self.assertEqual(rep["breakdown_by_major"][2], 2)
        self.assertEqual(rep["prereleases_count"], 1)


if __name__ == "__main__":
    unittest.main()
