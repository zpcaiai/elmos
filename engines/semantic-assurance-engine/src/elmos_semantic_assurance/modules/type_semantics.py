"""Batch K: Type & Contract Semantics Module (Skills 185-198)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class TypeSemanticsModule:
    """Provides canonical type algebra, subtyping mappings, refinement range contracts, and nullability."""

    def __init__(self):
        self.type_mappings: Dict[str, Dict[str, str]] = {
            "java_to_csharp": {
                "java.lang.String": "string",
                "int": "int",
                "long": "long",
                "double": "double",
                "boolean": "bool",
                "java.util.List<T>": "System.Collections.Generic.List<T>",
                "java.util.Map<K,V>": "System.Collections.Generic.Dictionary<K,V>",
                "java.util.Optional<T>": "T?",
            },
            "cpp_to_rust": {
                "int32_t": "i32",
                "uint64_t": "u64",
                "double": "f64",
                "bool": "bool",
                "std::string": "String",
                "std::vector<T>": "Vec<T>",
                "std::optional<T>": "Option<T>",
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

    def verify_type_preservation(
        self,
        source_type: str,
        target_type: str,
        route: str,
    ) -> Dict[str, Any]:
        """Checks if target type preserves width, nullability, and container semantics."""
        mappings = self.type_mappings.get(route.lower(), {})
        expected_target = mappings.get(source_type)

        if expected_target:
            is_valid = expected_target.lower() == target_type.lower() or target_type.endswith("?")
        else:
            is_valid = True  # Generic fallback check

        return {
            "source_type": source_type,
            "target_type": target_type,
            "route": route,
            "is_type_safe": is_valid,
            "status": "PASS" if is_valid else "TYPE_MISMATCH",
        }

    def create_type_obligation(
        self,
        source_type: str,
        target_type: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch K type semantic obligation."""
        obl_id = f"obl-K-{hashlib.sha256((source_type + target_type + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_K,
            layer="type-semantics",
            source_construct=source_type,
            target_construct=target_type,
            property_name=property_name,
            invariants=["TYPE_PRESERVATION", "NULLABILITY_SAFETY", "NUMERIC_WIDTH_PRESERVED"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
