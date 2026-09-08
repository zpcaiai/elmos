"""Versioned context caching with ACL epoch and tombstone revalidation."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import (
    ContextRequest,
    EvidenceContext,
    ScopeDeniedError,
    TrustedScope,
    canonical_digest,
)
from .scope import HostAuthority


@dataclass(frozen=True)
class CacheEntry:
    key: str
    tenant: str
    principal: str
    acl_epoch: int
    scope_digest: str
    context: EvidenceContext
    tombstone_check_anchors: tuple[tuple[str, str], ...]  # (tenant, blob_digest)


class ContextCache:
    """Fail-closed, permission-aware cache for EvidenceContext results."""

    def __init__(self, authority: HostAuthority) -> None:
        self.authority = authority
        self._entries: dict[str, CacheEntry] = {}
        self._tombstones: set[tuple[str, str]] = set()  # (tenant, blob_digest)

    @staticmethod
    def compute_key(scope: TrustedScope, request: ContextRequest, prompt_version: str = "v1") -> str:
        payload = {
            "scope_digest": scope.digest,
            "query": request.query,
            "mode": request.mode,
            "selector": dict(request.selector),
            "top_k": request.top_k,
            "budget": request.context_token_budget,
            "prompt_version": prompt_version,
            "acl_epoch": scope.acl_epoch,
        }
        return canonical_digest(payload)

    def put(
        self,
        scope: TrustedScope,
        request: ContextRequest,
        context: EvidenceContext,
        prompt_version: str = "v1",
    ) -> str:
        key = self.compute_key(scope, request, prompt_version)
        anchors = tuple((scope.tenant, item.anchor.blob_digest) for item in context.items)
        entry = CacheEntry(
            key=key,
            tenant=scope.tenant,
            principal=scope.principal,
            acl_epoch=scope.acl_epoch,
            scope_digest=scope.digest,
            context=copy.deepcopy(context),
            tombstone_check_anchors=anchors,
        )
        self._entries[key] = entry
        return key

    def get(self, key: str, scope: TrustedScope) -> EvidenceContext | None:
        entry = self._entries.get(key)
        if entry is None:
            return None

        # 1. Tenant match
        if entry.tenant != scope.tenant:
            return None

        # 2. Principal check
        if entry.principal != scope.principal:
            return None

        # 3. Epoch revalidation: fail closed if authority epoch has changed
        current_epoch = self.authority.get_acl_epoch(scope.tenant)
        if entry.acl_epoch != current_epoch or scope.acl_epoch != current_epoch:
            del self._entries[key]
            return None

        # 4. Tombstone check
        for anchor_ref in entry.tombstone_check_anchors:
            if anchor_ref in self._tombstones:
                del self._entries[key]
                return None

        return copy.deepcopy(entry.context)

    def mark_tombstone(self, tenant: str, blob_digest: str) -> None:
        self._tombstones.add((tenant, blob_digest))
        # Remove any entries that contain this tombstone
        to_delete = [
            k for k, v in self._entries.items()
            if (tenant, blob_digest) in v.tombstone_check_anchors
        ]
        for k in to_delete:
            del self._entries[k]

    def invalidate_tenant(self, tenant: str) -> None:
        to_delete = [k for k, v in self._entries.items() if v.tenant == tenant]
        for k in to_delete:
            del self._entries[k]
