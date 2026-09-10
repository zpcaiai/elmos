import unittest
from elmos_mature_platform.types import (
    PlatformComponent,
    VersionEntry,
    CompatibilityRecord,
    CompatibilityStatus
)
from elmos_mature_platform.platform_version_compatibility_engine import PlatformVersionCompatibilityEngine

class TestPlatformVersionCompatibilityEngineComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = PlatformVersionCompatibilityEngine()
        
        # Setup basic data
        self.engine.register_version(VersionEntry(PlatformComponent.RUNNER, "1.0.0", breaking_changes=[]))
        self.engine.register_version(VersionEntry(PlatformComponent.RUNNER, "2.0.0", breaking_changes=["API changed"]))
        self.engine.register_version(VersionEntry(PlatformComponent.CONTROL_PLANE, "1.0.0", min_compatible_versions={PlatformComponent.RUNNER: "1.0.0"}))
        self.engine.register_version(VersionEntry(PlatformComponent.CONTROL_PLANE, "2.0.0", min_compatible_versions={PlatformComponent.RUNNER: "2.0.0"}))
        
        self.engine.record_compatibility(CompatibilityRecord(
            record_id="rec1",
            component_a=PlatformComponent.RUNNER, version_a="1.0.0",
            component_b=PlatformComponent.CONTROL_PLANE, version_b="1.0.0",
            status=CompatibilityStatus.COMPATIBLE
        ))
        
    def test_register_version(self):
        res = self.engine.register_version(VersionEntry(PlatformComponent.DATABASE, "3.2.1"))
        self.assertEqual(res, "database:3.2.1")
        
    def test_record_compatibility_explicit(self):
        rec = CompatibilityRecord(
            record_id="",
            component_a=PlatformComponent.DATABASE, version_a="3.2.1",
            component_b=PlatformComponent.RUNNER, version_b="2.0.0",
            status=CompatibilityStatus.COMPATIBLE
        )
        res = self.engine.record_compatibility(rec)
        self.assertTrue(len(res) > 0)
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.DATABASE, "3.2.1", PlatformComponent.RUNNER, "2.0.0"),
            CompatibilityStatus.COMPATIBLE
        )

    def test_check_compatibility_symmetric(self):
        # Should be symmetric
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.RUNNER, "1.0.0", PlatformComponent.CONTROL_PLANE, "1.0.0"),
            CompatibilityStatus.COMPATIBLE
        )
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.CONTROL_PLANE, "1.0.0", PlatformComponent.RUNNER, "1.0.0"),
            CompatibilityStatus.COMPATIBLE
        )
        
    def test_check_compatibility_min_versions_incompatible(self):
        # CONTROL_PLANE 2.0.0 requires RUNNER 2.0.0. RUNNER 1.0.0 should be INCOMPATIBLE.
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.RUNNER, "1.0.0", PlatformComponent.CONTROL_PLANE, "2.0.0"),
            CompatibilityStatus.INCOMPATIBLE
        )

    def test_check_compatibility_untested(self):
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.RUNNER, "2.0.0", PlatformComponent.CONTROL_PLANE, "2.0.0"),
            CompatibilityStatus.UNTESTED
        )
        
    def test_get_compatible_versions(self):
        comps = self.engine.get_compatible_versions(PlatformComponent.RUNNER, "1.0.0")
        self.assertIn("1.0.0", comps[PlatformComponent.CONTROL_PLANE])
        self.assertNotIn("2.0.0", comps[PlatformComponent.CONTROL_PLANE])
        
    def test_detect_breaking_changes(self):
        changes = self.engine.detect_breaking_changes(PlatformComponent.RUNNER, "1.0.0", "2.0.0")
        self.assertEqual(changes, ["API changed"])
        
    def test_detect_breaking_changes_empty(self):
        changes = self.engine.detect_breaking_changes(PlatformComponent.RUNNER, "1.0.0", "1.0.0")
        self.assertEqual(changes, [])
        
    def test_get_upgrade_path(self):
        self.engine.register_version(VersionEntry(PlatformComponent.RUNNER, "1.5.0"))
        path = self.engine.get_upgrade_path(PlatformComponent.RUNNER, "1.0.0", "2.0.0")
        self.assertEqual(path, ["1.5.0", "2.0.0"])

    def test_get_upgrade_path_reverse(self):
        path = self.engine.get_upgrade_path(PlatformComponent.RUNNER, "2.0.0", "1.0.0")
        self.assertEqual(path, [])
        
    def test_get_eol_versions(self):
        self.engine.register_version(VersionEntry(PlatformComponent.API, "0.1", supported=False))
        self.engine.register_version(VersionEntry(PlatformComponent.API, "0.2", eol_date="2020-01-01"))
        eols = self.engine.get_eol_versions()
        self.assertEqual(len(eols), 2)
        
    def test_get_version_matrix(self):
        mat = self.engine.get_version_matrix([PlatformComponent.RUNNER, PlatformComponent.CONTROL_PLANE])
        self.assertIn(PlatformComponent.RUNNER, mat)
        self.assertIn("1.0.0", mat[PlatformComponent.RUNNER])
        self.assertEqual(mat[PlatformComponent.RUNNER]["1.0.0"][PlatformComponent.CONTROL_PLANE]["1.0.0"], "compatible")
        
    def test_validate_deployment_valid(self):
        deploy = {
            "runner": "1.0.0",
            "control_plane": "1.0.0"
        }
        res = self.engine.validate_deployment(deploy)
        self.assertTrue(res["valid"])
        
    def test_validate_deployment_invalid(self):
        deploy = {
            "runner": "1.0.0",
            "control_plane": "2.0.0"  # Requires runner >= 2.0.0
        }
        res = self.engine.validate_deployment(deploy)
        self.assertFalse(res["valid"])
        self.assertEqual(len(res["issues"]), 1)
        self.assertIn("incompatible", res["issues"][0])
        
    def test_validate_deployment_untested(self):
        deploy = {
            "runner": "2.0.0",
            "control_plane": "2.0.0"
        }
        res = self.engine.validate_deployment(deploy)
        self.assertTrue(res["valid"])
        self.assertEqual(len(res["issues"]), 1)
        self.assertIn("untested", res["issues"][0])

    def test_get_compatibility_report(self):
        rep = self.engine.get_compatibility_report()
        self.assertEqual(rep["total_versions"], 4)
        self.assertEqual(rep["tested_pairs"], 1)
        self.assertEqual(rep["compatible_pairs"], 1)
        self.assertEqual(rep["incompatible_pairs"], 0)
        self.assertEqual(rep["compatibility_percentage"], 100.0)

    # Adding more tests to reach 28-32 tests
    def test_extra_1(self):
        self.engine.register_version(VersionEntry(PlatformComponent.CLI, "3.0"))
        self.assertIn("3.0", self.engine._versions[PlatformComponent.CLI])

    def test_extra_2(self):
        rec = CompatibilityRecord("test2", PlatformComponent.CLI, "3.0", PlatformComponent.API, "1.0", CompatibilityStatus.DEPRECATED)
        self.engine.record_compatibility(rec)
        self.assertEqual(self.engine.check_compatibility(PlatformComponent.CLI, "3.0", PlatformComponent.API, "1.0"), CompatibilityStatus.DEPRECATED)

    def test_extra_3(self):
        rec = CompatibilityRecord("test3", PlatformComponent.CLI, "3.0", PlatformComponent.API, "1.0", CompatibilityStatus.CONDITIONAL)
        self.engine.record_compatibility(rec)
        self.assertEqual(self.engine.check_compatibility(PlatformComponent.CLI, "3.0", PlatformComponent.API, "1.0"), CompatibilityStatus.CONDITIONAL)

    def test_extra_4(self):
        self.engine.register_version(VersionEntry(PlatformComponent.PLUGIN, "1.0.0"))
        self.engine.register_version(VersionEntry(PlatformComponent.PLUGIN, "1.1.0"))
        self.engine.register_version(VersionEntry(PlatformComponent.PLUGIN, "1.2.0"))
        path = self.engine.get_upgrade_path(PlatformComponent.PLUGIN, "1.0.0", "1.2.0")
        self.assertEqual(path, ["1.1.0", "1.2.0"])

    def test_extra_5(self):
        self.engine.register_version(VersionEntry(PlatformComponent.SDK, "1.0.0", min_compatible_versions={PlatformComponent.API: "2.0.0"}))
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.SDK, "1.0.0", PlatformComponent.API, "1.0.0"),
            CompatibilityStatus.INCOMPATIBLE
        )

    def test_extra_6(self):
        self.engine.register_version(VersionEntry(PlatformComponent.AGENT, "5.0.0", min_compatible_versions={PlatformComponent.DATABASE: "5.0.0"}))
        self.engine.register_version(VersionEntry(PlatformComponent.DATABASE, "6.0.0", min_compatible_versions={PlatformComponent.AGENT: "4.0.0"}))
        # Agent requires DB 5.0.0, DB is 6.0.0 -> OK. DB requires Agent 4.0.0, Agent is 5.0.0 -> OK. Untested.
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.AGENT, "5.0.0", PlatformComponent.DATABASE, "6.0.0"),
            CompatibilityStatus.UNTESTED
        )

    def test_extra_7(self):
        # Inverse of above check
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.DATABASE, "6.0.0", PlatformComponent.AGENT, "5.0.0"),
            CompatibilityStatus.UNTESTED
        )

    def test_extra_8(self):
        self.engine.register_version(VersionEntry(PlatformComponent.AGENT, "5.0.0", min_compatible_versions={PlatformComponent.DATABASE: "5.0.0"}))
        self.engine.register_version(VersionEntry(PlatformComponent.DATABASE, "4.0.0"))
        self.assertEqual(
            self.engine.check_compatibility(PlatformComponent.DATABASE, "4.0.0", PlatformComponent.AGENT, "5.0.0"),
            CompatibilityStatus.INCOMPATIBLE
        )

    def test_extra_9(self):
        self.assertEqual(len(self.engine.get_eol_versions()), 0)

    def test_extra_10(self):
        matrix = self.engine.get_version_matrix([PlatformComponent.RUNNER])
        self.assertIn(PlatformComponent.RUNNER, matrix)
        self.assertEqual(matrix[PlatformComponent.RUNNER]["1.0.0"], {})

    def test_extra_11(self):
        deploy = {"runner": "1.0.0", "control_plane": "1.0.0", "database": "2.0.0"}
        res = self.engine.validate_deployment(deploy)
        # 1.0.0 <-> 1.0.0 is compatible. others are untested.
        self.assertTrue(res["valid"])

    def test_extra_12(self):
        self.engine.record_compatibility(CompatibilityRecord("tx", PlatformComponent.RUNNER, "1.0.0", PlatformComponent.DATABASE, "2.0.0", CompatibilityStatus.INCOMPATIBLE))
        deploy = {"runner": "1.0.0", "control_plane": "1.0.0", "database": "2.0.0"}
        res = self.engine.validate_deployment(deploy)
        self.assertFalse(res["valid"])

    def test_extra_13(self):
        self.engine.record_compatibility(CompatibilityRecord("tx2", PlatformComponent.RUNNER, "1.0.0", PlatformComponent.DATABASE, "2.0.0", CompatibilityStatus.DEPRECATED))
        deploy = {"runner": "1.0.0", "control_plane": "1.0.0", "database": "2.0.0"}
        res = self.engine.validate_deployment(deploy)
        self.assertFalse(res["valid"])

    def test_extra_14(self):
        self.engine.record_compatibility(CompatibilityRecord("tx3", PlatformComponent.RUNNER, "1.0.0", PlatformComponent.DATABASE, "2.0.0", CompatibilityStatus.CONDITIONAL))
        deploy = {"runner": "1.0.0", "control_plane": "1.0.0", "database": "2.0.0"}
        res = self.engine.validate_deployment(deploy)
        self.assertTrue(res["valid"])

    def test_extra_15(self):
        rep = self.engine.get_compatibility_report()
        self.assertTrue("total_versions" in rep)
        
    def test_extra_16(self):
        # Empty get_compatible_versions
        res = self.engine.get_compatible_versions(PlatformComponent.RUNNER, "9.9.9")
        self.assertEqual(len(res[PlatformComponent.CONTROL_PLANE]), 0)

    def test_extra_17(self):
        deploy = {"runner": "1.0.0"}
        res = self.engine.validate_deployment(deploy)
        self.assertTrue(res["valid"])

if __name__ == '__main__':
    unittest.main()
