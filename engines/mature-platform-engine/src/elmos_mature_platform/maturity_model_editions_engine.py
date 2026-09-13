"""Maturity Model Editions Engine (Batch 45 - Skill 1476).

Governs enterprise platform maturity progression across 5 defined stages:
Level 1 Foundational, Level 2 Reliable, Level 3 Commercial-Ready,
Level 4 High-Assurance, and Level 5 Autonomous Enterprise.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    EditionMaturityProfile,
    MaturityGapAssessment,
    PlatformMaturityLevel,
)

LEVEL_HIERARCHY: Dict[PlatformMaturityLevel, int] = {
    PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL: 1,
    PlatformMaturityLevel.LEVEL_2_RELIABLE: 2,
    PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY: 3,
    PlatformMaturityLevel.LEVEL_4_HIGH_ASSURANCE: 4,
    PlatformMaturityLevel.LEVEL_5_AUTONOMOUS_ENTERPRISE: 5,
}

STANDARD_LEVEL_CAPABILITIES: Dict[PlatformMaturityLevel, List[str]] = {
    PlatformMaturityLevel.LEVEL_1_FOUNDATIONAL: [
        "reproducible_build",
        "basic_telemetry",
        "unit_test_harness",
    ],
    PlatformMaturityLevel.LEVEL_2_RELIABLE: [
        "automated_failover",
        "slo_monitoring",
        "dr_restore_tested",
    ],
    PlatformMaturityLevel.LEVEL_3_COMMERCIAL_READY: [
        "multi_tenant_isolation",
        "chargeback_metering",
        "rbac_sso",
    ],
    PlatformMaturityLevel.LEVEL_4_HIGH_ASSURANCE: [
        "formal_verification",
        "slsa_provenance_level_3",
        "fips_cryptography",
    ],
    PlatformMaturityLevel.LEVEL_5_AUTONOMOUS_ENTERPRISE: [
        "self_healing_ai_agents",
        "closed_loop_remediation",
        "zero_touch_operations",
    ],
}


class MaturityModelEditionsEngine:
    """Multi-edition platform maturity evaluation and roadmap promotion engine."""

    def __init__(self) -> None:
        self._profiles: Dict[str, EditionMaturityProfile] = {}
        self._edition_to_profile: Dict[str, str] = {}

    def register_edition_profile(self, profile: EditionMaturityProfile) -> str:
        """Register a maturity profile for an edition."""
        if not profile.edition:
            raise ValueError("edition is required")

        if not profile.profile_id:
            profile.profile_id = f"matprof-{uuid.uuid4().hex[:8]}"

        if not profile.last_audited:
            profile.last_audited = datetime.now(timezone.utc).isoformat()

        # If pending capabilities not specified, populate from standard level capabilities
        if not profile.capabilities_pending and not profile.capabilities_fulfilled:
            reqs = STANDARD_LEVEL_CAPABILITIES.get(profile.current_level, [])
            profile.capabilities_pending = list(reqs)

        self._profiles[profile.profile_id] = profile
        self._edition_to_profile[profile.edition] = profile.profile_id
        return profile.profile_id

    def fulfill_capability(
        self, profile_id: str, capability_name: str
    ) -> EditionMaturityProfile:
        """Mark a required capability as fulfilled for the edition profile."""
        profile = self._profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        if capability_name in profile.capabilities_pending:
            profile.capabilities_pending.remove(capability_name)

        if capability_name not in profile.capabilities_fulfilled:
            profile.capabilities_fulfilled.append(capability_name)

        profile.last_audited = datetime.now(timezone.utc).isoformat()
        return profile

    def promote_maturity_level(
        self, profile_id: str, target_level: PlatformMaturityLevel
    ) -> EditionMaturityProfile:
        """Promote platform edition to target maturity level after verifying all prerequisites."""
        profile = self._profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        curr_rank = LEVEL_HIERARCHY[profile.current_level]
        target_rank = LEVEL_HIERARCHY[target_level]

        if target_rank <= curr_rank:
            raise ValueError(
                f"Target level {target_level.value} must be strictly higher than current {profile.current_level.value}"
            )

        if profile.capabilities_pending:
            raise ValueError(
                f"Cannot promote with unfulfilled pending capabilities: {profile.capabilities_pending}"
            )

        profile.current_level = target_level
        profile.last_audited = datetime.now(timezone.utc).isoformat()

        # Set up next pending capabilities if target_level != LEVEL_5
        if target_rank < 5:
            next_level = [
                lvl for lvl, rank in LEVEL_HIERARCHY.items() if rank == target_rank + 1
            ][0]
            next_reqs = STANDARD_LEVEL_CAPABILITIES.get(next_level, [])
            profile.capabilities_pending = [
                c for c in next_reqs if c not in profile.capabilities_fulfilled
            ]
            profile.target_level = next_level

        return profile

    def assess_maturity_gap(
        self, edition: str, target_level: PlatformMaturityLevel
    ) -> MaturityGapAssessment:
        """Conduct gap analysis between current edition maturity and target maturity level."""
        profile_id = self._edition_to_profile.get(edition)
        if not profile_id:
            raise ValueError(f"No profile registered for edition: {edition}")

        profile = self._profiles[profile_id]
        curr_rank = LEVEL_HIERARCHY[profile.current_level]
        target_rank = LEVEL_HIERARCHY[target_level]

        gap_capabilities: List[str] = []
        for lvl, rank in LEVEL_HIERARCHY.items():
            if curr_rank < rank <= target_rank:
                reqs = STANDARD_LEVEL_CAPABILITIES.get(lvl, [])
                for r in reqs:
                    if r not in profile.capabilities_fulfilled and r not in gap_capabilities:
                        gap_capabilities.append(r)

        # Include any currently pending capabilities
        for p in profile.capabilities_pending:
            if p not in gap_capabilities and p not in profile.capabilities_fulfilled:
                gap_capabilities.append(p)

        weeks_estimate = max(2, len(gap_capabilities) * 3)

        return MaturityGapAssessment(
            assessment_id=f"gap-{uuid.uuid4().hex[:8]}",
            edition=edition,
            from_level=profile.current_level,
            to_level=target_level,
            gap_capabilities=gap_capabilities,
            estimated_remediation_weeks=weeks_estimate,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_profile(self, profile_id: str) -> Optional[EditionMaturityProfile]:
        """Retrieve edition maturity profile."""
        return self._profiles.get(profile_id)

    def get_maturity_report(self) -> Dict[str, Any]:
        """Generate platform-wide multi-edition maturity governance report."""
        total = len(self._profiles)
        by_level: Dict[str, int] = {lvl.value: 0 for lvl in PlatformMaturityLevel}
        total_fulfilled = 0
        total_pending = 0

        for p in self._profiles.values():
            by_level[p.current_level.value] += 1
            total_fulfilled += len(p.capabilities_fulfilled)
            total_pending += len(p.capabilities_pending)

        return {
            "total_editions_profiled": total,
            "distribution_by_level": by_level,
            "total_capabilities_fulfilled": total_fulfilled,
            "total_capabilities_pending": total_pending,
            "average_fulfilled_per_edition": round(total_fulfilled / total, 1) if total > 0 else 0.0,
        }
