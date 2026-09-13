"""Implementation of B00: elmos-assurance-scope.

Manages frozen scope definitions, denominator freezing, mandatory claims derivation,
and strict rejection of empty scopes or unapproved field modifications.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import GateDecision, sha256_digest


@dataclass(frozen=True)
class ScopeExclusion:
    feature_id: str
    rationale: str
    owner: str
    risk_impact: str

    def to_dict(self) -> dict[str, str]:
        return {
            "feature_id": self.feature_id,
            "rationale": self.rationale,
            "owner": self.owner,
            "risk_impact": self.risk_impact,
        }


@dataclass(frozen=True)
class AssuranceScope:
    tenant_id: str
    project_id: str
    run_id: str
    target_profile: str
    supported_features: tuple[str, ...]
    exclusions: tuple[ScopeExclusion, ...]
    mandatory_claims: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "target_profile": self.target_profile,
            "supported_features": sorted(self.supported_features),
            "exclusions": [e.to_dict() for e in sorted(self.exclusions, key=lambda x: x.feature_id)],
            "mandatory_claims": sorted(self.mandatory_claims),
        }

    def digest(self) -> str:
        return sha256_digest(self.to_dict())


class ScopeCompiler:
    """Compiles and validates AssuranceScope under elmos.assurance/v4."""

    CRITICAL_MANDATORY_MAP = {
        "order-permission-flow": "claim:order-auth-dominance",
        "tenant-data-isolation": "claim:tenant-noninterference",
        "payment-idempotency": "claim:payment-idempotent-commit",
        "atomic-transaction": "claim:transaction-all-or-nothing",
    }

    @classmethod
    def compile_scope(
        cls,
        tenant_id: str,
        project_id: str,
        run_id: str,
        supported_features: Sequence[str],
        exclusions: Sequence[ScopeExclusion] = (),
        target_profile: str = "elmos.assurance/v4",
    ) -> AssuranceScope:
        if not supported_features:
            raise ValueError("EMPTY_SCOPE_REJECTED: supported_features cannot be empty")

        # Derive mandatory claims from supported features
        claims = set()
        for feat in supported_features:
            if feat in cls.CRITICAL_MANDATORY_MAP:
                claims.add(cls.CRITICAL_MANDATORY_MAP[feat])
            claims.add(f"claim:{feat}:conformance")

        # Verify no critical unknown was tucked into exclusions
        for ex in exclusions:
            if ex.feature_id in cls.CRITICAL_MANDATORY_MAP and not ex.rationale:
                raise ValueError(f"CRITICAL_FEATURE_EXCLUSION_REQUIRES_RATIONALE: {ex.feature_id}")

        return AssuranceScope(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            target_profile=target_profile,
            supported_features=tuple(sorted(supported_features)),
            exclusions=tuple(sorted(exclusions, key=lambda x: x.feature_id)),
            mandatory_claims=tuple(sorted(claims)),
        )

    @classmethod
    def validate_approved_scope(
        cls,
        scope: AssuranceScope,
        approved_digest: str,
        frozen_denominator: int | None = None,
    ) -> tuple[GateDecision, list[str]]:
        reasons: list[str] = []
        current_digest = scope.digest()

        if current_digest != approved_digest:
            reasons.append(f"SCOPE_APPROVAL_INVALIDATED: expected {approved_digest}, got {current_digest}")
            return GateDecision.INCONCLUSIVE, reasons

        if not scope.supported_features or not scope.mandatory_claims:
            reasons.append("EMPTY_SCOPE_OR_CLAIMS_ATTEMPTED")
            return GateDecision.FAIL, reasons

        if frozen_denominator is not None:
            current_count = len(scope.mandatory_claims)
            if current_count < frozen_denominator:
                reasons.append(
                    f"FROZEN_DENOMINATOR_VIOLATION: claim count reduced from {frozen_denominator} to {current_count}"
                )
                return GateDecision.FAIL, reasons

        return GateDecision.PASS, ["SCOPE_APPROVED_AND_INTACT"]
