"""Batch B: Universal IR & Lossless AST/CST Normalization Module (Skills 017-032)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk
from ..contracts import digest_json


class IrNormalizationModule:
    """Manages Universal IR (UIR) lifting, lossless CST preservation, symbol tables, and type-attributed trees."""

    def __init__(self) -> None:
        self.uir_trees: Dict[str, Dict[str, Any]] = {}

    def lift_to_uir(
        self,
        source_language: str,
        ast_nodes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Create an IR lifting plan without treating caller data as normalized IR."""
        uir_id = f"uir-{source_language}-{len(ast_nodes)}"
        uir_document = {
            "uir_id": uir_id,
            "source_language": source_language,
            "schema_version": "3.0.0",
            "source_nodes_count": len(ast_nodes),
            "source_nodes_digest": digest_json(ast_nodes),
            "modules": [],
            "status": "TYPED_IR_ADAPTER_REQUIRED",
            "roundtrip_verified": False,
            "execution_evidence": "NOT_RUN",
        }
        self.uir_trees[uir_id] = uir_document
        return uir_document

    def create_ir_obligation(
        self,
        source_ast: str,
        target_uir: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch B IR semantic obligation."""
        obl_id = f"obl-B-{hashlib.sha256((source_ast + target_uir + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_B,
            layer="ir",
            source_construct=source_ast,
            target_construct=target_uir,
            property_name=property_name,
            invariants=("LOSSLESS_ROUNDTRIP_UIR", "TYPE_ATTRIBUTION_CONFORMANCE"),
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
