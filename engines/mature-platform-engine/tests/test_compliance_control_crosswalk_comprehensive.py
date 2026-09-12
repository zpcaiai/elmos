"""Comprehensive test suite for ComplianceControlCrosswalkEngine (B40 - Skill 1381)."""

import unittest

from elmos_mature_platform.compliance_control_crosswalk_engine import (
    ComplianceControlCrosswalkEngine,
)
from elmos_mature_platform.types import (
    ComplianceFramework,
    ControlCrosswalkRecord,
    CrosswalkMappingType,
)


class TestComplianceControlCrosswalkComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ComplianceControlCrosswalkEngine()

    def test_default_crosswalk_seeds(self):
        mappings = self.engine.get_mappings()
        self.assertGreaterEqual(len(mappings), 5)
        soc2_mappings = self.engine.get_mappings(source_framework=ComplianceFramework.SOC2_TYPE2)
        self.assertGreaterEqual(len(soc2_mappings), 2)

    def test_add_custom_crosswalk_mapping(self):
        custom = ControlCrosswalkRecord(
            mapping_id="map-hipaa-soc2-audit",
            source_framework=ComplianceFramework.HIPAA,
            source_control_id="164.312(b)",
            target_framework=ComplianceFramework.SOC2_TYPE2,
            target_control_id="CC7.2",
            mapping_type=CrosswalkMappingType.EXACT_EQUIVALENT,
            rationale="Audit logging and event review equivalence",
        )
        mid = self.engine.add_mapping(custom)
        self.assertEqual(mid, "map-hipaa-soc2-audit")

        retrieved = self.engine.get_mappings(source_framework=ComplianceFramework.HIPAA)
        self.assertTrue(any(m.mapping_id == "map-hipaa-soc2-audit" for m in retrieved))

    def test_find_equivalent_controls_bidirectional(self):
        # SOC2 CC6.1 -> ISO27001 A.9.1.1 was seeded
        forward = self.engine.find_equivalent_controls(
            from_framework=ComplianceFramework.SOC2_TYPE2,
            control_id="CC6.1",
            to_framework=ComplianceFramework.ISO27001,
        )
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward[0].target_control_id, "A.9.1.1")

        # Reverse query: ISO27001 A.9.1.1 -> SOC2
        reverse = self.engine.find_equivalent_controls(
            from_framework=ComplianceFramework.ISO27001,
            control_id="A.9.1.1",
            to_framework=ComplianceFramework.SOC2_TYPE2,
        )
        self.assertEqual(len(reverse), 1)
        self.assertEqual(reverse[0].source_control_id, "CC6.1")

    def test_perform_gap_analysis_partial_coverage(self):
        implemented = ["CC6.1"]  # Covers ISO A.9.1.1
        target_iso_controls = ["A.9.1.1", "A.12.1.2", "A.14.2.1"]

        analysis = self.engine.perform_gap_analysis(
            from_framework=ComplianceFramework.SOC2_TYPE2,
            to_framework=ComplianceFramework.ISO27001,
            implemented_source_controls=implemented,
            all_target_controls=target_iso_controls,
        )
        self.assertEqual(analysis.covered_controls_count, 1)
        self.assertIn("A.12.1.2", analysis.gap_controls)
        self.assertIn("A.14.2.1", analysis.gap_controls)
        self.assertEqual(analysis.crosswalk_coverage_pct, 33.33)

    def test_perform_gap_analysis_100_percent_coverage(self):
        implemented = ["CC6.1"]
        target_iso_controls = ["A.9.1.1"]

        analysis = self.engine.perform_gap_analysis(
            from_framework=ComplianceFramework.SOC2_TYPE2,
            to_framework=ComplianceFramework.ISO27001,
            implemented_source_controls=implemented,
            all_target_controls=target_iso_controls,
        )
        self.assertEqual(analysis.covered_controls_count, 1)
        self.assertEqual(len(analysis.gap_controls), 0)
        self.assertEqual(analysis.crosswalk_coverage_pct, 100.0)

    def test_perform_gap_analysis_empty_targets(self):
        analysis = self.engine.perform_gap_analysis(
            from_framework=ComplianceFramework.HIPAA,
            to_framework=ComplianceFramework.PCI_DSS,
            implemented_source_controls=[],
            all_target_controls=[],
        )
        self.assertEqual(analysis.crosswalk_coverage_pct, 100.0)
        self.assertEqual(analysis.covered_controls_count, 0)


if __name__ == "__main__":
    unittest.main()
