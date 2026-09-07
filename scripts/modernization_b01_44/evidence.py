#!/usr/bin/env python3
"""Evidence records, the evidence graph, and dual-run reconciliation.

Two rules are enforced mechanically here rather than by convention:

* *A model claim is not evidence.*  ``trust_level: model-inferred`` never
  satisfies an obligation when the package's ``evidence-first`` policy says
  ``model_claim_is_evidence: false``.
* *Unknown must be preserved.*  Reconciliation returns unknowns as a distinct
  bucket; it cannot collapse them into "match".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from scripts.modernization_b01_44.canonical import (
    canonical_bytes,
    digest,
    format_instant,
    is_digest,
    parse_instant,
    stable_sort,
)
from scripts.modernization_b01_44.errors import (
    EvidenceExpired,
    EvidenceMissing,
    RuntimeRefusal,
)

#: Trust levels ordered from weakest to strongest.
TRUST_ORDER = (
    "unknown",
    "model-inferred",
    "measured",
    "runtime-observed",
    "deterministic",
    "compiler-confirmed",
    "human-approved",
    "independent-verified",
)

#: Levels that can never discharge an execution obligation on their own.
NON_EXECUTION_TRUST = frozenset({"unknown", "model-inferred"})


def trust_rank(level: str) -> int:
    try:
        return TRUST_ORDER.index(level)
    except ValueError:
        raise RuntimeRefusal("unknown trust level", trust_level=level) from None


@dataclass(frozen=True)
class Evidence:
    """One piece of evidence, addressed by the digest of what produced it."""

    evidence_id: str
    digest: str
    producer: str
    created_at: str
    trust_level: str
    scope: str
    expires_at: str | None = None
    inputs: tuple[str, ...] = ()

    def as_ref(self) -> dict[str, Any]:
        ref: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "digest": self.digest,
            "producer": self.producer,
            "created_at": self.created_at,
            "trust_level": self.trust_level,
            "scope": self.scope,
        }
        if self.expires_at is not None:
            ref["expires_at"] = self.expires_at
        return ref

    def is_expired(self, now: datetime) -> bool:
        if self.expires_at is None:
            return False
        return parse_instant(self.expires_at, "expires_at") <= now

    def is_execution_grade(self) -> bool:
        return self.trust_level not in NON_EXECUTION_TRUST


def make_evidence(
    *,
    evidence_id: str,
    producer: str,
    created_at: datetime | str,
    trust_level: str,
    scope: str,
    payload: Any,
    ttl: timedelta | None = None,
    inputs: Iterable[str] = (),
) -> Evidence:
    """Create evidence whose digest is the content address of ``payload``.

    The digest is computed, never accepted from the caller, so evidence cannot
    claim to attest to something it did not observe.
    """

    trust_rank(trust_level)
    created = created_at if isinstance(created_at, datetime) else parse_instant(created_at, "created_at")
    created = created.astimezone(timezone.utc)
    expires = format_instant(created + ttl) if ttl is not None else None
    return Evidence(
        evidence_id=evidence_id,
        digest=digest(payload),
        producer=producer,
        created_at=format_instant(created),
        trust_level=trust_level,
        scope=scope,
        expires_at=expires,
        inputs=tuple(stable_sort(inputs)),
    )


class EvidenceStore:
    """Append-only evidence index with an explicit invalidation edge."""

    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._invalidated: dict[str, str] = {}

    def __contains__(self, evidence_id: object) -> bool:
        return evidence_id in self._items

    def __len__(self) -> int:
        return len(self._items)

    def add(self, evidence: Evidence) -> Evidence:
        existing = self._items.get(evidence.evidence_id)
        if existing is not None:
            if existing != evidence:
                raise RuntimeRefusal(
                    "evidence is append-only and cannot be redefined",
                    evidence_id=evidence.evidence_id,
                )
            return existing
        if not is_digest(evidence.digest):
            raise RuntimeRefusal("evidence digest is malformed", evidence_id=evidence.evidence_id)
        self._items[evidence.evidence_id] = evidence
        return evidence

    def get(self, evidence_id: str) -> Evidence:
        try:
            return self._items[evidence_id]
        except KeyError:
            raise EvidenceMissing("evidence is not present", evidence_id=evidence_id) from None

    def invalidate(self, evidence_id: str, reason: str) -> None:
        self.get(evidence_id)
        self._invalidated[evidence_id] = reason

    def invalidation_reason(self, evidence_id: str) -> str | None:
        return self._invalidated.get(evidence_id)

    def ids(self) -> list[str]:
        return sorted(self._items)

    def resolve(
        self,
        evidence_ids: Iterable[str],
        *,
        now: datetime,
        require_execution_grade: bool = True,
        scope: str | None = None,
    ) -> list[Evidence]:
        """Return usable evidence or refuse with the precise reason."""

        resolved: list[Evidence] = []
        for evidence_id in evidence_ids:
            item = self.get(evidence_id)
            reason = self._invalidated.get(evidence_id)
            if reason is not None:
                raise EvidenceMissing(
                    "evidence has been invalidated", evidence_id=evidence_id, reason=reason
                )
            if item.is_expired(now):
                raise EvidenceExpired(
                    "evidence has expired",
                    evidence_id=evidence_id,
                    expires_at=item.expires_at,
                    now=format_instant(now),
                )
            if require_execution_grade and not item.is_execution_grade():
                raise EvidenceMissing(
                    "evidence is not execution grade",
                    evidence_id=evidence_id,
                    trust_level=item.trust_level,
                )
            if scope is not None and item.scope != scope:
                raise EvidenceMissing(
                    "evidence scope does not cover the request",
                    evidence_id=evidence_id,
                    evidence_scope=item.scope,
                    requested_scope=scope,
                )
            resolved.append(item)
        return resolved

    def expiring_before(self, moment: datetime) -> list[Evidence]:
        return [item for item in self._items.values() if item.is_expired(moment)]


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


@dataclass
class LineageGraph:
    """Directed evidence lineage with cycle detection and downstream sweep."""

    edges: dict[str, set[str]] = field(default_factory=dict)

    def link(self, downstream: str, upstream: str) -> None:
        if downstream == upstream:
            raise RuntimeRefusal("lineage self-edge", node=downstream)
        self.edges.setdefault(downstream, set()).add(upstream)
        self.edges.setdefault(upstream, set())
        if self._reaches(upstream, downstream):
            self.edges[downstream].discard(upstream)
            raise RuntimeRefusal("lineage cycle", downstream=downstream, upstream=upstream)

    def _reaches(self, start: str, target: str) -> bool:
        seen: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node in seen:
                continue
            seen.add(node)
            stack.extend(self.edges.get(node, ()))
        return False

    def upstream_closure(self, node: str) -> list[str]:
        seen: set[str] = set()
        stack = list(self.edges.get(node, ()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.edges.get(current, ()))
        return sorted(seen)

    def downstream_of(self, node: str) -> list[str]:
        """Everything that (transitively) depends on ``node``."""

        affected: set[str] = set()
        changed = True
        while changed:
            changed = False
            for downstream, upstreams in self.edges.items():
                if downstream in affected:
                    continue
                if node in upstreams or upstreams & affected:
                    affected.add(downstream)
                    changed = True
        return sorted(affected)


# ---------------------------------------------------------------------------
# Dual run reconciliation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    matched: tuple[str, ...]
    mismatched: tuple[str, ...]
    unknown: tuple[str, ...]
    only_source: tuple[str, ...]
    only_target: tuple[str, ...]

    @property
    def denominator(self) -> int:
        """Explicit denominator: every key considered, including unknowns."""

        return (
            len(self.matched)
            + len(self.mismatched)
            + len(self.unknown)
            + len(self.only_source)
            + len(self.only_target)
        )

    @property
    def reconciled(self) -> bool:
        return not (self.mismatched or self.unknown or self.only_source or self.only_target)

    def as_dict(self) -> dict[str, Any]:
        return {
            "matched": list(self.matched),
            "mismatched": list(self.mismatched),
            "unknown": list(self.unknown),
            "only_source": list(self.only_source),
            "only_target": list(self.only_target),
            "denominator": self.denominator,
            "reconciled": self.reconciled,
        }


UNKNOWN = object()
"""Sentinel for a value the dual run could not observe."""


def reconcile(source: dict[str, Any], target: dict[str, Any]) -> ReconciliationResult:
    """Compare two runs without ever collapsing an unknown into a match."""

    matched: list[str] = []
    mismatched: list[str] = []
    unknown: list[str] = []
    for key in sorted(set(source) & set(target)):
        left, right = source[key], target[key]
        if left is UNKNOWN or right is UNKNOWN:
            unknown.append(key)
        elif canonical_bytes(left) == canonical_bytes(right):
            matched.append(key)
        else:
            mismatched.append(key)
    return ReconciliationResult(
        matched=tuple(matched),
        mismatched=tuple(mismatched),
        unknown=tuple(unknown),
        only_source=tuple(sorted(set(source) - set(target))),
        only_target=tuple(sorted(set(target) - set(source))),
    )
