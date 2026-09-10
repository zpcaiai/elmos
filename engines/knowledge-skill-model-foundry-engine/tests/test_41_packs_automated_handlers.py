import unittest
from elmos_foundry.automated_handlers.pack_handlers import AutomatedPackHandlerRegistry, get_automated_handler
from elmos_foundry.domain import TenantScope


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

    def test_all_1244_skills_have_handlers(self):
        handlers = self.registry.get_all_handlers()
        self.assertEqual(len(handlers), 1244, f"Expected 1244 handlers, got {len(handlers)}")

    def test_sample_execution_across_packs(self):
        sample_skills = [
            "a2a-agent-discovery-messaging",
            "airflow-dag-modernization",
            "alipay-miniapp-codegen",
            "android-compose-adapter",
            "api-contract-and-client-compatibility",
            "cics-transaction-screen-migration",
            "cobol-language-adapter",
            "dameng-database-adapter",
            "dbt-model-test-documentation",
            "django-adapter",
            "ethercat-profinet-industrial-ethernet",
            "fastapi-python-project-generation",
            "flutter-adapter",
            "go-language-adapter",
            "java-csharp-repository-conversion",
            "kubernetes-workload-manifest-generation",
            "lakehouse-iceberg-delta-hudi-selection",
            "modbus-register-semantic-mapping",
            "oracle-plsql-package-migration",
            "ros2-action-lifecycle-qos",
            "rust-language-adapter",
            "sap-abap-code-data-interface-migration",
            "spring-modernization-golden-route",
            "sql-dialect-parser-and-semantic-ir",
            "swift-language-adapter",
            "typescript-strictness-and-type-recovery",
            "vue-options-composition-api-migration",
            "wechat-miniapp-platform-adapter",
        ]

        for skill_name in sample_skills:
            handler = self.registry.get_handler(skill_name)
            self.assertIsNotNone(handler, f"Handler for {skill_name} should exist")
            res = handler(skill_name, {"test_key": "val"}, self.scope, f"inv-{skill_name[:8]}")
            self.assertEqual(res["status"], "SUCCEEDED")
            self.assertIn("outputs", res)
            self.assertIsInstance(res["outputs"], dict)
            self.assertGreater(len(res["outputs"]), 0)
            self.assertEqual(res["execution_status"], "LOCAL_EXECUTED_SELF_ATTESTED")


if __name__ == "__main__":
    unittest.main()
