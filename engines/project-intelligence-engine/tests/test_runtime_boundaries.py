from __future__ import annotations

import unittest

from elmos_project_intelligence.runtime import dispatch_skill
from test_runtime import base_inputs, request


class RuntimeBoundaryTests(unittest.TestCase):
    def test_outer_revision_is_injected_and_mismatch_fails_closed(self) -> None:
        inputs = base_inputs()
        inputs.pop("revision")
        frozen = dispatch_skill("elmos-repository-ingestion", request(inputs))
        self.assertEqual(frozen["outputs"]["revision"], "abc123")

        secret_revision = "different-secret-revision"
        inputs["revision"] = secret_revision
        rejected = dispatch_skill("elmos-repository-ingestion", request(inputs))
        self.assertEqual(rejected["state"], "BLOCKED")
        self.assertNotIn(secret_revision, repr(rejected))

    def test_deep_input_is_rejected_without_recursion_or_value_disclosure(self) -> None:
        deep: dict[str, object] = {}
        cursor = deep
        for _ in range(70):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        cursor["sentinel"] = "deep-secret-value"

        rejected = dispatch_skill("elmos-project-fingerprinting", request(deep))

        self.assertEqual(rejected["state"], "BLOCKED")
        self.assertEqual(rejected["error"]["type"], "CONTRACT_REJECTED")
        self.assertNotIn("deep-secret-value", repr(rejected))

    def test_nested_caller_authority_fields_cannot_launder_into_outputs(self) -> None:
        inputs = base_inputs()
        inputs["claims"] = [
            {
                "id": "claim-authority",
                "certification": "CERTIFIED",
                "release_authorized": True,
            }
        ]

        rejected = dispatch_skill("elmos-project-intelligence-graph", request(inputs))

        self.assertEqual(rejected["state"], "BLOCKED")
        self.assertNotIn("'certification': 'CERTIFIED'", repr(rejected))
        self.assertNotIn("release_authorized", repr(rejected))


if __name__ == "__main__":
    unittest.main()
