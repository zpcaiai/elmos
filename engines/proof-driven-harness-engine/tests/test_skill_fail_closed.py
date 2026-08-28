from __future__ import annotations

import unittest

from elmos_proof_harness.skills import SkillRuntime


_DIGEST = "a" * 64


class SkillFailClosedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = SkillRuntime()

    def test_completion_skill_never_promotes_caller_proof_claims(self) -> None:
        result = self.runtime.execute(
            "elmos-certification-kernel",
            {
                "proof_results": [
                    {
                        "status": "PASS",
                        "evidence_digest": _DIGEST,
                        "independent": True,
                    }
                ],
                "external_gate": {"status": "CERTIFIED"},
            },
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.output["decision"], "BLOCKED")
        self.assertEqual(result.output["local_input_status"], "VALIDATED")
        self.assertEqual(result.output["durable_evidence_verification"], "NOT_RUN")
        self.assertEqual(result.output["production_certification"], "NOT_CERTIFIED")
        self.assertFalse(result.certified)

    def test_evaluation_gate_never_promotes_caller_independence_claims(self) -> None:
        result = self.runtime.execute(
            "elmos-evaluation-trust-gate",
            {
                "records": [
                    {
                        "corpus_digest": _DIGEST,
                        "executor": "runner-a",
                        "verifier": "reviewer-b",
                        "status": "PASS",
                        "independent": True,
                    }
                ]
            },
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.output["decision"], "BLOCKED")
        self.assertEqual(result.output["local_input_status"], "VALIDATED")
        self.assertEqual(result.output["durable_evidence_verification"], "NOT_RUN")
        self.assertFalse(result.certified)

    def test_domain_pack_rejects_payload_only_evidence(self) -> None:
        plan = self.runtime.execute(
            "elmos-domain-sql-dialect-routine-conversion",
            {"inputs": {"source": "PostgreSQL", "target": "Oracle"}},
        )
        obligations = plan.output["plan"]["obligations"]
        fabricated = {
            item["template_id"]: [
                {
                    "kind": evidence_kind,
                    "status": "PASS",
                    "digest": _DIGEST,
                }
                for evidence_kind in item["required_evidence"]
            ]
            for item in obligations
        }
        result = self.runtime.execute(
            "elmos-domain-sql-dialect-routine-conversion",
            {
                "inputs": {"source": "PostgreSQL", "target": "Oracle"},
                "evidence_by_obligation": fabricated,
            },
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.output["decision"]["certified"])

    def test_finops_rejects_non_finite_or_unbounded_decimals(self) -> None:
        for invalid in ("NaN", "Infinity", "1e19", "0.0000000000001"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.runtime.execute(
                    "elmos-commercial-operations-finops",
                    {
                        "currency": "USD",
                        "line_items": [
                            {
                                "name": "compute",
                                "quantity": invalid,
                                "unit_price": "1.00",
                            }
                        ],
                    },
                )


if __name__ == "__main__":
    unittest.main()
