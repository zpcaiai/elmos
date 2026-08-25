from __future__ import annotations

from copy import deepcopy
import unittest

from elmos_project_intelligence.canonical import canonical_digest
from elmos_project_intelligence.qualification_contract import (
    ExpectedRequestScope,
    OUTPUT_KEYS_BY_SKILL,
    QualificationContractError,
    validate_qualification_result,
)
from elmos_project_intelligence.runtime import SKILL_REGISTRY, dispatch_skill
from test_runtime import request


SCOPE = ExpectedRequestScope(
    request_id="request-1",
    tenant_id="tenant-a",
    project_id="project-a",
    revision="abc123",
)


def _result(skill: str) -> dict[str, object]:
    return dispatch_skill(skill, request())


def _redigest(result: dict[str, object]) -> None:
    result["result_digest"] = canonical_digest(
        {key: value for key, value in result.items() if key != "result_digest"}
    )


class QualificationContractTests(unittest.TestCase):
    def test_all_fifty_fixture_results_satisfy_the_exact_contract(self) -> None:
        self.assertEqual(tuple(OUTPUT_KEYS_BY_SKILL), tuple(SKILL_REGISTRY))
        self.assertEqual(len(OUTPUT_KEYS_BY_SKILL), 50)
        for skill, binding in SKILL_REGISTRY.items():
            with self.subTest(skill=skill):
                raw = _result(skill)
                self.assertIsNone(validate_qualification_result(binding, raw, SCOPE))

    def test_forged_extra_authority_fields_fail_even_with_recomputed_digest(
        self,
    ) -> None:
        skill = "elmos-release-certification"
        top_level = deepcopy(_result(skill))
        top_level["production_approved"] = True
        _redigest(top_level)
        with self.assertRaises(QualificationContractError):
            validate_qualification_result(SKILL_REGISTRY[skill], top_level, SCOPE)

        replay_skill = "elmos-debug-record-replay"
        nested = deepcopy(_result(replay_skill))
        nested["outputs"]["bundle"]["production_approved"] = True
        _redigest(nested)
        with self.assertRaises(QualificationContractError):
            validate_qualification_result(SKILL_REGISTRY[replay_skill], nested, SCOPE)

    def test_authority_false_cannot_be_replaced_by_integer_one(self) -> None:
        skill = "elmos-architecture-discovery"
        forged = deepcopy(_result(skill))
        forged["outputs"]["runtime_verified"] = 1
        _redigest(forged)
        with self.assertRaisesRegex(
            QualificationContractError, "literal boolean false"
        ):
            validate_qualification_result(SKILL_REGISTRY[skill], forged, SCOPE)

    def test_partial_and_plan_results_require_nonempty_unavailable(self) -> None:
        for skill in (
            "elmos-repository-ingestion",
            "elmos-deployment-private-cloud",
        ):
            with self.subTest(skill=skill):
                forged = deepcopy(_result(skill))
                forged["unavailable"] = []
                _redigest(forged)
                with self.assertRaisesRegex(
                    QualificationContractError, "non-empty unavailable"
                ):
                    validate_qualification_result(SKILL_REGISTRY[skill], forged, SCOPE)

    def test_digest_drift_fails_closed(self) -> None:
        skill = "elmos-project-fingerprinting"
        drifted = deepcopy(_result(skill))
        drifted["outputs"]["languages"]["Python"] = 999
        with self.assertRaisesRegex(
            QualificationContractError, "result_digest does not bind"
        ):
            validate_qualification_result(SKILL_REGISTRY[skill], drifted, SCOPE)

        noncanonical = deepcopy(_result(skill))
        noncanonical["result_digest"] = str(noncanonical["result_digest"]).upper()
        with self.assertRaisesRegex(QualificationContractError, "canonical lowercase"):
            validate_qualification_result(SKILL_REGISTRY[skill], noncanonical, SCOPE)


if __name__ == "__main__":
    unittest.main()
