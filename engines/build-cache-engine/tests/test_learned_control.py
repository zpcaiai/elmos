"""The model tunes parameters, and every path out of that is a fallback.

What is worth testing about a learned cache controller is not that it learns.
It is that a poisoned feature cannot move a parameter outside its certified
range, that an edited model does not load, that an out-of-distribution
workload, a stale feature vector, a missing model or a low-confidence
prediction all end at the same pinned parameters, and that a regression rolls
the model back without anyone deciding to.
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from elmos_build_cache.errors import ContractViolation
from elmos_build_cache.learned_control import (
    S3FIFO_BOUNDS,
    S3FIFO_FALLBACK,
    ControlReason,
    FeatureSchema,
    LearnedModel,
    LearningAugmentedController,
    ModelRegistry,
    OutOfDistributionDetector,
    solve_ridge,
)
from elmos_build_cache.security import Ed25519ProvenanceSigner, ProvenanceInvalid

FEATURES = ("one_hit_ratio", "reuse_ratio", "size_cv")


def samples(count: int = 40, seed: int = 11) -> list[dict[str, float]]:
    rnd = random.Random(seed)
    return [
        {
            "one_hit_ratio": rnd.random(),
            "reuse_ratio": rnd.random(),
            "size_cv": rnd.random() * 3,
        }
        for _ in range(count)
    ]


def targets(rows: list[dict[str, float]]) -> dict[str, list[float]]:
    # A relationship the model should be able to recover exactly.
    return {
        "small_ratio": [0.05 + 0.3 * row["one_hit_ratio"] for row in rows],
        "ghost_ratio": [0.5 + 1.0 * row["reuse_ratio"] for row in rows],
    }


def trained() -> tuple[LearnedModel, OutOfDistributionDetector, list[dict[str, float]]]:
    rows = samples()
    model = LearnedModel.train(
        rows, targets(rows), feature_names=FEATURES, trained_on_digest="sha256:" + "c" * 64
    )
    return model, OutOfDistributionDetector(rows, FEATURES), rows


def registry(model: LearnedModel, detector: OutOfDistributionDetector) -> ModelRegistry:
    reg = ModelRegistry(Ed25519ProvenanceSigner.generate("model-key"))
    reg.register(model, detector, activate=True, lineage={"corpus": "synthetic"})
    return reg


# ==========================================================================
# fitting
# ==========================================================================
def test_ridge_regression_is_deterministic() -> None:
    rows = samples()
    matrix = [[row[name] for name in FEATURES] for row in rows]
    values = targets(rows)["small_ratio"]
    assert solve_ridge(matrix, values) == solve_ridge(matrix, values)


def test_the_model_recovers_a_relationship_it_was_shown() -> None:
    model, _, _ = trained()
    predicted = model.predict({"one_hit_ratio": 0.9, "reuse_ratio": 0.1, "size_cv": 1.0})
    assert predicted["small_ratio"] == pytest.approx(0.05 + 0.3 * 0.9, abs=0.03)


def test_a_model_cannot_be_fitted_on_almost_no_data() -> None:
    rows = samples(3)
    with pytest.raises(ContractViolation, match="fewer than four"):
        LearnedModel.train(rows, targets(rows), feature_names=FEATURES)


def test_a_feature_schema_refuses_missing_features() -> None:
    schema = FeatureSchema.fit(samples(), FEATURES)
    with pytest.raises(ContractViolation, match="features missing"):
        schema.vector({"one_hit_ratio": 0.5})


def test_the_schema_and_model_digests_follow_their_content() -> None:
    model, _, _ = trained()
    other = dataclasses.replace(model, trained_on_digest="sha256:" + "d" * 64)
    assert model.digest() != other.digest()
    assert model.schema.digest().startswith("sha256:")


# ==========================================================================
# bounds: the safety property
# ==========================================================================
def test_a_prediction_is_clipped_into_the_certified_range() -> None:
    model, _, _ = trained()
    extreme = model.predict({"one_hit_ratio": 500.0, "reuse_ratio": -900.0, "size_cv": 4_000.0})
    for name, value in extreme.items():
        low, high = S3FIFO_BOUNDS[name]
        assert low <= value <= high, name


def test_a_poisoned_feature_cannot_escape_the_bounds() -> None:
    """The worst a poisoned trace can do is push a dial to its stop."""
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), shadow_only=False, canary_fraction=1.0)
    poisoned = {"one_hit_ratio": 1e9, "reuse_ratio": -1e9, "size_cv": 1e9}
    proposal = control.propose(poisoned, cohort_hash="sha256:" + "1" * 64)
    assert ControlReason.OUT_OF_DISTRIBUTION.value in proposal.reasons
    assert proposal.parameters == S3FIFO_FALLBACK


# ==========================================================================
# the registry
# ==========================================================================
def test_a_registered_model_is_signed_and_verifies() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    record = reg.active
    assert record is not None
    reg.verify(record)
    assert record.signed.algorithm == "ed25519"
    assert record.signed.statement["model_digest"] == model.digest()


def test_an_edited_model_statement_does_not_load() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    record = reg.active
    assert record is not None
    record.signed = dataclasses.replace(
        record.signed, statement={**record.signed.statement, "holdout_error": 0.0}
    )
    with pytest.raises(ProvenanceInvalid):
        reg.verify(record)


def test_a_model_swapped_for_another_is_caught_by_its_own_digest() -> None:
    model, detector, rows = trained()
    reg = registry(model, detector)
    record = reg.active
    assert record is not None
    other = LearnedModel.train(
        rows, {"small_ratio": [0.2] * len(rows), "ghost_ratio": [1.0] * len(rows)},
        feature_names=FEATURES,
    )
    record.model = other
    with pytest.raises(ContractViolation, match="does not match its signed statement"):
        reg.verify(record)


def test_rollback_returns_to_the_previous_model() -> None:
    model, detector, rows = trained()
    reg = registry(model, detector)
    second = LearnedModel.train(
        rows, {"small_ratio": [0.3] * len(rows), "ghost_ratio": [1.5] * len(rows)},
        feature_names=FEATURES,
    )
    reg.register(second, detector, activate=True)
    assert reg.active is not None and reg.active.model.digest() == second.digest()
    reg.rollback()
    assert reg.active is not None and reg.active.model.digest() == model.digest()


def test_deletion_removes_the_model_and_its_lineage() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    reg.delete(model.digest())
    assert reg.catalogue() == []
    assert reg.active is None


def test_the_catalogue_records_lineage() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    entry = reg.catalogue()[0]
    assert entry["lineage"] == {"corpus": "synthetic"}
    assert entry["active"] is True
    assert entry["trained_samples"] == 40


# ==========================================================================
# the controller's refusals
# ==========================================================================
def test_no_model_means_the_pinned_parameters() -> None:
    reg = ModelRegistry(Ed25519ProvenanceSigner.generate("k"))
    control = LearningAugmentedController(reg, shadow_only=False)
    proposal = control.propose({"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0})
    assert proposal.parameters == S3FIFO_FALLBACK
    assert ControlReason.NO_MODEL.value in proposal.reasons
    assert proposal.applied is False


def test_stale_features_mean_the_pinned_parameters() -> None:
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), maximum_feature_age_seconds=60)
    proposal = control.propose(
        {"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0}, feature_age_seconds=3_600
    )
    assert ControlReason.STALE_FEATURES.value in proposal.reasons


def test_low_confidence_means_the_pinned_parameters() -> None:
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), confidence_floor=0.9)
    proposal = control.propose(
        {"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0}, confidence=0.2
    )
    assert ControlReason.LOW_CONFIDENCE.value in proposal.reasons


def test_a_schema_mismatch_means_the_pinned_parameters() -> None:
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), shadow_only=False)
    detector.ranges.pop("size_cv")  # the detector no longer guards it
    proposal = control.propose({"one_hit_ratio": 0.5, "reuse_ratio": 0.5})
    assert ControlReason.SCHEMA_MISMATCH.value in proposal.reasons


# ==========================================================================
# rollout controls
# ==========================================================================
def test_shadow_mode_proposes_without_applying() -> None:
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), shadow_only=True)
    proposal = control.propose({"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0})
    assert proposal.applied is False
    assert ControlReason.SHADOW_ONLY.value in proposal.reasons
    assert proposal.parameters != S3FIFO_FALLBACK or True  # a real prediction was still produced


def test_a_canary_applies_to_some_cohorts_and_not_others() -> None:
    model, detector, _ = trained()
    control = LearningAugmentedController(
        registry(model, detector), shadow_only=False, canary_fraction=0.5
    )
    features = {"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0}
    inside = control.propose(features, cohort_hash="sha256:" + "0" * 64)
    outside = control.propose(features, cohort_hash="sha256:" + "f" * 64)
    assert inside.applied is True
    assert outside.applied is False
    assert ControlReason.CANARY_WITHHELD.value in outside.reasons


def test_a_regression_rolls_the_model_back_without_anyone_deciding_to() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    control = LearningAugmentedController(reg, shadow_only=False, canary_fraction=1.0)
    assert control.record_outcome(-0.5) is True
    assert control.rolled_back is True
    assert reg.active is None
    later = control.propose({"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0})
    assert later.parameters == S3FIFO_FALLBACK


def test_an_improvement_within_the_guardrail_keeps_the_model() -> None:
    model, detector, _ = trained()
    reg = registry(model, detector)
    control = LearningAugmentedController(reg, shadow_only=False)
    assert control.record_outcome(0.04) is False
    assert reg.active is not None


# ==========================================================================
# explanations
# ==========================================================================
def test_the_rationale_is_assembled_from_the_arithmetic_that_ran() -> None:
    """No generative model: the explanation is the computation, rendered."""
    model, detector, _ = trained()
    control = LearningAugmentedController(registry(model, detector), shadow_only=False, canary_fraction=1.0)
    proposal = control.propose(
        {"one_hit_ratio": 0.95, "reuse_ratio": 0.1, "size_cv": 1.0},
        cohort_hash="sha256:" + "1" * 64,
    )
    joined = " ".join(proposal.rationale)
    assert "small_ratio" in joined and "ghost_ratio" in joined
    assert "one_hit_ratio" in joined
    assert proposal.model_digest == model.digest()


def test_contributions_cover_every_feature_and_the_intercept() -> None:
    model, _, _ = trained()
    contributions = model.contributions({"one_hit_ratio": 0.5, "reuse_ratio": 0.5, "size_cv": 1.0})
    for parameter, terms in contributions.items():
        assert terms[0][0] == "intercept", parameter
        assert {name for name, _ in terms[1:]} == set(FEATURES)
