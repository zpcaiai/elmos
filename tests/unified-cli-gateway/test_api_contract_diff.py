"""Unit tests for Polyglot API Contract & Backward-Compatibility Drift Differ."""

import unittest
from elmos_polyglot_compiler.api_contract_diff import (
    ApiContractDiffer,
    ContractDiffReport,
    run_api_contract_diff,
)


class TestApiContractDiffer(unittest.TestCase):

    def setUp(self):
        self.differ = ApiContractDiffer()
        self.src_spec = {
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "number", "required": True},
                    },
                    "response_fields": {
                        "order_id": {"type": "string", "required": True},
                        "status": {"type": "string", "required": True},
                    },
                }
            },
        }
        self.tgt_spec_compatible = {
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "number", "required": True},
                        "currency": {"type": "string", "required": False},
                    },
                    "response_fields": {
                        "order_id": {"type": "string", "required": True},
                        "status": {"type": "string", "required": True},
                        "trace_id": {"type": "string", "required": False},
                    },
                }
            },
        }
        self.tgt_spec_breaking = {
            "schema_version": "1.0",
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "integer", "required": True},  # Type changed -> BREAKING
                        "amount": {"type": "number", "required": True},
                    },
                    "response_fields": {
                        "order_id": {"type": "string", "required": True},
                        # status dropped -> BREAKING
                    },
                }
            },
        }

    def test_compatible_diff(self):
        rep = self.differ.compare_specs(self.src_spec, self.tgt_spec_compatible)
        self.assertIsInstance(rep, ContractDiffReport)
        self.assertTrue(rep.is_backward_compatible)
        self.assertEqual(rep.breaking_changes_count, 0)
        self.assertEqual(rep.non_breaking_count, 2)

    def test_breaking_diff(self):
        rep = self.differ.compare_specs(self.src_spec, self.tgt_spec_breaking)
        self.assertFalse(rep.is_backward_compatible)
        self.assertGreater(rep.breaking_changes_count, 0)

    def test_run_api_contract_diff_helper(self):
        res = run_api_contract_diff()
        self.assertIn("status", res)
        self.assertIn("changes", res)
        self.assertIn("is_backward_compatible", res)
        self.assertEqual(res["status"], "NOT_RUN")

        res_compat = run_api_contract_diff(source_spec=self.src_spec, target_spec=self.tgt_spec_compatible)
        self.assertEqual(res_compat["status"], "COMPATIBLE")
        self.assertTrue(res_compat["is_backward_compatible"])


if __name__ == "__main__":
    unittest.main()

