import unittest
from elmos_mature_platform.types import (
    DesignPartner, PartnerEngagementStatus, ValidationOutcome, ValidationScenario, PartnerReport
)
from elmos_mature_platform.design_partner_validation_engine import DesignPartnerValidationEngine

class TestDesignPartnerValidationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DesignPartnerValidationEngine()

    def test_register_partner(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.assertEqual(self.engine.get_partner("p1").company_name, "C1")

    def test_register_duplicate_partner(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        with self.assertRaises(ValueError):
            self.engine.register_partner(p)

    def test_get_nonexistent_partner(self):
        with self.assertRaises(ValueError):
            self.engine.get_partner("nope")

    def test_update_partner_status_forward(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.ONBOARDING)
        self.assertEqual(self.engine.get_partner("p1").engagement_status, PartnerEngagementStatus.ONBOARDING)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.ACTIVE)
        self.assertEqual(self.engine.get_partner("p1").engagement_status, PartnerEngagementStatus.ACTIVE)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.FEEDBACK)
        self.assertEqual(self.engine.get_partner("p1").engagement_status, PartnerEngagementStatus.FEEDBACK)

    def test_update_partner_status_backward(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.ONBOARDING)
        with self.assertRaises(ValueError):
            self.engine.update_partner_status("p1", PartnerEngagementStatus.PROSPECT)

    def test_update_partner_status_churned(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.CHURNED)
        self.assertEqual(self.engine.get_partner("p1").engagement_status, PartnerEngagementStatus.CHURNED)

    def test_update_churned_partner(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.CHURNED)
        with self.assertRaises(ValueError):
            self.engine.update_partner_status("p1", PartnerEngagementStatus.ACTIVE)

    def test_graduate_without_passed_scenario(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        with self.assertRaises(ValueError):
            self.engine.update_partner_status("p1", PartnerEngagementStatus.GRADUATED)

    def test_graduate_with_passed_scenario(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        self.engine.record_validation_result("s1", ValidationOutcome.PASSED, "good", 1.0)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.GRADUATED)
        self.assertEqual(self.engine.get_partner("p1").engagement_status, PartnerEngagementStatus.GRADUATED)

    def test_create_validation_scenario(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        self.assertEqual(len(self.engine.get_partner_scenarios("p1")), 1)

    def test_create_validation_scenario_unknown_partner(self):
        s = ValidationScenario(scenario_id="s1", partner_id="nope", feature="f1", description="desc")
        with self.assertRaises(ValueError):
            self.engine.create_validation_scenario(s)

    def test_create_duplicate_validation_scenario(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        with self.assertRaises(ValueError):
            self.engine.create_validation_scenario(s)

    def test_record_validation_result_passed(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        self.engine.record_validation_result("s1", ValidationOutcome.PASSED, "good", 1.0)
        scenarios = self.engine.get_partner_scenarios("p1")
        self.assertEqual(scenarios[0].outcome, ValidationOutcome.PASSED)
        self.assertIn("f1", self.engine.get_partner("p1").features_validated)

    def test_record_validation_result_failed(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        self.engine.record_validation_result("s1", ValidationOutcome.FAILED, "bad", 1.0)
        scenarios = self.engine.get_partner_scenarios("p1")
        self.assertEqual(scenarios[0].outcome, ValidationOutcome.FAILED)
        self.assertNotIn("f1", self.engine.get_partner("p1").features_validated)

    def test_record_validation_result_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.record_validation_result("nope", ValidationOutcome.PASSED, "good", 1.0)

    def test_get_partner_scenarios_unknown(self):
        with self.assertRaises(ValueError):
            self.engine.get_partner_scenarios("nope")

    def test_record_nps(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.record_nps("p1", 50)
        self.assertEqual(self.engine.get_partner("p1").nps_score, 50)

    def test_record_nps_too_high(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        with self.assertRaises(ValueError):
            self.engine.record_nps("p1", 150)

    def test_record_nps_too_low(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        with self.assertRaises(ValueError):
            self.engine.record_nps("p1", -150)

    def test_add_feature_request(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.add_feature_request("p1", "f1")
        self.assertIn("f1", self.engine.get_partner("p1").features_requested)

    def test_add_feature_request_duplicate(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.add_feature_request("p1", "f1")
        self.engine.add_feature_request("p1", "f1")
        self.assertEqual(self.engine.get_partner("p1").features_requested.count("f1"), 1)

    def test_get_feature_demand(self):
        p1 = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        p2 = DesignPartner(partner_id="p2", company_name="C2", contact_name="B", industry="Tech")
        self.engine.register_partner(p1)
        self.engine.register_partner(p2)
        self.engine.add_feature_request("p1", "f1")
        self.engine.add_feature_request("p2", "f1")
        self.engine.add_feature_request("p2", "f2")
        demand = self.engine.get_feature_demand()
        self.assertEqual(demand["f1"], 2)
        self.assertEqual(demand["f2"], 1)

    def test_get_validation_coverage(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s1 = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        s2 = ValidationScenario(scenario_id="s2", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s1)
        self.engine.create_validation_scenario(s2)
        self.engine.record_validation_result("s1", ValidationOutcome.PASSED, "good", 1.0)
        self.engine.record_validation_result("s2", ValidationOutcome.FAILED, "bad", 1.0)
        coverage = self.engine.get_validation_coverage("f1")
        self.assertEqual(coverage["partners_validated"], 1)
        self.assertEqual(coverage["pass_rate"], 0.5)

    def test_get_validation_coverage_no_scenarios(self):
        coverage = self.engine.get_validation_coverage("f1")
        self.assertEqual(coverage["partners_validated"], 0)
        self.assertEqual(coverage["pass_rate"], 0.0)

    def test_get_partner_report_empty(self):
        report = self.engine.get_partner_report()
        self.assertEqual(report.total_partners, 0)

    def test_get_partner_report(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech", blockers=["b1"])
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.ACTIVE)
        self.engine.record_nps("p1", 80)
        self.engine.add_feature_request("p1", "f1")
        
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f1", description="desc")
        self.engine.create_validation_scenario(s)
        self.engine.record_validation_result("s1", ValidationOutcome.PASSED, "good", 1.0)
        
        report = self.engine.get_partner_report()
        self.assertEqual(report.total_partners, 1)
        self.assertEqual(report.active_count, 1)
        self.assertEqual(report.average_nps, 80.0)
        self.assertEqual(report.validation_pass_rate, 1.0)
        self.assertEqual(report.top_requested_features[0]["feature"], "f1")
        self.assertIn("b1", report.blockers)

    def test_assess_product_readiness_not_ready_due_to_graduated(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        with self.assertRaises(ValueError):
            self.engine.assess_product_readiness()

    def test_assess_product_readiness_not_ready_due_to_pass_rate(self):
        for i in range(3):
            pid = f"p{i}"
            p = DesignPartner(partner_id=pid, company_name="C", contact_name="A", industry="Tech")
            self.engine.register_partner(p)
            s = ValidationScenario(scenario_id=f"s{i}", partner_id=pid, feature="f1", description="desc")
            self.engine.create_validation_scenario(s)
            self.engine.record_validation_result(f"s{i}", ValidationOutcome.PASSED, "good", 1.0)
            self.engine.update_partner_status(pid, PartnerEngagementStatus.GRADUATED)
            
        for i in range(2):
            sid = f"s_fail{i}"
            s = ValidationScenario(scenario_id=sid, partner_id="p0", feature="f1", description="desc")
            self.engine.create_validation_scenario(s)
            self.engine.record_validation_result(sid, ValidationOutcome.FAILED, "bad", 1.0)
            
        with self.assertRaises(ValueError):
            self.engine.assess_product_readiness()

    def test_assess_product_readiness_ready(self):
        for i in range(3):
            pid = f"p{i}"
            p = DesignPartner(partner_id=pid, company_name="C", contact_name="A", industry="Tech")
            self.engine.register_partner(p)
            s = ValidationScenario(scenario_id=f"s{i}", partner_id=pid, feature="f1", description="desc")
            self.engine.create_validation_scenario(s)
            self.engine.record_validation_result(f"s{i}", ValidationOutcome.PASSED, "good", 1.0)
            self.engine.update_partner_status(pid, PartnerEngagementStatus.GRADUATED)
            
        report = self.engine.assess_product_readiness()
        self.assertEqual(report.graduated_count, 3)
        self.assertEqual(report.validation_pass_rate, 1.0)

    def test_status_order_active_to_prospect_fails(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        self.engine.update_partner_status("p1", PartnerEngagementStatus.ACTIVE)
        with self.assertRaises(ValueError):
            self.engine.update_partner_status("p1", PartnerEngagementStatus.PROSPECT)

    def test_record_validation_result_updates_partner_features(self):
        p = DesignPartner(partner_id="p1", company_name="C1", contact_name="A", industry="Tech")
        self.engine.register_partner(p)
        s = ValidationScenario(scenario_id="s1", partner_id="p1", feature="f_special", description="desc")
        self.engine.create_validation_scenario(s)
        self.engine.record_validation_result("s1", ValidationOutcome.PASSED, "good", 1.0)
        self.assertIn("f_special", self.engine.get_partner("p1").features_validated)
