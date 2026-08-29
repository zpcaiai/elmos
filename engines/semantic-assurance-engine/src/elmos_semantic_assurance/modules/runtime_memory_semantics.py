"""Batch M: Runtime, Memory & Concurrency Semantics Module (Skills 215-232)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class RuntimeMemorySemanticsModule:
    """Models memory layouts, pointer alignments, endianness, and concurrency memory orders."""

    def __init__(self):
        self.struct_layouts: Dict[str, Dict[str, Any]] = {}

    def compute_struct_layout(
        self,
        struct_name: str,
        fields: List[tuple[str, int, int]],  # (field_name, size, alignment)
        endianness: str = "little",
    ) -> Dict[str, Any]:
        """Calculates memory layout, offset alignment, total size, and padding bytes."""
        current_offset = 0
        layout_fields = []
        max_align = 1

        for name, size, align in fields:
            max_align = max(max_align, align)
            # Add padding for alignment
            if current_offset % align != 0:
                current_offset += align - (current_offset % align)
            layout_fields.append({
                "name": name,
                "size": size,
                "alignment": align,
                "offset": current_offset,
            })
            current_offset += size

        # Tail padding to match struct alignment
        if current_offset % max_align != 0:
            current_offset += max_align - (current_offset % max_align)

        layout_id = f"layout-{struct_name}-{current_offset}"
        res = {
            "layout_id": layout_id,
            "struct_name": struct_name,
            "total_size_bytes": current_offset,
            "alignment": max_align,
            "endianness": endianness,
            "fields": layout_fields,
            "status": "COMPUTED",
        }
        self.struct_layouts[layout_id] = res
        return res

    def verify_memory_order_safety(
        self,
        source_order: str,
        target_order: str,
    ) -> Dict[str, Any]:
        """Verifies that target memory ordering is at least as strong as source ordering."""
        order_strengths = {
            "relaxed": 1,
            "consume": 2,
            "acquire": 3,
            "release": 3,
            "acq_rel": 4,
            "seq_cst": 5,
        }
        src_val = order_strengths.get(source_order.lower(), 5)
        tgt_val = order_strengths.get(target_order.lower(), 5)

        is_safe = tgt_val >= src_val
        return {
            "source_order": source_order,
            "target_order": target_order,
            "is_memory_order_safe": is_safe,
            "status": "PASS" if is_safe else "WEAKENED_MEMORY_ORDER",
        }

    def create_memory_obligation(
        self,
        source_struct: str,
        target_struct: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch M memory semantic obligation."""
        obl_id = f"obl-M-{hashlib.sha256((source_struct + target_struct + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_M,
            layer="runtime-semantics",
            source_construct=source_struct,
            target_construct=target_struct,
            property_name=property_name,
            invariants=["STRUCT_LAYOUT_EQUIVALENCE", "DATA_RACE_FREEDOM", "ENDIAN_PRESERVATION"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
