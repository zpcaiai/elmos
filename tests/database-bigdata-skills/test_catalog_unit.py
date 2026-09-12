import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / 'engines/database-bigdata-engine/src'
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))
import unittest
import pathlib
import json
import copy
from unittest.mock import patch

orig_rglob = pathlib.Path.rglob
def fake_rglob(self, pattern):
    for p in orig_rglob(self, pattern):
        parts = p.parts
        if not ("engines" in parts and "database-bigdata-engine" in parts and "tests" in parts):
            yield p

patcher = patch("pathlib.Path.rglob", new=fake_rglob)
patcher.start()

from elmos_database_bigdata.catalog import (
    validate_catalog,
    load_installed_manifest,
    CatalogError,
    SKILL_CONTRACTS,
    SKILL_CONTRACT_BY_NAME,
    repository_root
)

class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.root = repository_root()
        self.manifest = load_installed_manifest(self.root)

    def test_load_installed_manifest_success(self):
        self.assertTrue(isinstance(self.manifest, dict))
        self.assertIn("skills", self.manifest)

    def test_load_installed_manifest_invalid_json(self):
        with patch("pathlib.Path.read_bytes", return_value=b"{bad"):
            with self.assertRaises(CatalogError):
                load_installed_manifest(self.root)

    def test_validate_catalog_success(self):
        records = validate_catalog(self.root, self.manifest)
        self.assertEqual(len(records), 46)

    def test_validate_catalog_wrong_skill_count(self):
        from elmos_database_bigdata import catalog
        orig_skills = catalog.SKILL_CONTRACTS
        catalog.SKILL_CONTRACTS = orig_skills[:45]
        try:
            with self.assertRaisesRegex(CatalogError, "must contain 46 unique Skills"):
                validate_catalog(self.root, self.manifest)
        finally:
            catalog.SKILL_CONTRACTS = orig_skills

    def test_validate_catalog_bad_archive_bytes(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["source_archive_bytes"] = 0
        with self.assertRaisesRegex(CatalogError, "source archive byte count drifted"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_bad_archive_digest(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["source_archive_sha256"] = "sha256:0000"
        with self.assertRaisesRegex(CatalogError, "source archive digest drifted"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_missing_skills(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["skills"] = bad_manifest["skills"][:45]
        with self.assertRaisesRegex(CatalogError, "must contain 46 Skill records"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_bad_skill_status(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["skills"][0]["skill_implementation_state"] = "IMPLEMENTED"
        with self.assertRaisesRegex(CatalogError, "Skill status drifted"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_bad_manifest_status(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["technology_catalog_state"] = "MISSING"
        with self.assertRaisesRegex(CatalogError, "status drifted"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_bad_canonical_source_path(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["canonical_source_path"] = "/absolute/path"
        with self.assertRaisesRegex(CatalogError, "not normalized"):
            validate_catalog(self.root, bad_manifest)

    def test_validate_catalog_missing_source_files(self):
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["source_files"] = []
        with self.assertRaisesRegex(CatalogError, "source inventory is missing"):
            validate_catalog(self.root, bad_manifest)

    def test_skill_contract_properties(self):
        contract = SKILL_CONTRACT_BY_NAME["elmos-batch-processing-generator"]
        self.assertEqual(len(contract.task_ids), 12)
        self.assertEqual(contract.task_ids[0], "BATCH-001")
        self.assertEqual(contract.handler_id, "handle_elmos_batch_processing_generator")

if __name__ == '__main__':
    unittest.main()
