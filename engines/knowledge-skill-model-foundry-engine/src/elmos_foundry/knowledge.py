"""Consent-bound, tenant/project-isolated knowledge metadata ingestion."""

from __future__ import annotations

from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence, cast

from .authorizations import AuthorizationVerifier, require_authorization
from .canonical import canonical_digest, canonical_value, digest_bytes
from .domain import (
    CertificationStatus,
    ConsentStatus,
    EvidenceState,
    KnowledgeObject,
    RightsClass,
    TenantScope,
)
from .kernel import ExecutionKernel

_MAX_CONTENT_BYTES = 8 * 1024 * 1024


class KnowledgeManager:
    """Keep governed metadata only; raw source bytes never enter this store."""

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        consent_verifier: AuthorizationVerifier | None = None,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._consent_verifier = consent_verifier
        self._objects: dict[tuple[str, str, str], KnowledgeObject] = {}
        self._identity_index: dict[tuple[str, str, str], str] = {}
        self._lock = RLock()

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
        *,
        consent_receipt_digest: str | None = None,
    ) -> KnowledgeObject:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.knowledge.ingest")
        if not isinstance(content, (str, bytes)):
            raise TypeError("knowledge content must be UTF-8 text or bytes")
        data = content.encode("utf-8", "strict") if isinstance(content, str) else content
        if not data or len(data) > _MAX_CONTENT_BYTES:
            raise ValueError("knowledge content must contain 1..8388608 bytes")
        for label, value in {
            "source_id": source_id,
            "object_type": object_type,
            "confidentiality": confidentiality,
        }.items():
            if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 512:
                raise ValueError(f"{label} must be non-empty and bounded")
        normalized_provenance_value = canonical_value(provenance or {})
        if not isinstance(normalized_provenance_value, dict):
            raise ValueError("provenance did not canonicalize to an object")
        normalized_provenance = cast(dict[str, Any], normalized_provenance_value)
        content_digest = digest_bytes(data)
        consent_authorization = None
        if training_consent is not ConsentStatus.DENY:
            consent_authorization = require_authorization(
                self._consent_verifier,
                authorization_type="knowledge-training-consent",
                receipt_digest=consent_receipt_digest,
                request={
                    "source_id": source_id,
                    "object_type": object_type,
                    "content_digest": content_digest,
                    "confidentiality": confidentiality,
                    "rights_class": rights_class.value,
                    "training_consent": training_consent.value,
                    "provenance_digest": canonical_digest(normalized_provenance),
                },
                scope=scope,
            )
        identity = canonical_digest(
            {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "source_id": source_id,
                "object_type": object_type,
                "content_digest": content_digest,
                "rights_class": rights_class.value,
                "training_consent": training_consent.value,
                "consent_receipt_digest": consent_receipt_digest,
                "consent_request_digest": None
                if consent_authorization is None
                else consent_authorization.request_digest,
                "provenance": normalized_provenance,
            }
        )
        object_id = "ko-" + identity.removeprefix("sha256:")[:32]
        key = (scope.tenant_id, scope.project_id, object_id)
        with self._lock:
            existing_id = self._identity_index.get(
                (scope.tenant_id, scope.project_id, identity)
            )
            if existing_id is not None:
                return self._objects[(scope.tenant_id, scope.project_id, existing_id)]
            obj = KnowledgeObject(
                object_id=object_id,
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                source_id=source_id,
                object_type=object_type,
                content_hash=content_digest,
                confidentiality=confidentiality,
                payload=MappingProxyType(
                    {
                        "content_bytes": len(data),
                        "content_encoding": "binary" if isinstance(content, bytes) else "utf-8",
                        "raw_content_stored": False,
                        "instructions_authoritative": False,
                        "consent_receipt_digest": consent_receipt_digest,
                        "consent_request_digest": None
                        if consent_authorization is None
                        else consent_authorization.request_digest,
                    }
                ),
                provenance=MappingProxyType(dict(normalized_provenance)),
                rights_class=rights_class,
                training_consent=training_consent,
                evidence_state=EvidenceState.COLLECTED_SELF_ATTESTED,
                certification_status=CertificationStatus.NOT_CERTIFIED,
            )
            self._objects[key] = obj
            self._identity_index[(scope.tenant_id, scope.project_id, identity)] = object_id
            return obj

    def get_object(
        self, object_id: str, tenant_scope: TenantScope | None = None
    ) -> KnowledgeObject | None:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.knowledge.read")
        with self._lock:
            return self._objects.get((scope.tenant_id, scope.project_id, object_id))

    def query_objects(
        self,
        object_type: str | None = None,
        rights_class: RightsClass | None = None,
        training_consent: ConsentStatus | None = None,
        tenant_scope: TenantScope | None = None,
        *,
        limit: int = 100,
    ) -> Sequence[KnowledgeObject]:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.knowledge.read")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("knowledge query limit must be in [1, 1000]")
        with self._lock:
            candidates = sorted(
                (
                    obj
                    for (tenant, project, _), obj in self._objects.items()
                    if tenant == scope.tenant_id and project == scope.project_id
                ),
                key=lambda item: item.object_id,
            )
        return tuple(
            obj
            for obj in candidates
            if (object_type is None or obj.object_type == object_type)
            and (rights_class is None or obj.rights_class is rights_class)
            and (training_consent is None or obj.training_consent is training_consent)
        )[:limit]


__all__ = ["KnowledgeManager"]
