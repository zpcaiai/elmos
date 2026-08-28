"""ISO/IEC 17025 Laboratory Competence and Digital Metrology Governor."""

from __future__ import annotations

import math
from typing import Any, Mapping

from ..domain import (
    ConformityDecision,
    DecisionRuleType,
    FunctionalAssuranceContext,
    GuardBandSpecification,
    MeasurementUncertaintyBudget,
    UncertaintyComponent,
)


class LabMetrologyGovernor:
    """Governor for laboratory competence, measurement uncertainty, and conformity decision rules."""

    @staticmethod
    def compile_uncertainty_budget(
        context: FunctionalAssuranceContext,
        measurand: str,
        nominal_value: float,
        components_spec: list[Mapping[str, Any]],
        coverage_factor_k: float = 2.0,
    ) -> dict[str, Any]:
        components = [
            UncertaintyComponent(
                name=str(c["name"]),
                value=float(c["value"]),
                distribution=str(c.get("distribution", "NORMAL")),
                degrees_of_freedom=int(c.get("degrees_of_freedom", 100)),
            )
            for c in components_spec
        ]
        budget = MeasurementUncertaintyBudget(
            measurand=measurand,
            nominal_value=nominal_value,
            components=components,
            coverage_factor_k=coverage_factor_k,
        )
        return {
            "skill": "elmos-measurement-uncertainty-budget-engine",
            "budget": budget.to_dict(),
            "standard": "ISO/IEC Guide 98-3 (GUM) / ILAC G17:01/2021",
            "traceability_chain_valid": True,
            "decision": ConformityDecision.CONFORMING.value,
        }

    @staticmethod
    def evaluate_conformity_decision_rule(
        context: FunctionalAssuranceContext,
        measured_value: float,
        expanded_uncertainty: float,
        lower_spec: float | None = None,
        upper_spec: float | None = None,
        rule_type: str = "GUARD_BAND_EXPANDED",
    ) -> dict[str, Any]:
        spec = GuardBandSpecification(
            lower_spec_limit=lower_spec,
            upper_spec_limit=upper_spec,
            rule_type=DecisionRuleType(rule_type),
        )
        decision = spec.evaluate_conformity(measured_value, expanded_uncertainty)
        return {
            "skill": "elmos-conformity-decision-guard-band-controller",
            "standard": "ILAC G8:09/2019",
            "measured_value": measured_value,
            "expanded_uncertainty": expanded_uncertainty,
            "lower_spec_limit": lower_spec,
            "upper_spec_limit": upper_spec,
            "decision": decision.value,
            "guard_band_applied": expanded_uncertainty,
        }

    @staticmethod
    def evaluate_interlaboratory_comparison(
        context: FunctionalAssuranceContext,
        lab_value: float,
        lab_uncertainty: float,
        reference_value: float,
        reference_uncertainty: float,
    ) -> dict[str, Any]:
        # En score formula: En = |x_lab - x_ref| / sqrt(U_lab^2 + U_ref^2)
        diff = abs(lab_value - reference_value)
        combined_u = math.sqrt(lab_uncertainty**2 + reference_uncertainty**2)
        en_score = diff / max(1e-9, combined_u)
        satisfactory = en_score <= 1.0

        return {
            "skill": "elmos-interlaboratory-comparison-controller",
            "standard": "ISO/IEC 17043 / ISO 13528",
            "en_score": round(en_score, 4),
            "satisfactory": satisfactory,
            "decision": (ConformityDecision.CONFORMING if satisfactory else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def audit_laboratory_competence(
        context: FunctionalAssuranceContext,
        accreditation_number: str,
        scopes: list[str],
        equipment_calibrated: bool = True,
        personnel_authorized: bool = True,
        environmental_controlled: bool = True,
    ) -> dict[str, Any]:
        all_passed = equipment_calibrated and personnel_authorized and environmental_controlled
        return {
            "skill": "elmos-ai-test-laboratory-competence-governor",
            "standard": "ISO/IEC 17025:2017",
            "accreditation_number": accreditation_number,
            "scopes": scopes,
            "audit_passed": all_passed,
            "decision": (ConformityDecision.CONFORMING if all_passed else ConformityDecision.NON_CONFORMING).value,
        }
