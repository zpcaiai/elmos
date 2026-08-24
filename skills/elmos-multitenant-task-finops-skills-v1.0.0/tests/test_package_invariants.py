from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


class PackageInvariantTests(unittest.TestCase):
    def test_manifest_counts_and_hard_limit(self):
        manifest = json.loads((ROOT / "skill-manifest.json").read_text())
        self.assertEqual(12, manifest["total_skills"])
        self.assertEqual(144, manifest["total_tasks"])
        self.assertEqual(3, manifest["hard_requirements"]["account_active_root_task_limit"])

    def test_task_matrix_is_complete_and_unique(self):
        with (ROOT / "docs" / "TASK-MATRIX.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        ids = [row["task_id"] for row in rows]
        self.assertEqual(144, len(ids))
        self.assertEqual(144, len(set(ids)))
        self.assertTrue(all(row["evidence_required"] == "true" for row in rows))

    def test_exactly_twelve_skill_directories(self):
        skills = [p for p in (ROOT / ".agents" / "skills").iterdir() if p.is_dir()]
        self.assertEqual(12, len(skills))
        self.assertTrue(all((p / "SKILL.md").is_file() for p in skills))

    def test_json_schemas_are_draft_2020_12(self):
        schemas = list((ROOT / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 13)
        for path in schemas:
            schema = json.loads(path.read_text())
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            Draft202012Validator.check_schema(schema)

    def test_openapi_and_asyncapi_versions(self):
        openapi = yaml.safe_load((ROOT / "api" / "openapi.yaml").read_text())
        asyncapi = yaml.safe_load((ROOT / "events" / "asyncapi.yaml").read_text())
        self.assertEqual("3.1.0", openapi["openapi"])
        self.assertEqual("2.6.0", asyncapi["asyncapi"])

    def test_sql_expresses_three_slots_and_forced_rls(self):
        sql = "\n".join(p.read_text() for p in sorted((ROOT / "sql").glob("V*.sql"))).lower()
        self.assertIn("slot_no between 1 and 3", sql)
        self.assertIn("generate_series(1, 3)", sql)
        self.assertIn("for update skip locked", sql)
        self.assertIn("force row level security", sql)
        self.assertIn("lease_generation", sql)

    def test_financial_dimensions_are_separate(self):
        schema = (ROOT / "sql" / "V100__multitenant_task_finops.sql").read_text().lower()
        for term in ("usage_event", "revenue_entry", "inbox_event_dedup", "recognized_revenue", "collected_cash", "gross_profit"):
            self.assertIn(term, schema)


if __name__ == "__main__":
    unittest.main()
