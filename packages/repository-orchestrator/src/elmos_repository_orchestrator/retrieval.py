"""Versioned, tenant-safe hybrid retrieval with source provenance.

The in-process index is the deterministic reference implementation used for
contract tests and small repositories. External projections implement the same
contracts and remain disposable: immutable source records are authoritative.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .contracts import ContractError, canonical_json, require_string, sha256_payload


_WORD = re.compile(r"[\w]+", re.UNICODE)
_CJK = re.compile(r"[\u3400-\u9fff]+")


def tokenize(text: str) -> tuple[str, ...]:
    """Tokenize Latin identifiers and CJK unigrams/bigrams deterministically."""

    value = require_string(text, "text").casefold()
    tokens = [token for token in _WORD.findall(value) if not _CJK.fullmatch(token)]
    for run in _CJK.findall(value):
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tuple(tokens)


def _vector(value: Sequence[float] | None, field_name: str) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes, bytearray)) or not value:
        raise ContractError("invalid_vector", f"{field_name} must be a non-empty numeric array")
    parsed: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ContractError("invalid_vector", f"{field_name} contains a non-numeric value")
        number = float(item)
        if not math.isfinite(number):
            raise ContractError("invalid_vector", f"{field_name} contains a non-finite value")
        parsed.append(number)
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class SourceAnchor:
    uri: str
    kind: str
    content_sha256: str
    start: int | None = None
    end: int | None = None
    locator: Mapping[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_string(self.uri, "anchor.uri")
        require_string(self.kind, "anchor.kind")
        if not self.content_sha256.startswith("sha256:") or len(self.content_sha256) != 71:
            raise ContractError("invalid_anchor_digest", "anchor.content_sha256 must be a prefixed SHA-256")
        if (self.start is None) != (self.end is None):
            raise ContractError("invalid_anchor_range", "anchor range requires both start and end")
        if self.start is not None and (self.start < 0 or self.end is None or self.end < self.start):
            raise ContractError("invalid_anchor_range", "anchor range is invalid")
        for key, value in self.locator.items():
            require_string(key, "anchor.locator.key")
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ContractError("invalid_anchor_locator", "anchor locator values must be scalar")
            if isinstance(value, float) and not math.isfinite(value):
                raise ContractError("invalid_anchor_locator", "anchor locator values must be finite")


@dataclass(frozen=True, slots=True)
class SearchDocument:
    document_id: str
    tenant_id: str
    project_id: str
    revision_id: str
    content: str
    anchor: SourceAnchor
    allowed_principals: frozenset[str]
    vector: tuple[float, ...] | None = None
    modality: str = "text"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    _document_digest: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in ("document_id", "tenant_id", "project_id", "revision_id", "content", "modality"):
            require_string(getattr(self, field_name), field_name)
        if not self.allowed_principals:
            raise ContractError("missing_acl", "allowed_principals must not be empty")
        for principal in self.allowed_principals:
            require_string(principal, "allowed_principals[]")
        object.__setattr__(self, "vector", _vector(self.vector, "vector"))
        object.__setattr__(
            self,
            "_document_digest",
            sha256_payload(
                {
                    "identity": self.identity,
                    "content": self.content,
                    "anchor": self.anchor,
                    "acl": sorted(self.allowed_principals),
                    "vector": self.vector,
                    "modality": self.modality,
                    "metadata": self.metadata,
                }
            ),
        )

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.project_id, self.revision_id, self.document_id

    @property
    def digest(self) -> str:
        return self._document_digest


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    tenant_id: str
    project_id: str
    revision_id: str
    principal_ids: frozenset[str]
    text: str
    vector: tuple[float, ...] | None = None
    top_k: int = 10
    modalities: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "revision_id", "text"):
            require_string(getattr(self, field_name), field_name)
        if not self.principal_ids:
            raise ContractError("missing_principal", "principal_ids must not be empty")
        if not 1 <= self.top_k <= 100:
            raise ContractError("invalid_top_k", "top_k must be between 1 and 100")
        object.__setattr__(self, "vector", _vector(self.vector, "query.vector"))


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    document: SearchDocument
    score: float
    lexical_rank: int | None
    vector_rank: int | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "document_id": self.document.document_id,
            "score": self.score,
            "lexical_rank": self.lexical_rank,
            "vector_rank": self.vector_rank,
            "tenant_id": self.document.tenant_id,
            "project_id": self.document.project_id,
            "revision_id": self.document.revision_id,
            "allowed_principals": sorted(self.document.allowed_principals),
            "modality": self.document.modality,
            "anchor": {
                "uri": self.document.anchor.uri,
                "kind": self.document.anchor.kind,
                "content_sha256": self.document.anchor.content_sha256,
                "start": self.document.anchor.start,
                "end": self.document.anchor.end,
                "locator": dict(self.document.anchor.locator),
            },
            "metadata": dict(self.document.metadata),
        }


class HybridIndex:
    """Reference BM25 + cosine RRF index with hard scope filters."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str, str, str], SearchDocument] = {}
        self._digests: dict[tuple[str, str, str, str], str] = {}
        self._terms: dict[tuple[str, str, str, str], Counter[str]] = {}
        self._lengths: dict[tuple[str, str, str, str], int] = {}
        self._unit_vectors: dict[tuple[str, str, str, str], tuple[float, ...]] = {}
        self._scope_ids: dict[tuple[str, str, str], set[tuple[str, str, str, str]]] = defaultdict(set)
        self._postings: dict[str, set[tuple[str, str, str, str]]] = defaultdict(set)

    def _remove_indexes(self, key: tuple[str, str, str, str]) -> None:
        existing = self._documents.get(key)
        if existing is None:
            return
        self._scope_ids[key[:3]].discard(key)
        for term in self._terms.get(key, ()):
            self._postings[term].discard(key)
            if not self._postings[term]:
                del self._postings[term]
        self._terms.pop(key, None)
        self._lengths.pop(key, None)
        self._unit_vectors.pop(key, None)

    def upsert(self, documents: Iterable[SearchDocument]) -> tuple[int, int]:
        inserted = unchanged = 0
        for document in documents:
            key = document.identity
            digest = document.digest
            if self._digests.get(key) == digest:
                unchanged += 1
                continue
            self._remove_indexes(key)
            self._documents[key] = document
            self._digests[key] = digest
            terms = Counter(tokenize(document.content))
            self._terms[key] = terms
            self._lengths[key] = sum(terms.values())
            if document.vector is not None:
                norm = math.sqrt(sum(item * item for item in document.vector))
                self._unit_vectors[key] = tuple(0.0 for _ in document.vector) if norm == 0 else tuple(
                    item / norm for item in document.vector
                )
            self._scope_ids[key[:3]].add(key)
            for term in terms:
                self._postings[term].add(key)
            inserted += 1
        return inserted, unchanged

    def delete_revision(self, *, tenant_id: str, project_id: str, revision_id: str) -> int:
        scope = (tenant_id, project_id, revision_id)
        keys = [key for key in self._documents if key[:3] == scope]
        for key in keys:
            self._remove_indexes(key)
            del self._documents[key]
            del self._digests[key]
        self._scope_ids.pop(scope, None)
        return len(keys)

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            raise ContractError("vector_dimension_mismatch", "query and document vectors have different dimensions")
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(item * item for item in left))
        right_norm = math.sqrt(sum(item * item for item in right))
        return 0.0 if left_norm == 0 or right_norm == 0 else dot / (left_norm * right_norm)

    def _visible_ids(self, query: RetrievalQuery) -> set[tuple[str, str, str, str]]:
        scope = (query.tenant_id, query.project_id, query.revision_id)
        return {
            key
            for key in self._scope_ids.get(scope, ())
            if bool(self._documents[key].allowed_principals & query.principal_ids)
            and (not query.modalities or self._documents[key].modality in query.modalities)
        }

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        visible_ids = self._visible_ids(query)
        if not visible_ids:
            return ()
        query_terms = Counter(tokenize(query.text))
        avg_length = sum(self._lengths[key] for key in visible_ids) / len(visible_ids)
        frequencies = {
            term: len(self._postings.get(term, set()) & visible_ids)
            for term in query_terms
        }
        lexical_scores: dict[tuple[str, str, str, str], float] = defaultdict(float)
        k1, b = 1.2, 0.75
        for term, query_frequency in query_terms.items():
            for key in self._postings.get(term, set()) & visible_ids:
                terms = self._terms[key]
                length = self._lengths[key]
                term_frequency = terms[term]
                inverse = math.log(1 + (len(visible_ids) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                denominator = term_frequency + k1 * (1 - b + b * length / max(avg_length, 1))
                lexical_scores[key] += query_frequency * inverse * term_frequency * (k1 + 1) / denominator
        lexical = sorted(
            (self._documents[key] for key in lexical_scores if lexical_scores[key] > 0),
            key=lambda item: (-lexical_scores[item.identity], item.document_id),
        )
        vector_scores: dict[tuple[str, str, str, str], float] = {}
        if query.vector is not None:
            query_norm = math.sqrt(sum(item * item for item in query.vector))
            unit_query = tuple(0.0 for _ in query.vector) if query_norm == 0 else tuple(
                item / query_norm for item in query.vector
            )
            for key in visible_ids:
                document = self._documents[key]
                if document.vector is not None:
                    if len(unit_query) != len(self._unit_vectors[key]):
                        raise ContractError("vector_dimension_mismatch", "query and document vectors have different dimensions")
                    vector_scores[document.identity] = sum(
                        left * right for left, right in zip(unit_query, self._unit_vectors[key])
                    )
        vectors = sorted(
            (self._documents[key] for key in vector_scores),
            key=lambda item: (-vector_scores[item.identity], item.document_id),
        )
        lexical_rank = {item.identity: rank for rank, item in enumerate(lexical, 1)}
        vector_rank = {item.identity: rank for rank, item in enumerate(vectors, 1)}
        combined: list[RetrievalHit] = []
        for key in visible_ids:
            document = self._documents[key]
            lr = lexical_rank.get(document.identity)
            vr = vector_rank.get(document.identity)
            if lr is None and vr is None:
                continue
            score = (0.0 if lr is None else 1.0 / (60 + lr)) + (0.0 if vr is None else 1.0 / (60 + vr))
            combined.append(RetrievalHit(document=document, score=score, lexical_rank=lr, vector_rank=vr))
        combined.sort(key=lambda item: (-item.score, item.document.document_id))
        unique: list[RetrievalHit] = []
        seen_anchors: set[tuple[object, ...]] = set()
        for hit in combined:
            anchor = hit.document.anchor
            anchor_key = (anchor.uri, anchor.kind, anchor.content_sha256, anchor.start, anchor.end, canonical_json(anchor.locator))
            if anchor_key in seen_anchors:
                continue
            seen_anchors.add(anchor_key)
            unique.append(hit)
            if len(unique) == query.top_k:
                break
        return tuple(unique)


def recall_at_k(actual: Sequence[str], relevant: frozenset[str], *, k: int = 10) -> float:
    if not relevant:
        raise ContractError("missing_relevance_judgments", "relevant set must not be empty")
    return len(set(actual[:k]) & relevant) / len(relevant)


def ndcg_at_k(actual: Sequence[str], relevance: Mapping[str, float], *, k: int = 10) -> float:
    gains = [float(relevance.get(identity, 0.0)) for identity in actual[:k]]
    dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted((float(value) for value in relevance.values()), reverse=True)[:k]
    idcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal))
    return 0.0 if idcg == 0 else dcg / idcg
