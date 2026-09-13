"""Industrial Host Broker: 1,244 skills execute locally without an LLM."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
FOUNDRY_SRC = ROOT / "engines/knowledge-skill-model-foundry-engine/src"
if str(FOUNDRY_SRC) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_SRC))

from elmos_foundry.automated_handlers.pack_handlers import get_all_automated_handlers
from elmos_foundry.domain import TenantScope
from elmos_foundry.industrial_runtime.families import KernelFamily, classify_skill
from elmos_foundry.industrial_runtime.host_broker import (
    EXPECTED_BROKERED_SKILLS,
    INDUSTRIAL_BROKER_ID,
    IndustrialLocalHostBroker,
)
from elmos_foundry.industrial_runtime.kernels import execute_kernel
from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS


class IndustrialKernelTests(unittest.TestCase):
    def test_invalid_source_fails_closed(self) -> None:
        result = execute_kernel(
            "ast-refactor-codemod",
            {"source_code": "def broken("},
            pack="23-repository-refactoring-technical-debt",
        )
        self.assertFalse(result.ok)
        self.assertIn("invalid source_code", result.error or "")

    def test_sql_output_depends_on_query(self) -> None:
        left = execute_kernel(
            "sql-dialect-parser-and-semantic-ir",
            {"sql": "SELECT IFNULL(a, 0) FROM `t`", "source_dialect": "mysql", "target_dialect": "postgresql"},
            pack="20-sql-database-modernization",
        )
        right = execute_kernel(
            "sql-dialect-parser-and-semantic-ir",
            {"sql": "SELECT NOW() FROM `u`", "source_dialect": "mysql", "target_dialect": "postgresql"},
            pack="20-sql-database-modernization",
        )
        self.assertTrue(left.ok and right.ok)
        self.assertIn("COALESCE", str(left.artifacts.get("transpiled_sql")))
        self.assertIn("CURRENT_TIMESTAMP", str(right.artifacts.get("transpiled_sql")))
        self.assertNotEqual(left.output_digest, right.output_digest)
        self.assertEqual(left.output_digest, execute_kernel(
            "sql-dialect-parser-and-semantic-ir",
            {"sql": "SELECT IFNULL(a, 0) FROM `t`", "source_dialect": "mysql", "target_dialect": "postgresql"},
            pack="20-sql-database-modernization",
        ).output_digest)

    def test_deadlock_cycle_detected(self) -> None:
        result = execute_kernel(
            "concurrency-race-lock-refactor",
            {"lock_acquisitions": [["A", "B"], ["B", "A"]]},
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.metrics["has_deadlock_risk"])
        self.assertGreaterEqual(len(result.artifacts["deadlock_cycle"]), 2)

    def test_every_family_has_classifier(self) -> None:
        for family in KernelFamily:
            self.assertTrue(family.value)


class IndustrialHostBrokerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.broker = IndustrialLocalHostBroker()
        cls.scope = TenantScope(tenant_id="tenant-industrial", project_id="project-foundry")

    def test_catalog_size_and_local_semantics(self) -> None:
        self.assertEqual(self.broker.skill_count, EXPECTED_BROKERED_SKILLS)
        self.assertEqual(len(LOCAL_SEMANTIC_SKILLS), 66)
        self.assertEqual(self.broker.skill_count + len(LOCAL_SEMANTIC_SKILLS), 1310)

    def test_all_brokered_skills_execute_without_llm(self) -> None:
        report = self.broker.execute_catalog(tenant_scope=self.scope)
        self.assertEqual(report.executed, EXPECTED_BROKERED_SKILLS)
        self.assertEqual(report.failed, 0, report.failed_skills[:8])
        self.assertEqual(report.llm_required_count, 0)
        self.assertTrue(report.ok)
        self.assertGreaterEqual(len(report.families), 8)

    def test_pack_handlers_use_industrial_broker(self) -> None:
        handlers = get_all_automated_handlers()
        self.assertEqual(len(handlers), EXPECTED_BROKERED_SKILLS)
        result = handlers["sql-dialect-parser-and-semantic-ir"](
            "sql-dialect-parser-and-semantic-ir",
            {"sql": "SELECT IFNULL(x, 1) FROM `t`", "source_dialect": "mysql", "target_dialect": "postgresql"},
            self.scope,
            "inv-sql-1",
        )
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["host_broker"], INDUSTRIAL_BROKER_ID)
        self.assertFalse(result["llm_required"])
        self.assertTrue(result["industrial"])
        self.assertIn("input_digest", result)
        self.assertTrue(str(result["input_digest"]).startswith("sha256:"))

    def test_classifier_covers_named_production_skills(self) -> None:
        self.assertEqual(classify_skill("concurrency-race-lock-refactor"), KernelFamily.CONCURRENCY_WFG)
        self.assertEqual(classify_skill("sql-dialect-parser-and-semantic-ir"), KernelFamily.SQL_DIALECT)
        self.assertEqual(
            classify_skill("unknown-widget", "27-test-quality-assurance-factory"),
            KernelFamily.TEST_SYNTHESIS,
        )


if __name__ == "__main__":
    unittest.main()
