import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / 'engines/database-bigdata-engine/src'
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
import unittest
import pathlib
import json
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

from elmos_database_bigdata.bootstrap import (
    BootstrapError,
    VerificationReceipt,
    _verify_repository_runtime,
    initialize_repository_runtime,
    assert_repository_runtime_unchanged,
    manifest_document,
    verify_repository_runtime,
    _tree_digest,
    _parse_manifest,
    _load_manifest,
    DIRECT_IMPORT_ASSURANCE,
    ISOLATED_LAUNCH_ASSURANCE
)

class TestBootstrap(unittest.TestCase):
    def test_verify_repository_runtime_success(self):
        receipt = _verify_repository_runtime(DIRECT_IMPORT_ASSURANCE)
        self.assertIsInstance(receipt, VerificationReceipt)
        self.assertEqual(receipt.launch_assurance, DIRECT_IMPORT_ASSURANCE)

    def test_verify_repository_runtime_invalid_assurance(self):
        with self.assertRaisesRegex(BootstrapError, "invalid"):
            _verify_repository_runtime("BAD_ASSURANCE")

    def test_initialize_repository_runtime(self):
        receipt1 = initialize_repository_runtime()
        receipt2 = initialize_repository_runtime()
        self.assertEqual(receipt1, receipt2)
        
        self.assertEqual(verify_repository_runtime(), receipt1)
        self.assertEqual(assert_repository_runtime_unchanged(), receipt1)

    def test_tree_digest(self):
        files = {
            "a.py": b"print(1)",
            "b/c.py": b"print(2)"
        }
        digest = _tree_digest(files)
        self.assertTrue(digest.startswith("sha256:"))

    def test_parse_manifest_valid(self):
        doc = b'{"a": 1, "b": "test"}'
        res = _parse_manifest(doc)
        self.assertEqual(res, {"a": 1, "b": "test"})

    def test_parse_manifest_invalid_json(self):
        with self.assertRaises(BootstrapError):
            _parse_manifest(b'{bad')

    def test_parse_manifest_duplicate_keys(self):
        with self.assertRaises(BootstrapError):
            _parse_manifest(b'{"a": 1, "a": 2}')

    def test_parse_manifest_unsafe_int(self):
        with self.assertRaises(BootstrapError):
            _parse_manifest(b'{"a": 9007199254740992}') # MAX_SAFE_INTEGER + 1

    def test_parse_manifest_forbidden_number(self):
        with self.assertRaises(BootstrapError):
            _parse_manifest(b'{"a": 1.5}')

    def test_manifest_document(self):
        receipt = _verify_repository_runtime()
        doc = manifest_document(receipt)
        self.assertIsInstance(doc, dict)
        self.assertEqual(doc["namespace"], "elmos-database-bigdata-v1")

    @patch("elmos_database_bigdata.bootstrap._load_manifest")
    def test_verify_repository_runtime_bad_manifest(self, mock_load):
        # Provide a manifest missing required fields
        mock_load.return_value = ({"namespace": "bad"}, b"")
        with self.assertRaisesRegex(BootstrapError, "status drifted"):
            _verify_repository_runtime()

if __name__ == '__main__':
    unittest.main()
