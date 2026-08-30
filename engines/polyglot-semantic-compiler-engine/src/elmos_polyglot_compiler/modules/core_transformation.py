"""Batch D directional transformation planning.

No language adapter is bundled in this module. Requests are converted into a
content-addressed external-adapter plan; source text is never relabelled as a
successful target transformation.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{label} exceeds the bounded size")
    return value


class CoreTransformationModule:
    """Builds exact directional plans for an authorized external adapter."""

    def __init__(self) -> None:
        self.transformation_history: List[Dict[str, Any]] = []

    def transform_snippet(
        self,
        source_language: str,
        target_language: str,
        source_code: str,
    ) -> Dict[str, Any]:
        """Create an external-adapter plan without generating target code."""

        source_language = _require_text(
            source_language, "source_language", maximum=64
        ).lower()
        target_language = _require_text(
            target_language, "target_language", maximum=64
        ).lower()
        source_code = _require_text(source_code, "source_code", maximum=4_194_304)
        if source_language == target_language:
            raise ValueError("source_language and target_language must differ")

        source_digest = _digest_text(source_code)
        route_id = f"{source_language}_to_{target_language}"
        tx_material = "\0".join((route_id, source_digest))
        tx_id = (
            "tx-plan-"
            + hashlib.sha256(tx_material.encode("utf-8")).hexdigest()[:24]
        )
        record: Dict[str, Any] = {
            "transformation_id": tx_id,
            "route_id": route_id,
            "source_language": source_language,
            "target_language": target_language,
            "source_code": source_code,
            "source_digest": source_digest,
            "target_code": None,
            "target_digest": None,
            "status": "EXTERNAL_ADAPTER_REQUIRED",
            "execution_state": "NOT_RUN",
            "capability_mode": "EXTERNAL_ADAPTER_REQUIRED",
            "adapter_plan": {
                "directional_route": route_id,
                "required_inputs": (
                    "IMMUTABLE_SOURCE_ARTIFACT",
                    "EXACT_SOURCE_PROFILE",
                    "EXACT_TARGET_PROFILE",
                    "TYPED_SEMANTIC_IR",
                    "AUTHORIZED_ADAPTER",
                ),
                "required_outputs": (
                    "TARGET_ARTIFACT",
                    "SOURCE_MAP",
                    "SEMANTIC_GAP_RECORDS",
                    "BUILD_RECEIPT",
                    "RUNTIME_EVIDENCE",
                ),
                "certification_authority": False,
            },
            "missing_evidence": (
                "EXTERNAL_ADAPTER_EXECUTION",
                "TARGET_BUILD",
                "TARGET_RUNTIME",
                "INDEPENDENT_SEMANTIC_VERIFICATION",
            ),
        }
        # Retain only content-addressed planning metadata in process history.
        self.transformation_history.append(
            {key: value for key, value in record.items() if key != "source_code"}
        )
        return record

    def create_transformation_obligation(
        self,
        source_idiom: str,
        target_idiom: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emit a Batch D obligation without claiming transformation success."""

        source_idiom = _require_text(source_idiom, "source_idiom", maximum=65_536)
        target_idiom = _require_text(target_idiom, "target_idiom", maximum=65_536)
        property_name = _require_text(property_name, "property_name", maximum=512)
        digest = _digest_text("\0".join((source_idiom, target_idiom, property_name)))
        return SemanticObligation(
            obligation_id=f"obl-D-{digest.removeprefix('sha256:')[:24]}",
            batch=BatchType.BATCH_D,
            layer="transformation",
            property_name=property_name,
            invariants=(
                "IDIOM_SEMANTIC_PRESERVATION",
                "CONTROL_EQUIVALENCE",
                "INTERFACE_COMPATIBILITY",
            ),
            input_digest=digest,
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
