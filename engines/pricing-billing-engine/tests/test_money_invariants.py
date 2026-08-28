from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from elmos_pricing_billing.money_invariants import observation_from_mapping, verify_money_invariants

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACK_ROOT = REPOSITORY_ROOT / "verification-packs" / "pricing-billing-local-v1"


def _object(value: object) -> Mapping[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _cases(relative: str) -> list[Mapping[str, object]]:
    document: object = json.loads((PACK_ROOT / relative).read_text())
    root = _object(document)
    values = root.get("cases")
    assert isinstance(values, list)
    return [_object(value) for value in values]


NEGATIVE_CASES = _cases("corpus/negative/cases.json")


def test_development_observation_satisfies_all_invariants() -> None:
    case = _cases("corpus/development/cases.json")[0]
    report = verify_money_invariants(observation_from_mapping(_object(case["observation"])))

    assert report.passed
    assert report.violations == ()


@pytest.mark.parametrize("case", NEGATIVE_CASES, ids=lambda case: str(case["case_id"]))
def test_seeded_financial_defect_is_detected(case: Mapping[str, object]) -> None:
    report = verify_money_invariants(observation_from_mapping(_object(case["observation"])))

    expected_codes = case["expected_codes"]
    assert isinstance(expected_codes, list)
    assert [violation.code for violation in report.violations] == expected_codes
    assert [violation.fingerprint for violation in report.violations] == [case["expected_fingerprint"]]


def test_report_and_fingerprints_are_deterministic() -> None:
    case = NEGATIVE_CASES[0]
    observation = observation_from_mapping(_object(case["observation"]))

    first = verify_money_invariants(observation)
    second = verify_money_invariants(observation)

    assert first == second


def test_float_amounts_are_rejected_to_preserve_exact_decimal_arithmetic() -> None:
    with pytest.raises(ValueError, match="decimal string"):
        observation_from_mapping(
            {
                "allocation_pools": [
                    {
                        "tenant_id": "tenant-a",
                        "source_id": "cost-1",
                        "currency": "USD",
                        "source_amount": 10.0,
                        "allocations": ["10.000000"],
                    }
                ]
            }
        )


def test_same_transaction_id_is_reconciled_per_tenant() -> None:
    observation = observation_from_mapping(
        {
            "ledger_postings": [
                {
                    "tenant_id": "tenant-a",
                    "transaction_id": "same-id",
                    "posting_id": "a-debit",
                    "currency": "USD",
                    "side": "DEBIT",
                    "amount": "10.000000",
                },
                {
                    "tenant_id": "tenant-a",
                    "transaction_id": "same-id",
                    "posting_id": "a-credit",
                    "currency": "USD",
                    "side": "CREDIT",
                    "amount": "10.000000",
                },
                {
                    "tenant_id": "tenant-b",
                    "transaction_id": "same-id",
                    "posting_id": "b-debit",
                    "currency": "USD",
                    "side": "DEBIT",
                    "amount": "7.000000",
                },
                {
                    "tenant_id": "tenant-b",
                    "transaction_id": "same-id",
                    "posting_id": "b-credit",
                    "currency": "USD",
                    "side": "CREDIT",
                    "amount": "6.000000",
                },
            ]
        }
    )

    report = verify_money_invariants(observation)

    assert [violation.entity_key for violation in report.violations] == ["tenant-b/same-id/USD"]
