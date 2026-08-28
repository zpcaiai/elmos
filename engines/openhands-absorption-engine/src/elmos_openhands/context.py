"""Evidence-aware context retrieval and deterministic token packing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .errors import ContractViolation, TenantIsolationError
from .models import Identity, digest_of


@dataclass(frozen=True, slots=True)
class ContextCandidate:
    candidate_id: str
    tenant_id: str
    source: str
    text: str
    relevance: float = 0.0
    freshness: float = 1.0
    security_label: str = "internal"
    must_retain: bool = False
    provenance: Mapping[str, Any] = field(default_factory=dict)
    conflict_key: str | None = None

    def __post_init__(self) -> None:
        if self.tenant_id == "" or not self.candidate_id or not self.source or not self.text:
            raise ContractViolation("context candidate identity and text are required")
        if not 0 <= self.relevance <= 1 or not 0 <= self.freshness <= 1:
            raise ContractViolation("context relevance/freshness must be in [0,1]")
        if self.security_label not in {"public", "internal", "confidential", "restricted"}:
            raise ContractViolation("unknown context security label")

    def as_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "tenant_id": self.tenant_id, "source": self.source, "text": self.text, "relevance": self.relevance, "freshness": self.freshness, "security_label": self.security_label, "must_retain": self.must_retain, "provenance": dict(self.provenance or {}), "conflict_key": self.conflict_key}


@dataclass(frozen=True, slots=True)
class ContextView:
    role: str
    candidates: tuple[ContextCandidate, ...]
    estimated_tokens: int
    fingerprint: str
    dropped_candidates: tuple[str, ...]
    explanations: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "candidates": [candidate.as_dict() for candidate in self.candidates], "estimated_tokens": self.estimated_tokens, "fingerprint": self.fingerprint, "dropped_candidates": list(self.dropped_candidates), "explanations": dict(self.explanations)}


class ContextEngine:
    MUST_RETAIN_MARKERS = ("acceptance", "must", "forbidden", "security", "failed", "error", "destructive", "migration")

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], ContextView] = {}

    def build(self, identity: Identity, role: str, candidates: Iterable[ContextCandidate], *, max_tokens: int, query: str = "") -> ContextView:
        if max_tokens <= 0:
            raise ContractViolation("context token budget must be positive")
        source = [candidate for candidate in candidates]
        if any(candidate.tenant_id != identity.tenant_id for candidate in source):
            raise TenantIsolationError("context candidate belongs to another tenant")
        normalized = [self._classify(candidate) for candidate in source]
        key = (identity.tenant_id + ":" + identity.project_id, digest_of([candidate.as_dict() for candidate in normalized]) + ":" + query, max_tokens)
        if key in self._cache:
            return self._cache[key]
        unique: dict[str, ContextCandidate] = {}
        for candidate in normalized:
            unique.setdefault(digest_of(candidate.text), candidate)
        ranked = sorted(unique.values(), key=lambda candidate: (not candidate.must_retain, -(candidate.relevance * 0.65 + candidate.freshness * 0.35), candidate.candidate_id))
        selected: list[ContextCandidate] = []
        dropped: list[str] = []
        explanations: dict[str, str] = {}
        used = 0
        for candidate in ranked:
            cost = estimate_tokens(candidate.text)
            if candidate.must_retain and used + cost > max_tokens:
                raise ContractViolation("context budget is too small to retain a mandatory fact")
            if used + cost > max_tokens:
                dropped.append(candidate.candidate_id)
                continue
            selected.append(candidate)
            used += cost
            explanations[candidate.candidate_id] = "must-retain" if candidate.must_retain else f"relevance={candidate.relevance:.2f};freshness={candidate.freshness:.2f}"
        view = ContextView(role, tuple(selected), used, digest_of({"role": role, "candidates": [candidate.as_dict() for candidate in selected]}), tuple(dropped), explanations)
        self._cache[key] = view
        return view

    @classmethod
    def _classify(cls, candidate: ContextCandidate) -> ContextCandidate:
        lowered = candidate.text.lower()
        must = candidate.must_retain or any(marker in lowered for marker in cls.MUST_RETAIN_MARKERS)
        return ContextCandidate(candidate.candidate_id, candidate.tenant_id, candidate.source, candidate.text, candidate.relevance, candidate.freshness, candidate.security_label, must, candidate.provenance or {}, candidate.conflict_key)


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return max(1, cjk + max(0, len(text) - cjk) // 4)
