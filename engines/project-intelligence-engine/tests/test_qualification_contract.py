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

    def test_unverified_evidence_and_external_release_gate_are_value_pinned(
        self,
    ) -> None:
        evidence_skill = "elmos-evidence-provenance"
        evidence = deepcopy(_result(evidence_skill))
        evidence["outputs"]["bindings"][0]["confidence"] = "CONFIRMED"
        evidence["outputs"]["bindings"][0]["verification_state"] = "VERIFIED"
        _redigest(evidence)
        with self.assertRaisesRegex(
            QualificationContractError, "cannot claim verified or confirmed"
        ):
            validate_qualification_result(
                SKILL_REGISTRY[evidence_skill], evidence, SCOPE
            )

        release_skill = "elmos-release-certification"
        release = deepcopy(_result(release_skill))
        release["outputs"]["decision"] = "READY_FOR_EXTERNAL_GATE"
        _redigest(release)
        with self.assertRaisesRegex(QualificationContractError, "external gate"):
            validate_qualification_result(SKILL_REGISTRY[release_skill], release, SCOPE)

    def test_artifact_and_policy_authority_flags_are_literal_false(self) -> None:
        for skill, field in (
            ("elmos-artifact-versioning-human-lock", "version_persisted"),
            ("elmos-artifact-versioning-human-lock", "authoritative_lock_verified"),
            ("elmos-collaboration-governance", "enforcement_authorized"),
        ):
            with self.subTest(skill=skill, field=field):
                forged = deepcopy(_result(skill))
                forged["outputs"][field] = True
                _redigest(forged)
                with self.assertRaisesRegex(
                    QualificationContractError, "literal boolean false"
                ):
                    validate_qualification_result(SKILL_REGISTRY[skill], forged, SCOPE)

    def test_diagram_cache_and_estimate_nested_contracts_are_value_pinned(
        self,
    ) -> None:
        diagram_skill = "elmos-diagram-spec-engine"
        dangling = deepcopy(_result(diagram_skill))
        dangling["outputs"]["diagram_spec"]["edges"][0]["target"] = "missing"
        dangling["outputs"]["digest"] = canonical_digest(
            dangling["outputs"]["diagram_spec"]
        )
        _redigest(dangling)
        with self.assertRaisesRegex(QualificationContractError, "dangling"):
            validate_qualification_result(
                SKILL_REGISTRY[diagram_skill], dangling, SCOPE
            )

        cache_skill = "elmos-incremental-analysis-cache"
        cross_tenant_key = deepcopy(_result(cache_skill))
        cross_tenant_key["outputs"]["cache_key"] = canonical_digest(
            {
                "schema_version": cross_tenant_key["outputs"]["schema_version"],
                "implementation_version": cross_tenant_key["outputs"][
                    "implementation_version"
                ],
                "tenant_id": "tenant-b",
                "project_id": SCOPE.project_id,
                "revision": SCOPE.revision,
                "stage": cross_tenant_key["outputs"]["stage"],
                "input_digest": cross_tenant_key["outputs"]["input_digest"],
            }
        )
        _redigest(cross_tenant_key)
        with self.assertRaisesRegex(
            QualificationContractError, "trusted request scope"
        ):
            validate_qualification_result(
                SKILL_REGISTRY[cache_skill], cross_tenant_key, SCOPE
            )

        estimate_skill = "elmos-runtime-cost-estimator"
        string_eta = deepcopy(_result(estimate_skill))
        string_eta["outputs"]["system_wall_clock_eta"]["p50_seconds"] = "0.1"
        _redigest(string_eta)
        with self.assertRaisesRegex(QualificationContractError, "must be a number"):
            validate_qualification_result(
                SKILL_REGISTRY[estimate_skill], string_eta, SCOPE
            )

        reversed_interval = deepcopy(_result(estimate_skill))
        reversed_interval["outputs"]["human_review_effort"]["p90_hours"] = 0
        reversed_interval["outputs"]["human_review_effort"]["p50_hours"] = 1
        _redigest(reversed_interval)
        with self.assertRaisesRegex(QualificationContractError, "P90"):
            validate_qualification_result(
                SKILL_REGISTRY[estimate_skill], reversed_interval, SCOPE
            )

        bundle_skill = "elmos-project-report-bundle"
        unverified_bundle = deepcopy(_result(bundle_skill))
        unverified_bundle["outputs"]["artifact_bytes_verified"] = False
        _redigest(unverified_bundle)
        with self.assertRaisesRegex(QualificationContractError, "literal boolean true"):
            validate_qualification_result(
                SKILL_REGISTRY[bundle_skill], unverified_bundle, SCOPE
            )

        drifted_bundle = deepcopy(_result(bundle_skill))
        drifted_bundle["outputs"]["artifacts"][0]["byte_count"] += 1
        _redigest(drifted_bundle)
        with self.assertRaisesRegex(QualificationContractError, "does not bind"):
            validate_qualification_result(
                SKILL_REGISTRY[bundle_skill], drifted_bundle, SCOPE
            )

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
