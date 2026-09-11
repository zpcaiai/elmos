import unittest
from elmos_mature_platform.migration_entity_relations_engine import (
    MigrationEntityRelationsEngine,
)
from elmos_mature_platform.types import (
    EntityRelationType,
    MigrationEntity,
    MigrationEntityType,
)


class TestMigrationEntityRelationsComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MigrationEntityRelationsEngine()

    def test_register_entity_and_retrieval(self):
        proj = MigrationEntity(
            entity_id="proj-alpha",
            entity_type=MigrationEntityType.PROJECT,
            name="Legacy-Billing-System",
            version_ref="1.0.0",
        )
        eid = self.engine.register_entity(proj)
        self.assertEqual(eid, "proj-alpha")

        retrieved = self.engine.get_entity("proj-alpha")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Legacy-Billing-System")

    def test_connect_entities_and_edge_validation(self):
        e1 = MigrationEntity(
            entity_id="mod-1", entity_type=MigrationEntityType.SOURCE_MODULE, name="InvoiceService.java"
        )
        e2 = MigrationEntity(
            entity_id="rule-1", entity_type=MigrationEntityType.TRANSFORMATION_RULE, name="SpringToAspnetRule"
        )
        self.engine.register_entity(e1)
        self.engine.register_entity(e2)

        edge_id = self.engine.connect_entities(
            "mod-1", "rule-1", EntityRelationType.TRANSFORMED_BY, confidence=0.98
        )
        self.assertTrue(bool(edge_id))

        with self.assertRaises(ValueError):
            self.engine.connect_entities("non-existent", "rule-1", EntityRelationType.DEPENDS_ON)

    def test_trace_patch_provenance_complete(self):
        # Build chain: Project -> Module -> Rule -> Patch -> Evidence
        proj = MigrationEntity("p-1", MigrationEntityType.PROJECT, "OldApp")
        mod = MigrationEntity("m-1", MigrationEntityType.SOURCE_MODULE, "OldModule")
        rule = MigrationEntity("r-1", MigrationEntityType.TRANSFORMATION_RULE, "RuleA")
        patch = MigrationEntity("pt-1", MigrationEntityType.GENERATED_PATCH, "PatchA.diff")
        ev = MigrationEntity("ev-1", MigrationEntityType.VERIFICATION_EVIDENCE, "JUnitReceipt")

        for e in [proj, mod, rule, patch, ev]:
            self.engine.register_entity(e)

        self.engine.connect_entities("p-1", "m-1", EntityRelationType.EXTRACTED_FROM)
        self.engine.connect_entities("m-1", "r-1", EntityRelationType.TRANSFORMED_BY)
        self.engine.connect_entities("r-1", "pt-1", EntityRelationType.PRODUCED_PATCH)
        self.engine.connect_entities("pt-1", "ev-1", EntityRelationType.VERIFIED_BY)

        trace = self.engine.trace_patch_provenance("pt-1")
        self.assertTrue(trace.complete)
        self.assertFalse(trace.has_unverified_patch)
        self.assertIn("p-1", trace.lineage_path)

    def test_find_verifications_for_patch(self):
        patch = MigrationEntity("patch-1", MigrationEntityType.GENERATED_PATCH, "Diff1")
        ev1 = MigrationEntity("ev-1", MigrationEntityType.VERIFICATION_EVIDENCE, "E1")
        ev2 = MigrationEntity("ev-2", MigrationEntityType.VERIFICATION_EVIDENCE, "E2")
        self.engine.register_entity(patch)
        self.engine.register_entity(ev1)
        self.engine.register_entity(ev2)

        self.engine.connect_entities("patch-1", "ev-1", EntityRelationType.VERIFIED_BY)
        self.engine.connect_entities("patch-1", "ev-2", EntityRelationType.VERIFIED_BY)

        verifs = self.engine.find_verifications_for_patch("patch-1")
        self.assertEqual(len(verifs), 2)
        names = [v.name for v in verifs]
        self.assertIn("E1", names)
        self.assertIn("E2", names)

    def test_find_affected_patches_by_rule(self):
        rule = MigrationEntity("rule-x", MigrationEntityType.TRANSFORMATION_RULE, "Rx")
        p1 = MigrationEntity("p-1", MigrationEntityType.GENERATED_PATCH, "P1")
        p2 = MigrationEntity("p-2", MigrationEntityType.GENERATED_PATCH, "P2")
        for e in [rule, p1, p2]:
            self.engine.register_entity(e)

        self.engine.connect_entities("rule-x", "p-1", EntityRelationType.PRODUCED_PATCH)
        self.engine.connect_entities("rule-x", "p-2", EntityRelationType.PRODUCED_PATCH)

        affected = self.engine.find_affected_patches_by_rule("rule-x")
        self.assertEqual(len(affected), 2)

    def test_invalidate_rule_and_descendants(self):
        rule = MigrationEntity("rule-bad", MigrationEntityType.TRANSFORMATION_RULE, "BadRule")
        p1 = MigrationEntity("p-bad-1", MigrationEntityType.GENERATED_PATCH, "PBad1")
        self.engine.register_entity(rule)
        self.engine.register_entity(p1)
        self.engine.connect_entities("rule-bad", "p-bad-1", EntityRelationType.PRODUCED_PATCH)

        invalidated = self.engine.invalidate_rule_and_descendants("rule-bad", "Security vulnerability discovered")
        self.assertIn("rule-bad", invalidated)
        self.assertIn("p-bad-1", invalidated)

    def test_detect_orphan_entities(self):
        orphan = MigrationEntity("orphan-1", MigrationEntityType.HOLD_OUT_TEST, "OrphanTest")
        connected = MigrationEntity("conn-1", MigrationEntityType.PROJECT, "ConnectedProject")
        self.engine.register_entity(orphan)
        self.engine.register_entity(connected)

        p = MigrationEntity("p-child", MigrationEntityType.SOURCE_MODULE, "ChildModule")
        self.engine.register_entity(p)
        self.engine.connect_entities("conn-1", "p-child", EntityRelationType.EXTRACTED_FROM)

        orphans = self.engine.detect_orphan_entities()
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0].entity_id, "orphan-1")

    def test_get_entity_graph_density_and_closed_provenance(self):
        proj = MigrationEntity("proj-c", MigrationEntityType.PROJECT, "ClosedProj")
        patch = MigrationEntity("patch-c", MigrationEntityType.GENERATED_PATCH, "ClosedPatch")
        ev = MigrationEntity("ev-c", MigrationEntityType.VERIFICATION_EVIDENCE, "ClosedEv")
        for e in [proj, patch, ev]:
            self.engine.register_entity(e)

        self.engine.connect_entities("proj-c", "patch-c", EntityRelationType.PRODUCED_PATCH)
        # Not verified yet -> verify_closed_provenance is False
        self.assertFalse(self.engine.verify_closed_provenance("proj-c"))

        # Add verification -> verify_closed_provenance becomes True
        self.engine.connect_entities("patch-c", "ev-c", EntityRelationType.VERIFIED_BY)
        self.assertTrue(self.engine.verify_closed_provenance("proj-c"))

        density = self.engine.get_entity_graph_density()
        self.assertEqual(density["total_entities"], 3)
        self.assertEqual(density["total_edges"], 2)
        self.assertGreater(density["average_degree"], 0.0)


if __name__ == "__main__":
    unittest.main()
