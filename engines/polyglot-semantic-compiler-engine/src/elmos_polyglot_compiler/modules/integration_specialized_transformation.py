"""Batch G: Integration, Enterprise & Legacy Specialized Transformation Module (Skills 107-130)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class IntegrationSpecializedTransformationModule:
    """Manages enterprise legacy migrations (Struts/JSP, COBOL, ABAP, IBMi, PLC, MATLAB, SAS, Salesforce, Delphi)."""

    def __init__(self) -> None:
        self.legacy_surfaces: Dict[str, Dict[str, Any]] = {
            "cobol": {"target": "java", "runtime": "JVM", "data_model": "COBOL Copybook"},
            "abap": {"target": "spring_boot", "runtime": "Java 21", "data_model": "SAP RFC / BAPI"},
            "struts1_2": {"target": "spring_boot_mvc", "runtime": "Spring Boot 3/4", "data_model": "Javabean ActionForm"},
            "plsql": {"target": "postgresql_plpgsql", "runtime": "PostgreSQL 16", "data_model": "Relational"},
        }

    def get_legacy_migration_strategy(self, legacy_system: str) -> Dict[str, Any]:
        """Return only an allowlisted declared strategy, never an invented fallback."""
        strategy = self.legacy_surfaces.get(legacy_system.lower())
        if strategy is None:
            return {
                "legacy_system": legacy_system,
                "supported": False,
                "status": "UNSUPPORTED",
                "execution_evidence": "NOT_RUN",
            }
        return {
            "legacy_system": legacy_system,
            **strategy,
            "supported": True,
            "status": "DECLARED_PLAN_NOT_EXECUTED",
            "execution_evidence": "NOT_RUN",
        }

    def create_legacy_obligation(
        self,
        source_legacy: str,
        target_modern: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch G legacy modernization obligation."""
        obl_id = f"obl-G-{hashlib.sha256((source_legacy + target_modern + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_G,
            layer="integration-transformation",
            source_construct=source_legacy,
            target_construct=target_modern,
            property_name=property_name,
            invariants=("LEGACY_BUSINESS_LOGIC_PRESERVED", "ZERO_DATA_LOSS_CONVERSION"),
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
