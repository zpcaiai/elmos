"""Batch M: Runtime, Memory & Concurrency Semantics Module (Skills 215-232)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class RuntimeMemoryConcurrencyModule:
    """Manages cross-language memory models, struct alignment/padding/endianness, atomic ordering, and GC/lifetimes."""

    def __init__(self) -> None:
        self.memory_profiles: Dict[str, Dict[str, Any]] = {}

    def calculate_memory_layout(
        self,
        type_name: str,
        fields: List[tuple[str, int, int]],  # (name, size, align)
    ) -> Dict[str, Any]:
        """Calculates memory offsets, struct padding, and overall byte alignment."""
        offset = 0
        max_align = 1
        layout = []

        names: set[str] = set()
        for name, size, align in fields:
            if not name or name in names:
                raise ValueError("memory layout field names must be unique and non-empty")
            if size < 0 or align <= 0 or align & (align - 1):
                raise ValueError("field size must be non-negative and alignment a positive power of two")
            names.add(name)

        for name, size, align in fields:
            max_align = max(max_align, align)
            if offset % align != 0:
                offset += align - (offset % align)
            layout.append({"name": name, "offset": offset, "size": size, "align": align})
            offset += size

        if offset % max_align != 0:
            offset += max_align - (offset % max_align)

        res = {
            "type_name": type_name,
            "total_size": offset,
            "alignment": max_align,
            "fields": layout,
            "status": "LOCAL_LAYOUT_ARITHMETIC_ONLY",
            "abi_evidence": "NOT_RUN",
            "equivalence_verified": False,
        }
        self.memory_profiles[type_name] = res
        return res

    def create_memory_obligation(
        self,
        source_struct: str,
        target_struct: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch M memory obligation."""
        obl_id = f"obl-M-{hashlib.sha256((source_struct + target_struct + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_M,
            layer="runtime-semantics",
            source_construct=source_struct,
            target_construct=target_struct,
            property_name=property_name,
            invariants=("STRUCT_LAYOUT_COMPATIBILITY", "DATA_RACE_FREEDOM", "MEMORY_ORDER_EQUIVALENCE"),
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
