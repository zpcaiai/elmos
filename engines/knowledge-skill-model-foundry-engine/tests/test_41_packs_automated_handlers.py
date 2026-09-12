import unittest
from elmos_foundry.automated_handlers.pack_handlers import AutomatedPackHandlerRegistry
from elmos_foundry.domain import TenantScope
from elmos_foundry.native_semantics import load_native_programs


class Test41PacksAutomatedHandlers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = AutomatedPackHandlerRegistry()
        cls.scope = TenantScope(
            tenant_id="tenant-test",
            project_id="project-test",
            actor_id="actor-test",
            environment_id="env-test",
            purpose="unit-test",
        )
        cls.programs = load_native_programs()

    def test_all_1244_skills_have_handlers(self):
        handlers = self.registry.get_all_handlers()
        self.assertEqual(len(handlers), 1244, f"Expected 1244 handlers, got {len(handlers)}")

    def test_sample_execution_across_all_packs(self):
        by_pack = {}
        for name, p in self.programs.items():
            pk = p.document.get('pack')
            if pk and pk not in by_pack:
                by_pack[pk] = name

        self.assertGreaterEqual(len(by_pack), 40, f"Expected at least 40 packs, found {len(by_pack)}")

        for pack_name, skill_name in by_pack.items():
            handler = self.registry.get_handler(skill_name)
            self.assertIsNotNone(handler, f"Handler for {skill_name} in pack {pack_name} should exist")
            res = handler(skill_name, {"test_key": "val"}, self.scope, f"inv-{skill_name[:8]}")
            self.assertEqual(res["status"], "SUCCEEDED", f"Execution failed for {skill_name}: {res}")
            self.assertIn("outputs", res)
            self.assertIsInstance(res["outputs"], dict)
            self.assertGreater(len(res["outputs"]), 0)
            self.assertEqual(res["execution_status"], "LOCAL_EXECUTED_SELF_ATTESTED")
            self.assertEqual(res["pack"], pack_name)


if __name__ == "__main__":
    unittest.main()
