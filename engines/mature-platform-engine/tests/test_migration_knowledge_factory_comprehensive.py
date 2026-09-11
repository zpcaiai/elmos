import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    KnowledgeConfidenceLevel,
    KnowledgeIngestionReceipt,
    KnowledgeItemType,
    MigrationKnowledgeUnit,
)
from elmos_mature_platform.migration_knowledge_factory_engine import MigrationKnowledgeFactoryEngine


class TestMigrationKnowledgeFactoryComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MigrationKnowledgeFactoryEngine()

    def test_ingest_knowledge_unit(self):
        unit = MigrationKnowledgeUnit(
            unit_id="mku-1",
            source_language_or_framework="Java 8",
            target_language_or_framework="Java 21",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Upgrade Spring 2 to Spring Boot 3",
            description="Migrate javax.* to jakarta.* and switch to Boot 3 autoconfig",
            tags=["spring", "boot3", "jakarta"],
        )
        receipt = self.engine.ingest_knowledge_unit(unit, project_ref="proj-alpha")
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.unit_id, "mku-1")
        self.assertEqual(receipt.status, "ingested")
        self.assertEqual(receipt.source_project_ref, "proj-alpha")

    def test_ingest_knowledge_unit_missing_fields(self):
        u1 = MigrationKnowledgeUnit(unit_id="u1", source_language_or_framework="", target_language_or_framework="Java", item_type=KnowledgeItemType.RECIPE_SNIPPET, title="t", description="d")
        with self.assertRaises(ValueError):
            self.engine.ingest_knowledge_unit(u1)

        u2 = MigrationKnowledgeUnit(unit_id="u2", source_language_or_framework="Java", target_language_or_framework="Kotlin", item_type=KnowledgeItemType.RECIPE_SNIPPET, title="", description="d")
        with self.assertRaises(ValueError):
            self.engine.ingest_knowledge_unit(u2)

    def test_promote_confidence_levels(self):
        unit = MigrationKnowledgeUnit(
            unit_id="mku-promote",
            source_language_or_framework="Python 2",
            target_language_or_framework="Python 3",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Print statement migration",
            description="print x -> print(x)",
            confidence_level=KnowledgeConfidenceLevel.EXPERIMENTAL,
        )
        self.engine.ingest_knowledge_unit(unit)

        # Promote to VERIFIED_LOCAL
        p1 = self.engine.promote_confidence("mku-promote", KnowledgeConfidenceLevel.PRODUCTION_PROVEN)
        self.assertEqual(p1.confidence_level, KnowledgeConfidenceLevel.PRODUCTION_PROVEN)

        # Promote to GOLD_CERTIFIED without approver raises PermissionError
        with self.assertRaises(PermissionError):
            self.engine.promote_confidence("mku-promote", KnowledgeConfidenceLevel.GOLD_CERTIFIED, approver="")

        # Promote with approver succeeds
        p2 = self.engine.promote_confidence("mku-promote", KnowledgeConfidenceLevel.GOLD_CERTIFIED, approver="lead-architect")
        self.assertEqual(p2.confidence_level, KnowledgeConfidenceLevel.GOLD_CERTIFIED)

    def test_record_usage(self):
        unit = MigrationKnowledgeUnit(
            unit_id="mku-usage",
            source_language_or_framework="JavaScript",
            target_language_or_framework="TypeScript",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Convert JS module to TS",
            description="Add types",
        )
        self.engine.ingest_knowledge_unit(unit)

        # 1st execution: success
        u1 = self.engine.record_usage("mku-usage", success=True)
        self.assertEqual(u1.usage_count, 1)
        self.assertEqual(u1.success_rate, 1.0)

        # 2nd execution: failure
        u2 = self.engine.record_usage("mku-usage", success=False)
        self.assertEqual(u2.usage_count, 2)
        self.assertEqual(u2.success_rate, 0.5)

    def test_search_knowledge(self):
        u1 = MigrationKnowledgeUnit(
            unit_id="u1",
            source_language_or_framework="C#",
            target_language_or_framework="Go",
            item_type=KnowledgeItemType.SCHEMA_TRANSLATION_MAP,
            title="Entity to Struct",
            description="Map EF entities to Go structs",
            tags=["backend", "orm"],
            confidence_level=KnowledgeConfidenceLevel.PRODUCTION_PROVEN,
        )
        u2 = MigrationKnowledgeUnit(
            unit_id="u2",
            source_language_or_framework="C#",
            target_language_or_framework="Go",
            item_type=KnowledgeItemType.ANTIPATTERN_RULE,
            title="Avoid Goroutine leaks",
            description="Always use context cancellation",
            tags=["concurrency"],
            confidence_level=KnowledgeConfidenceLevel.PRODUCTION_PROVEN,
        )
        self.engine.ingest_knowledge_unit(u1)
        self.engine.ingest_knowledge_unit(u2)

        # Search by source and target
        res = self.engine.search_knowledge("C#", "Go")
        self.assertEqual(len(res), 2)

        # Filter by item_type
        res_anti = self.engine.search_knowledge("C#", "Go", item_type=KnowledgeItemType.ANTIPATTERN_RULE)
        self.assertEqual(len(res_anti), 1)
        self.assertEqual(res_anti[0].unit_id, "u2")

        # Filter by tags
        res_tag = self.engine.search_knowledge("C#", "Go", tags=["orm"])
        self.assertEqual(len(res_tag), 1)
        self.assertEqual(res_tag[0].unit_id, "u1")

    def test_deprecation(self):
        unit = MigrationKnowledgeUnit(
            unit_id="mku-dep",
            source_language_or_framework="Java",
            target_language_or_framework="C#",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Old mapping",
            description="Obsolete transformation",
        )
        self.engine.ingest_knowledge_unit(unit)

        dep = self.engine.deprecate_unit("mku-dep", "Superseded by new Roslyn compiler recipe")
        self.assertEqual(dep.confidence_level, KnowledgeConfidenceLevel.DEPRECATED)
        self.assertTrue(any("deprecated_reason" in t for t in dep.tags))

        # Search should omit deprecated units
        active_results = self.engine.search_knowledge("Java", "C#")
        self.assertNotIn("mku-dep", [u.unit_id for u in active_results])

    def test_get_golden_recipes(self):
        u1 = MigrationKnowledgeUnit(
            unit_id="g1",
            source_language_or_framework="Vue2",
            target_language_or_framework="Vue3",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Options to Composition API",
            description="Vue 2 to Vue 3 migration",
            confidence_level=KnowledgeConfidenceLevel.GOLD_CERTIFIED,
        )
        u2 = MigrationKnowledgeUnit(
            unit_id="g2",
            source_language_or_framework="Vue2",
            target_language_or_framework="Vue3",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Draft Vue recipe",
            description="Experimental Vue transformation",
            confidence_level=KnowledgeConfidenceLevel.EXPERIMENTAL,
        )
        self.engine.ingest_knowledge_unit(u1)
        self.engine.ingest_knowledge_unit(u2)

        goldens = self.engine.get_golden_recipes("Vue2", "Vue3")
        self.assertEqual(len(goldens), 1)
        self.assertEqual(goldens[0].unit_id, "g1")

    def test_get_factory_knowledge_report(self):
        unit = MigrationKnowledgeUnit(
            unit_id="rep-1",
            source_language_or_framework="PHP",
            target_language_or_framework="NodeJS",
            item_type=KnowledgeItemType.RECIPE_SNIPPET,
            title="Laravel to Express",
            description="Convert controllers",
            usage_count=5,
            success_rate=0.8,
        )
        self.engine.ingest_knowledge_unit(unit)
        report = self.engine.get_factory_knowledge_report()
        self.assertEqual(report["total_knowledge_units"], 1)
        self.assertEqual(report["total_applied_usages"], 5)
        self.assertEqual(report["overall_empirical_success_rate"], 0.8)


if __name__ == "__main__":
    unittest.main()
