from __future__ import annotations

import json

import pytest

from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.miss_diagnostics import (
    DIMENSION_REASONS,
    REASON_DEFINITIONS,
    CacheCohort,
    CacheLayer,
    CacheOutcome,
    CacheOutcomeEvent,
    CacheOutcomeReason,
    IdentityDimension,
    ReasonFamily,
    UnexpectedMissBudget,
    first_difference,
)


def test_reason_and_dimension_taxonomies_are_closed_and_complete() -> None:
    assert set(REASON_DEFINITIONS) == set(CacheOutcomeReason)
    assert set(DIMENSION_REASONS) == set(IdentityDimension)


def test_first_difference_uses_contract_order_and_emits_only_digests() -> None:
    secret_model = "customer-model-and-secret"
    previous = {
        "provider": "openai",
        "model": secret_model,
        "effort": "high",
        "tool_schema": "tools-v1",
    }
    current = {
        "provider": "openai",
        "model": "different-model",
        "effort": "low",
        "tool_schema": "tools-v2",
    }
    difference = first_difference(previous, current)
    assert difference is not None
    assert difference.dimension is IdentityDimension.MODEL
    assert difference.reason is CacheOutcomeReason.MODEL_CHANGED

    encoded = json.dumps(difference.to_dict(), sort_keys=True)
    assert secret_model not in encoded
    assert "different-model" not in encoded
    assert difference.previous_digest.startswith("sha256:")
    assert difference.current_digest.startswith("sha256:")


def test_unknown_identity_dimensions_are_rejected_instead_of_guessed() -> None:
    with pytest.raises(ContractViolation, match="unknown dimensions"):
        first_difference({"provider": "openai"}, {"provider": "openai", "mystery": "x"})


def test_terminal_outcome_and_reason_must_be_compatible() -> None:
    with pytest.raises(ContractViolation, match="incompatible with terminal outcome"):
        CacheOutcomeEvent(
            layer=CacheLayer.ACTION,
            outcome=CacheOutcome.HIT,
            reason=CacheOutcomeReason.CACHE_EVICTED,
            eligible=True,
        )
    with pytest.raises(ContractViolation, match="ineligible request"):
        CacheOutcomeEvent(
            layer=CacheLayer.ACTION,
            outcome=CacheOutcome.HIT,
            reason=CacheOutcomeReason.EXACT_RESULT_REUSED,
            eligible=False,
        )


def test_first_difference_must_match_the_terminal_reason() -> None:
    difference = first_difference({"model": "v1"}, {"model": "v2"})
    assert difference is not None
    with pytest.raises(ContractViolation, match="does not match"):
        CacheOutcomeEvent(
            layer=CacheLayer.PROVIDER_PROMPT,
            outcome=CacheOutcome.NECESSARY_MISS,
            reason=CacheOutcomeReason.EFFORT_CHANGED,
            eligible=True,
            first_difference=difference,
        )


def test_unknown_reasons_always_consume_unexpected_budget() -> None:
    event = CacheOutcomeEvent(
        layer=CacheLayer.COORDINATOR,
        outcome=CacheOutcome.NECESSARY_MISS,
        reason=CacheOutcomeReason.UNKNOWN_MISS,
        eligible=False,
    )
    assert event.family is ReasonFamily.UNKNOWN
    assert event.consumes_unexpected_budget is True


def test_low_cardinality_metric_labels_exclude_identity_and_diagnostic_digests() -> None:
    difference = first_difference({"environment": {"lock": "old"}}, {"environment": {"lock": "new"}})
    assert difference is not None
    event = CacheOutcomeEvent(
        layer=CacheLayer.ENVIRONMENT,
        outcome=CacheOutcome.NECESSARY_MISS,
        reason=CacheOutcomeReason.ENVIRONMENT_CHANGED,
        eligible=True,
        cohort=CacheCohort.CANARY,
        first_difference=difference,
    )
    labels = event.metric_labels()
    assert labels == {
        "layer": "environment",
        "outcome": "NECESSARY_MISS",
        "reason": "ENVIRONMENT_CHANGED",
        "reason_family": "IDENTITY_CHANGED",
        "eligible": "true",
        "cohort": "canary",
        "unexpected_budget": "false",
    }
    assert all("sha256:" not in value for value in labels.values())
    assert all("tenant" not in key and "prompt" not in key and "secret" not in key for key in labels)
    assert event.diagnostic()["first_difference"]["dimension"] == "environment"  # type: ignore[index]


def test_budget_tracks_eligible_denominator_and_unknowns_separately() -> None:
    budget = UnexpectedMissBudget()
    events = (
        CacheOutcomeEvent(
            CacheLayer.ACTION,
            CacheOutcome.HIT,
            CacheOutcomeReason.EXACT_RESULT_REUSED,
            True,
        ),
        CacheOutcomeEvent(
            CacheLayer.PROVIDER_PROMPT,
            CacheOutcome.UNEXPECTED_MISS,
            CacheOutcomeReason.WRONG_SHARD,
            True,
        ),
        CacheOutcomeEvent(
            CacheLayer.CAS,
            CacheOutcome.LOOKUP_ERROR,
            CacheOutcomeReason.UNKNOWN_LOOKUP_ERROR,
            False,
        ),
    )
    for event in events:
        budget.observe(event)
    assert budget.to_dict() == {"eligible": 2, "consumed": 2, "unknown": 1, "rate": 1.0}


def test_exact_hit_and_intentional_economic_bypass_do_not_spend_budget() -> None:
    hit = CacheOutcomeEvent(
        CacheLayer.PROVIDER_PROMPT,
        CacheOutcome.HIT,
        CacheOutcomeReason.PROMPT_PREFIX_REUSED,
        True,
    )
    bypass = CacheOutcomeEvent(
        CacheLayer.ENVIRONMENT,
        CacheOutcome.BYPASS,
        CacheOutcomeReason.RESTORE_MORE_EXPENSIVE_THAN_RECOMPUTE,
        True,
    )
    assert hit.consumes_unexpected_budget is False
    assert bypass.consumes_unexpected_budget is False
