import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/spring-golden-route-commercial-skills/installed-manifest.json"
RUNTIME_BINDING = (
    ROOT
    / "modules/repair-orchestration/src/main/resources/META-INF/elmos/agent-registry-runtime.json"
)
STEP_BUDGET_RUNTIME_BINDING = (
    ROOT
    / "engines/spring-golden-route-engine/src/elmos_spring_golden_route/agent_step_budget_runtime.json"
)


class DomainRuntimeOverlayTest(unittest.TestCase):
    def test_agent_registry_overlay_is_exact_without_promoting_imported_specs(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        binding = json.loads(RUNTIME_BINDING.read_text(encoding="utf-8"))

        self.assertEqual(196, manifest["skill_count"])
        self.assertEqual(
            {"SPECIFICATION_IMPORTED"},
            {skill["implementation_state"] for skill in manifest["skills"]},
        )
        self.assertEqual(
            {"NOT_RUN"},
            {skill["runtime_evidence_status"] for skill in manifest["skills"]},
        )
        self.assertEqual(
            {"NOT_RUN"},
            {skill["customer_evidence_status"] for skill in manifest["skills"]},
        )
        self.assertEqual(
            {"NOT_RUN"},
            {skill["external_evidence_status"] for skill in manifest["skills"]},
        )
        self.assertEqual(
            {"NOT_CERTIFIED"},
            {skill["certification"] for skill in manifest["skills"]},
        )
        self.assertEqual(
            {False},
            {skill["side_effects_authorized"] for skill in manifest["skills"]},
        )

        imported = next(
            skill
            for skill in manifest["skills"]
            if skill["source_id"] == "FOUNDATION-06-agent-registry"
        )
        self.assertEqual(imported["source_id"], binding["source_id"])
        self.assertEqual(imported["source_name"], binding["skill_name"])
        self.assertEqual(imported["source_sha256"], binding["source_skill_sha256"])
        self.assertEqual(
            imported["source_contract_sha256"], binding["source_contract_sha256"]
        )

        self.assertEqual("LOCAL_RUNTIME_IMPLEMENTED", binding["binding_state"])
        self.assertEqual("NOT_RUN", binding["domain_runtime_evidence_status"])
        self.assertEqual("NOT_RUN", binding["customer_evidence_status"])
        self.assertEqual("NOT_RUN", binding["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", binding["certification"])
        self.assertFalse(binding["side_effects_authorized"])
        self.assertEqual(
            {"audit", "capability", "invoke-selected", "replace-layer", "select", "view"},
            set(binding["supported_operations"]),
        )

    def test_agent_step_budget_overlay_is_exact_and_fail_closed(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        binding = json.loads(STEP_BUDGET_RUNTIME_BINDING.read_text(encoding="utf-8"))
        imported = next(
            skill
            for skill in manifest["skills"]
            if skill["source_id"] == "FOUNDATION-06-agent-step-budget"
        )

        self.assertEqual(imported["source_id"], binding["source_id"])
        self.assertEqual(imported["source_name"], binding["skill_name"])
        self.assertEqual(imported["source_sha256"], binding["source_skill_sha256"])
        self.assertEqual(
            imported["source_contract_sha256"], binding["source_contract_sha256"]
        )
        self.assertEqual("LOCAL_RUNTIME_IMPLEMENTED", binding["binding_state"])
        self.assertEqual("LOCAL_TESTED", binding["domain_runtime_evidence_status"])
        self.assertTrue(binding["authorization_verifier_required"])
        self.assertFalse(binding["side_effects_authorized"])
        self.assertEqual("NOT_RUN", binding["customer_evidence_status"])
        self.assertEqual("NOT_RUN", binding["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", binding["certification"])
        self.assertEqual(
            {"admit", "audit", "cancel", "reserve", "settle", "status"},
            set(binding["supported_operations"]),
        )
        for field in ("request_schema", "response_schema", "error_schema"):
            schema_path = (
                ROOT
                / "engines/spring-golden-route-engine/src"
                / binding[field]
            )
            self.assertTrue(schema_path.is_file(), f"missing {field}: {schema_path}")


if __name__ == "__main__":
    unittest.main()
