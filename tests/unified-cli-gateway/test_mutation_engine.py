"""Unit tests for Autonomous QA Mutation Testing Engine."""

import unittest
from elmos_autonomous_qa.mutation_engine import (
    Mutant,
    MutationAnalysisReport,
    MutationTestingEngine,
    run_mutation_testing,
)


class TestMutationTestingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MutationTestingEngine()
        self.sample_code = """
        public int calculateDiscount(int price) {
            if (price > 100) {
                return price - 20;
            }
            return price;
        }
        """

    def test_generate_mutants(self):
        mutants = self.engine.generate_mutants(self.sample_code)
        self.assertGreater(len(mutants), 0)
        operators = {m.operator for m in mutants}
        self.assertTrue(operators.intersection({"CONDITION_NEGATION", "ARITHMETIC_SWAP"}))

    def test_evaluate_mutants_adequacy(self):
        report = self.engine.evaluate_mutants(self.sample_code)
        self.assertIsInstance(report, MutationAnalysisReport)
        self.assertGreater(report.total_mutants, 0)
        self.assertGreaterEqual(report.mutation_score, 0.0)
        self.assertLessEqual(report.mutation_score, 1.0)
        self.assertIsNotNone(report.source_digest)

    def test_run_mutation_testing_helper(self):
        result = run_mutation_testing(self.sample_code)
        self.assertIn("status", result)
        self.assertIn("mutation_score", result)
        self.assertIn("mutants", result)
        self.assertGreater(len(result["mutants"]), 0)


if __name__ == "__main__":
    unittest.main()
