import sys
class MockYaml:
    @staticmethod
    def safe_load(x): return {"tenant_id": "yaml-tenant", "fuzz_cases": 50}
    @staticmethod
    def dump(x, **kwargs): return "tenant_id: save-test-yaml\nbudget_limit_usd: 200.0\n"

sys.modules['yaml'] = MockYaml

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from elmos_cli.config import DEFAULT_CONFIG, find_config_file, load_config, save_config

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_find_config_file_json(self):
        config_path = self.cwd / ".elmosrc.json"
        config_path.write_text("{}")
        found = find_config_file(cwd=self.cwd)
        self.assertEqual(found, config_path)

    def test_find_config_file_yaml(self):
        config_path = self.cwd / ".elmosrc.yaml"
        config_path.write_text("tenant_id: test")
        found = find_config_file(cwd=self.cwd)
        self.assertEqual(found, config_path)

    def test_find_config_file_not_found(self):
        with patch("pathlib.Path.home", return_value=self.cwd):
            found = find_config_file(cwd=self.cwd)
            self.assertIsNone(found)

    def test_load_config_default(self):
        with patch("elmos_cli.config.find_config_file", return_value=None):
            cfg = load_config()
            self.assertEqual(cfg, DEFAULT_CONFIG)

    def test_load_config_json(self):
        config_path = self.cwd / ".elmosrc.json"
        config_path.write_text('{"tenant_id": "test-tenant", "fuzz_cases": 100}')
        cfg = load_config(config_path)
        self.assertEqual(cfg["tenant_id"], "test-tenant")
        self.assertEqual(cfg["fuzz_cases"], 100)
        self.assertEqual(cfg["default_src_lang"], DEFAULT_CONFIG["default_src_lang"])

    def test_load_config_yaml(self):
        config_path = self.cwd / ".elmosrc.yaml"
        config_path.write_text('tenant_id: yaml-tenant\nfuzz_cases: 50\n')
        cfg = load_config(config_path)
        self.assertEqual(cfg["tenant_id"], "yaml-tenant")
        self.assertEqual(cfg["fuzz_cases"], 50)
        self.assertEqual(cfg["default_src_lang"], DEFAULT_CONFIG["default_src_lang"])

    def test_load_config_invalid_json(self):
        config_path = self.cwd / ".elmosrc.json"
        config_path.write_text('{invalid_json')
        cfg = load_config(config_path)
        self.assertEqual(cfg, DEFAULT_CONFIG)

    def test_save_config_json(self):
        config_path = self.cwd / ".elmosrc.json"
        cfg = {"tenant_id": "save-test", "budget_limit_usd": 100.0}
        save_config(cfg, config_path)
        self.assertTrue(config_path.is_file())
        saved = json.loads(config_path.read_text())
        self.assertEqual(saved, cfg)

    def test_save_config_yaml(self):
        config_path = self.cwd / ".elmosrc.yaml"
        cfg = {"tenant_id": "save-test-yaml", "budget_limit_usd": 200.0}
        save_config(cfg, config_path)
        self.assertTrue(config_path.is_file())
        text = config_path.read_text()
        self.assertIn("tenant_id: save-test-yaml", text)
        self.assertIn("budget_limit_usd: 200.0", text)
        
    def test_save_config_creates_parents(self):
        config_path = self.cwd / "deep" / "dir" / "config.json"
        cfg = {"test": 1}
        save_config(cfg, config_path)
        self.assertTrue(config_path.is_file())
