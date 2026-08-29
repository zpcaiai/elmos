"""Unit tests for Distributed Multi-Tenant Private Runner Fleet Scheduler."""

from __future__ import annotations

import io
import json
import sys
import unittest

from elmos_cli.runner_fleet_scheduler import (
    RunnerFleetScheduler,
    get_fleet_scheduler,
    get_fleet_status,
)
from elmos_cli.dispatcher import main


class RunnerFleetSchedulerTests(unittest.TestCase):
    """Test runner node discovery, health aggregation, and consistent task sharding."""

    def setUp(self) -> None:
        self.scheduler = get_fleet_scheduler()

    def test_fleet_discovery(self) -> None:
        nodes = self.scheduler.get_fleet_nodes()
        self.assertGreaterEqual(len(nodes), 3)
        regions = [n.region for n in nodes]
        self.assertIn("cn-beijing", regions)
        self.assertIn("us-east-1", regions)

        status = get_fleet_status()
        self.assertEqual(status["status"], "OPERATIONAL")
        self.assertGreater(status["total_cpu_cores"], 100)
        self.assertGreater(status["total_memory_gb"], 500)

    def test_dispatch_task_shards(self) -> None:
        res = self.scheduler.dispatch_task_shards(
            repo_name="acme/monorepo",
            shards_count=4,
        )
        self.assertEqual(res["repo_name"], "acme/monorepo")
        self.assertEqual(res["shards_count"], 4)
        self.assertEqual(len(res["allocations"]), 4)
        for alloc in res["allocations"]:
            self.assertIn("assigned_runner", alloc)
            self.assertIn("shard_digest", alloc)

    def test_cli_runner_subcommands(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["runner", "fleet-status", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertEqual(data["status"], "OPERATIONAL")
            self.assertEqual(data["total_nodes"], 3)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
