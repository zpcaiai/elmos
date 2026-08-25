from __future__ import annotations

import copy
import unittest

from elmos_software_factory.canonical import canonical_digest
from elmos_software_factory.evidence_models import (
    CampaignReceipt,
    CampaignScope,
    EvidenceContractError,
)


SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


class CampaignReceiptParserHardeningTests(unittest.TestCase):
    @staticmethod
    def receipt() -> dict[str, object]:
        return CampaignReceipt.create(
            campaign_type="local-holdout",
            scope=CampaignScope(
                tenant_id="tenant-a",
                project_id="project-a",
                campaign_id="campaign-a",
                policy_revision="policy-v1",
                source_revision="source-v1",
            ),
            target_artifact_digest=SHA_A,
            environment_digest=SHA_A,
            corpus_digest=SHA_A,
            runtime_binding_digest=SHA_B,
            manifest_digest=SHA_A,
            status="PASSED",
            case_results=(
                {
                    "case_id": "case-001",
                    "status": "PASSED",
                    "case_digest": SHA_A,
                    "request_digest": SHA_A,
                    "observed_status": "EXECUTED",
                    "observed_error_code": None,
                    "observed_result_digest": SHA_B,
                },
            ),
            limitations=("SELF_ATTESTED", "INDEPENDENT_HOLDOUT_NOT_RUN"),
        ).as_dict()

    @staticmethod
    def reseal(receipt: dict[str, object]) -> None:
        body = copy.deepcopy(receipt)
        body.pop("receipt_digest")
        receipt["receipt_digest"] = canonical_digest(body)

    @classmethod
    def replace_cases(cls, receipt: dict[str, object], cases: list[object]) -> None:
        receipt["case_results"] = cases
        execution_digest = canonical_digest(
            {
                "runtime_binding_digest": receipt["runtime_binding_digest"],
                "case_results": cases,
            }
        )
        receipt["execution_digest"] = execution_digest
        replay = receipt["replay"]
        assert isinstance(replay, dict)
        replay["expected_execution_digest"] = execution_digest
        cls.reseal(receipt)

    def test_valid_common_case_envelope_round_trips(self) -> None:
        receipt = self.receipt()
        parsed = CampaignReceipt.from_mapping(receipt)
        self.assertEqual(receipt, parsed.as_dict())

    def test_replay_must_be_an_exact_object(self) -> None:
        for replay in (
            None,
            {
                "operation": "campaign-replay",
                "campaign_type": "local-holdout",
                "manifest_digest": SHA_A,
            },
            {
                "operation": "campaign-replay",
                "campaign_type": "local-holdout",
                "manifest_digest": SHA_A,
                "expected_execution_digest": SHA_A,
                "unexpected": "field",
            },
        ):
            with self.subTest(replay=replay):
                receipt = self.receipt()
                receipt["replay"] = replay
                self.reseal(receipt)
                with self.assertRaises(EvidenceContractError):
                    CampaignReceipt.from_mapping(receipt)

    def test_replay_fields_are_cross_linked_to_the_receipt(self) -> None:
        mutations = {
            "operation": "different-operation",
            "campaign_type": "provider-contract-simulation",
            "manifest_digest": SHA_B,
            "expected_execution_digest": SHA_B,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                receipt = self.receipt()
                replay = receipt["replay"]
                assert isinstance(replay, dict)
                replay[field] = value
                self.reseal(receipt)
                with self.assertRaisesRegex(EvidenceContractError, field):
                    CampaignReceipt.from_mapping(receipt)

    def test_case_results_must_be_non_empty_objects_with_common_fields(self) -> None:
        malformed_cases: tuple[list[object], ...] = (
            [],
            [None],
            ["not-an-object"],
            [[]],
            [{}],
            [{"case_id": "case-001"}],
            [{"status": "PASSED"}],
            [{"case_id": "case with spaces", "status": "PASSED"}],
            [{"case_id": "case-001", "status": "UNKNOWN"}],
        )
        for cases in malformed_cases:
            with self.subTest(cases=cases):
                receipt = self.receipt()
                self.replace_cases(receipt, cases)
                with self.assertRaises(EvidenceContractError):
                    CampaignReceipt.from_mapping(receipt)

    def test_non_json_case_content_is_reported_as_a_contract_error(self) -> None:
        receipt = self.receipt()
        receipt["case_results"] = [{"case_id": "case-001", "status": "PASSED", "detail": object()}]
        with self.assertRaises(EvidenceContractError):
            CampaignReceipt.from_mapping(receipt)

    def test_case_order_identity_and_top_level_status_are_semantically_bound(self) -> None:
        receipt = self.receipt()
        cases = receipt["case_results"]
        assert isinstance(cases, list)
        first = copy.deepcopy(cases[0])
        second = copy.deepcopy(first)
        second["case_id"] = "case-002"

        duplicate = self.receipt()
        self.replace_cases(duplicate, [first, copy.deepcopy(first)])
        with self.assertRaisesRegex(EvidenceContractError, "duplicate case_id"):
            CampaignReceipt.from_mapping(duplicate)

        reordered = self.receipt()
        self.replace_cases(reordered, [second, first])
        with self.assertRaisesRegex(EvidenceContractError, "sorted by case_id"):
            CampaignReceipt.from_mapping(reordered)

        contradictory = self.receipt()
        contradictory["status"] = "FAILED"
        self.reseal(contradictory)
        with self.assertRaisesRegex(EvidenceContractError, "contradicts derived case status"):
            CampaignReceipt.from_mapping(contradictory)

        failed_case = copy.deepcopy(first)
        failed_case["status"] = "FAILED"
        with self.assertRaisesRegex(EvidenceContractError, "contradicts derived case status"):
            CampaignReceipt.create(
                campaign_type="local-holdout",
                scope=CampaignScope(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    campaign_id="campaign-a",
                    policy_revision="policy-v1",
                    source_revision="source-v1",
                ),
                target_artifact_digest=SHA_A,
                environment_digest=SHA_A,
                corpus_digest=SHA_A,
                runtime_binding_digest=SHA_B,
                manifest_digest=SHA_A,
                status="PASSED",
                case_results=(failed_case,),
                limitations=("SELF_ATTESTED",),
            )


if __name__ == "__main__":
    unittest.main()
