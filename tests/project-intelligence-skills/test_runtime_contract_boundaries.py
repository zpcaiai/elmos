from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_project_intelligence.canonical import canonical_digest  # noqa: E402
from elmos_project_intelligence.runtime import (  # noqa: E402
    REJECTION_CODE,
    REJECTION_SCHEMA_VERSION,
    dispatch_skill,
)


def _request(inputs: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": "boundary-run",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "revision": "abc123",
        "inputs": {**inputs, "revision": "abc123"},
    }


class RuntimeContractBoundaryTests(unittest.TestCase):
    def assert_rejection(self, result: dict[str, object]) -> None:
        self.assertEqual(result["schema_version"], REJECTION_SCHEMA_VERSION)
        self.assertEqual(result["code"], REJECTION_CODE)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("capability_state", result)
        self.assertIn("unavailable", result)
        self.assertIn("warnings", result)
        self.assertNotIn("request_id", result)
        self.assertNotIn("tenant_id", result)
        self.assertNotIn("project_id", result)
        digest = result["result_digest"]
        without_digest = dict(result)
        del without_digest["result_digest"]
        self.assertEqual(digest, canonical_digest(without_digest))

    def test_rejection_is_a_distinct_digest_bound_envelope(self) -> None:
        secret = "must-not-disclose-this-path"
        result = dispatch_skill(
            "elmos-project-fingerprinting",
            _request(
                {
                    "files": [
                        {"path": secret, "text": "first"},
                        {"path": secret, "text": "second"},
                    ]
                }
            ),
        )

        self.assert_rejection(result)
        self.assertNotIn(secret, repr(result))

    def test_orchestrator_rejects_unknown_requested_and_dependency_skills(
        self,
    ) -> None:
        unknown = "unknown-secret-skill"
        cases = (
            {"requested_skills": [unknown], "dependency_edges": []},
            {
                "requested_skills": ["elmos-project-fingerprinting"],
                "dependency_edges": [
                    {
                        "dependency": unknown,
                        "skill": "elmos-project-fingerprinting",
                    }
                ],
            },
            {
                "requested_skills": ["elmos-project-fingerprinting"],
                "dependency_edges": [
                    {
                        "dependency": "elmos-project-fingerprinting",
                        "skill": unknown,
                    }
                ],
            },
        )
        for inputs in cases:
            with self.subTest(inputs=inputs):
                result = dispatch_skill(
                    "elmos-insight-orchestrator",
                    _request(inputs),
                )
                self.assert_rejection(result)
                self.assertNotIn(unknown, repr(result))

    def test_blocked_handler_branches_keep_exact_output_keys(self) -> None:
        cycle = dispatch_skill(
            "elmos-insight-orchestrator",
            _request(
                {
                    "requested_skills": [
                        "elmos-project-fingerprinting",
                        "elmos-repository-ingestion",
                    ],
                    "dependency_edges": [
                        {
                            "dependency": "elmos-project-fingerprinting",
                            "skill": "elmos-repository-ingestion",
                        },
                        {
                            "dependency": "elmos-repository-ingestion",
                            "skill": "elmos-project-fingerprinting",
                        },
                    ],
                }
            ),
        )
        self.assertEqual(cycle["code"], "DEPENDENCY_CYCLE_REJECTED")
        self.assertEqual(
            set(cycle["outputs"]),
            {"automatic_effects", "execution_order", "requested_skills"},
        )
        self.assertEqual(cycle["outputs"]["execution_order"], [])
        self.assertFalse(cycle["outputs"]["automatic_effects"])

        explanation = dispatch_skill(
            "elmos-code-explanation",
            _request({"files": [], "path": "missing.py"}),
        )
        self.assertEqual(explanation["code"], "EXPLANATION_TARGET_NOT_FOUND")
        self.assertEqual(
            set(explanation["outputs"]),
            {"evidence_refs", "facts", "narrative_model_used"},
        )
        self.assertFalse(explanation["outputs"]["narrative_model_used"])

        locked = dispatch_skill(
            "elmos-artifact-versioning-human-lock",
            _request(
                {
                    "artifact_id": "architecture",
                    "content": "human",
                    "proposed_content": "agent",
                    "previous_version": 7,
                    "human_locked": True,
                }
            ),
        )
        self.assertEqual(locked["code"], "HUMAN_LOCK_PREVENTED_OVERWRITE")
        self.assertEqual(
            set(locked["outputs"]),
            {
                "artifact_id",
                "authoritative_lock_verified",
                "caller_reported_human_locked",
                "content_digest",
                "proposed_version",
                "version_persisted",
            },
        )
        self.assertEqual(locked["outputs"]["proposed_version"], 8)
        self.assertEqual(
            locked["outputs"]["content_digest"],
            canonical_digest("agent"),
        )

    def test_slo_target_must_be_finite_and_within_unit_interval(self) -> None:
        for target in (
            "-0.01",
            "1.01",
            "NaN",
            "sNaN",
            "Infinity",
            "invalid",
            "1e-1000000000",
            "0." + ("0" * 64) + "1",
        ):
            with self.subTest(target=target):
                result = dispatch_skill(
                    "elmos-observability-slo",
                    _request(
                        {
                            "observations": [{"status": "SUCCEEDED"}],
                            "success_rate_target": target,
                        }
                    ),
                )
                self.assert_rejection(result)

        valid = dispatch_skill(
            "elmos-observability-slo",
            _request(
                {
                    "observations": [{"status": "SUCCEEDED"}],
                    "success_rate_target": "1",
                }
            ),
        )
        self.assertEqual(valid["code"], "SLO_EVALUATED")
        self.assertTrue(valid["outputs"]["met"])


if __name__ == "__main__":
    unittest.main()
