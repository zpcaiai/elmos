import unittest
from elmos_cli.runner_fleet_scheduler import RunnerFleetScheduler, get_fleet_scheduler, get_fleet_status, RunnerNode

class TestRunnerFleetScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = RunnerFleetScheduler()

    def test_get_fleet_nodes(self):
        nodes = self.scheduler.get_fleet_nodes()
        self.assertEqual(len(nodes), 3)
        self.assertIsInstance(nodes[0], RunnerNode)

    def test_dispatch_task_shards_default(self):
        res = self.scheduler.dispatch_task_shards("test/repo")
        self.assertEqual(res["repo_name"], "test/repo")
        self.assertEqual(res["total_files"], 8)
        self.assertEqual(res["shards_count"], 4)
        self.assertEqual(len(res["allocations"]), 4)

    def test_dispatch_task_shards_custom_files(self):
        files = ["a.java", "b.java", "c.java"]
        res = self.scheduler.dispatch_task_shards("test/repo", files=files, shards_count=2)
        self.assertEqual(res["total_files"], 3)
        self.assertEqual(res["shards_count"], 2)
        self.assertEqual(len(res["allocations"]), 2)
        # Check files are assigned
        assigned = set()
        for alloc in res["allocations"]:
            assigned.update(alloc["files"])
        self.assertEqual(assigned, set(files))

    def test_dispatch_task_shards_no_active_runners(self):
        for r in self.scheduler._mock_fleet:
            r.status = "DRAINING"
        with self.assertRaises(RuntimeError):
            self.scheduler.dispatch_task_shards("test/repo")

    def test_get_fleet_scheduler(self):
        s1 = get_fleet_scheduler()
        s2 = get_fleet_scheduler()
        self.assertIs(s1, s2)
        self.assertIsInstance(s1, RunnerFleetScheduler)

    def test_get_fleet_status(self):
        status = get_fleet_status()
        self.assertEqual(status["status"], "OPERATIONAL")
        self.assertEqual(status["total_nodes"], 3)
        self.assertEqual(status["total_cpu_cores"], 224)
        self.assertEqual(status["total_memory_gb"], 896)
