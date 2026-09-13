"""Implementation of B02: Coverage obligations, denominator freezing, and test plan compiler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import sha256_digest
from .scope import AssuranceScope


@dataclass(frozen=True)
class TestObligation:
    obligation_id: str
    feature_id: str
    obligation_type: str  # smoke, regression, differential, mutation, formal
    critical: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "feature_id": self.feature_id,
            "obligation_type": self.obligation_type,
            "critical": self.critical,
            "description": self.description,
        }


@dataclass(frozen=True)
class ObligationSet:
    scope_digest: str
    obligations: tuple[TestObligation, ...]
    denominator: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_digest": self.scope_digest,
            "obligations": [o.to_dict() for o in sorted(self.obligations, key=lambda x: x.obligation_id)],
            "denominator": self.denominator,
        }

    def digest(self) -> str:
        return sha256_digest(self.to_dict())


class CoveragePlanner:
    """Compiles frozen obligation sets and smoke subsets from approved scopes."""

    @classmethod
    def compile_obligations(cls, scope: AssuranceScope) -> ObligationSet:
        obligations: list[TestObligation] = []

        for feat in scope.supported_features:
            # Each supported feature requires at least a smoke and regression obligation
            obligations.append(
                TestObligation(
                    obligation_id=f"obl:smoke:{feat}",
                    feature_id=feat,
                    obligation_type="smoke",
                    critical=True,
                    description=f"Smoke startup and critical route check for {feat}",
                )
            )
            obligations.append(
                TestObligation(
                    obligation_id=f"obl:regression:{feat}",
                    feature_id=feat,
                    obligation_type="regression",
                    critical=True,
                    description=f"Full regression test suite for {feat}",
                )
            )

        for claim in scope.mandatory_claims:
            obligations.append(
                TestObligation(
                    obligation_id=f"obl:claim:{claim}",
                    feature_id=claim,
                    obligation_type="regression",
                    critical=True,
                    description=f"Verification of mandatory claim {claim}",
                )
            )

        sorted_obls = tuple(sorted(obligations, key=lambda x: x.obligation_id))
        return ObligationSet(
            scope_digest=scope.digest(),
            obligations=sorted_obls,
            denominator=len(sorted_obls),
        )

    @classmethod
    def select_smoke_obligations(cls, obligation_set: ObligationSet) -> list[TestObligation]:
        return [o for o in obligation_set.obligations if o.obligation_type == "smoke"]

    @classmethod
    def select_regression_obligations(cls, obligation_set: ObligationSet) -> list[TestObligation]:
        return [o for o in obligation_set.obligations if o.obligation_type == "regression"]
