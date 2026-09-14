from __future__ import annotations

import hashlib
import unittest

from elmos_project_intelligence.canonical import canonical_digest, canonical_value
from elmos_project_intelligence.task_execution.scenario_verifier import (
    AcceptanceScenarioVerifier,
    ScenarioEvidence,
)


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def evidence_for(verifier: AcceptanceScenarioVerifier, scenario_id: str) -> list[ScenarioEvidence]:
    required = verifier.scenarios[scenario_id]["evidence_required"]
    return [
        ScenarioEvidence(
            requirement=item,
            artifact_digest=sha(f"{scenario_id}:{item}"),
            tenant_id="tenant-a",
            project_id="project-a",
            revision="abc123",
            corpus_role="HOLDOUT" if index == 0 else "DEVELOPMENT",
            executor_id="executor-a",
        )
        for index, item in enumerate(required)
    ]


class Verifier:
    verifier_id = "independent-verifier"

    def verify(self, claim, evidence):
        return {
            "claim_digest": canonical_digest(canonical_value(dict(claim))),
            "decision": "PASSED",
            "receipt_digest": sha("independent-receipt"),
            "signature_verified": True,
        }


class AcceptanceScenariosTests(unittest.TestCase):
    def setUp(self) -> None:
        self.verifier = AcceptanceScenarioVerifier()

    def test_catalog_is_exact_and_defaults_to_not_run(self) -> None:
        self.assertEqual(len(self.verifier.scenarios), 248)
        self.assertEqual(len(self.verifier.skill_scenarios), 50)
        verdicts = self.verifier.verify_all_scenarios()
        self.assertEqual(len(verdicts), 248)
        self.assertEqual({item.status for item in verdicts.values()}, {"NOT_RUN"})
        self.assertEqual({item.certification_status for item in verdicts.values()}, {"NOT_CERTIFIED"})

    def test_complete_evidence_waits_for_independent_verifier(self) -> None:
        items = evidence_for(self.verifier, "AC-00-01")
        verdict = self.verifier.verify_scenario("AC-00-01", evidence=items)
        self.assertEqual(verdict.status, "READY_FOR_INDEPENDENT_REVIEW")
        self.assertTrue(verdict.holdout_evidence_present)
        self.assertEqual(verdict.external_evidence_status, "NOT_RUN")

    def test_independent_receipt_may_pass_acceptance_but_never_certifies(self) -> None:
        items = evidence_for(self.verifier, "AC-00-01")
        verdict = self.verifier.verify_scenario(
            "AC-00-01", evidence=items, verifier=Verifier()
        )
        self.assertEqual(verdict.status, "PASSED")
        self.assertEqual(verdict.external_evidence_status, "VERIFIED_EXTERNAL")
        self.assertEqual(verdict.certification_status, "NOT_CERTIFIED")

    def test_missing_holdout_and_cross_scope_evidence_fail_closed(self) -> None:
        items = evidence_for(self.verifier, "AC-00-01")
        no_holdout = [
            ScenarioEvidence(
                item.requirement,
                item.artifact_digest,
                item.tenant_id,
                item.project_id,
                item.revision,
                "DEVELOPMENT",
                item.executor_id,
            )
            for item in items
        ]
        self.assertEqual(
            self.verifier.verify_scenario("AC-00-01", evidence=no_holdout).status,
            "BLOCKED",
        )
        mixed = list(items)
        mixed[-1] = ScenarioEvidence(
            mixed[-1].requirement,
            mixed[-1].artifact_digest,
            "tenant-b",
            mixed[-1].project_id,
            mixed[-1].revision,
            mixed[-1].corpus_role,
            mixed[-1].executor_id,
        )
        self.assertEqual(
            self.verifier.verify_scenario("AC-00-01", evidence=mixed).status,
            "BLOCKED",
        )


if __name__ == "__main__":
    unittest.main()
