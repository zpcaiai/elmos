"""Elmos Functional Assurance & Certification Engine v4.1.0."""

from __future__ import annotations

__version__ = "4.1.0"
__package_id__ = "elmos-functional-assurance-certification-skills-v4.1.0"

from .domain import (
    AssuranceLevel,
    ProductAssuranceLevel,
    CertificateStatus,
    DecisionRuleType,
    ConformityDecision,
    SectorType,
    MeasurementUncertaintyBudget,
    GuardBandSpecification,
    CertificateRecord,
    FunctionalAssuranceContext,
)
from .kernel import FunctionalAssuranceKernel
from .handler_registry import FunctionalAssuranceHandlerRegistry

__all__ = [
    "__version__",
    "__package_id__",
    "AssuranceLevel",
    "ProductAssuranceLevel",
    "CertificateStatus",
    "DecisionRuleType",
    "ConformityDecision",
    "SectorType",
    "MeasurementUncertaintyBudget",
    "GuardBandSpecification",
    "CertificateRecord",
    "FunctionalAssuranceContext",
    "FunctionalAssuranceKernel",
    "FunctionalAssuranceHandlerRegistry",
]
