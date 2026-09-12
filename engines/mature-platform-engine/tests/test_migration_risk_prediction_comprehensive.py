import unittest
from elmos_mature_platform.types import (
    MigrationProject,
    MigrationRiskFactor,
    MigrationRiskLevel,
    MigrationRiskCategory
)
from elmos_mature_platform.migration_risk_prediction_engine import MigrationRiskPredictionEngine

class TestMigrationRiskPredictionEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MigrationRiskPredictionEngine()
        self.p1 = MigrationProject(
            project_id="P1", name="Migrate DB", source_system="Oracle", target_system="Postgres",
            data_size_gb=100.0, complexity_score=5.0, team_experience_score=8.0
        )
        self.engine.create_project(self.p1)

    def test_create_project(self):
        self.assertIn("P1", self.engine.projects)
        self.assertEqual(self.engine.projects["P1"].name, "Migrate DB")

    def test_add_risk_factor_computes_score(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.5, 0.8)
        self.engine.add_risk_factor("P1", f)
        self.assertAlmostEqual(f.risk_score, 0.4)

    def test_add_risk_factor_not_found(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.5, 0.8)
        with self.assertRaises(ValueError):
            self.engine.add_risk_factor("P2", f)

    def test_get_risk_factors(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.5, 0.8)
        self.engine.add_risk_factor("P1", f)
        factors = self.engine.get_risk_factors("P1")
        self.assertEqual(len(factors), 1)

    def test_get_risk_factors_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_risk_factors("P2")

    def test_compute_overall_risk_minimal(self):
        # 0 factors -> minimal
        p = self.engine.compute_overall_risk("P1")
        self.assertEqual(p.overall_risk_level, MigrationRiskLevel.MINIMAL)
        self.assertEqual(p.overall_risk_score, 0.0)

    def test_compute_overall_risk_low(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.5, 0.6) # 0.3
        self.engine.add_risk_factor("P1", f)
        p = self.engine.compute_overall_risk("P1")
        self.assertEqual(p.overall_risk_level, MigrationRiskLevel.LOW)

    def test_compute_overall_risk_medium(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.7, 0.7) # 0.49
        self.engine.add_risk_factor("P1", f)
        p = self.engine.compute_overall_risk("P1")
        self.assertEqual(p.overall_risk_level, MigrationRiskLevel.MEDIUM)

    def test_compute_overall_risk_high(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.9, 0.8) # 0.72
        self.engine.add_risk_factor("P1", f)
        p = self.engine.compute_overall_risk("P1")
        self.assertEqual(p.overall_risk_level, MigrationRiskLevel.HIGH)

    def test_compute_overall_risk_critical(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.9, 0.95) # 0.855
        self.engine.add_risk_factor("P1", f)
        p = self.engine.compute_overall_risk("P1")
        self.assertEqual(p.overall_risk_level, MigrationRiskLevel.CRITICAL)

    def test_compute_overall_risk_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.compute_overall_risk("P2")

    def test_predict_outcome_base(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 0.5, 0.4) # score=0.2
        self.engine.add_risk_factor("P1", f)
        # score = 0.2, prob = 1 - 0.2 = 0.8
        # comp penalty = (5/10)*0.2 = 0.1
        # exp bonus = (8/10)*0.2 = 0.16
        # prob = 0.8 - 0.1 + 0.16 = 0.86
        pred = self.engine.predict_outcome("P1")
        self.assertAlmostEqual(pred.predicted_success_probability, 0.86)

    def test_predict_outcome_bounds_max(self):
        # 0 factors -> score=0, prob=1
        self.p1.complexity_score = 0
        self.p1.team_experience_score = 10
        pred = self.engine.predict_outcome("P1")
        self.assertEqual(pred.predicted_success_probability, 1.0)

    def test_predict_outcome_bounds_min(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "desc", 1.0, 1.0) # score=1.0
        self.engine.add_risk_factor("P1", f)
        self.p1.complexity_score = 10
        self.p1.team_experience_score = 0
        pred = self.engine.predict_outcome("P1")
        self.assertEqual(pred.predicted_success_probability, 0.0)

    def test_predict_outcome_confidence(self):
        pred = self.engine.predict_outcome("P1")
        self.assertAlmostEqual(pred.confidence, 0.5)
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.5, 0.5))
        pred = self.engine.predict_outcome("P1")
        self.assertAlmostEqual(pred.confidence, 0.6)

    def test_predict_outcome_top_factors(self):
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.5, 0.5))
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F2", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8)) # highest
        pred = self.engine.predict_outcome("P1")
        self.assertEqual(pred.top_risk_factors[0], "F2")

    def test_predict_outcome_mitigations(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8)
        f.mitigation = "Do X"
        self.engine.add_risk_factor("P1", f)
        pred = self.engine.predict_outcome("P1")
        self.assertIn("Do X", pred.recommended_mitigations)

    def test_mitigate_factor(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8) # 0.64
        self.engine.add_risk_factor("P1", f)
        self.engine.mitigate_factor("P1", "F1", "Do X")
        self.assertTrue(f.mitigated)
        self.assertEqual(f.mitigation, "Do X")
        self.assertAlmostEqual(f.risk_score, 0.32)

    def test_mitigate_factor_updates_overall(self):
        f = MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8) # 0.64 -> HIGH
        self.engine.add_risk_factor("P1", f)
        self.engine.mitigate_factor("P1", "F1", "Do X") # 0.32 -> LOW
        self.assertEqual(self.p1.overall_risk_level, MigrationRiskLevel.LOW)

    def test_mitigate_factor_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.mitigate_factor("P1", "F99", "X")

    def test_record_outcome(self):
        self.engine.record_outcome("P1", True, 42)
        self.assertEqual(self.p1.succeeded, True)
        self.assertEqual(self.p1.actual_duration_days, 42)

    def test_record_outcome_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_outcome("P2", True, 42)

    def test_get_historical_accuracy_empty(self):
        res = self.engine.get_historical_accuracy()
        self.assertEqual(res["total_completed"], 0)
        self.assertEqual(res["accuracy"], 0.0)

    def test_get_historical_accuracy(self):
        self.engine.record_outcome("P1", True, 42) # predicted 0.86 (True) -> matches True
        res = self.engine.get_historical_accuracy()
        self.assertEqual(res["total_completed"], 1)
        self.assertEqual(res["correct_predictions"], 1)
        self.assertEqual(res["accuracy"], 1.0)

    def test_get_historical_accuracy_incorrect(self):
        self.engine.record_outcome("P1", False, 42) # predicted 0.86 (True) -> matches False
        res = self.engine.get_historical_accuracy()
        self.assertEqual(res["total_completed"], 1)
        self.assertEqual(res["correct_predictions"], 0)
        self.assertEqual(res["accuracy"], 0.0)

    def test_get_similar_projects(self):
        p2 = MigrationProject("P2", "Migrate", "Oracle", "Postgres", 150.0, 5.0, 8.0) # match src, tgt, size diff < 100
        p3 = MigrationProject("P3", "Migrate", "SQLServer", "MySQL", 1000.0, 5.0, 8.0) # no match
        self.engine.create_project(p2)
        self.engine.create_project(p3)
        sim = self.engine.get_similar_projects("P1")
        self.assertEqual(len(sim), 1)
        self.assertEqual(sim[0].project_id, "P2")

    def test_get_similar_projects_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_similar_projects("P99")

    def test_get_risk_heatmap(self):
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8)) # 0.64
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F2", MigrationRiskCategory.DOWNTIME, "", 0.5, 0.4)) # 0.2
        hm = self.engine.get_risk_heatmap()
        self.assertAlmostEqual(hm[MigrationRiskCategory.DATA_LOSS.value], 0.64)
        self.assertAlmostEqual(hm[MigrationRiskCategory.DOWNTIME.value], 0.20)
        self.assertAlmostEqual(hm[MigrationRiskCategory.SECURITY.value], 0.0)

    def test_get_risk_report(self):
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8))
        self.engine.mitigate_factor("P1", "F1", "Do X")
        rep = self.engine.get_risk_report("P1")
        self.assertEqual(rep["project_id"], "P1")
        self.assertEqual(rep["total_factors"], 1)
        self.assertEqual(rep["mitigated_factors"], 1)

    def test_similar_projects_scoring(self):
        # target is P1 (Oracle -> Postgres, 100gb)
        # P2: same src, diff tgt, 200gb (diff=100) -> src(3) + size(1) = 4
        # P3: same tgt, diff src, 50gb (diff=50) -> tgt(3) + size(2) = 5
        # P4: diff src, diff tgt, 500gb (diff=400) -> size(1) = 1
        p2 = MigrationProject("P2", "2", "Oracle", "MySQL", 200.0, 0, 0)
        p3 = MigrationProject("P3", "3", "SQLServer", "Postgres", 50.0, 0, 0)
        p4 = MigrationProject("P4", "4", "MongoDB", "Cassandra", 500.0, 0, 0)
        self.engine.create_project(p2)
        self.engine.create_project(p3)
        self.engine.create_project(p4)
        sim = self.engine.get_similar_projects("P1")
        self.assertEqual([p.project_id for p in sim], ["P3", "P2", "P4"])
        
    def test_heatmap_averaging(self):
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F1", MigrationRiskCategory.DATA_LOSS, "", 0.8, 0.8)) # 0.64
        self.engine.add_risk_factor("P1", MigrationRiskFactor("F2", MigrationRiskCategory.DATA_LOSS, "", 0.4, 0.4)) # 0.16
        hm = self.engine.get_risk_heatmap()
        self.assertAlmostEqual(hm[MigrationRiskCategory.DATA_LOSS.value], 0.4) # avg of 0.64, 0.16
        
    def test_empty_heatmap(self):
        hm = self.engine.get_risk_heatmap()
        for v in hm.values():
            self.assertEqual(v, 0.0)

if __name__ == '__main__':
    unittest.main()
