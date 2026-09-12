import unittest
from elmos_mature_platform.types import (
    ProjectFingerprint
)
from elmos_mature_platform.similar_project_retrieval_engine import SimilarProjectRetrievalEngine

class TestSimilarProjectRetrievalComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SimilarProjectRetrievalEngine()

    def _create_fingerprint(self, pid="proj-1", lang="Java", fw="Struts1", tgt_lang="Java", tgt_fw="Spring-Boot-3", loc=50000, pattern="monolith", tags=None, vec=None):
        return ProjectFingerprint(
            project_id=pid,
            project_name=f"Name-{pid}",
            source_language=lang,
            source_framework=fw,
            target_language=tgt_lang,
            target_framework=tgt_fw,
            loc_count=loc,
            module_count=5,
            architectural_pattern=pattern,
            tags=tags or ["banking", "legacy", "web"],
            feature_vector=vec or [0.5, 0.8, 0.2, 0.1]
        )

    def test_index_and_get_project(self):
        fp = self._create_fingerprint()
        self.engine.index_project(fp, duration_days=45.0, recipes=["struts1-to-springmvc"])
        retrieved = self.engine.get_project("proj-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.source_framework, "Struts1")

    def test_index_duplicate_project_raises(self):
        fp = self._create_fingerprint()
        self.engine.index_project(fp)
        with self.assertRaises(ValueError):
            self.engine.index_project(fp)

    def test_calculate_similarity_identical_matches_high(self):
        p1 = self._create_fingerprint("p1")
        p2 = self._create_fingerprint("p2")
        sim = self.engine.calculate_similarity(p1, p2)
        self.assertGreater(sim, 0.90)

    def test_calculate_similarity_different_tech_matches_low(self):
        p1 = self._create_fingerprint("p1", lang="Java", fw="Struts1", pattern="monolith", tags=["banking"])
        p2 = self._create_fingerprint("p2", lang="Python", fw="Django-3", pattern="microservices", tags=["ml", "ai"])
        sim = self.engine.calculate_similarity(p1, p2)
        self.assertLessEqual(sim, 0.40)

    def test_find_similar_projects_ranking(self):
        query = self._create_fingerprint("query", lang="Java", fw="Struts1", loc=45000, tags=["banking", "legacy"])
        
        # Candidate 1: Very similar
        c1 = self._create_fingerprint("c1", lang="Java", fw="Struts1", loc=50000, tags=["banking", "legacy"], vec=[0.5, 0.8, 0.2, 0.1])
        # Candidate 2: Moderately similar
        c2 = self._create_fingerprint("c2", lang="Java", fw="Spring-Boot-2", loc=60000, tags=["banking"], vec=[0.4, 0.7, 0.3, 0.1])
        # Candidate 3: Distant
        c3 = self._create_fingerprint("c3", lang="Go", fw="Gin", loc=10000, tags=["cloud"], vec=[0.1, 0.1, 0.9, 0.9])

        self.engine.index_project(c1, duration_days=40.0, recipes=["struts1-recipe"])
        self.engine.index_project(c2, duration_days=25.0, recipes=["spring2-recipe"])
        self.engine.index_project(c3, duration_days=10.0, recipes=["go-recipe"])

        matches = self.engine.find_similar_projects(query, top_k=2)
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].matched_project_id, "c1")
        self.assertEqual(matches[1].matched_project_id, "c2")
        self.assertIn("banking", matches[0].shared_tags)
        self.assertIn("struts1-recipe", matches[0].recommended_recipes)

    def test_recommend_target_stack_default_and_fallback(self):
        rec_struts = self.engine.recommend_target_stack("struts1")
        self.assertEqual(rec_struts.recommended_target_framework, "spring-boot-3")
        self.assertGreater(rec_struts.confidence_score, 0.9)

        rec_unknown = self.engine.recommend_target_stack("custom-proprietary-fw")
        self.assertEqual(rec_unknown.recommended_target_framework, "cloud-native-modern-stack")

    def test_estimate_migration_effort_with_matches(self):
        query = self._create_fingerprint("query", lang="Java", fw="Struts1", loc=50000)
        c1 = self._create_fingerprint("c1", lang="Java", fw="Struts1", loc=50000)
        self.engine.index_project(c1, duration_days=45.0, recipes=["recipe-a"])

        effort = self.engine.estimate_migration_effort(query)
        self.assertEqual(effort["similar_projects_found"], 1)
        self.assertAlmostEqual(effort["estimated_duration_days"], 45.0, delta=2.0)
        self.assertEqual(effort["recommended_target_stack"], "spring-boot-3")
        self.assertIn("recipe-a", effort["recommended_recipes"])

    def test_estimate_migration_effort_fallback_no_matches(self):
        query = self._create_fingerprint("query", lang="Erlang", fw="Custom", loc=20000)
        effort = self.engine.estimate_migration_effort(query)
        self.assertEqual(effort["similar_projects_found"], 0)
        self.assertGreater(effort["estimated_duration_days"], 5.0)

if __name__ == "__main__":
    unittest.main()
