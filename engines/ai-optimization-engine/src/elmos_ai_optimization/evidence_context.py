"""Evidence-first context retrieval and packaging service."""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import (
    BudgetExceededError,
    ContextItem,
    ContextRequest,
    ContractError,
    EvidenceContext,
    ScopeDeniedError,
    SourceAnchor,
    TrustedScope,
    canonical_digest,
)
from .scope import ScopeResolver


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if t]


@dataclass(frozen=True)
class Document:
    """Indexed document in the repository."""
    doc_id: str
    tenant: str
    repository: str
    snapshot: str
    generation: str
    path: str
    symbol: str
    text: str
    blob_digest: str
    vector: tuple[float, ...] | None = None
    tombstoned: bool = False

    @classmethod
    def create(
        cls,
        doc_id: str,
        tenant: str,
        repository: str,
        snapshot: str,
        generation: str,
        path: str,
        symbol: str,
        text: str,
        vector: Sequence[float] | None = None,
    ) -> Document:
        blob_bytes = text.encode("utf-8")
        blob_digest = hashlib.sha256(blob_bytes).hexdigest()
        v = tuple(vector) if vector is not None else None
        return cls(
            doc_id=doc_id,
            tenant=tenant,
            repository=repository,
            snapshot=snapshot,
            generation=generation,
            path=path,
            symbol=symbol,
            text=text,
            blob_digest=blob_digest,
            vector=v,
            tombstoned=False,
        )


class EvidenceContextService:
    """Production service for evidence packaging and query retrieval."""

    def __init__(self, scope_resolver: ScopeResolver | None = None) -> None:
        self.scope_resolver = scope_resolver
        # (tenant, doc_id) -> Document
        self._documents: dict[tuple[str, str], Document] = {}
        # In-memory SQLite FTS table for deterministic lexical query support
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5("
            "doc_id UNINDEXED, tenant UNINDEXED, repository UNINDEXED, "
            "snapshot UNINDEXED, generation UNINDEXED, path, symbol, text)"
        )
        self._db.commit()

    def add_document(self, doc: Document) -> None:
        key = (doc.tenant, doc.doc_id)
        self._documents[key] = doc
        if not doc.tombstoned:
            with self._db:
                self._db.execute(
                    "INSERT INTO docs_fts VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc.doc_id, doc.tenant, doc.repository, doc.snapshot, doc.generation, doc.path, doc.symbol, doc.text),
                )

    def tombstone_document(self, tenant: str, doc_id: str) -> None:
        key = (tenant, doc_id)
        if key in self._documents:
            d = self._documents[key]
            self._documents[key] = Document(
                doc_id=d.doc_id,
                tenant=d.tenant,
                repository=d.repository,
                snapshot=d.snapshot,
                generation=d.generation,
                path=d.path,
                symbol=d.symbol,
                text=d.text,
                blob_digest=d.blob_digest,
                vector=d.vector,
                tombstoned=True,
            )
            with self._db:
                self._db.execute("DELETE FROM docs_fts WHERE doc_id = ? AND tenant = ?", (doc_id, tenant))

    def _filter_by_scope(self, docs: Sequence[Document], scope: TrustedScope) -> list[Document]:
        allowed_revisions = {(r.repository, r.snapshot, r.generation) for r in scope.revisions}
        valid = []
        for d in docs:
            if d.tombstoned:
                continue
            if d.tenant != scope.tenant:
                continue
            if (d.repository, d.snapshot, d.generation) in allowed_revisions:
                valid.append(d)
        return valid

    def _fast_path_lookup(self, scope: TrustedScope, selector: Mapping[str, str]) -> list[Document]:
        """Exact path or symbol matching bypassing embedding and model routing."""
        target_path = selector.get("path")
        target_symbol = selector.get("symbol")
        if not target_path and not target_symbol:
            return []

        candidates = [d for (t, _), d in self._documents.items() if t == scope.tenant and not d.tombstoned]
        candidates = self._filter_by_scope(candidates, scope)

        matches: list[Document] = []
        for d in candidates:
            path_ok = target_path is None or d.path == target_path
            symbol_ok = target_symbol is None or d.symbol == target_symbol
            if path_ok and symbol_ok:
                matches.append(d)
        return matches

    def _fts_search(self, scope: TrustedScope, query: str, limit: int) -> list[Document]:
        """Sanitized lexical FTS query matching tokens deterministically with substring fallback."""
        tokens = _tokenize(query)
        allowed_revisions = {(r.repository, r.snapshot, r.generation) for r in scope.revisions}
        matched_docs: list[Document] = []
        seen_ids: set[str] = set()

        if tokens:
            clean_query = " OR ".join(f'"{t}"' for t in tokens)
            try:
                cursor = self._db.execute(
                    "SELECT doc_id, repository, snapshot, generation FROM docs_fts "
                    "WHERE tenant = ? AND docs_fts MATCH ? ORDER BY rank",
                    (scope.tenant, clean_query),
                )
                for row in cursor.fetchall():
                    doc_id, repo, snap, gen = row[0], row[1], row[2], row[3]
                    if (repo, snap, gen) in allowed_revisions and doc_id not in seen_ids:
                        key = (scope.tenant, doc_id)
                        doc = self._documents.get(key)
                        if doc and not doc.tombstoned:
                            matched_docs.append(doc)
                            seen_ids.add(doc_id)
                    if len(matched_docs) >= limit:
                        break
            except sqlite3.OperationalError:
                pass

        # Substring fallback for CJK phrases or tokens not split by FTS tokenizer
        if len(matched_docs) < limit and query.strip():
            q_lower = query.lower().strip()
            for (t, doc_id), doc in self._documents.items():
                if t != scope.tenant or doc.tombstoned or doc_id in seen_ids:
                    continue
                if (doc.repository, doc.snapshot, doc.generation) not in allowed_revisions:
                    continue
                if q_lower in doc.text.lower() or q_lower in doc.symbol.lower() or q_lower in doc.path.lower():
                    matched_docs.append(doc)
                    seen_ids.add(doc_id)
                if len(matched_docs) >= limit:
                    break

        return matched_docs

    def _dense_search(self, scope: TrustedScope, query_vector: Sequence[float], limit: int) -> list[Document]:
        """Cosine similarity dense search over scoped documents."""
        candidates = [
            d for (t, _), d in self._documents.items()
            if t == scope.tenant and not d.tombstoned and d.vector is not None
        ]
        candidates = self._filter_by_scope(candidates, scope)

        q_mag = math.sqrt(sum(x * x for x in query_vector))
        if q_mag == 0.0:
            return []

        scored: list[tuple[float, Document]] = []
        for d in candidates:
            assert d.vector is not None
            if len(d.vector) != len(query_vector):
                continue
            dot = sum(a * b for a, b in zip(query_vector, d.vector))
            d_mag = math.sqrt(sum(b * b for b in d.vector))
            if d_mag > 0:
                sim = dot / (q_mag * d_mag)
                scored.append((sim, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:limit]]

    @staticmethod
    def rrf_fuse(ranked_lists: Sequence[Sequence[Document]], k: int = 60) -> list[Document]:
        """Reciprocal Rank Fusion with deduplication."""
        scores: dict[str, float] = defaultdict(float)
        docs_by_id: dict[str, Document] = {}

        for r_list in ranked_lists:
            seen_in_lane: set[str] = set()
            for rank, doc in enumerate(r_list):
                if doc.doc_id in seen_in_lane:
                    continue
                seen_in_lane.add(doc.doc_id)
                docs_by_id[doc.doc_id] = doc
                scores[doc.doc_id] += 1.0 / (k + rank + 1)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [docs_by_id[doc_id] for doc_id, _ in ranked]

    def query(self, scope: TrustedScope, request: ContextRequest, query_vector: Sequence[float] | None = None) -> EvidenceContext:
        """Execute evidence retrieval under strict scope and pack within token budget."""
        if self.scope_resolver:
            self.scope_resolver.revalidate(scope)

        candidates: list[Document] = []

        # 1. Try exact fast path if selector is specified or query matches path/symbol exactly
        if request.selector:
            candidates = self._fast_path_lookup(scope, request.selector)
        elif request.mode == "exact":
            candidates = self._fast_path_lookup(scope, {"symbol": request.query})
            if not candidates:
                candidates = self._fast_path_lookup(scope, {"path": request.query})

        # 2. Mode dispatch
        if not candidates:
            if request.mode in {"auto", "lexical"}:
                candidates = self._fts_search(scope, request.query, request.top_k)
            elif request.mode == "hybrid":
                fts_candidates = self._fts_search(scope, request.query, request.top_k)
                dense_candidates = self._dense_search(scope, query_vector, request.top_k) if query_vector else []
                candidates = self.rrf_fuse([fts_candidates, dense_candidates])[:request.top_k]

        # 3. Deduplicate by anchor (repository, path, symbol, start, end)
        seen_anchors: set[tuple[str, str, str]] = set()
        deduped: list[Document] = []
        for d in candidates:
            anchor_key = (d.repository, d.path, d.symbol)
            if anchor_key not in seen_anchors:
                seen_anchors.add(anchor_key)
                deduped.append(d)

        # 4. Pack into token budget
        # Estimation: ~4 characters per token
        char_budget = request.context_token_budget * 4
        consumed_chars = 0
        items: list[ContextItem] = []

        for d in deduped[:request.top_k]:
            blob_bytes = d.text.encode("utf-8")
            text_len = len(d.text)
            rem_chars = char_budget - consumed_chars

            if rem_chars <= 0:
                break

            truncated = False
            out_text = d.text
            if text_len > rem_chars:
                out_text = d.text[:rem_chars]
                # Ensure valid UTF-8 boundary
                out_text_bytes = out_text.encode("utf-8", errors="ignore")
                out_text = out_text_bytes.decode("utf-8", errors="ignore")
                truncated = True

            anchor = SourceAnchor(
                repository=d.repository,
                snapshot=d.snapshot,
                generation=d.generation,
                path=d.path,
                blob_digest=d.blob_digest,
                start_byte=0,
                end_byte=len(out_text.encode("utf-8")),
                symbol=d.symbol,
            )

            item = ContextItem(
                anchor=anchor,
                text=out_text,
                truncated=truncated,
                evidence_ref=f"ev-{anchor.blob_digest[:16]}-{anchor.start_byte}-{anchor.end_byte}",
            )
            items.append(item)
            consumed_chars += len(out_text)

        status = "ok" if items else "insufficient_evidence"
        return EvidenceContext(
            status=status,
            scope_digest=scope.digest,
            items=tuple(items),
        )
