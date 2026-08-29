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
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "float", "required": True},
                        "currency": {"type": "string", "required": False},
                    },
                    "response_fields": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                    },
                }
            }
        }
        self.tgt_spec_compatible = {
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "string", "required": True},
                        "amount": {"type": "float", "required": True},
                    },
                    "response_fields": {
                        "order_id": {"type": "string"},
                        "status": {"type": "string"},
                        "trace_id": {"type": "string"},
                    },
                }
            }
        }
        self.tgt_spec_breaking = {
            "endpoints": {
                "POST /api/v1/orders": {
                    "request_fields": {
                        "order_id": {"type": "int", "required": True},  # Type changed -> BREAKING
                        "amount": {"type": "float", "required": True},
                    },
                    "response_fields": {
                        "order_id": {"type": "string"},
                        # status dropped -> BREAKING
                    },
                }
            }
        }

    def test_compatible_diff(self):
        rep = self.differ.compare_specs(self.src_spec, self.tgt_spec_compatible)
        self.assertIsInstance(rep, ContractDiffReport)
        self.assertTrue(rep.is_backward_compatible)
        self.assertEqual(rep.breaking_changes_count, 0)
        self.assertEqual(rep.non_breaking_count, 1)

    def test_breaking_diff(self):
        rep = self.differ.compare_specs(self.src_spec, self.tgt_spec_breaking)
        self.assertFalse(rep.is_backward_compatible)
        self.assertGreater(rep.breaking_changes_count, 0)

    def test_run_api_contract_diff_helper(self):
        res = run_api_contract_diff()
        self.assertIn("status", res)
        self.assertIn("changes", res)
        self.assertIn("is_backward_compatible", res)


if __name__ == "__main__":
    unittest.main()
