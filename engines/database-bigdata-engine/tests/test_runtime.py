import unittest
import pathlib
import copy
from unittest.mock import patch, MagicMock

orig_rglob = pathlib.Path.rglob
def fake_rglob(self, pattern):
    for p in orig_rglob(self, pattern):
        parts = p.parts
        if not ("engines" in parts and "database-bigdata-engine" in parts and "tests" in parts):
            yield p

patcher = patch("pathlib.Path.rglob", new=fake_rglob)
patcher.start()

from elmos_database_bigdata.runtime import (
    dispatch_skill,
    execute_skill,
    capability_manifest,
    RuntimeError as ElmosRuntimeError,
    SKILL_REGISTRY,
    _validate_authoritative_result
)
from elmos_database_bigdata.contracts import (
    REQUEST_SCHEMA,
    RESULT_SCHEMA,
    denied_external_capabilities,
    ContractError
)

class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.skill = "elmos-batch-processing-generator"
        self.valid_doc = {
            "schema_version": REQUEST_SCHEMA,
            "skill": self.skill,
            "operation": "plan",
            "request_id": "req-1",
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "actor_id": "actor-1",
            "idempotency_key": "idemp-1",
            "inputs": {},
            "external_capabilities": denied_external_capabilities()
        }

    def test_execute_skill_success(self):
        result = execute_skill(self.valid_doc)
        self.assertEqual(result["schema_version"], RESULT_SCHEMA)
        self.assertEqual(result["skill"], self.skill)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("provenance", result)
        self.assertIn("artifacts", result)

    def test_execute_skill_unknown(self):
        doc = copy.deepcopy(self.valid_doc)
        doc["skill"] = "unknown-skill"
        with self.assertRaisesRegex(ElmosRuntimeError, "unknown database/Big Data Skill"):
            execute_skill(doc)

    def test_dispatch_skill_mismatch(self):
        with self.assertRaisesRegex(ContractError, "must be identical"):
            dispatch_skill("another-skill", self.valid_doc)

    def test_dispatch_skill_success(self):
        result = dispatch_skill(self.skill, self.valid_doc)
        self.assertEqual(result["schema_version"], RESULT_SCHEMA)

    def test_capability_manifest(self):
        manifest = capability_manifest()
        self.assertEqual(manifest["schema_version"], "elmos.database-bigdata.capabilities.v1")
        self.assertEqual(manifest["skill_count"], 46)
        self.assertEqual(manifest["stable_task_id_count"], 554)
        self.assertEqual(len(manifest["capabilities"]), 46)
        self.assertIn("manifest_digest", manifest)

    def test_validate_authoritative_result_success(self):
        result = {
            "state": "BLOCKED",
            "code": "DECLARED_SKILL_PLAN_SKELETON",
            "planning_state": "SKELETON_ONLY",
            "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
            "external_effects_performed": False,
            "skill_implementation_state": "DECLARED",
            "repository_handler_runtime_evidence": "NOT_RUN",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
        }
        _validate_authoritative_result(result)  # should not raise

    def test_validate_authoritative_result_fail(self):
        result = {
            "state": "RUNNING",  # invalid
            "code": "DECLARED_SKILL_PLAN_SKELETON",
            "planning_state": "SKELETON_ONLY",
            "context_assurance": "CALLER_ASSERTED_UNVERIFIED",
            "external_effects_performed": False,
            "skill_implementation_state": "DECLARED",
            "repository_handler_runtime_evidence": "NOT_RUN",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
        }
        with self.assertRaisesRegex(ElmosRuntimeError, "authoritative result postcondition failed"):
            _validate_authoritative_result(result)

if __name__ == '__main__':
    unittest.main()
