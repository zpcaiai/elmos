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

    def __post_init__(self) -> None:
        require_string(self.uri, "anchor.uri")
        require_string(self.kind, "anchor.kind")
        if not self.content_sha256.startswith("sha256:") or len(self.content_sha256) != 71:
            raise ContractError("invalid_anchor_digest", "anchor.content_sha256 must be a prefixed SHA-256")
        if (self.start is None) != (self.end is None):
            raise ContractError("invalid_anchor_range", "anchor range requires both start and end")
        if self.start is not None and (self.start < 0 or self.end is None or self.end < self.start):
            raise ContractError("invalid_anchor_range", "anchor range is invalid")


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

    def __post_init__(self) -> None:
        for field_name in ("document_id", "tenant_id", "project_id", "revision_id", "content", "modality"):
            require_string(getattr(self, field_name), field_name)
        if not self.allowed_principals:
            raise ContractError("missing_acl", "allowed_principals must not be empty")
        for principal in self.allowed_principals:
            require_string(principal, "allowed_principals[]")
        object.__setattr__(self, "vector", _vector(self.vector, "vector"))

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return self.tenant_id, self.project_id, self.revision_id, self.document_id

    @property
    def digest(self) -> str:
        return sha256_payload(
            {
                "identity": self.identity,
                "content": self.content,
                "anchor": self.anchor,
                "acl": sorted(self.allowed_principals),
                "vector": self.vector,
                "modality": self.modality,
                "metadata": self.metadata,
            }
        )


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
            },
            "metadata": dict(self.document.metadata),
        }


class HybridIndex:
    """Reference BM25 + cosine RRF index with hard scope filters."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str, str, str], SearchDocument] = {}
        self._digests: dict[tuple[str, str, str, str], str] = {}

    def upsert(self, documents: Iterable[SearchDocument]) -> tuple[int, int]:
        inserted = unchanged = 0
        for document in documents:
            key = document.identity
            digest = document.digest
            if self._digests.get(key) == digest:
                unchanged += 1
                continue
            self._documents[key] = document
            self._digests[key] = digest
            inserted += 1
        return inserted, unchanged

    def delete_revision(self, *, tenant_id: str, project_id: str, revision_id: str) -> int:
        scope = (tenant_id, project_id, revision_id)
        keys = [key for key in self._documents if key[:3] == scope]
        for key in keys:
            del self._documents[key]
            del self._digests[key]
        return len(keys)

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            raise ContractError("vector_dimension_mismatch", "query and document vectors have different dimensions")
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(item * item for item in left))
        right_norm = math.sqrt(sum(item * item for item in right))
        return 0.0 if left_norm == 0 or right_norm == 0 else dot / (left_norm * right_norm)

    def _visible(self, query: RetrievalQuery) -> list[SearchDocument]:
        return [
            document
            for document in self._documents.values()
            if document.tenant_id == query.tenant_id
            and document.project_id == query.project_id
            and document.revision_id == query.revision_id
            and bool(document.allowed_principals & query.principal_ids)
            and (not query.modalities or document.modality in query.modalities)
        ]

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        documents = self._visible(query)
        if not documents:
            return ()
        query_terms = Counter(tokenize(query.text))
        document_terms = {document.identity: Counter(tokenize(document.content)) for document in documents}
        avg_length = sum(sum(terms.values()) for terms in document_terms.values()) / len(documents)
        frequencies: Counter[str] = Counter()
        for terms in document_terms.values():
            frequencies.update(terms.keys())
        lexical_scores: dict[tuple[str, str, str, str], float] = defaultdict(float)
        k1, b = 1.2, 0.75
        for document in documents:
            terms = document_terms[document.identity]
            length = sum(terms.values())
            for term, query_frequency in query_terms.items():
                term_frequency = terms[term]
                if not term_frequency:
                    continue
                inverse = math.log(1 + (len(documents) - frequencies[term] + 0.5) / (frequencies[term] + 0.5))
                denominator = term_frequency + k1 * (1 - b + b * length / max(avg_length, 1))
                lexical_scores[document.identity] += query_frequency * inverse * term_frequency * (k1 + 1) / denominator
        lexical = sorted(
            (document for document in documents if lexical_scores[document.identity] > 0),
            key=lambda item: (-lexical_scores[item.identity], item.document_id),
        )
        vector_scores: dict[tuple[str, str, str, str], float] = {}
        if query.vector is not None:
            for document in documents:
                if document.vector is not None:
                    vector_scores[document.identity] = self._cosine(query.vector, document.vector)
        vectors = sorted(
            (document for document in documents if document.identity in vector_scores),
            key=lambda item: (-vector_scores[item.identity], item.document_id),
        )
        lexical_rank = {item.identity: rank for rank, item in enumerate(lexical, 1)}
        vector_rank = {item.identity: rank for rank, item in enumerate(vectors, 1)}
        combined: list[RetrievalHit] = []
        for document in documents:
            lr = lexical_rank.get(document.identity)
            vr = vector_rank.get(document.identity)
            if lr is None and vr is None:
                continue
            score = (0.0 if lr is None else 1.0 / (60 + lr)) + (0.0 if vr is None else 1.0 / (60 + vr))
            combined.append(RetrievalHit(document=document, score=score, lexical_rank=lr, vector_rank=vr))
        combined.sort(key=lambda item: (-item.score, item.document.document_id))
        unique: list[RetrievalHit] = []
        seen_anchors: set[str] = set()
        for hit in combined:
            anchor_key = canonical_json(hit.to_payload()["anchor"])
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
