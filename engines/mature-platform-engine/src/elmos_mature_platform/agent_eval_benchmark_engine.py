from typing import Dict, List, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    BenchmarkDifficulty,
    EvalMetricType,
    BenchmarkTask,
    AgentEvalRun,
    BenchmarkSuite
)

class AgentEvalBenchmarkEngine:
    def __init__(self):
        self._suites: Dict[str, BenchmarkSuite] = {}
        self._tasks: Dict[str, BenchmarkTask] = {}
        self._runs: Dict[str, AgentEvalRun] = {}

    def create_suite(self, suite: BenchmarkSuite) -> str:
        """Create a new benchmark suite."""
        self._suites[suite.suite_id] = suite
        return suite.suite_id

    def add_task(self, task: BenchmarkTask) -> str:
        """Add a benchmark task to the registry."""
        self._tasks[task.task_id] = task
        return task.task_id

    def add_task_to_suite(self, suite_id: str, task_id: str) -> None:
        """Link a task to a suite."""
        if suite_id not in self._suites:
            raise ValueError(f"Suite {suite_id} not found")
        if task_id not in self._tasks:
            raise ValueError(f"Task {task_id} not found")
        
        suite = self._suites[suite_id]
        if task_id not in suite.task_ids:
            suite.task_ids.append(task_id)

    def record_run(self, run: AgentEvalRun) -> None:
        """Record an evaluation run result."""
        if run.task_id not in self._tasks:
            raise ValueError(f"Task {run.task_id} not found")
        self._runs[run.run_id] = run

    def score_run(self, run_id: str) -> Dict:
        """Score a run based on success, cost efficiency, latency grade, and safety score."""
        if run_id not in self._runs:
            raise ValueError(f"Run {run_id} not found")
        
        run = self._runs[run_id]
        task = self._tasks[run.task_id]

        cost_eff = 1.0 - (run.cost_usd / task.max_cost_usd) if task.max_cost_usd > 0 else 0.0
        cost_eff = max(0.0, min(1.0, cost_eff))

        latency_grade = 1.0 - (run.latency_seconds / task.timeout_seconds) if task.timeout_seconds > 0 else 0.0
        latency_grade = max(0.0, min(1.0, latency_grade))

        safety_score = 1.0 if run.safety_violations == 0 else max(0.0, 1.0 - 0.2 * run.safety_violations)

        success_score = 1.0 if run.success else 0.0
        composite = 0.4 * success_score + 0.2 * cost_eff + 0.2 * latency_grade + 0.2 * safety_score

        return {
            "success": run.success,
            "cost_efficiency": cost_eff,
            "latency_grade": latency_grade,
            "safety_score": safety_score,
            "composite_score": composite
        }

    def get_agent_scores(self, agent_id: str) -> Dict:
        """Aggregate scores across all tasks for a specific agent."""
        agent_runs = [run for run in self._runs.values() if run.agent_id == agent_id]
        if not agent_runs:
            return {}

        total_runs = len(agent_runs)
        successes = 0
        total_cost_eff = 0.0
        total_lat_grade = 0.0
        total_safety = 0.0
        total_comp = 0.0

        for run in agent_runs:
            scores = self.score_run(run.run_id)
            if scores["success"]:
                successes += 1
            total_cost_eff += scores["cost_efficiency"]
            total_lat_grade += scores["latency_grade"]
            total_safety += scores["safety_score"]
            total_comp += scores["composite_score"]

        return {
            "success_rate": successes / total_runs,
            "avg_cost_efficiency": total_cost_eff / total_runs,
            "avg_latency_grade": total_lat_grade / total_runs,
            "avg_safety_score": total_safety / total_runs,
            "avg_composite_score": total_comp / total_runs,
            "total_runs": total_runs
        }

    def compare_agents(self, agent_ids: List[str]) -> Dict:
        """Head-to-head comparison of multiple agents."""
        return {agent_id: self.get_agent_scores(agent_id) for agent_id in agent_ids}

    def get_suite_results(self, suite_id: str) -> Dict:
        """Get results for all tasks in a suite."""
        if suite_id not in self._suites:
            raise ValueError(f"Suite {suite_id} not found")
        
        suite = self._suites[suite_id]
        results = {}

        for task_id in suite.task_ids:
            task_runs = [r for r in self._runs.values() if r.task_id == task_id]
            task_results = []
            for run in task_runs:
                scores = self.score_run(run.run_id)
                task_results.append({
                    "run_id": run.run_id,
                    "agent_id": run.agent_id,
                    "scores": scores
                })
            results[task_id] = task_results
            
        return results

    def get_leaderboard(self, suite_id: str) -> List[Dict]:
        """Ranked agents by composite score for a specific suite."""
        suite_results = self.get_suite_results(suite_id)
        
        agent_scores: Dict[str, List[float]] = {}
        for task_id, runs in suite_results.items():
            for run in runs:
                agent_id = run["agent_id"]
                comp = run["scores"]["composite_score"]
                agent_scores.setdefault(agent_id, []).append(comp)

        leaderboard = []
        for agent_id, scores in agent_scores.items():
            avg_score = sum(scores) / len(scores) if scores else 0.0
            leaderboard.append({
                "agent_id": agent_id,
                "composite_score": avg_score,
                "tasks_completed": len(scores)
            })

        return sorted(leaderboard, key=lambda x: x["composite_score"], reverse=True)

    def get_task_difficulty_distribution(self, suite_id: str) -> Dict:
        """Get the distribution of tasks by difficulty in a suite."""
        if suite_id not in self._suites:
            raise ValueError(f"Suite {suite_id} not found")
        
        suite = self._suites[suite_id]
        dist = {diff.value: 0 for diff in BenchmarkDifficulty}
        
        for task_id in suite.task_ids:
            if task_id in self._tasks:
                diff = self._tasks[task_id].difficulty
                dist[diff.value] += 1
                
        return dist

    def detect_regressions(self, agent_id: str, baseline_suite_id: str, current_suite_id: str) -> Dict:
        """Find tasks that passed in the baseline suite but failed in the current suite."""
        if baseline_suite_id not in self._suites or current_suite_id not in self._suites:
            raise ValueError("One or both suites not found")
            
        baseline_suite = self._suites[baseline_suite_id]
        current_suite = self._suites[current_suite_id]
        
        baseline_runs = {}
        for r in self._runs.values():
            if r.agent_id == agent_id and r.task_id in baseline_suite.task_ids:
                if r.task_id not in baseline_runs or r.success:
                    baseline_runs[r.task_id] = r
                    
        current_runs = {}
        for r in self._runs.values():
            if r.agent_id == agent_id and r.task_id in current_suite.task_ids:
                if r.task_id not in current_runs or not r.success:
                    current_runs[r.task_id] = r
        
        regressions = []
        for task_id, baseline_run in baseline_runs.items():
            if baseline_run.success and task_id in current_runs:
                current_run = current_runs[task_id]
                if not current_run.success:
                    regressions.append(task_id)
                    
        return {"regressed_tasks": regressions}
