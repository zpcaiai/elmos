import sys
from unittest.mock import MagicMock, patch

class MockGenerate:
    @staticmethod
    def generate_lean4_proof(*args, **kwargs):
        raise Exception("mocked")

class MockBridge:
    generate_lean4_proof = MockGenerate.generate_lean4_proof

class MockAssurance:
    lean_dafny_bridge = MockBridge

sys.modules['elmos_formal_assurance'] = MockAssurance
sys.modules['elmos_formal_assurance.lean_dafny_bridge'] = MockBridge

import unittest
from elmos_cli.composite_pipeline import derive_action_key, run_composite_pipeline, _ACTION_CACHE_STORE

class TestCompositePipeline(unittest.TestCase):
    def setUp(self):
        _ACTION_CACHE_STORE.clear()
        if 'elmos_formal_assurance.lean_dafny_bridge' in sys.modules:
            sys.modules['elmos_formal_assurance.lean_dafny_bridge'].generate_lean4_proof = MagicMock(side_effect=Exception("mocked"))

    def test_derive_action_key(self):
        key1 = derive_action_key("java", "csharp", "code1", {"opt1": 1})
        key2 = derive_action_key("java", "csharp", "code1", {"opt1": 1})
        key3 = derive_action_key("java", "python", "code1", {"opt1": 1})
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)

    def test_run_composite_pipeline_budget_exhausted(self):
        result = run_composite_pipeline(options={"budget_limit_usd": 0.0})
        self.assertEqual(result["status"], "BUDGET_EXHAUSTED")
        self.assertIn("reason", result)

    def test_run_composite_pipeline_budget_exhausted_kwargs(self):
        result = run_composite_pipeline(budget_limit_usd=0.0)
        self.assertEqual(result["status"], "BUDGET_EXHAUSTED")

    def test_run_composite_pipeline_success(self):
        result = run_composite_pipeline(
            src_lang="java",
            tgt_lang="csharp",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": False}
        )
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIn("total_duration_ms", result)
        self.assertIn("transformed_code", result)
        self.assertIn("public class Modernized", result["transformed_code"])
        self.assertEqual(result["formal_assurance"]["status"], "SAT_PROVED")

    def test_run_composite_pipeline_cache(self):
        result1 = run_composite_pipeline(
            src_lang="java",
            tgt_lang="python",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": True}
        )
        self.assertEqual(result1["cache_hit"], False)

        result2 = run_composite_pipeline(
            src_lang="java",
            tgt_lang="python",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": True}
        )
        self.assertEqual(result2["cache_hit"], True)
        self.assertEqual(result1["action_key"], result2["action_key"])

    def test_run_composite_pipeline_rust_target(self):
        result = run_composite_pipeline(
            src_lang="java",
            tgt_lang="rust",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": False}
        )
        self.assertIn("pub fn execute()", result["transformed_code"])

    def test_run_composite_pipeline_go_target(self):
        result = run_composite_pipeline(
            src_lang="java",
            tgt_lang="go",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": False}
        )
        self.assertIn("func Execute() error", result["transformed_code"])

    def test_run_composite_pipeline_python_target(self):
        result = run_composite_pipeline(
            src_lang="java",
            tgt_lang="python",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": False}
        )
        self.assertIn("def execute() -> None:", result["transformed_code"])
        
    def test_run_composite_pipeline_other_target(self):
        result = run_composite_pipeline(
            src_lang="java",
            tgt_lang="abap",
            code_snippet="public class Test {}",
            options={"budget_limit_usd": 10.0, "cache_enabled": False}
        )
        self.assertIn("// Target (abap) equivalent", result["transformed_code"])

    def test_run_composite_pipeline_lean_bridge_success(self):
        mock_proof = {
            "lean4_specification": "mock_lean",
            "dafny_specification": "mock_dafny",
            "proof_id": "mock_id"
        }
        with patch.object(sys.modules['elmos_formal_assurance.lean_dafny_bridge'], 'generate_lean4_proof', return_value=mock_proof):
            result = run_composite_pipeline(
                src_lang="java",
                tgt_lang="csharp",
                code_snippet="public class Test {}",
                options={"budget_limit_usd": 10.0, "cache_enabled": False}
            )
            self.assertEqual(result["formal_assurance"]["proof_id"], "mock_id")
            self.assertEqual(result["formal_assurance"]["lean4_specification"], "mock_lean")
            self.assertEqual(result["formal_assurance"]["dafny_specification"], "mock_dafny")

    def test_run_composite_pipeline_kwargs_support(self):
        result = run_composite_pipeline(
            source_language="java",
            target_language="csharp",
            source_code="public class Test {}",
            budget_limit_usd=10.0,
            cache_enabled=False
        )
        self.assertEqual(result["status"], "SUCCESS")
