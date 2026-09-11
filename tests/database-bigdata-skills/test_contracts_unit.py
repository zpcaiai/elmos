import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / 'engines/database-bigdata-engine/src'
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
import unittest
import pathlib
from unittest.mock import patch

orig_rglob = pathlib.Path.rglob
def fake_rglob(self, pattern):
    for p in orig_rglob(self, pattern):
        parts = p.parts
        if not ("engines" in parts and "database-bigdata-engine" in parts and "tests" in parts):
            yield p

patcher = patch("pathlib.Path.rglob", new=fake_rglob)
patcher.start()

from elmos_database_bigdata.contracts import (
    require_identifier,
    require_relative_path,
    RuntimeRequest,
    ContractError,
    EXTERNAL_CAPABILITIES,
    REQUEST_SCHEMA,
    denied_external_capabilities,
    _validate_paths,
)

class TestContracts(unittest.TestCase):
    def test_require_identifier_valid(self):
        self.assertEqual(require_identifier("A1_b.c-d:e@f", "test"), "A1_b.c-d:e@f")
        self.assertEqual(require_identifier("a", "test"), "a")

    def test_require_identifier_invalid(self):
        with self.assertRaisesRegex(ContractError, "must match"):
            require_identifier("_a", "test")
        with self.assertRaisesRegex(ContractError, "must match"):
            require_identifier("a" * 129, "test")
        with self.assertRaisesRegex(ContractError, "must match"):
            require_identifier("a b", "test")

    def test_require_relative_path_valid(self):
        self.assertEqual(require_relative_path("a/b", "p"), "a/b")
        self.assertEqual(require_relative_path("a", "p"), "a")

    def test_require_relative_path_invalid(self):
        invalid_paths = [
            "/a", "a/../b", "./a", "a/.", "a//b", "", "a\\b", "a\x00b", ".."
        ]
        for path in invalid_paths:
            with self.assertRaises(ContractError, msg=f"path: {path}"):
                require_relative_path(path, "p")

    def test_validate_paths(self):
        # Should not raise
        _validate_paths({"path": "a/b", "my_directory": "c", "my_paths": ["d", "e"]})
        
        with self.assertRaises(ContractError):
            _validate_paths({"path": "/a/b"})
        
        with self.assertRaises(ContractError):
            _validate_paths({"my_paths": ["a", "/b"]})

        with self.assertRaises(ContractError):
            _validate_paths({"path": 123})

    def test_runtime_request_parse_valid(self):
        doc = {
            "schema_version": REQUEST_SCHEMA,
            "skill": "test-skill",
            "operation": "plan",
            "request_id": "req1",
            "tenant_id": "ten1",
            "project_id": "proj1",
            "actor_id": "act1",
            "idempotency_key": "idemp1",
            "inputs": {"a": 1, "path": "b/c"},
            "external_capabilities": denied_external_capabilities()
        }
        req = RuntimeRequest.parse(doc)
        self.assertEqual(req.skill, "test-skill")
        self.assertEqual(req.inputs, {"a": 1, "path": "b/c"})

    def test_runtime_request_parse_invalid_type(self):
        with self.assertRaises(ContractError):
            RuntimeRequest.parse([])

    def test_runtime_request_parse_missing_keys(self):
        doc = {"schema_version": REQUEST_SCHEMA}
        with self.assertRaisesRegex(ContractError, "missing="):
            RuntimeRequest.parse(doc)

    def test_runtime_request_parse_extra_keys(self):
        doc = {
            "schema_version": REQUEST_SCHEMA,
            "skill": "test-skill",
            "operation": "plan",
            "request_id": "req1",
            "tenant_id": "ten1",
            "project_id": "proj1",
            "actor_id": "act1",
            "idempotency_key": "idemp1",
            "inputs": {},
            "external_capabilities": denied_external_capabilities(),
            "extra": 1
        }
        with self.assertRaisesRegex(ContractError, "extra="):
            RuntimeRequest.parse(doc)

    def test_runtime_request_parse_invalid_schema(self):
        doc = self._valid_doc()
        doc["schema_version"] = "bad"
        with self.assertRaisesRegex(ContractError, "schema_version"):
            RuntimeRequest.parse(doc)

    def test_runtime_request_parse_invalid_operation(self):
        doc = self._valid_doc()
        doc["operation"] = "run"
        with self.assertRaisesRegex(ContractError, "operation must be plan"):
            RuntimeRequest.parse(doc)

    def test_runtime_request_parse_invalid_capabilities(self):
        doc = self._valid_doc()
        doc["external_capabilities"] = {"database": True}
        with self.assertRaisesRegex(ContractError, "exact deny-list"):
            RuntimeRequest.parse(doc)
            
        doc["external_capabilities"] = denied_external_capabilities()
        doc["external_capabilities"]["database"] = True
        with self.assertRaisesRegex(ContractError, "disabled"):
            RuntimeRequest.parse(doc)

    def test_runtime_request_parse_invalid_inputs(self):
        doc = self._valid_doc()
        doc["inputs"] = []
        with self.assertRaisesRegex(ContractError, "inputs must be an object"):
            RuntimeRequest.parse(doc)

    def test_runtime_request_binding_digest(self):
        doc = self._valid_doc()
        req = RuntimeRequest.parse(doc)
        self.assertTrue(req.binding_digest().startswith("sha256:"))

    def _valid_doc(self):
        return {
            "schema_version": REQUEST_SCHEMA,
            "skill": "test-skill",
            "operation": "plan",
            "request_id": "req1",
            "tenant_id": "ten1",
            "project_id": "proj1",
            "actor_id": "act1",
            "idempotency_key": "idemp1",
            "inputs": {},
            "external_capabilities": denied_external_capabilities()
        }

if __name__ == '__main__':
    unittest.main()
