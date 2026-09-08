"""Canonical data contracts, models, and errors for ao.v1."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


class ContractError(ValueError):
    """Base error for contract and payload validation failures."""


class ScopeDeniedError(ContractError):
    """Raised when an operation is denied due to permission, tenant, or scope mismatch."""


class StaleVersionError(ContractError):
    """Raised when a generation, CAS head, or version precondition is stale."""


class BudgetExceededError(ContractError):
    """Raised when a token or step budget limit is violated."""


class ActionFenceError(ContractError):
    """Raised when execution fencing or lease verification fails."""


def canonical_json(value: Any) -> str:
    """Serialize value to deterministic canonical JSON (sorted keys, no spaces, no NaN)."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_digest(value: Any) -> str:
    """Compute SHA-256 digest over canonical JSON representation."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_finite_float(val: Any, name: str) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ContractError(f"{name} must be a numeric float")
    f = float(val)
    if not math.isfinite(f):
        raise ContractError(f"{name} must be finite")
    return f


@dataclass(frozen=True, slots=True)
class RevisionBinding:
    """Exact repository, snapshot, and generation tuple."""
    repository: str
    snapshot: str
    generation: str

    def __post_init__(self) -> None:
        if not self.repository or not isinstance(self.repository, str):
            raise ContractError("RevisionBinding.repository must be a non-empty string")
        if not self.snapshot or not isinstance(self.snapshot, str):
            raise ContractError("RevisionBinding.snapshot must be a non-empty string")
        if not self.generation or not isinstance(self.generation, str):
            raise ContractError("RevisionBinding.generation must be a non-empty string")

    def to_dict(self) -> dict[str, str]:
        return {"repository": self.repository, "snapshot": self.snapshot, "generation": self.generation}


@dataclass(frozen=True, slots=True)
class TrustedScope:
    """Host-minted, unforgeable security scope."""
    tenant: str
    principal: str
    acl_epoch: int
    security_context_ref: str
    revisions: tuple[RevisionBinding, ...]
    _is_trusted: bool = field(default=True, repr=False)

    def __post_init__(self) -> None:
        if not self.tenant or not isinstance(self.tenant, str):
            raise ScopeDeniedError("TrustedScope.tenant must be a non-empty string")
        if not self.principal or not isinstance(self.principal, str):
            raise ScopeDeniedError("TrustedScope.principal must be a non-empty string")
        if not isinstance(self.acl_epoch, int) or self.acl_epoch < 0:
            raise ScopeDeniedError("TrustedScope.acl_epoch must be a non-negative integer")
        if not self.security_context_ref or not isinstance(self.security_context_ref, str):
            raise ScopeDeniedError("TrustedScope.security_context_ref must be a non-empty string")
        if not self.revisions or not isinstance(self.revisions, tuple):
            raise ScopeDeniedError("TrustedScope.revisions must be a non-empty tuple of RevisionBinding")
        for r in self.revisions:
            if not isinstance(r, RevisionBinding):
                raise ScopeDeniedError("All revisions must be instances of RevisionBinding")

    @property
    def digest(self) -> str:
        data = {
            "tenant": self.tenant,
            "principal": self.principal,
            "acl_epoch": self.acl_epoch,
            "security_context_ref": self.security_context_ref,
            "revisions": [r.to_dict() for r in self.revisions],
        }
        return canonical_digest(data)


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    """Byte-accurate source location anchor."""
    repository: str
    snapshot: str
    generation: str
    path: str
    blob_digest: str
    start_byte: int
    end_byte: int
    symbol: str

    def __post_init__(self) -> None:
        if not self.repository or not self.snapshot or not self.generation or not self.path:
            raise ContractError("SourceAnchor requires non-empty repository, snapshot, generation, and path")
        if not self.blob_digest or len(self.blob_digest) != 64:
            raise ContractError("SourceAnchor.blob_digest must be a 64-char sha256 hex string")
        if not isinstance(self.start_byte, int) or not isinstance(self.end_byte, int):
            raise ContractError("SourceAnchor byte offsets must be integers")
        if self.start_byte < 0 or self.end_byte < self.start_byte:
            raise ContractError(f"Invalid byte bounds: [{self.start_byte}, {self.end_byte}]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "snapshot": self.snapshot,
            "generation": self.generation,
            "path": self.path,
            "blob_digest": self.blob_digest,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "symbol": self.symbol,
        }


@dataclass(frozen=True, slots=True)
class ContextRequest:
    """Client request for evidence context."""
    request_id: str
    query: str
    mode: str  # 'auto' | 'exact' | 'lexical' | 'hybrid'
    top_k: int
    context_token_budget: int
    snapshot_refs: tuple[str, ...] = field(default_factory=tuple)
    selector: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id or not isinstance(self.request_id, str):
            raise ContractError("request_id must be non-empty string")
        if not isinstance(self.query, str):
            raise ContractError("query must be string")
        if self.mode not in {"auto", "exact", "lexical", "hybrid"}:
            raise ContractError(f"Invalid mode: {self.mode}")
        if not isinstance(self.top_k, int) or not 1 <= self.top_k <= 100:
            raise ContractError(f"top_k must be between 1 and 100, got {self.top_k}")
        if not isinstance(self.context_token_budget, int) or not 1 <= self.context_token_budget <= 128_000:
            raise ContractError(f"context_token_budget must be between 1 and 128000, got {self.context_token_budget}")


@dataclass(frozen=True, slots=True)
class ContextItem:
    """Individual packed evidence piece."""
    anchor: SourceAnchor
    text: str
    truncated: bool
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor.to_dict(),
            "text": self.text,
            "truncated": self.truncated,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    """Structured response containing packaged evidence."""
    status: str  # 'ok' | 'insufficient_evidence' | 'degraded'
    scope_digest: str
    items: tuple[ContextItem, ...]

    def __post_init__(self) -> None:
        if self.status not in {"ok", "insufficient_evidence", "degraded"}:
            raise ContractError(f"Invalid EvidenceContext status: {self.status}")
        if not self.scope_digest or len(self.scope_digest) != 64:
            raise ContractError("scope_digest must be a 64-char sha256 hex string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "scope_digest": self.scope_digest,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True, slots=True)
class ActionIntent:
    """Proposed action intent before gateway dispatch."""
    run_ref: str
    logical_step: str
    base_revision: str
    intent_digest: str
    artifact_ref: str
    budget_ref: str
    verification_plan_ref: str

    def to_dict(self) -> dict[str, str]:
        return {
            "run_ref": self.run_ref,
            "logical_step": self.logical_step,
            "base_revision": self.base_revision,
            "intent_digest": self.intent_digest,
            "artifact_ref": self.artifact_ref,
            "budget_ref": self.budget_ref,
            "verification_plan_ref": self.verification_plan_ref,
        }


@dataclass(frozen=True, slots=True)
class Receipt:
    """Committed execution receipt from gateway."""
    action_id: str
    state: str  # 'SUCCEEDED' | 'FAILED' | 'UNKNOWN_RESULT'
    receipt_ref: str | None = None

    def __post_init__(self) -> None:
        if self.state not in {"SUCCEEDED", "FAILED", "UNKNOWN_RESULT"}:
            raise ContractError(f"Invalid receipt state: {self.state}")

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {"action_id": self.action_id, "state": self.state}
        if self.receipt_ref is not None:
            res["receipt_ref"] = self.receipt_ref
        return res
