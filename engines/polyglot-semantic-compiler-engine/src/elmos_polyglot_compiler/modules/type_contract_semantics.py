"""Batch K: Type & Contract Semantics Module (Skills 185-198)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class TypeContractSemanticsModule:
    """Manages canonical type algebra, subtyping, refinement ranges, variance, nullability, and numeric precision."""

    def __init__(self) -> None:
        self.algebraic_mappings: Dict[str, Dict[str, str]] = {
            "java_to_csharp": {
                "java.lang.String": "string",
                "int": "int",
                "long": "long",
                "double": "double",
                "boolean": "bool",
                "java.util.List<T>": "System.Collections.Generic.List<T>",
                "java.util.Map<K,V>": "System.Collections.Generic.Dictionary<K,V>",
            },
            "csharp_to_java": {
                "string": "java.lang.String",
                "int": "int",
                "long": "long",
                "bool": "boolean",
                "List<T>": "java.util.List<T>",
                "Dictionary<K,V>": "java.util.Map<K,V>",
            },
        }

    def verify_algebraic_preservation(self, source_type: str, target_type: str, route: str) -> Dict[str, Any]:
        """Apply a bounded lookup rule without promoting it to type safety."""
        mappings = self.algebraic_mappings.get(route.lower(), {})
        expected = mappings.get(source_type)
        local_rule_match = expected is not None and expected.lower() == target_type.lower()
        status = (
            "LOCAL_RULE_MATCH_NOT_VERIFIED"
            if local_rule_match
            else "TYPE_MISMATCH"
            if expected is not None
            else "UNSUPPORTED_MAPPING"
        )
        return {
            "source_type": source_type,
            "target_type": target_type,
            "expected_target_type": expected,
            "local_rule_match": local_rule_match,
            "is_type_safe": False,
            "status": status,
            "native_type_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }

    def create_type_obligation(
        self,
        source_type: str,
        target_type: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch K type obligation."""
        obl_id = f"obl-K-{hashlib.sha256((source_type + target_type + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_K,
            layer="type-semantics",
            source_construct=source_type,
            target_construct=target_type,
            property_name=property_name,
            invariants=("CANONICAL_TYPE_PRESERVATION", "NULLABILITY_EQUIVALENCE", "NUMERIC_PRECISION_PRESERVED"),
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
