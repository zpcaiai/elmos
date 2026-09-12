import unittest
from elmos_mature_platform.types import (
    BenchmarkDifficulty,
    BenchmarkTask,
    AgentEvalRun,
    BenchmarkSuite
)
from elmos_mature_platform.agent_eval_benchmark_engine import AgentEvalBenchmarkEngine

class TestAgentEvalBenchmarkEngine(unittest.TestCase):
    def setUp(self):
        self.engine = AgentEvalBenchmarkEngine()
        
        self.task1 = BenchmarkTask(
            task_id="t1", name="Task 1", difficulty=BenchmarkDifficulty.EASY, category="coding",
            max_cost_usd=1.0, timeout_seconds=100
        )
        self.task2 = BenchmarkTask(
            task_id="t2", name="Task 2", difficulty=BenchmarkDifficulty.HARD, category="research",
            max_cost_usd=2.0, timeout_seconds=200
        )
        self.suite = BenchmarkSuite(suite_id="s1", name="Suite 1")
        
        self.engine.add_task(self.task1)
        self.engine.add_task(self.task2)
        self.engine.create_suite(self.suite)
        self.engine.add_task_to_suite("s1", "t1")
        self.engine.add_task_to_suite("s1", "t2")

    def test_create_suite(self):
        suite2 = BenchmarkSuite(suite_id="s2", name="Suite 2")
        self.assertEqual(self.engine.create_suite(suite2), "s2")
        self.assertIn("s2", self.engine._suites)

    def test_add_task(self):
        task3 = BenchmarkTask(task_id="t3", name="Task 3", difficulty=BenchmarkDifficulty.MEDIUM, category="debugging")
        self.assertEqual(self.engine.add_task(task3), "t3")
        self.assertIn("t3", self.engine._tasks)

    def test_add_task_to_suite(self):
        task3 = BenchmarkTask(task_id="t3", name="Task 3", difficulty=BenchmarkDifficulty.MEDIUM, category="debugging")
        self.engine.add_task(task3)
        self.engine.add_task_to_suite("s1", "t3")
        self.assertIn("t3", self.engine._suites["s1"].task_ids)

    def test_add_task_to_suite_invalid_suite(self):
        with self.assertRaises(ValueError):
            self.engine.add_task_to_suite("s99", "t1")

    def test_add_task_to_suite_invalid_task(self):
        with self.assertRaises(ValueError):
            self.engine.add_task_to_suite("s1", "t99")

    def test_record_run(self):
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1")
        self.engine.record_run(run)
        self.assertIn("r1", self.engine._runs)

    def test_record_run_invalid_task(self):
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t99")
        with self.assertRaises(ValueError):
            self.engine.record_run(run)

    def test_score_run_success_perfect(self):
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=0.0, latency_seconds=0.0, safety_violations=0)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["success"], True)
        self.assertEqual(score["cost_efficiency"], 1.0)
        self.assertEqual(score["latency_grade"], 1.0)
        self.assertEqual(score["safety_score"], 1.0)
        self.assertEqual(score["composite_score"], 1.0)

    def test_score_run_failure(self):
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=False, cost_usd=1.0, latency_seconds=100.0, safety_violations=5)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["success"], False)
        self.assertEqual(score["cost_efficiency"], 0.0)
        self.assertEqual(score["latency_grade"], 0.0)
        self.assertEqual(score["safety_score"], 0.0)
        self.assertEqual(score["composite_score"], 0.0)

    def test_score_run_partial(self):
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=0.5, latency_seconds=50.0, safety_violations=1)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertAlmostEqual(score["cost_efficiency"], 0.5)
        self.assertAlmostEqual(score["latency_grade"], 0.5)
        self.assertAlmostEqual(score["safety_score"], 0.8)
        self.assertAlmostEqual(score["composite_score"], 0.4*1.0 + 0.2*0.5 + 0.2*0.5 + 0.2*0.8)

    def test_score_run_invalid_run(self):
        with self.assertRaises(ValueError):
            self.engine.score_run("r99")

    def test_get_agent_scores(self):
        run1 = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True)
        run2 = AgentEvalRun(run_id="r2", agent_id="a1", task_id="t2", success=False)
        self.engine.record_run(run1)
        self.engine.record_run(run2)
        
        scores = self.engine.get_agent_scores("a1")
        self.assertEqual(scores["success_rate"], 0.5)
        self.assertEqual(scores["total_runs"], 2)

    def test_get_agent_scores_empty(self):
        scores = self.engine.get_agent_scores("a99")
        self.assertEqual(scores, {})

    def test_compare_agents(self):
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True))
        self.engine.record_run(AgentEvalRun(run_id="r2", agent_id="a2", task_id="t1", success=False))
        
        comparison = self.engine.compare_agents(["a1", "a2"])
        self.assertIn("a1", comparison)
        self.assertIn("a2", comparison)
        self.assertEqual(comparison["a1"]["success_rate"], 1.0)
        self.assertEqual(comparison["a2"]["success_rate"], 0.0)

    def test_get_suite_results(self):
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True))
        results = self.engine.get_suite_results("s1")
        self.assertIn("t1", results)
        self.assertIn("t2", results)
        self.assertEqual(len(results["t1"]), 1)
        self.assertEqual(len(results["t2"]), 0)

    def test_get_suite_results_invalid_suite(self):
        with self.assertRaises(ValueError):
            self.engine.get_suite_results("s99")

    def test_get_leaderboard(self):
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=0.0, latency_seconds=0.0))
        self.engine.record_run(AgentEvalRun(run_id="r2", agent_id="a2", task_id="t1", success=False, cost_usd=1.0, latency_seconds=100.0))
        
        leaderboard = self.engine.get_leaderboard("s1")
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["agent_id"], "a1")
        self.assertEqual(leaderboard[1]["agent_id"], "a2")

    def test_get_leaderboard_empty(self):
        suite2 = BenchmarkSuite(suite_id="s2", name="Suite 2")
        self.engine.create_suite(suite2)
        leaderboard = self.engine.get_leaderboard("s2")
        self.assertEqual(leaderboard, [])

    def test_get_task_difficulty_distribution(self):
        dist = self.engine.get_task_difficulty_distribution("s1")
        self.assertEqual(dist["easy"], 1)
        self.assertEqual(dist["medium"], 0)
        self.assertEqual(dist["hard"], 1)
        self.assertEqual(dist["expert"], 0)

    def test_get_task_difficulty_distribution_invalid_suite(self):
        with self.assertRaises(ValueError):
            self.engine.get_task_difficulty_distribution("s99")

    def test_detect_regressions_no_regressions(self):
        suite2 = BenchmarkSuite(suite_id="s2", name="Suite 2")
        self.engine.create_suite(suite2)
        self.engine.add_task_to_suite("s2", "t1")
        
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True))
        # Need to simulate runs for suite2 - normally we'd have a suite context for a run.
        # But our engine associates runs with tasks. If the task is in both suites, and it fails in current suite, it's a regression.
        # Let's change the task run to failure to simulate a new run later...
        self.engine.record_run(AgentEvalRun(run_id="r2", agent_id="a1", task_id="t1", success=True)) # no regression
        
        regs = self.engine.detect_regressions("a1", "s1", "s2")
        self.assertEqual(regs["regressed_tasks"], [])

    def test_detect_regressions_with_regression(self):
        suite2 = BenchmarkSuite(suite_id="s2", name="Suite 2")
        self.engine.create_suite(suite2)
        self.engine.add_task_to_suite("s2", "t1")
        
        # We need to simulate that t1 passed in s1, but failed in s2.
        # Since runs are just mapped by run_id, and we query by agent and task:
        # Our naive implementation in engine: 
        # baseline_runs = {r.task_id: r for r in self._runs.values() ...}
        # This takes the last one in self._runs dict for the task.
        # To make a regression, we can just record a fail run that overwrites the success? No, it just takes the last one in the dict if they share a task id.
        # Actually our implementation in detect_regressions takes ANY run for the task in the current suite.
        # Let's add task3 for baseline and current to properly test this.
        task3 = BenchmarkTask(task_id="t3", name="Task 3", difficulty=BenchmarkDifficulty.EASY, category="coding")
        self.engine.add_task(task3)
        self.engine.add_task_to_suite("s1", "t3")
        self.engine.add_task_to_suite("s2", "t3")
        
        # Add run for baseline
        self.engine._runs["r_base"] = AgentEvalRun(run_id="r_base", agent_id="a1", task_id="t3", success=True)
        # Add run for current (would be found later in dict iteration if we ensure order or something, 
        # wait, python dicts are ordered. The last one overrides in the dictionary comprehension!
        self.engine._runs["r_curr"] = AgentEvalRun(run_id="r_curr", agent_id="a1", task_id="t3", success=False)
        
        regs = self.engine.detect_regressions("a1", "s1", "s2")
        self.assertIn("t3", regs["regressed_tasks"])

    def test_detect_regressions_invalid_suites(self):
        with self.assertRaises(ValueError):
            self.engine.detect_regressions("a1", "s1", "s99")

    def test_latency_clamping(self):
        # Latency > timeout
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=0.0, latency_seconds=200.0, safety_violations=0)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["latency_grade"], 0.0)

    def test_cost_clamping(self):
        # Cost > max_cost
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=2.0, latency_seconds=0.0, safety_violations=0)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["cost_efficiency"], 0.0)

    def test_safety_clamping(self):
        # > 5 violations should clamp to 0
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True, cost_usd=0.0, latency_seconds=0.0, safety_violations=10)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["safety_score"], 0.0)
        
    def test_zero_max_cost(self):
        t0 = BenchmarkTask(task_id="t0", name="T0", difficulty=BenchmarkDifficulty.EASY, category="coding", max_cost_usd=0.0)
        self.engine.add_task(t0)
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t0", cost_usd=1.0)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["cost_efficiency"], 0.0)

    def test_zero_timeout(self):
        t0 = BenchmarkTask(task_id="t0", name="T0", difficulty=BenchmarkDifficulty.EASY, category="coding", timeout_seconds=0)
        self.engine.add_task(t0)
        run = AgentEvalRun(run_id="r1", agent_id="a1", task_id="t0", latency_seconds=1.0)
        self.engine.record_run(run)
        score = self.engine.score_run("r1")
        self.assertEqual(score["latency_grade"], 0.0)

    def test_multiple_tasks_in_suite(self):
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a1", task_id="t1", success=True))
        self.engine.record_run(AgentEvalRun(run_id="r2", agent_id="a1", task_id="t2", success=True))
        scores = self.engine.get_agent_scores("a1")
        self.assertEqual(scores["total_runs"], 2)

    def test_leaderboard_ordering(self):
        self.engine.record_run(AgentEvalRun(run_id="r1", agent_id="a_best", task_id="t1", success=True, cost_usd=0.0, latency_seconds=0.0, safety_violations=0))
        self.engine.record_run(AgentEvalRun(run_id="r2", agent_id="a_worst", task_id="t1", success=False, cost_usd=1.0, latency_seconds=100.0, safety_violations=5))
        self.engine.record_run(AgentEvalRun(run_id="r3", agent_id="a_mid", task_id="t1", success=True, cost_usd=0.5, latency_seconds=50.0, safety_violations=1))
        lb = self.engine.get_leaderboard("s1")
        self.assertEqual(lb[0]["agent_id"], "a_best")
        self.assertEqual(lb[1]["agent_id"], "a_mid")
        self.assertEqual(lb[2]["agent_id"], "a_worst")

    def test_detect_regressions_missing_task_in_current(self):
        suite2 = BenchmarkSuite(suite_id="s2", name="Suite 2")
        self.engine.create_suite(suite2)
        # Don't add t1 to s2
        self.engine._runs["r_base"] = AgentEvalRun(run_id="r_base", agent_id="a1", task_id="t1", success=True)
        regs = self.engine.detect_regressions("a1", "s1", "s2")
        self.assertEqual(regs["regressed_tasks"], [])

if __name__ == '__main__':
    unittest.main()
