import unittest
from elmos_mature_platform.threat_modeling_engine import ThreatModelingEngine
from elmos_mature_platform.types import (
    ThreatModelAsset,
    DataFlow,
    ThreatRecord,
    ThreatCategory,
    ThreatSeverity,
    ThreatStatus
)

class TestThreatModelingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ThreatModelingEngine()

    # Asset Registration
    def test_register_asset_success(self):
        asset = ThreatModelAsset(asset_id="a1", name="App", asset_type="service", trust_level="internal")
        res = self.engine.register_asset(asset)
        self.assertEqual(res, "a1")
        self.assertIn("a1", self.engine._assets)

    def test_register_multiple_assets(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "database"))
        self.assertEqual(len(self.engine._assets), 2)

    # Data Flow Registration
    def test_register_data_flow_success(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "database"))
        flow = DataFlow("f1", "a1", "a2")
        res = self.engine.register_data_flow(flow)
        self.assertEqual(res, "f1")

    def test_register_flow_missing_source(self):
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "database"))
        with self.assertRaises(ValueError):
            self.engine.register_data_flow(DataFlow("f1", "a1", "a2"))

    def test_register_flow_missing_target(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        with self.assertRaises(ValueError):
            self.engine.register_data_flow(DataFlow("f1", "a1", "a2"))

    # Threat Identification
    def test_identify_threat(self):
        t = ThreatRecord("t1", "Test", ThreatCategory.SPOOFING, ThreatSeverity.LOW)
        res = self.engine.identify_threat(t)
        self.assertEqual(res, "t1")
        self.assertEqual(t.risk_score, 4.0)

    def test_identify_threat_risk_score_calculation(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="public"))
        t = ThreatRecord("t1", "Test", ThreatCategory.SPOOFING, ThreatSeverity.CRITICAL, affected_assets=["a1"])
        self.engine.identify_threat(t)
        self.assertEqual(t.risk_score, 40.0)

    # Auto Discovery
    def test_auto_discover_public_asset(self):
        self.engine.register_asset(ThreatModelAsset("a1", "Pub", "service", trust_level="public"))
        threats = self.engine.auto_discover_threats("a1")
        self.assertTrue(any(t.category == ThreatCategory.SPOOFING for t in threats))
        self.assertTrue(any(t.category == ThreatCategory.DENIAL_OF_SERVICE for t in threats))

    def test_auto_discover_unencrypted_flow(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", encrypted=False))
        threats = self.engine.auto_discover_threats("a1")
        self.assertTrue(any(t.category == ThreatCategory.INFORMATION_DISCLOSURE for t in threats))
        self.assertTrue(any(t.category == ThreatCategory.TAMPERING for t in threats))

    def test_auto_discover_unauthenticated_flow(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", authenticated=False))
        threats = self.engine.auto_discover_threats("a1")
        self.assertTrue(any(t.category == ThreatCategory.SPOOFING for t in threats))
        self.assertTrue(any(t.category == ThreatCategory.ELEVATION_OF_PRIVILEGE for t in threats))

    def test_auto_discover_restricted_data_flow(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", data_classification="restricted"))
        threats = self.engine.auto_discover_threats("a2")
        cats = [t.category for t in threats]
        self.assertIn(ThreatCategory.INFORMATION_DISCLOSURE, cats)

    def test_auto_discover_missing_asset(self):
        with self.assertRaises(ValueError):
            self.engine.auto_discover_threats("missing")

    def test_auto_discover_multiple_flows(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db"))
        self.engine.register_asset(ThreatModelAsset("a3", "A3", "api"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", encrypted=False))
        self.engine.register_data_flow(DataFlow("f2", "a1", "a3", authenticated=False))
        threats = self.engine.auto_discover_threats("a1")
        self.assertEqual(len(threats), 4)

    # Mitigation & Acceptance
    def test_mitigate_threat(self):
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.HIGH)
        self.engine.identify_threat(t)
        mitigated = self.engine.mitigate_threat("t1", "Use TLS")
        self.assertEqual(mitigated.status, ThreatStatus.MITIGATED)
        self.assertEqual(mitigated.mitigation, "Use TLS")

    def test_mitigate_missing_threat(self):
        with self.assertRaises(ValueError):
            self.engine.mitigate_threat("t_none", "fix")

    def test_accept_threat(self):
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.LOW)
        self.engine.identify_threat(t)
        accepted = self.engine.accept_threat("t1", "Business risk accepted")
        self.assertEqual(accepted.status, ThreatStatus.ACCEPTED)

    def test_accept_missing_threat(self):
        with self.assertRaises(ValueError):
            self.engine.accept_threat("t_none", "ok")

    def test_mitigate_accepted_threat(self):
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.LOW)
        self.engine.identify_threat(t)
        self.engine.accept_threat("t1", "Accepted")
        with self.assertRaises(ValueError):
            self.engine.mitigate_threat("t1", "Fix")

    # Risk Score Calculation
    def test_calculate_risk_missing_threat(self):
        with self.assertRaises(ValueError):
            self.engine.calculate_risk_score("t_none")

    def test_calculate_risk_multiple_assets(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="internal"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db", trust_level="restricted"))
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.HIGH, affected_assets=["a1", "a2"])
        self.engine.identify_threat(t)
        self.assertEqual(t.risk_score, 14.0)

    # Reporting and Summaries
    def test_analyze_attack_surface(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="public"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db", trust_level="internal"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", encrypted=False, authenticated=True))
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.CRITICAL)
        self.engine.identify_threat(t)
        
        surface = self.engine.analyze_attack_surface()
        self.assertEqual(surface["total_assets"], 2)
        self.assertEqual(surface["external_facing_count"], 1)
        self.assertEqual(surface["unencrypted_flows"], 1)
        self.assertEqual(surface["unauthenticated_flows"], 0)
        self.assertEqual(surface["high_risk_threats"], 1)

    def test_analyze_attack_surface_mitigated_excluded(self):
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.CRITICAL)
        self.engine.identify_threat(t)
        self.engine.mitigate_threat("t1", "fixed")
        surface = self.engine.analyze_attack_surface()
        self.assertEqual(surface["high_risk_threats"], 0)

    def test_get_stride_summary(self):
        t1 = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.INFO)
        t2 = ThreatRecord("t2", "T2", ThreatCategory.SPOOFING, ThreatSeverity.LOW)
        t3 = ThreatRecord("t3", "T3", ThreatCategory.TAMPERING, ThreatSeverity.MEDIUM)
        for t in [t1, t2, t3]:
            self.engine.identify_threat(t)
            
        stride = self.engine.get_stride_summary()
        self.assertEqual(stride["spoofing"], 2)
        self.assertEqual(stride["tampering"], 1)
        self.assertEqual(stride["repudiation"], 0)

    def test_get_threat_model_report(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="internal"))
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.HIGH)
        self.engine.identify_threat(t)
        self.engine.mitigate_threat("t1", "TLS")
        
        report = self.engine.get_threat_model_report()
        self.assertEqual(report["assets_count"], 1)
        self.assertEqual(report["flows_count"], 0)
        self.assertEqual(report["threats_by_status"]["mitigated"], 1)
        self.assertEqual(report["threats_by_severity"]["high"], 1)

    def test_get_unmitigated_critical_threats(self):
        t1 = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.CRITICAL)
        t2 = ThreatRecord("t2", "T2", ThreatCategory.TAMPERING, ThreatSeverity.HIGH)
        t3 = ThreatRecord("t3", "T3", ThreatCategory.TAMPERING, ThreatSeverity.CRITICAL)
        t4 = ThreatRecord("t4", "T4", ThreatCategory.TAMPERING, ThreatSeverity.MEDIUM)
        for t in [t1, t2, t3, t4]:
            self.engine.identify_threat(t)
            
        self.engine.mitigate_threat("t1", "fixed")
        self.engine.accept_threat("t2", "accepted")
        
        unmitigated = self.engine.get_unmitigated_critical_threats()
        self.assertEqual(len(unmitigated), 1)
        self.assertEqual(unmitigated[0].threat_id, "t3")

    # Additional Edge Cases
    def test_auto_discover_dmz_asset(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="dmz"))
        threats = self.engine.auto_discover_threats("a1")
        self.assertEqual(len(threats), 0)

    def test_calculate_risk_dmz(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="dmz"))
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.MEDIUM, affected_assets=["a1"])
        self.engine.identify_threat(t)
        self.assertEqual(t.risk_score, 12.0)

    def test_calculate_risk_restricted(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service", trust_level="restricted"))
        t = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.INFO, affected_assets=["a1"])
        self.engine.identify_threat(t)
        self.assertEqual(t.risk_score, 1.0)

    def test_zero_threats_average_risk_score(self):
        report = self.engine.get_threat_model_report()
        self.assertEqual(report["average_risk_score"], 0.0)
        
    def test_auto_discover_all_flows_combined(self):
        self.engine.register_asset(ThreatModelAsset("a1", "A1", "service"))
        self.engine.register_asset(ThreatModelAsset("a2", "A2", "db"))
        self.engine.register_data_flow(DataFlow("f1", "a1", "a2", encrypted=False, authenticated=False, data_classification="restricted"))
        threats = self.engine.auto_discover_threats("a2")
        self.assertEqual(len(threats), 5)
        
    def test_register_asset_overwrite(self):
        a1 = ThreatModelAsset("a1", "Old", "service")
        a2 = ThreatModelAsset("a1", "New", "service")
        self.engine.register_asset(a1)
        self.engine.register_asset(a2)
        self.assertEqual(self.engine._assets["a1"].name, "New")

    def test_threat_already_identified(self):
        t1 = ThreatRecord("t1", "T1", ThreatCategory.SPOOFING, ThreatSeverity.INFO)
        self.engine.identify_threat(t1)
        t2 = ThreatRecord("t1", "T2", ThreatCategory.TAMPERING, ThreatSeverity.HIGH)
        self.engine.identify_threat(t2)
        self.assertEqual(self.engine._threats["t1"].title, "T2")

if __name__ == '__main__':
    unittest.main()
