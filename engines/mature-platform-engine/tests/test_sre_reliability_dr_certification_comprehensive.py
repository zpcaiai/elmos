import unittest
from elmos_mature_platform.types import (
    ReliabilityDomain,
    CertificationLevel,
    ReliabilityMetric,
    ReliabilityCertification
)
from elmos_mature_platform.sre_reliability_dr_certification_engine import SreReliabilityDrCertificationEngine

class TestSreReliabilityDrCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SreReliabilityDrCertificationEngine()

    def test_record_metric_availability_met(self):
        m = ReliabilityMetric("m1", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        self.assertTrue(self.engine._metrics["m1"].met)

    def test_record_metric_availability_unmet(self):
        m = ReliabilityMetric("m2", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 98.5)
        self.engine.record_metric(m)
        self.assertFalse(self.engine._metrics["m2"].met)

    def test_record_metric_latency_met(self):
        m = ReliabilityMetric("m3", ReliabilityDomain.LATENCY, "Lat", 200.0, 150.0)
        self.engine.record_metric(m)
        self.assertTrue(self.engine._metrics["m3"].met)

    def test_record_metric_latency_unmet(self):
        m = ReliabilityMetric("m4", ReliabilityDomain.LATENCY, "Lat", 200.0, 250.0)
        self.engine.record_metric(m)
        self.assertFalse(self.engine._metrics["m4"].met)

    def test_record_metric_error_rate_met(self):
        m = ReliabilityMetric("m5", ReliabilityDomain.ERROR_RATE, "Err", 1.0, 0.5)
        self.engine.record_metric(m)
        self.assertTrue(self.engine._metrics["m5"].met)

    def test_record_metric_error_rate_unmet(self):
        m = ReliabilityMetric("m6", ReliabilityDomain.ERROR_RATE, "Err", 1.0, 1.5)
        self.engine.record_metric(m)
        self.assertFalse(self.engine._metrics["m6"].met)

    def test_record_metric_throughput_met(self):
        m = ReliabilityMetric("m7", ReliabilityDomain.THROUGHPUT, "Tps", 1000.0, 1500.0)
        self.engine.record_metric(m)
        self.assertTrue(self.engine._metrics["m7"].met)

    def test_record_metric_throughput_unmet(self):
        m = ReliabilityMetric("m8", ReliabilityDomain.THROUGHPUT, "Tps", 1000.0, 500.0)
        self.engine.record_metric(m)
        self.assertFalse(self.engine._metrics["m8"].met)

    def test_record_metric_dr_met(self):
        # DR RTO/RPO lower is better
        m = ReliabilityMetric("m9", ReliabilityDomain.DISASTER_RECOVERY, "RTO", 4.0, 2.0)
        self.engine.record_metric(m)
        self.assertTrue(self.engine._metrics["m9"].met)

    def test_record_metric_dr_unmet(self):
        m = ReliabilityMetric("m10", ReliabilityDomain.DISASTER_RECOVERY, "RTO", 4.0, 6.0)
        self.engine.record_metric(m)
        self.assertFalse(self.engine._metrics["m10"].met)

    def test_create_certification(self):
        c = ReliabilityCertification("c1", "svc1", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        self.assertIn("c1", self.engine._certifications)

    def test_add_metric_to_cert(self):
        c = ReliabilityCertification("c2", "svc1", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m11", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c2", "m11")
        self.assertIn("m11", self.engine._certifications["c2"].metrics)

    def test_add_metric_invalid_cert(self):
        m = ReliabilityMetric("m12", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        with self.assertRaises(ValueError):
            self.engine.add_metric_to_cert("invalid", "m12")

    def test_add_metric_invalid_metric(self):
        c = ReliabilityCertification("c3", "svc1", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        with self.assertRaises(ValueError):
            self.engine.add_metric_to_cert("c3", "invalid")

    def test_add_metric_duplicate_ignore(self):
        c = ReliabilityCertification("c4", "svc1", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m13", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c4", "m13")
        self.engine.add_metric_to_cert("c4", "m13")
        self.assertEqual(len(self.engine._certifications["c4"].metrics), 1)

    def test_evaluate_certification_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_certification("invalid")

    def test_evaluate_certification_no_availability(self):
        c = ReliabilityCertification("c5", "svc2", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m14", ReliabilityDomain.LATENCY, "Lat", 200, 150)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c5", "m14")
        self.engine.evaluate_certification("c5")
        self.assertIn("Missing required AVAILABILITY metric", self.engine._certifications["c5"].gaps)

    def test_evaluate_certification_all_met(self):
        c = ReliabilityCertification("c6", "svc3", CertificationLevel.SILVER)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m15", ReliabilityDomain.AVAILABILITY, "Avail", 99.9, 99.95)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c6", "m15")
        self.engine.evaluate_certification("c6")
        self.assertEqual(len(self.engine._certifications["c6"].gaps), 0)

    def test_evaluate_certification_bronze_target(self):
        c = ReliabilityCertification("c7", "svc4", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m16", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c7", "m16")
        self.engine.evaluate_certification("c7")
        self.assertEqual(len(self.engine._certifications["c7"].gaps), 0)

    def test_evaluate_certification_platinum_target_fail(self):
        c = ReliabilityCertification("c8", "svc5", CertificationLevel.PLATINUM)
        self.engine.create_certification(c)
        # 99.95 is below PLATINUM 99.99
        m = ReliabilityMetric("m17", ReliabilityDomain.AVAILABILITY, "Avail", 99.9, 99.95)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c8", "m17")
        self.engine.evaluate_certification("c8")
        self.assertTrue(any("target 99.99%" in g for g in self.engine._certifications["c8"].gaps))

    def test_certify_invalid(self):
        with self.assertRaises(ValueError):
            self.engine.certify("invalid", "certifier")

    def test_certify_success(self):
        c = ReliabilityCertification("c9", "svc6", CertificationLevel.GOLD)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m18", ReliabilityDomain.AVAILABILITY, "Avail", 99.95, 99.99)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c9", "m18")
        certified = self.engine.certify("c9", "alice")
        self.assertTrue(certified.certified)
        self.assertEqual(certified.certifier, "alice")
        self.assertNotEqual(certified.certified_at, "")

    def test_certify_failure_due_to_gaps(self):
        c = ReliabilityCertification("c10", "svc7", CertificationLevel.SILVER)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m19", ReliabilityDomain.AVAILABILITY, "Avail", 99.9, 99.0)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c10", "m19")
        with self.assertRaises(ValueError):
            self.engine.certify("c10", "alice")

    def test_get_level_requirements(self):
        reqs = self.engine.get_level_requirements(CertificationLevel.GOLD)
        self.assertEqual(reqs["availability_target"], 99.95)

    def test_get_service_reliability_score_empty(self):
        self.assertEqual(self.engine.get_service_reliability_score("unknown"), 0.0)

    def test_get_service_reliability_score_partial(self):
        c = ReliabilityCertification("c11", "svc8", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m1 = ReliabilityMetric("m20", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        m2 = ReliabilityMetric("m21", ReliabilityDomain.LATENCY, "Lat", 200.0, 250.0) # fails
        self.engine.record_metric(m1)
        self.engine.record_metric(m2)
        self.engine.add_metric_to_cert("c11", "m20")
        self.engine.add_metric_to_cert("c11", "m21")
        
        score = self.engine.get_service_reliability_score("svc8")
        self.assertEqual(score, 50.0)

    def test_get_service_reliability_score_perfect(self):
        c = ReliabilityCertification("c12", "svc9", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m1 = ReliabilityMetric("m22", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m1)
        self.engine.add_metric_to_cert("c12", "m22")
        score = self.engine.get_service_reliability_score("svc9")
        self.assertEqual(score, 100.0)

    def test_get_gaps(self):
        c = ReliabilityCertification("c13", "svc10", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m23", ReliabilityDomain.LATENCY, "Lat", 200, 150)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c13", "m23")
        gaps = self.engine.get_gaps("c13")
        self.assertIn("Missing required AVAILABILITY metric", gaps)

    def test_get_certification_history_empty(self):
        history = self.engine.get_certification_history("unknown")
        self.assertEqual(len(history), 0)

    def test_get_certification_history(self):
        c = ReliabilityCertification("c14", "svc11", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        history = self.engine.get_certification_history("svc11")
        self.assertEqual(len(history), 1)

    def test_get_fleet_reliability_report_empty(self):
        report = self.engine.get_fleet_reliability_report()
        self.assertEqual(len(report), 0)

    def test_get_fleet_reliability_report(self):
        c = ReliabilityCertification("c15", "svc12", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m = ReliabilityMetric("m24", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        self.engine.record_metric(m)
        self.engine.add_metric_to_cert("c15", "m24")
        self.engine.certify("c15", "bob")
        
        report = self.engine.get_fleet_reliability_report()
        self.assertIn("svc12", report)
        self.assertEqual(report["svc12"]["cert_levels"], ["bronze"])
        self.assertTrue(report["svc12"]["certified"])
        self.assertEqual(report["svc12"]["reliability_score"], 100.0)

    def test_evaluate_certification_failover(self):
        c = ReliabilityCertification("c16", "svc13", CertificationLevel.BRONZE)
        self.engine.create_certification(c)
        m1 = ReliabilityMetric("m25", ReliabilityDomain.AVAILABILITY, "Avail", 99.0, 99.5)
        m2 = ReliabilityMetric("m26", ReliabilityDomain.FAILOVER, "FailoverTime", 10.0, 5.0)
        self.engine.record_metric(m1)
        self.engine.record_metric(m2)
        self.engine.add_metric_to_cert("c16", "m25")
        self.engine.add_metric_to_cert("c16", "m26")
        self.engine.evaluate_certification("c16")
        self.assertEqual(len(self.engine._certifications["c16"].gaps), 0)

if __name__ == '__main__':
    unittest.main()
