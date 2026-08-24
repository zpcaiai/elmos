from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_openapi_core_paths(self) -> None:
        api = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text(encoding="utf-8"))
        self.assertTrue(str(api["openapi"]).startswith("3."))
        paths = api["paths"]
        for path in [
            "/tasks",
            "/tasks/{taskId}",
            "/tasks/{taskId}/pause",
            "/tasks/{taskId}/resume",
            "/tasks/{taskId}/cancel",
            "/tasks/{taskId}/events",
            "/tasks/{taskId}/financial-summary",
        ]:
            self.assertIn(path, paths)

    def test_asyncapi_channels(self) -> None:
        api = yaml.safe_load((ROOT / "events" / "asyncapi.yaml").read_text(encoding="utf-8"))
        self.assertEqual("2.6.0", api["asyncapi"])
        self.assertGreaterEqual(len(api["channels"]), 7)

    def test_sql_contains_concurrency_and_finops_contracts(self) -> None:
        sql = "\n".join(path.read_text(encoding="utf-8") for path in sorted((ROOT / "sql").glob("V*.sql"))).lower()
        for marker in [
            "slot_no between 1 and 3",
            "for update skip locked",
            "create table task_checkpoint",
            "create table task_side_effect_receipt",
            "create table usage_event",
            "create table revenue_entry",
            "force row level security",
            "task_profitability_v",
        ]:
            self.assertIn(marker, sql)


if __name__ == "__main__":
    unittest.main()
