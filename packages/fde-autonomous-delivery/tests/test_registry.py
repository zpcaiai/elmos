"""Unit tests for FDE registry integrity and topological order."""

from __future__ import annotations

import unittest

from elmos_fde_delivery.registry import (
    ARCHIVE_SHA256,
    DEPENDENCIES,
    PACK_BY_SKILL,
    PACKAGE_NAME,
    PACKAGE_VERSION,
    SKILL_BINDINGS,
    TOPOLOGICAL_ORDER,
    WORKFLOW_SKILLS,
    EffectClass,
    describe_registry,
    topological_order,
)


class TestFdeRegistry(unittest.TestCase):
    def test_metadata_constants(self) -> None:
        self.assertEqual(
            PACKAGE_NAME,
            "elmos-fde-autonomous-delivery-repository-refactoring-skills",
        )
        self.assertEqual(PACKAGE_VERSION, "5.2.0")
        self.assertEqual(
            ARCHIVE_SHA256,
            "4dbd6f20b0d27dbacf12ed432f0486f9e59151c2b138c6e7d8a9f60f395b1428",
        )

    def test_cardinality(self) -> None:
        self.assertEqual(len(SKILL_BINDINGS), 45)
        self.assertEqual(len(DEPENDENCIES), 45)
        self.assertEqual(len(PACK_BY_SKILL), 45)
        self.assertEqual(len(WORKFLOW_SKILLS), 12)
        self.assertEqual(len(TOPOLOGICAL_ORDER), 45)

    def test_topological_order_validity(self) -> None:
        order = topological_order()
        self.assertEqual(len(order), 45)
        seen: set[str] = set()
        for skill_id in order:
            deps = DEPENDENCIES[skill_id]
            for dep in deps:
                self.assertIn(dep, seen, f"Dependency {dep} must precede {skill_id}")
            seen.add(skill_id)

    def test_effect_classes(self) -> None:
        read_only_count = 0
        ws_mutation_count = 0
        ext_effect_count = 0
        for binding in SKILL_BINDINGS.values():
            self.assertIsInstance(binding.effect_class, EffectClass)
            if binding.effect_class == EffectClass.READ_ONLY:
                read_only_count += 1
            elif binding.effect_class == EffectClass.PREPARE_WORKSPACE_MUTATION:
                ws_mutation_count += 1
            elif binding.effect_class == EffectClass.PREPARE_EXTERNAL_EFFECT:
                ext_effect_count += 1
        self.assertGreater(read_only_count, 0)
        self.assertGreater(ws_mutation_count, 0)
        self.assertGreater(ext_effect_count, 0)
        self.assertEqual(
            read_only_count + ws_mutation_count + ext_effect_count, 45
        )

    def test_describe_registry(self) -> None:
        desc = describe_registry()
        self.assertEqual(desc["package"], PACKAGE_NAME)
        self.assertEqual(desc["version"], PACKAGE_VERSION)
        self.assertEqual(desc["atomic_skill_count"], 45)
        self.assertEqual(desc["workflow_skill_count"], 12)
        self.assertEqual(len(desc["skills"]), 45)  # type: ignore
