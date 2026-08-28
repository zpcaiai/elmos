"""Evidence-aware context retrieval and deterministic token packing."""

from __future__ import annotations

import re
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol

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
    fact_type: str = "general"
    observed_at_epoch: float = 0.0
    expires_at_epoch: float | None = None

    def __post_init__(self) -> None:
        if self.tenant_id == "" or not self.candidate_id or not self.source or not self.text:
            raise ContractViolation("context candidate identity and text are required")
        if not 0 <= self.relevance <= 1 or not 0 <= self.freshness <= 1:
            raise ContractViolation("context relevance/freshness must be in [0,1]")
        if self.security_label not in {"public", "internal", "confidential", "restricted"}:
            raise ContractViolation("unknown context security label")
        if self.fact_type not in {"general", "requirement", "dependency", "symbol", "diff", "git_history", "event", "failed_test", "security_policy", "decision"}:
            raise ContractViolation("unknown context fact type")
        if self.expires_at_epoch is not None and self.expires_at_epoch <= self.observed_at_epoch:
            raise ContractViolation("context expiry must be after observation")

    def as_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "tenant_id": self.tenant_id, "source": self.source, "text": self.text, "relevance": self.relevance, "freshness": self.freshness, "security_label": self.security_label, "must_retain": self.must_retain, "provenance": dict(self.provenance or {}), "conflict_key": self.conflict_key, "fact_type": self.fact_type, "observed_at_epoch": self.observed_at_epoch, "expires_at_epoch": self.expires_at_epoch}


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
        return ContextCandidate(candidate.candidate_id, candidate.tenant_id, candidate.source, candidate.text, candidate.relevance, candidate.freshness, candidate.security_label, must, candidate.provenance or {}, candidate.conflict_key, candidate.fact_type, candidate.observed_at_epoch, candidate.expires_at_epoch)


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    return max(1, cjk + max(0, len(text) - cjk) // 4)


SECURITY_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


@dataclass(frozen=True, slots=True)
class ContextRolePolicy:
    role: str
    allowed_sources: frozenset[str]
    allowed_fact_types: frozenset[str]
    max_security_label: str
    minimum_freshness: float = 0.0
    source_weights: Mapping[str, float] = field(default_factory=dict)
    must_retain_types: frozenset[str] = frozenset({"requirement", "failed_test", "security_policy"})

    def __post_init__(self) -> None:
        if not self.role or self.max_security_label not in SECURITY_RANK or not 0 <= self.minimum_freshness <= 1:
            raise ContractViolation("context role policy is invalid")
        if any(value < 0 for value in self.source_weights.values()):
            raise ContractViolation("context source weights cannot be negative")


class ContextSource(Protocol):
    name: str

    def collect(self, identity: Identity, query: str) -> Iterable[ContextCandidate]: ...


class ContextSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, ContextSource] = {}

    def register(self, source: ContextSource) -> None:
        if not source.name or source.name in self._sources:
            raise ContractViolation("context source is absent or duplicated")
        self._sources[source.name] = source

    def collect(self, identity: Identity, query: str, names: Iterable[str]) -> tuple[ContextCandidate, ...]:
        result: list[ContextCandidate] = []
        for name in sorted(set(names)):
            source = self._sources.get(name)
            if source is None:
                raise ContractViolation("context source is not registered: " + name)
            values = tuple(source.collect(identity, query))
            if any(item.source != name or item.tenant_id != identity.tenant_id for item in values):
                raise TenantIsolationError("context source returned an invalid scope or identity")
            result.extend(values)
        return tuple(result)


class PersistentContextStore:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS context_candidates(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,candidate_id TEXT NOT NULL,digest TEXT NOT NULL,body_json TEXT NOT NULL,updated_at REAL NOT NULL,PRIMARY KEY(tenant_id,project_id,candidate_id));
               CREATE TABLE IF NOT EXISTS context_views(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,fingerprint TEXT NOT NULL,role TEXT NOT NULL,model TEXT NOT NULL,token_count INTEGER NOT NULL,body_json TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(tenant_id,project_id,fingerprint));
               CREATE TABLE IF NOT EXISTS context_outcomes(tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,fingerprint TEXT NOT NULL,outcome TEXT NOT NULL,score REAL NOT NULL,recorded_at REAL NOT NULL);"""
        )

    def close(self) -> None:
        self._connection.close()

    def put_candidates(self, identity: Identity, candidates: Iterable[ContextCandidate]) -> None:
        for candidate in candidates:
            if candidate.tenant_id != identity.tenant_id:
                raise TenantIsolationError("context persistence tenant mismatch")
            body = candidate.as_dict()
            digest = digest_of(body)
            existing = self._connection.execute("SELECT digest FROM context_candidates WHERE tenant_id=? AND project_id=? AND candidate_id=?", (identity.tenant_id, identity.project_id, candidate.candidate_id)).fetchone()
            if existing is not None and existing["digest"] == digest:
                continue
            self._connection.execute("INSERT INTO context_candidates VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id,project_id,candidate_id) DO UPDATE SET digest=excluded.digest,body_json=excluded.body_json,updated_at=excluded.updated_at", (identity.tenant_id, identity.project_id, candidate.candidate_id, digest, json.dumps(body, sort_keys=True), time.time()))

    def put_view(self, identity: Identity, view: "EvidenceContextView") -> None:
        self._connection.execute("INSERT OR IGNORE INTO context_views VALUES(?,?,?,?,?,?,?,?)", (identity.tenant_id, identity.project_id, view.fingerprint, view.role, view.model, view.estimated_tokens, json.dumps(view.as_dict(), sort_keys=True), time.time()))

    def record_outcome(self, identity: Identity, fingerprint: str, outcome: str, score: float) -> None:
        if outcome not in {"success", "failure", "blocked"} or not 0 <= score <= 1:
            raise ContractViolation("context outcome is invalid")
        self._connection.execute("INSERT INTO context_outcomes VALUES(?,?,?,?,?,?)", (identity.tenant_id, identity.project_id, fingerprint, outcome, score, time.time()))

    def historical_score(self, identity: Identity, candidate_id: str) -> float:
        rows = self._connection.execute("SELECT v.body_json,o.score FROM context_views v JOIN context_outcomes o ON v.tenant_id=o.tenant_id AND v.project_id=o.project_id AND v.fingerprint=o.fingerprint WHERE v.tenant_id=? AND v.project_id=?", (identity.tenant_id, identity.project_id)).fetchall()
        scores = [float(row["score"]) for row in rows if candidate_id in json.loads(row["body_json"]).get("candidate_ids", [])]
        return sum(scores) / len(scores) if scores else 0.5


@dataclass(frozen=True, slots=True)
class EvidenceContextView:
    role: str
    model: str
    candidates: tuple[ContextCandidate, ...]
    estimated_tokens: int
    fingerprint: str
    dropped_candidates: tuple[str, ...]
    conflict_decisions: Mapping[str, str]
    explanations: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "model": self.model, "candidate_ids": [item.candidate_id for item in self.candidates], "candidates": [item.as_dict() for item in self.candidates], "estimated_tokens": self.estimated_tokens, "fingerprint": self.fingerprint, "dropped_candidates": list(self.dropped_candidates), "conflict_decisions": dict(self.conflict_decisions), "explanations": dict(self.explanations)}


class EvidenceAwareContextEngine:
    def __init__(self, policies: Iterable[ContextRolePolicy], store: PersistentContextStore, *, token_estimators: Mapping[str, Callable[[str], int]] | None = None) -> None:
        self.policies = {policy.role: policy for policy in policies}
        self.store = store
        self.token_estimators = dict(token_estimators or {})

    def build(self, identity: Identity, *, role: str, model: str, candidates: Iterable[ContextCandidate], query: str, max_tokens: int, now: float | None = None) -> EvidenceContextView:
        now = time.time() if now is None else now
        policy = self.policies.get(role)
        if policy is None or max_tokens <= 0:
            raise ContractViolation("context role policy and positive token budget are required")
        values = tuple(candidates)
        if any(item.tenant_id != identity.tenant_id for item in values):
            raise TenantIsolationError("context candidate belongs to another tenant")
        self.store.put_candidates(identity, values)
        eligible: list[ContextCandidate] = []
        dropped: list[str] = []
        for item in values:
            expired = item.expires_at_epoch is not None and item.expires_at_epoch <= now
            if item.source not in policy.allowed_sources or item.fact_type not in policy.allowed_fact_types or SECURITY_RANK[item.security_label] > SECURITY_RANK[policy.max_security_label] or item.freshness < policy.minimum_freshness or expired:
                dropped.append(item.candidate_id)
                continue
            must = item.must_retain or item.fact_type in policy.must_retain_types
            eligible.append(ContextCandidate(item.candidate_id, item.tenant_id, item.source, item.text, item.relevance, item.freshness, item.security_label, must, item.provenance, item.conflict_key, item.fact_type, item.observed_at_epoch, item.expires_at_epoch))
        resolved, conflicts = self._resolve_conflicts(eligible)
        query_tokens = set(re.findall(r"[\w.-]+", query.lower()))
        estimator = self.token_estimators.get(model, estimate_tokens)
        ranked = sorted(resolved, key=lambda item: (not item.must_retain, -self._score(identity, item, query_tokens, policy), item.candidate_id))
        selected: list[ContextCandidate] = []
        explanations: dict[str, str] = {}
        used = 0
        for item in ranked:
            cost = max(1, int(estimator(item.text)))
            if used + cost > max_tokens:
                if item.must_retain:
                    raise ContractViolation("context token budget cannot retain mandatory evidence")
                dropped.append(item.candidate_id)
                continue
            score = self._score(identity, item, query_tokens, policy)
            selected.append(item)
            used += cost
            explanations[item.candidate_id] = f"role={role};source={item.source};fact={item.fact_type};score={score:.4f};must_retain={str(item.must_retain).lower()}"
        body = {"identity": identity.scope(), "role": role, "model": model, "candidate_digests": [digest_of(item.as_dict()) for item in selected], "tokens": used, "conflicts": conflicts}
        view = EvidenceContextView(role, model, tuple(selected), used, digest_of(body), tuple(sorted(set(dropped))), conflicts, explanations)
        self.store.put_view(identity, view)
        return view

    def _score(self, identity: Identity, item: ContextCandidate, query_tokens: set[str], policy: ContextRolePolicy) -> float:
        text_tokens = set(re.findall(r"[\w.-]+", item.text.lower()))
        semantic = len(query_tokens & text_tokens) / max(1, len(query_tokens))
        history = self.store.historical_score(identity, item.candidate_id)
        source_weight = policy.source_weights.get(item.source, 1.0)
        return source_weight * (item.relevance * 0.35 + item.freshness * 0.2 + semantic * 0.3 + history * 0.15)

    @staticmethod
    def _resolve_conflicts(values: Iterable[ContextCandidate]) -> tuple[tuple[ContextCandidate, ...], dict[str, str]]:
        ungrouped: list[ContextCandidate] = []
        grouped: dict[str, list[ContextCandidate]] = {}
        for item in values:
            if item.conflict_key is None:
                ungrouped.append(item)
            else:
                grouped.setdefault(item.conflict_key, []).append(item)
        decisions: dict[str, str] = {}
        for key, candidates in grouped.items():
            texts = {candidate.text for candidate in candidates}
            ranked = sorted(candidates, key=lambda item: (-item.observed_at_epoch, -item.freshness, -item.relevance, item.candidate_id))
            winner = ranked[0]
            if len(texts) > 1 and sum(candidate.must_retain for candidate in candidates) > 1 and ranked[0].observed_at_epoch == ranked[1].observed_at_epoch:
                raise ContractViolation("mandatory context conflict is unresolved: " + key)
            ungrouped.append(winner)
            decisions[key] = f"selected={winner.candidate_id};superseded={','.join(item.candidate_id for item in ranked[1:])}"
        return tuple(ungrouped), decisions


@dataclass(frozen=True, slots=True)
class ContextBenchmarkResult:
    dependency_recall: float
    failed_test_retention: float
    stale_context_rate: float
    status: str
    digest: str


class ContextBenchmark:
    def evaluate(self, view: EvidenceContextView, *, expected_dependencies: Iterable[str], expected_failed_tests: Iterable[str], stale_ids: Iterable[str]) -> ContextBenchmarkResult:
        selected = {item.candidate_id for item in view.candidates}
        dependencies = set(expected_dependencies)
        failures = set(expected_failed_tests)
        stale = set(stale_ids)
        dependency_recall = len(selected & dependencies) / max(1, len(dependencies))
        failed_retention = len(selected & failures) / max(1, len(failures))
        stale_rate = len(selected & stale) / max(1, len(selected))
        status = "PASS" if dependency_recall >= 0.9 and failed_retention == 1.0 and stale_rate <= 0.01 else "FAIL"
        body = {"dependency_recall": dependency_recall, "failed_test_retention": failed_retention, "stale_context_rate": stale_rate, "status": status, "view": view.fingerprint}
        return ContextBenchmarkResult(dependency_recall, failed_retention, stale_rate, status, digest_of(body))
