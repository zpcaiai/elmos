import unittest
from elmos_mature_platform.types import (
    FunctionalArea,
    DepthLevel,
    FunctionalRequirement,
    DepthCertification,
    DepthGap
)
from elmos_mature_platform.functional_depth_certification_engine import FunctionalDepthCertificationEngine

class TestFunctionalDepthCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FunctionalDepthCertificationEngine()

    def test_add_requirement(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc")
        self.engine.add_requirement(req)
        self.assertIn("R1", self.engine.requirements)

    def test_record_test_results_success(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc")
        self.engine.add_requirement(req)
        self.engine.record_test_results("R1", 10, 10)
        self.assertTrue(self.engine.requirements["R1"].certified)

    def test_record_test_results_failure(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc")
        self.engine.add_requirement(req)
        self.engine.record_test_results("R1", 10, 9)
        self.assertFalse(self.engine.requirements["R1"].certified)

    def test_record_test_results_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_test_results("R999", 10, 10)

    def test_mark_implemented_success(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc")
        self.engine.add_requirement(req)
        self.engine.mark_implemented("R1")
        self.assertTrue(self.engine.requirements["R1"].implemented)

    def test_mark_implemented_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.mark_implemented("R999")

    def test_create_certification(self):
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        cert_id = self.engine.create_certification(cert)
        self.assertEqual(cert_id, "C1")
        self.assertIn("C1", self.engine.certifications)

    def test_is_requirement_met(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc")
        req.implemented = True
        req.certified = True
        self.assertTrue(self.engine._is_requirement_met(req))

    def test_evaluate_depth_no_cert(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_depth("C999")

    def test_evaluate_depth_no_reqs(self):
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        evaluated = self.engine.evaluate_depth("C1")
        self.assertEqual(evaluated.achieved_depth, DepthLevel.BASIC)
        self.assertEqual(evaluated.requirements_total, 0)
        self.assertEqual(evaluated.coverage_pct, 0.0)

    def test_evaluate_depth_all_met(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC)
        self.engine.add_requirement(req)
        self.engine.mark_implemented("R1")
        self.engine.record_test_results("R1", 1, 1)

        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        evaluated = self.engine.evaluate_depth("C1")

        self.assertEqual(evaluated.achieved_depth, DepthLevel.BASIC)
        self.assertEqual(evaluated.requirements_total, 1)
        self.assertEqual(evaluated.requirements_met, 1)
        self.assertEqual(evaluated.coverage_pct, 100.0)

    def test_evaluate_depth_partial_met(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=True, certified=False))

        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.STANDARD)
        self.engine.create_certification(cert)
        evaluated = self.engine.evaluate_depth("C1")

        self.assertEqual(evaluated.achieved_depth, DepthLevel.BASIC)
        self.assertEqual(evaluated.requirements_met, 1)
        self.assertEqual(evaluated.requirements_total, 2)
        self.assertEqual(evaluated.coverage_pct, 50.0)

    def test_certify_area_success(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        
        certified = self.engine.certify_area("C1", "tester")
        self.assertTrue(certified.certified)
        self.assertEqual(certified.certifier, "tester")
        self.assertNotEqual(certified.certified_at, "")

    def test_certify_area_failure_target_not_met(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=False, certified=False))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.STANDARD)
        self.engine.create_certification(cert)
        
        certified = self.engine.certify_area("C1", "tester")
        self.assertFalse(certified.certified)

    def test_certify_area_failure_basic_not_met(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=False, certified=False))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        
        certified = self.engine.certify_area("C1", "tester")
        self.assertFalse(certified.certified)

    def test_get_depth_gaps_none(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        
        gaps = self.engine.get_depth_gaps("C1")
        self.assertEqual(len(gaps), 0)

    def test_get_depth_gaps_exists(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=False, certified=False))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.STANDARD)
        self.engine.create_certification(cert)
        
        gaps = self.engine.get_depth_gaps("C1")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].missing_requirements, ["R2"])
        self.assertEqual(gaps[0].effort_estimate_hours, 16.0)

    def test_get_area_coverage_empty(self):
        coverage = self.engine.get_area_coverage(FunctionalArea.DATA_INGESTION)
        self.assertEqual(coverage["total_requirements"], 0)
        self.assertEqual(coverage["overall_coverage"], 0.0)

    def test_get_area_coverage_populated(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=False, certified=False))
        
        coverage = self.engine.get_area_coverage(FunctionalArea.DATA_INGESTION)
        self.assertEqual(coverage["total_requirements"], 2)
        self.assertEqual(coverage["met_requirements"], 1)
        self.assertEqual(coverage["overall_coverage"], 50.0)
        self.assertEqual(coverage["by_depth"]["basic"]["met"], 1)
        self.assertEqual(coverage["by_depth"]["standard"]["met"], 0)

    def test_get_requirements_by_depth(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.TRANSFORMATION, description="desc", depth=DepthLevel.STANDARD))
        
        reqs = self.engine.get_requirements_by_depth(DepthLevel.BASIC)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0].req_id, "R1")

    def test_get_certification_report_empty(self):
        report = self.engine.get_certification_report()
        self.assertEqual(report["total_certifications"], 0)
        self.assertEqual(report["certified_count"], 0)

    def test_get_certification_report_populated(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        self.engine.certify_area("C1", "tester")
        
        report = self.engine.get_certification_report()
        self.assertEqual(report["total_certifications"], 1)
        self.assertEqual(report["certified_count"], 1)
        self.assertEqual(report["overall_coverage"], 100.0)
        self.assertEqual(len(report["certifications"]), 1)

    def test_estimate_effort_to_depth_none(self):
        effort = self.engine.estimate_effort_to_depth(FunctionalArea.DATA_INGESTION, DepthLevel.ADVANCED)
        self.assertEqual(effort, 0.0)

    def test_estimate_effort_to_depth_some(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=False, certified=False))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=False, certified=False))
        self.engine.add_requirement(FunctionalRequirement(req_id="R3", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.ADVANCED, implemented=False, certified=False))
        
        effort = self.engine.estimate_effort_to_depth(FunctionalArea.DATA_INGESTION, DepthLevel.STANDARD)
        # R1 (8) + R2 (16) = 24
        self.assertEqual(effort, 24.0)

    def test_is_requirement_met_unimplemented(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=False, certified=True)
        self.assertFalse(self.engine._is_requirement_met(req))

    def test_is_requirement_met_uncertified(self):
        req = FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=False)
        self.assertFalse(self.engine._is_requirement_met(req))

    def test_record_test_results_zero_tests(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc"))
        self.engine.record_test_results("R1", 0, 0)
        self.assertFalse(self.engine.requirements["R1"].certified)

    def test_certify_area_ignores_unrelated_areas(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.TRANSFORMATION, description="desc", depth=DepthLevel.BASIC, implemented=False, certified=False))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC)
        self.engine.create_certification(cert)
        # Should evaluate to true or basically achieving BASIC since no requirements fail the area, but wait, without basic_met it might not certify
        # Wait, if there are NO basic requirements for DATA_INGESTION, basic_met is False.
        # So achieved_val is 0, target_val = 1. certified = False.
        certified = self.engine.certify_area("C1", "tester")
        self.assertFalse(certified.certified)

    def test_certify_area_advanced(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R3", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.ADVANCED, implemented=True, certified=True))
        
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.ADVANCED)
        self.engine.create_certification(cert)
        certified = self.engine.certify_area("C1", "tester")
        
        self.assertTrue(certified.certified)
        self.assertEqual(certified.achieved_depth, DepthLevel.ADVANCED)

    def test_certify_area_complete_fails_if_advanced_fails(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.STANDARD, implemented=True, certified=True))
        self.engine.add_requirement(FunctionalRequirement(req_id="R3", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.ADVANCED, implemented=False, certified=False))
        self.engine.add_requirement(FunctionalRequirement(req_id="R4", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.COMPLETE, implemented=True, certified=True))
        
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.COMPLETE)
        self.engine.create_certification(cert)
        certified = self.engine.certify_area("C1", "tester")
        
        self.assertFalse(certified.certified)
        self.assertEqual(certified.achieved_depth, DepthLevel.STANDARD)
        
    def test_gap_effort_calculation(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.COMPLETE, implemented=False, certified=False))
        cert = DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.COMPLETE)
        self.engine.create_certification(cert)
        
        gaps = self.engine.get_depth_gaps("C1")
        self.assertEqual(gaps[0].effort_estimate_hours, 48.0)

    def test_multiple_certifications_report(self):
        self.engine.add_requirement(FunctionalRequirement(req_id="R1", area=FunctionalArea.DATA_INGESTION, description="desc", depth=DepthLevel.BASIC, implemented=True, certified=True))
        self.engine.create_certification(DepthCertification(cert_id="C1", product_name="P1", area=FunctionalArea.DATA_INGESTION, target_depth=DepthLevel.BASIC))
        self.engine.certify_area("C1", "tester")
        
        self.engine.add_requirement(FunctionalRequirement(req_id="R2", area=FunctionalArea.TRANSFORMATION, description="desc", depth=DepthLevel.BASIC, implemented=False, certified=False))
        self.engine.create_certification(DepthCertification(cert_id="C2", product_name="P2", area=FunctionalArea.TRANSFORMATION, target_depth=DepthLevel.BASIC))
        self.engine.certify_area("C2", "tester")
        
        report = self.engine.get_certification_report()
        self.assertEqual(report["total_certifications"], 2)
        self.assertEqual(report["certified_count"], 1)
        self.assertEqual(report["overall_coverage"], 50.0)

if __name__ == '__main__':
    unittest.main()
