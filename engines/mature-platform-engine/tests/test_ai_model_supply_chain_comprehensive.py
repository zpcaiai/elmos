import unittest
from elmos_mature_platform.types import AiModelRecord, ModelProvenance, ModelRiskLevel, ModelScanResult
from elmos_mature_platform.ai_model_supply_chain_engine import AiModelSupplyChainEngine

class TestAiModelSupplyChainEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AiModelSupplyChainEngine()

    def test_register_model(self):
        model = AiModelRecord(model_id="m1", name="Model 1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        res = self.engine.register_model(model)
        self.assertEqual(res, "m1")
        self.assertIn("m1", self.engine.models)
        self.assertTrue(self.engine.models["m1"].registered_at)

    def test_register_duplicate(self):
        model = AiModelRecord(model_id="m1", name="Model 1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(model)
        with self.assertRaises(ValueError):
            self.engine.register_model(model)

    def test_register_missing_dependency(self):
        model = AiModelRecord(model_id="m1", name="Model 1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["nonexistent"])
        with self.assertRaises(ValueError):
            self.engine.register_model(model)

    def test_register_circular_dependency_self(self):
        model = AiModelRecord(model_id="m1", name="Model 1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"])
        with self.assertRaises(ValueError):
            self.engine.register_model(model)

    def test_register_circular_dependency_indirect(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"])
        self.engine.register_model(m2)
        # Update m1 to depend on m3 (which doesn't exist yet, but we bypass for the test)
        self.engine.models["m1"].dependencies = ["m3"]
        
        m3 = AiModelRecord(model_id="m3", name="M3", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m2"])
        with self.assertRaises(ValueError):
            self.engine.register_model(m3)

    def test_scan_model(self):
        model = AiModelRecord(model_id="m1", name="Model 1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(model)
        scan = ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True)
        res = self.engine.scan_model(scan)
        self.assertEqual(res, "s1")
        self.assertEqual(len(self.engine.scans["m1"]), 1)

    def test_scan_model_not_found(self):
        scan = ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True)
        with self.assertRaises(ValueError):
            self.engine.scan_model(scan)

    def test_assess_risk_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.assess_risk("m1")

    def test_assess_risk_low(self):
        model = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(model)
        risk = self.engine.assess_risk("m1")
        self.assertEqual(risk, ModelRiskLevel.LOW)

    def test_assess_risk_unknown_provenance(self):
        model = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.UNKNOWN, training_data_hash="abc")
        self.engine.register_model(model)
        risk = self.engine.assess_risk("m1")
        self.assertEqual(risk, ModelRiskLevel.HIGH)

    def test_assess_risk_no_training_data_hash(self):
        model = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(model)
        risk = self.engine.assess_risk("m1")
        self.assertEqual(risk, ModelRiskLevel.MEDIUM)

    def test_assess_risk_failed_scans(self):
        model = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(model)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=False))
        risk = self.engine.assess_risk("m1")
        self.assertEqual(risk, ModelRiskLevel.MEDIUM)
        
        self.engine.scan_model(ModelScanResult(scan_id="s2", model_id="m1", scanner="s", passed=False))
        self.assertEqual(self.engine.assess_risk("m1"), ModelRiskLevel.HIGH)
        
        self.engine.scan_model(ModelScanResult(scan_id="s3", model_id="m1", scanner="s", passed=False))
        self.assertEqual(self.engine.assess_risk("m1"), ModelRiskLevel.CRITICAL)

    def test_assess_risk_vulnerabilities(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc", vulnerabilities=["v1"])
        self.engine.register_model(m1)
        self.assertEqual(self.engine.assess_risk("m1"), ModelRiskLevel.MEDIUM)

    def test_approve_model_no_scans(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        with self.assertRaises(ValueError):
            self.engine.approve_model("m1", "admin")

    def test_approve_model_failed_scan(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=False))
        with self.assertRaises(ValueError):
            self.engine.approve_model("m1", "admin")

    def test_approve_model_critical_risk(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.UNKNOWN)
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.scan_model(ModelScanResult(scan_id="s2", model_id="m1", scanner="s", passed=False))
        self.engine.scan_model(ModelScanResult(scan_id="s3", model_id="m1", scanner="s", passed=False))
        with self.assertRaises(ValueError):
            self.engine.approve_model("m1", "admin")

    def test_approve_model_success(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        model = self.engine.approve_model("m1", "admin")
        self.assertTrue(model.approved)
        self.assertEqual(model.approved_by, "admin")

    def test_revoke_approval(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.approve_model("m1", "admin")
        self.engine.revoke_approval("m1", "reason")
        self.assertFalse(self.engine.models["m1"].approved)

    def test_check_dependencies_all_approved(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.approve_model("m1", "admin")
        
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"])
        self.engine.register_model(m2)
        res = self.engine.check_dependencies("m2")
        self.assertTrue(res["all_approved"])
        self.assertEqual(len(res["unapproved_dependencies"]), 0)

    def test_check_dependencies_unapproved(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"])
        self.engine.register_model(m2)
        res = self.engine.check_dependencies("m2")
        self.assertFalse(res["all_approved"])
        self.assertIn("m1", res["unapproved_dependencies"])

    def test_get_vulnerability_report(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, vulnerabilities=["v1"])
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, vulnerabilities=["v2"], dependencies=["m1"])
        self.engine.register_model(m2)
        
        rep = self.engine.get_vulnerability_report("m2")
        self.assertEqual(len(rep["direct_vulnerabilities"]), 1)
        self.assertEqual(rep["direct_vulnerabilities"][0], "v2")
        self.assertEqual(len(rep["inherited_vulnerabilities"]), 1)
        self.assertEqual(rep["inherited_vulnerabilities"][0]["vulnerability"], "v1")

    def test_get_model_lineage(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"])
        self.engine.register_model(m2)
        
        lin = self.engine.get_model_lineage("m2")
        self.assertEqual(lin["model_id"], "m2")
        self.assertIn("m1", lin["dependencies"])

    def test_get_unapproved_models(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m2)
        
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.approve_model("m1", "admin")
        
        unapproved = self.engine.get_unapproved_models()
        self.assertEqual(len(unapproved), 1)
        self.assertEqual(unapproved[0].model_id, "m2")

    def test_get_supply_chain_report_empty(self):
        rep = self.engine.get_supply_chain_report()
        self.assertEqual(rep, {})

    def test_get_supply_chain_report(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.approve_model("m1", "admin")
        
        rep = self.engine.get_supply_chain_report()
        self.assertEqual(rep["total_models"], 1)
        self.assertEqual(rep["approval_percentage"], 100.0)
        self.assertEqual(rep["scan_coverage_percentage"], 100.0)

    def test_quarantine_model(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY)
        self.engine.register_model(m1)
        self.engine.quarantine_model("m1", "reason")
        self.assertEqual(self.engine.models["m1"].risk_level, ModelRiskLevel.CRITICAL)
        self.assertFalse(self.engine.models["m1"].approved)

    def test_quarantine_model_cascade(self):
        m1 = AiModelRecord(model_id="m1", name="M1", version="1.0", provenance=ModelProvenance.FIRST_PARTY, training_data_hash="abc")
        self.engine.register_model(m1)
        m2 = AiModelRecord(model_id="m2", name="M2", version="1.0", provenance=ModelProvenance.FIRST_PARTY, dependencies=["m1"], training_data_hash="abc")
        self.engine.register_model(m2)
        
        self.engine.scan_model(ModelScanResult(scan_id="s1", model_id="m1", scanner="s", passed=True))
        self.engine.scan_model(ModelScanResult(scan_id="s2", model_id="m2", scanner="s", passed=True))
        self.engine.approve_model("m1", "admin")
        self.engine.approve_model("m2", "admin")
        
        self.engine.quarantine_model("m1", "reason")
        self.assertEqual(self.engine.models["m1"].risk_level, ModelRiskLevel.CRITICAL)
        self.assertFalse(self.engine.models["m1"].approved)
        self.assertEqual(self.engine.models["m2"].risk_level, ModelRiskLevel.CRITICAL)
        self.assertFalse(self.engine.models["m2"].approved)

    def test_approve_model_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.approve_model("missing", "admin")

    def test_revoke_approval_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.revoke_approval("missing", "reason")

    def test_check_dependencies_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.check_dependencies("missing")

    def test_get_vulnerability_report_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_vulnerability_report("missing")

    def test_get_model_lineage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_model_lineage("missing")
            
    def test_quarantine_model_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.quarantine_model("missing", "reason")

if __name__ == '__main__':
    unittest.main()
