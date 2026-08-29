"""Knowledge ingestion, rights classification, and semantic indexing for Elmos Foundry.

Manages knowledge objects with strict provenance, licensing, and consent governance.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Mapping, Sequence

from .domain import (
    ConsentStatus,
    ContentDigest,
    ExecutionResult,
    KnowledgeObject,
    RightsClass,
    TenantScope,
)
from .kernel import ExecutionKernel


class KnowledgeManager:
    """Enterprise knowledge lifecycle manager."""

    def __init__(self, kernel: ExecutionKernel | None = None) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._objects: dict[str, KnowledgeObject] = {}  # object_id -> KnowledgeObject
        self._hash_index: dict[tuple[str, str], str] = {}  # (tenant_id, content_hash) -> object_id

    def ingest_document(
        self,
        source_id: str,
        object_type: str,
        content: str | bytes,
        confidentiality: str = "internal",
        rights_class: RightsClass = RightsClass.INTERNAL,
        training_consent: ConsentStatus = ConsentStatus.DENY,
        provenance: Mapping[str, Any] | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> KnowledgeObject:
        scope = tenant_scope or self.kernel.current_tenant
        data_bytes = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(data_bytes).hexdigest()
        
        index_key = (scope.tenant_id, content_hash)
        if index_key in self._hash_index:
            existing_id = self._hash_index[index_key]
            return self._objects[existing_id]

        obj_id = str(uuid.uuid4())
        obj = KnowledgeObject(
            object_id=obj_id,
            tenant_id=scope.tenant_id,
            source_id=source_id,
            object_type=object_type,
            content_hash=content_hash,
            confidentiality=confidentiality,
            payload={
                "content_len": len(data_bytes),
                "is_binary": isinstance(content, bytes),
                "sample": data_bytes[:200].decode("utf-8", errors="replace"),
            },
            provenance=provenance or {"ingested_by": scope.actor_id, "project_id": scope.project_id},
            rights_class=rights_class,
            training_consent=training_consent,
            quality_score=1.0,
        )
        self._objects[obj_id] = obj
        self._hash_index[index_key] = obj_id
        return obj

    def get_object(self, object_id: str, tenant_scope: TenantScope | None = None) -> KnowledgeObject | None:
        scope = tenant_scope or self.kernel.current_tenant
        obj = self._objects.get(object_id)
        if obj is not None and obj.tenant_id == scope.tenant_id:
            return obj
        return None

    def query_objects(
        self,
        object_type: str | None = None,
        rights_class: RightsClass | None = None,
        training_consent: ConsentStatus | None = None,
        tenant_scope: TenantScope | None = None,
    ) -> Sequence[KnowledgeObject]:
        scope = tenant_scope or self.kernel.current_tenant
        results = []
        for obj in self._objects.values():
            if obj.tenant_id != scope.tenant_id:
                continue
            if object_type and obj.object_type != object_type:
                continue
            if rights_class and obj.rights_class != rights_class:
                continue
            if training_consent and obj.training_consent != training_consent:
                continue
            results.append(obj)
        return results
