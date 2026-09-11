"""Design Partner Reference Validation Engine (Batch 45 - Skill 1482).

Orchestrates design partner enterprise pilot studies, tracks rigorous acceptance
criteria across phased migrations, validates verified ROI cost/time savings,
and certifies reference case studies for enterprise go-to-market.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    DesignPartnerPhase,
    DesignPartnerValidationStudy,
    PartnerAcceptanceCriteria,
)


class DesignPartnerReferenceValidationEngine:
    """Industrial engine for design partner studies and reference validation (B45)."""

    PHASE_ORDER = [
        DesignPartnerPhase.ONBOARDING,
        DesignPartnerPhase.PILOT_EXECUTION,
        DesignPartnerPhase.UAT_VALIDATION,
        DesignPartnerPhase.ACCEPTANCE_SIGNED,
        DesignPartnerPhase.REFERENCE_PUBLISHED,
    ]

    def __init__(self):
        self._studies: Dict[str, DesignPartnerValidationStudy] = {}

    def create_study(
        self,
        partner_name: str,
        industry: str,
        source_platform: str,
        target_platform: str,
        lead_sponsor: str = "",
    ) -> DesignPartnerValidationStudy:
        """Initialize a new design partner study in ONBOARDING phase."""
        study_id = f"study-{uuid.uuid4().hex[:8]}"
        study = DesignPartnerValidationStudy(
            study_id=study_id,
            partner_name=partner_name,
            industry=industry,
            source_platform=source_platform,
            target_platform=target_platform,
            phase=DesignPartnerPhase.ONBOARDING,
            criteria=[],
            roi_savings_pct=0.0,
            testimonial_quote="",
            formal_acceptance_signed=False,
            lead_sponsor=lead_sponsor,
            signed_at="",
        )
        self._studies[study_id] = study
        return study

    def add_acceptance_criterion(
        self,
        study_id: str,
        description: str,
        target_metric: str,
    ) -> PartnerAcceptanceCriteria:
        """Add a specific success criterion to a design partner study."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")
        if study.formal_acceptance_signed:
            raise ValueError(f"Cannot add criteria to signed study '{study_id}'")

        criterion_id = f"crit-{uuid.uuid4().hex[:6]}"
        criterion = PartnerAcceptanceCriteria(
            criterion_id=criterion_id,
            description=description,
            target_metric=target_metric,
            actual_metric="",
            passed=False,
        )
        study.criteria.append(criterion)
        return criterion

    def record_criterion_result(
        self,
        study_id: str,
        criterion_id: str,
        actual_metric: str,
        passed: bool,
    ) -> PartnerAcceptanceCriteria:
        """Record the empirical outcome of an acceptance criterion."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")
        if study.formal_acceptance_signed:
            raise ValueError(f"Cannot mutate results of signed study '{study_id}'")

        target_crit: Optional[PartnerAcceptanceCriteria] = None
        for c in study.criteria:
            if c.criterion_id == criterion_id:
                target_crit = c
                break

        if not target_crit:
            raise ValueError(f"Criterion '{criterion_id}' not found in study '{study_id}'")

        target_crit.actual_metric = actual_metric
        target_crit.passed = passed
        return target_crit

    def advance_phase(
        self,
        study_id: str,
        next_phase: DesignPartnerPhase,
    ) -> DesignPartnerValidationStudy:
        """Advance the study lifecycle to next phase with strict progression check."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")

        curr_idx = self.PHASE_ORDER.index(study.phase)
        next_idx = self.PHASE_ORDER.index(next_phase)

        if next_idx != curr_idx + 1:
            raise ValueError(
                f"Invalid phase progression: cannot transition from {study.phase.value} to {next_phase.value}"
            )

        study.phase = next_phase
        return study

    def sign_formal_acceptance(
        self,
        study_id: str,
        lead_sponsor: str,
        roi_savings_pct: float,
    ) -> DesignPartnerValidationStudy:
        """Execute formal partner sign-off once all criteria pass."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")

        if not study.criteria:
            raise ValueError(f"Cannot sign acceptance for study '{study_id}' with zero criteria")

        failed_criteria = [c for c in study.criteria if not c.passed]
        if failed_criteria:
            raise ValueError(
                f"Cannot sign acceptance: {len(failed_criteria)} criteria have not passed"
            )

        if not lead_sponsor.strip():
            raise ValueError("Lead sponsor sign-off name cannot be empty")
        if roi_savings_pct < 0.0:
            raise ValueError("ROI savings percentage cannot be negative")

        study.formal_acceptance_signed = True
        study.lead_sponsor = lead_sponsor
        study.roi_savings_pct = roi_savings_pct
        study.signed_at = datetime.now(timezone.utc).isoformat()
        study.phase = DesignPartnerPhase.ACCEPTANCE_SIGNED

        return study

    def publish_reference_case(
        self,
        study_id: str,
        testimonial_quote: str,
    ) -> Dict[str, Any]:
        """Publish study as a verified enterprise customer reference."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")

        if not study.formal_acceptance_signed:
            raise ValueError(
                f"Cannot publish reference: study '{study_id}' does not have signed formal acceptance"
            )

        if not testimonial_quote.strip():
            raise ValueError("Testimonial quote cannot be empty for published reference")

        study.testimonial_quote = testimonial_quote
        study.phase = DesignPartnerPhase.REFERENCE_PUBLISHED

        return {
            "study_id": study.study_id,
            "partner_name": study.partner_name,
            "industry": study.industry,
            "source_platform": study.source_platform,
            "target_platform": study.target_platform,
            "roi_savings_pct": study.roi_savings_pct,
            "testimonial_quote": study.testimonial_quote,
            "signed_by": study.lead_sponsor,
            "signed_at": study.signed_at,
            "status": "REFERENCE_PUBLISHED",
        }

    def get_study(self, study_id: str) -> Optional[DesignPartnerValidationStudy]:
        """Retrieve study by ID."""
        return self._studies.get(study_id)

    def get_study_report(self, study_id: str) -> Dict[str, Any]:
        """Generate comprehensive progress report for a partner study."""
        study = self._studies.get(study_id)
        if not study:
            raise ValueError(f"Study '{study_id}' not found")

        total_criteria = len(study.criteria)
        passed_criteria = sum(1 for c in study.criteria if c.passed)
        pass_rate = round((passed_criteria / total_criteria) * 100.0, 2) if total_criteria > 0 else 0.0

        return {
            "study_id": study.study_id,
            "partner_name": study.partner_name,
            "industry": study.industry,
            "phase": study.phase.value,
            "total_criteria": total_criteria,
            "passed_criteria": passed_criteria,
            "pass_rate_pct": pass_rate,
            "formal_acceptance_signed": study.formal_acceptance_signed,
            "signed_by": study.lead_sponsor,
            "roi_savings_pct": study.roi_savings_pct,
            "is_reference_published": study.phase == DesignPartnerPhase.REFERENCE_PUBLISHED,
        }

    def get_fleet_roi_metrics(self) -> Dict[str, Any]:
        """Aggregate ROI and reference study metrics across all design partners."""
        signed_studies = [s for s in self._studies.values() if s.formal_acceptance_signed]
        published_studies = [
            s for s in self._studies.values() if s.phase == DesignPartnerPhase.REFERENCE_PUBLISHED
        ]

        total_roi = sum(s.roi_savings_pct for s in signed_studies)
        avg_roi = round(total_roi / len(signed_studies), 2) if signed_studies else 0.0

        by_industry: Dict[str, int] = {}
        for s in self._studies.values():
            by_industry[s.industry] = by_industry.get(s.industry, 0) + 1

        return {
            "total_partners": len(self._studies),
            "signed_partners_count": len(signed_studies),
            "published_references_count": len(published_studies),
            "average_roi_savings_pct": avg_roi,
            "partners_by_industry": by_industry,
        }

    def list_studies(
        self,
        phase: Optional[DesignPartnerPhase] = None,
    ) -> List[DesignPartnerValidationStudy]:
        """List studies, optionally filtered by phase."""
        if phase:
            return [s for s in self._studies.values() if s.phase == phase]
        return list(self._studies.values())
