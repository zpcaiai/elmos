"""Learning-augmented control: the model tunes the dial, never turns the wheel.

The tempting version of "AI for caching" is a model that decides what to evict.
The version that survives production is the one the recent literature converged
on: keep a simple deterministic policy in the data plane and let a small model
choose its *bounded parameters*, off the hot path, at safe boundaries only.
That is what this module implements.

The consequences of that choice are the point:

- A model failure degrades performance, never correctness. Inference happens
  between epochs; a lookup never waits for it.
- Every parameter is clipped to a range that was certified. A poisoned feature
  vector can push a parameter to the edge of its range and no further.
- The model is a linear map with named coefficients, so "why did the small
  queue shrink" has an arithmetic answer, printed from the contributions.
- Models are signed with the same key material as provenance. An unsigned or
  edited model is not loaded, and a rollback is one call.
- Out-of-distribution features, drift, stale telemetry, a missing model or a
  low-confidence prediction all resolve the same way: the pinned fixed
  parameters, with the reason recorded.

Training happens offline, from benchmark reports, and is deterministic: ridge
regression solved by Gaussian elimination, no randomness, no external solver.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .canonical import digest_of
from .errors import ContractViolation
from .security import ProvenanceSigner, SignedStatement

SCHEMA_VERSION = "1.1.0"

#: Bounded parameter space for S3-FIFO. These are the certified ranges; the
#: controller may move inside them and nowhere else.
S3FIFO_BOUNDS: dict[str, tuple[float, float]] = {
    "small_ratio": (0.05, 0.35),
    "ghost_ratio": (0.5, 2.0),
}

#: The parameters used when anything at all is wrong.
S3FIFO_FALLBACK: dict[str, float] = {"small_ratio": 0.1, "ghost_ratio": 1.0}


@dataclass(frozen=True)
class FeatureSchema:
    """Which features, in which order, normalised how.

    Versioned and digested because a model is only meaningful against the exact
    feature definitions it was trained on. A schema mismatch is a fallback
    trigger, not something to coerce.
    """

    names: tuple[str, ...]
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    version: str = "cache-features/1.1.0"

    def __post_init__(self) -> None:
        if not (len(self.names) == len(self.centers) == len(self.scales)):
            raise ContractViolation("feature schema arrays disagree in length")
        if any(scale <= 0 for scale in self.scales):
            raise ContractViolation("feature scales must be positive")

    def vector(self, features: Mapping[str, float]) -> list[float]:
        missing = [name for name in self.names if name not in features]
        if missing:
            raise ContractViolation("features missing for this schema", missing=missing)
        return [
            (float(features[name]) - center) / scale
            for name, center, scale in zip(self.names, self.centers, self.scales, strict=True)
        ]

    def digest(self) -> str:
        return digest_of(
            {
                "version": self.version,
                "names": list(self.names),
                "centers": list(self.centers),
                "scales": list(self.scales),
            }
        )

    @classmethod
    def fit(cls, samples: Sequence[Mapping[str, float]], names: Sequence[str]) -> FeatureSchema:
        centers: list[float] = []
        scales: list[float] = []
        for name in names:
            column = [float(sample[name]) for sample in samples]
            center = sum(column) / len(column)
            spread = math.sqrt(sum((value - center) ** 2 for value in column) / len(column))
            centers.append(round(center, 9))
            scales.append(round(spread if spread > 1e-9 else 1.0, 9))
        return cls(tuple(names), tuple(centers), tuple(scales))


def solve_ridge(matrix: Sequence[Sequence[float]], targets: Sequence[float], penalty: float = 0.1) -> list[float]:
    """Least squares with a ridge penalty, by Gaussian elimination.

    Deterministic and dependency-free: the same samples always produce the same
    coefficients, which is what makes a model digest mean anything.
    """
    if not matrix:
        raise ContractViolation("cannot fit a model without samples")
    width = len(matrix[0]) + 1  # + intercept
    design = [[1.0, *row] for row in matrix]
    normal = [[0.0] * width for _ in range(width)]
    right = [0.0] * width
    for sample, target in zip(design, targets, strict=True):
        for i in range(width):
            right[i] += sample[i] * target
            for j in range(width):
                normal[i][j] += sample[i] * sample[j]
    for i in range(1, width):  # never penalise the intercept
        normal[i][i] += penalty

    # Gaussian elimination with partial pivoting.
    for column in range(width):
        pivot = max(range(column, width), key=lambda index: abs(normal[index][column]))
        if abs(normal[pivot][column]) < 1e-12:
            continue
        normal[column], normal[pivot] = normal[pivot], normal[column]
        right[column], right[pivot] = right[pivot], right[column]
        divisor = normal[column][column]
        normal[column] = [value / divisor for value in normal[column]]
        right[column] /= divisor
        for index in range(width):
            if index == column:
                continue
            factor = normal[index][column]
            if factor == 0.0:
                continue
            normal[index] = [
                value - factor * other
                for value, other in zip(normal[index], normal[column], strict=True)
            ]
            right[index] -= factor * right[column]
    return [round(value, 9) for value in right]


@dataclass(frozen=True)
class LearnedModel:
    """A linear map from workload features to bounded policy parameters."""

    schema: FeatureSchema
    coefficients: Mapping[str, tuple[float, ...]]
    bounds: Mapping[str, tuple[float, float]]
    fallback: Mapping[str, float]
    version: str = "s4fifo-parameters/1.1.0"
    trained_on_digest: str = ""
    holdout_error: float = 0.0
    trained_samples: int = 0

    def digest(self) -> str:
        return digest_of(
            {
                "version": self.version,
                "schema": self.schema.digest(),
                "coefficients": {name: list(values) for name, values in sorted(self.coefficients.items())},
                "bounds": {name: list(values) for name, values in sorted(self.bounds.items())},
                "trained_on_digest": self.trained_on_digest,
            }
        )

    def statement(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": "elmos.cache-parameter-model/v1",
            "version": self.version,
            "model_digest": self.digest(),
            "feature_schema": self.schema.digest(),
            "features": list(self.schema.names),
            "parameters": sorted(self.coefficients),
            "bounds": {name: list(values) for name, values in sorted(self.bounds.items())},
            "trained_on_digest": self.trained_on_digest,
            "trained_samples": self.trained_samples,
            "holdout_error": round(self.holdout_error, 9),
        }

    def contributions(self, features: Mapping[str, float]) -> dict[str, list[tuple[str, float]]]:
        """Per-feature contribution to each parameter, before clipping."""
        vector = self.schema.vector(features)
        rows: dict[str, list[tuple[str, float]]] = {}
        for parameter, coefficients in sorted(self.coefficients.items()):
            terms = [("intercept", round(coefficients[0], 6))]
            for name, value, weight in zip(self.schema.names, vector, coefficients[1:], strict=True):
                terms.append((name, round(value * weight, 6)))
            rows[parameter] = terms
        return rows

    def predict(self, features: Mapping[str, float]) -> dict[str, float]:
        """Predict, then clip. Clipping is the safety property, not a detail."""
        vector = self.schema.vector(features)
        predicted: dict[str, float] = {}
        for parameter, coefficients in self.coefficients.items():
            raw = coefficients[0] + sum(
                value * weight for value, weight in zip(vector, coefficients[1:], strict=True)
            )
            low, high = self.bounds[parameter]
            predicted[parameter] = round(min(max(raw, low), high), 6)
        return predicted

    @classmethod
    def train(
        cls,
        samples: Sequence[Mapping[str, float]],
        targets: Mapping[str, Sequence[float]],
        *,
        feature_names: Sequence[str],
        bounds: Mapping[str, tuple[float, float]] = None,  # type: ignore[assignment]
        fallback: Mapping[str, float] = None,  # type: ignore[assignment]
        penalty: float = 0.1,
        trained_on_digest: str = "",
    ) -> LearnedModel:
        if len(samples) < 4:
            raise ContractViolation("refusing to fit a model on fewer than four samples")
        schema = FeatureSchema.fit(samples, feature_names)
        matrix = [schema.vector(sample) for sample in samples]
        coefficients = {
            parameter: tuple(solve_ridge(matrix, list(values), penalty))
            for parameter, values in targets.items()
        }
        model = cls(
            schema=schema,
            coefficients=coefficients,
            bounds=dict(bounds or S3FIFO_BOUNDS),
            fallback=dict(fallback or S3FIFO_FALLBACK),
            trained_on_digest=trained_on_digest,
            trained_samples=len(samples),
        )
        # Fit error on the training set is reported, never presented as holdout.
        errors = []
        for sample, index in zip(samples, range(len(samples)), strict=True):
            predicted = model.predict(sample)
            for parameter, values in targets.items():
                errors.append((predicted[parameter] - values[index]) ** 2)
        return cls(
            schema=model.schema,
            coefficients=model.coefficients,
            bounds=model.bounds,
            fallback=model.fallback,
            version=model.version,
            trained_on_digest=trained_on_digest,
            holdout_error=math.sqrt(sum(errors) / len(errors)) if errors else 0.0,
            trained_samples=len(samples),
        )


class OutOfDistributionDetector:
    """The range each feature had while training, and whether we are in it."""

    def __init__(self, samples: Sequence[Mapping[str, float]], names: Sequence[str], slack: float = 0.2) -> None:
        self.ranges: dict[str, tuple[float, float]] = {}
        for name in names:
            column = [float(sample[name]) for sample in samples]
            low, high = min(column), max(column)
            margin = (high - low) * slack
            self.ranges[name] = (low - margin, high + margin)

    def check(self, features: Mapping[str, float]) -> tuple[str, ...]:
        outside: list[str] = []
        for name, (low, high) in sorted(self.ranges.items()):
            value = features.get(name)
            if value is None:
                outside.append(f"MISSING:{name}")
            elif value < low or value > high:
                outside.append(f"OOD:{name}")
        return tuple(outside)


@dataclass
class ModelRecord:
    model: LearnedModel
    signed: SignedStatement
    detector: OutOfDistributionDetector
    lineage: dict[str, Any] = field(default_factory=dict)
    active: bool = False


class ModelRegistry:
    """Signed models, their lineage, and the ability to go back.

    A model is only usable through this: registration signs it, loading
    verifies it, and rollback is an operation rather than a redeploy.
    """

    def __init__(self, signer: ProvenanceSigner) -> None:
        self.signer = signer
        self._records: dict[str, ModelRecord] = {}
        self._order: list[str] = []
        self._active: str | None = None

    def register(
        self,
        model: LearnedModel,
        detector: OutOfDistributionDetector,
        *,
        lineage: Mapping[str, Any] | None = None,
        activate: bool = False,
    ) -> ModelRecord:
        signed = self.signer.sign_statement("elmos.cache-parameter-model/v1", model.statement())
        record = ModelRecord(model=model, signed=signed, detector=detector, lineage=dict(lineage or {}))
        digest = model.digest()
        self._records[digest] = record
        self._order.append(digest)
        if activate:
            self.activate(digest)
        return record

    def activate(self, digest: str) -> ModelRecord:
        record = self._records.get(digest)
        if record is None:
            raise ContractViolation("unknown model", model_digest=digest)
        self.verify(record)
        for other in self._records.values():
            other.active = False
        record.active = True
        self._active = digest
        return record

    def verify(self, record: ModelRecord) -> None:
        """Signature *and* self-consistency: an edited statement is not loadable."""
        self.signer.verify_statement(record.signed)
        if record.signed.statement.get("model_digest") != record.model.digest():
            raise ContractViolation(
                "model does not match its signed statement", model_digest=record.model.digest()
            )

    @property
    def active(self) -> ModelRecord | None:
        return self._records.get(self._active) if self._active else None

    def rollback(self) -> ModelRecord | None:
        """Return to the previously active model, or to no model at all."""
        if self._active is None:
            return None
        history = [digest for digest in self._order if digest != self._active]
        self._records[self._active].active = False
        self._active = history[-1] if history else None
        if self._active is not None:
            return self.activate(self._active)
        return None

    def delete(self, digest: str) -> None:
        """Right-to-deletion: the model and its lineage go, not just the pointer."""
        self._records.pop(digest, None)
        self._order = [item for item in self._order if item != digest]
        if self._active == digest:
            self._active = self._order[-1] if self._order else None

    def catalogue(self) -> list[dict[str, Any]]:
        return [
            {
                "model_digest": digest,
                "active": self._records[digest].active,
                "version": self._records[digest].model.version,
                "trained_samples": self._records[digest].model.trained_samples,
                "lineage": self._records[digest].lineage,
            }
            for digest in self._order
        ]


class ControlReason(str, Enum):
    APPLIED = "APPLIED"
    SHADOW_ONLY = "SHADOW_ONLY"
    NO_MODEL = "NO_MODEL"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    STALE_FEATURES = "STALE_FEATURES"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    CANARY_WITHHELD = "CANARY_WITHHELD"
    ROLLED_BACK = "ROLLED_BACK"
    FIXED_FALLBACK = "FIXED_FALLBACK"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass(frozen=True)
class ParameterProposal:
    parameters: Mapping[str, float]
    confidence: float
    reasons: tuple[str, ...]
    rationale: tuple[str, ...]
    model_digest: str | None
    applied: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameters": dict(self.parameters),
            "confidence": round(self.confidence, 6),
            "reasons": list(self.reasons),
            "rationale": list(self.rationale),
            "model_digest": self.model_digest,
            "applied": self.applied,
        }


class LearningAugmentedController:
    """Proposes bounded parameters, and refuses to when anything is off.

    ``shadow_only`` and ``canary_fraction`` are the rollout controls: a model
    can be run for a long time producing proposals nobody applies, and then be
    applied to a fraction of tenants before it is applied to all of them.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        confidence_floor: float = 0.6,
        maximum_feature_age_seconds: float = 900.0,
        shadow_only: bool = True,
        canary_fraction: float = 0.0,
        fallback: Mapping[str, float] | None = None,
    ) -> None:
        self.registry = registry
        self.confidence_floor = confidence_floor
        self.maximum_feature_age_seconds = maximum_feature_age_seconds
        self.shadow_only = shadow_only
        self.canary_fraction = canary_fraction
        self.fallback = dict(fallback or S3FIFO_FALLBACK)
        self.proposals: list[ParameterProposal] = []
        self.rolled_back = False

    def propose(
        self,
        features: Mapping[str, float],
        *,
        feature_age_seconds: float = 0.0,
        confidence: float = 1.0,
        cohort_hash: str | None = None,
    ) -> ParameterProposal:
        record = self.registry.active
        reasons: list[str] = []
        if record is None:
            return self._fallback_proposal(ControlReason.NO_MODEL, reasons)
        try:
            self.registry.verify(record)
        except Exception:  # noqa: BLE001 - any verification failure is a fallback
            return self._fallback_proposal(ControlReason.SIGNATURE_INVALID, reasons)
        if feature_age_seconds > self.maximum_feature_age_seconds:
            return self._fallback_proposal(ControlReason.STALE_FEATURES, reasons)
        outside = record.detector.check(features)
        if outside:
            return self._fallback_proposal(ControlReason.OUT_OF_DISTRIBUTION, [*reasons, *outside])
        if confidence < self.confidence_floor:
            return self._fallback_proposal(ControlReason.LOW_CONFIDENCE, reasons)
        try:
            parameters = record.model.predict(features)
        except ContractViolation:
            return self._fallback_proposal(ControlReason.SCHEMA_MISMATCH, reasons)

        rationale = self._rationale(record.model, features)
        applied = not self.shadow_only and not self.rolled_back
        if applied and self.canary_fraction < 1.0:
            applied = self._in_canary(cohort_hash)
            if not applied:
                reasons.append(ControlReason.CANARY_WITHHELD.value)
        reasons.append(ControlReason.APPLIED.value if applied else ControlReason.SHADOW_ONLY.value)
        proposal = ParameterProposal(
            parameters=parameters,
            confidence=confidence,
            reasons=tuple(reasons),
            rationale=rationale,
            model_digest=record.model.digest(),
            applied=applied,
        )
        self.proposals.append(proposal)
        return proposal

    def _in_canary(self, cohort_hash: str | None) -> bool:
        if self.canary_fraction <= 0.0 or cohort_hash is None:
            return False
        bucket = int(cohort_hash[-8:], 16) / 0xFFFFFFFF
        return bucket < self.canary_fraction

    def _fallback_proposal(self, reason: ControlReason, extra: Sequence[str]) -> ParameterProposal:
        proposal = ParameterProposal(
            parameters=dict(self.fallback),
            confidence=0.0,
            reasons=(reason.value, *extra, ControlReason.FIXED_FALLBACK.value),
            rationale=("the pinned fixed parameters were used",),
            model_digest=None,
            applied=False,
        )
        self.proposals.append(proposal)
        return proposal

    @staticmethod
    def _rationale(model: LearnedModel, features: Mapping[str, float]) -> tuple[str, ...]:
        """Structured contributions, rendered as sentences. No generative model.

        The text is assembled from the arithmetic the prediction actually did,
        which is the only kind of explanation that cannot drift away from the
        decision it explains.
        """
        lines: list[str] = []
        for parameter, terms in model.contributions(features).items():
            ranked = sorted(
                (term for term in terms if term[0] != "intercept"),
                key=lambda item: -abs(item[1]),
            )[:3]
            rendered = ", ".join(f"{name} {value:+.4f}" for name, value in ranked)
            lines.append(f"{parameter}: intercept {terms[0][1]:+.4f} then {rendered}")
        return tuple(lines)

    def record_outcome(self, improvement: float, *, guardrail: float = -0.01) -> bool:
        """A regression past the guardrail rolls the model back, immediately."""
        if improvement < guardrail:
            self.registry.rollback()
            self.rolled_back = True
            self.proposals.append(
                ParameterProposal(
                    parameters=dict(self.fallback),
                    confidence=0.0,
                    reasons=(ControlReason.ROLLED_BACK.value, ControlReason.FIXED_FALLBACK.value),
                    rationale=(f"observed improvement {improvement:+.4f} breached the guardrail",),
                    model_digest=None,
                    applied=True,
                )
            )
            return True
        return False
