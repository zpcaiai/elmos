from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pydantic import BaseModel

from .domain import EvidenceExtension


class UnifiedPythonEvidenceMapper:
    FINDING_MAP = {
        "PYTHON_DEPENDENCY_CONFLICT": "DEPENDENCY_CONFLICT",
        "DJANGO_URL_BREAKING": "HTTP_API_BREAKING",
        "DATASET_SCHEMA_DRIFT": "DATA_CONTRACT_BREAKING",
        "MODEL_METRIC_REGRESSION": "MODEL_BEHAVIOR_REGRESSION",
        "NUMERICAL_DRIFT": "BEHAVIOR_COMPATIBILITY_RISK",
        "PYTHON_NATIVE_ABI_BREAK": "PLATFORM_BINARY_COMPATIBILITY_RISK",
    }

    def map(
        self, organization_id: str, source_ref: str, artifact_type: str, artifact: Any, status: str
    ) -> EvidenceExtension:
        normalized = self._normalize(artifact)
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return EvidenceExtension(
            organization_id=organization_id,
            artifact_type=artifact_type,
            source_ref=source_ref,
            status=status,
            content_hash=sha256(canonical.encode()).hexdigest(),
            artifact=normalized,
        )

    @classmethod
    def _normalize(cls, artifact: Any) -> dict[str, Any]:
        if isinstance(artifact, BaseModel):
            value = artifact.model_dump(mode="json", by_alias=True)
        elif hasattr(artifact, "__dict__"):
            value = dict(artifact.__dict__)
        elif isinstance(artifact, dict):
            value = artifact
        else:
            value = {"value": artifact}
        normalized = json.loads(json.dumps(value, sort_keys=True, default=str))
        return normalized if isinstance(normalized, dict) else {"value": normalized}
