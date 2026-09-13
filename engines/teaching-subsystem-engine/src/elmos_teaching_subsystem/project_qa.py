"""LLM-driven project Q&A with RAG (Retrieval-Augmented Generation).

This module provides a local code index and retrieval system that can answer
questions about a project's codebase. It does NOT call external LLMs - instead
it builds a local inverted index of code symbols, comments, and documentation,
and uses BM25 scoring to retrieve relevant context.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any

MAX_INDEX_FILES = 10_000
MAX_CHUNK_SIZE = 500  # lines per chunk
MAX_RESULTS = 10
MAX_QUERY_TERMS = 50

@dataclass(frozen=True)
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    symbols: list[str]
    doc_strings: list[str]
    language: str

@dataclass(frozen=True)
class SearchResult:
    chunk: CodeChunk
    score: float
    matched_terms: list[str]
    context_before: str = ""
    context_after: str = ""

class CodebaseIndex:
    def __init__(self) -> None:
        self.chunks: list[CodeChunk] = []
        self.inverted_index: defaultdict[str, set[int]] = defaultdict(set)
        self.df: Counter[str] = Counter()
        self.total_docs: int = 0
        self.avgdl: float = 0.0
        self.doc_lengths: dict[int, int] = {}
        
    def index_directory(self, root: Path, extensions: tuple[str, ...] = ('.py','.java','.ts','.js','.go','.cs','.rs')) -> None:
        count = 0
        for path in root.rglob('*'):
            if count >= MAX_INDEX_FILES:
                break
            if path.is_file() and path.suffix in extensions:
                try:
                    file_chunks = self._chunk_file(path)
                    for chunk in file_chunks:
                        self.chunks.append(chunk)
                except Exception:
                    pass
                count += 1
        self._build_inverted_index()
        
    def _chunk_file(self, path: Path) -> list[CodeChunk]:
        try:
            content = path.read_text(errors='ignore')
        except Exception:
            content = ""
        lines = content.splitlines()
        chunks = []
        for i in range(0, len(lines), MAX_CHUNK_SIZE):
            chunk_lines = lines[i:i + MAX_CHUNK_SIZE]
            chunk_content = "\n".join(chunk_lines)
            chunk = CodeChunk(
                file_path=str(path),
                start_line=i + 1,
                end_line=i + len(chunk_lines),
                content=chunk_content,
                symbols=self._extract_symbols(chunk_content),
                doc_strings=[],
                language=path.suffix.lstrip('.')
            )
            chunks.append(chunk)
        return chunks

    def _extract_symbols(self, text: str) -> list[str]:
        return list(set(re.findall(r'[a-zA-Z_]\w*', text)))
        
    def _extract_terms(self, chunk: CodeChunk) -> set[str]:
        terms = set()
        words = re.findall(r'[A-Za-z0-9]+', chunk.content)
        for w in words:
            sub = re.sub(r'([a-z])([A-Z])', r'\1 \2', w).lower()
            terms.update(sub.split())
            terms.add(w.lower())
        return terms
        
    def _build_inverted_index(self) -> None:
        self.total_docs = len(self.chunks)
        total_len = 0
        for i, chunk in enumerate(self.chunks):
            terms = self._extract_terms(chunk)
            self.doc_lengths[i] = len(terms)
            total_len += len(terms)
            for term in terms:
                self.inverted_index[term].add(i)
                self.df[term] += 1
        self.avgdl = total_len / max(1, self.total_docs)
        
    def search(self, query: str, max_results: int = MAX_RESULTS) -> list[SearchResult]:
        if not self.total_docs:
            return []
        
        query_terms = re.findall(r'[a-zA-Z0-9]+', query.lower())[:MAX_QUERY_TERMS]
        if not query_terms:
            return []
            
        scores: defaultdict[int, float] = defaultdict(float)
        matched: defaultdict[int, set[str]] = defaultdict(set)
        
        k1 = 1.5
        b = 0.75
        
        for term in query_terms:
            if term not in self.inverted_index:
                continue
            df = self.df[term]
            idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
            
            for doc_id in self.inverted_index[term]:
                tf = 1.0
                dl = self.doc_lengths[doc_id]
                score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / self.avgdl)))
                scores[doc_id] += score
                matched[doc_id].add(term)
                
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max_results]
        results = []
        for doc_id, score in sorted_docs:
            results.append(SearchResult(
                chunk=self.chunks[doc_id],
                score=score,
                matched_terms=list(matched[doc_id])
            ))
        return results
        
    def get_symbol_definition(self, symbol: str) -> list[CodeChunk]:
        res = []
        for c in self.chunks:
            if symbol in c.symbols:
                res.append(c)
        return res

@dataclass(frozen=True)
class QAResponse:
    question: str
    answer_context: str
    relevant_chunks: list[SearchResult]
    confidence: float

class ProjectQAService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.index = CodebaseIndex()
        self.index.index_directory(root)
        
    def ask(self, question: str) -> QAResponse:
        results = self.index.search(question)
        context = "\n\n".join(f"--- {r.chunk.file_path} ---\n{r.chunk.content}" for r in results)
        conf = 0.0
        if results:
            conf = min(1.0, results[0].score / 10.0)
        return QAResponse(question=question, answer_context=context, relevant_chunks=results, confidence=conf)
        
    def explain_symbol(self, symbol: str) -> str:
        defs = self.index.get_symbol_definition(symbol)
        if not defs:
            return f"Symbol {symbol} not found."
        return f"Symbol {symbol} found in {len(defs)} locations."
        
    def find_usage(self, symbol: str) -> list[CodeChunk]:
        res = self.index.search(symbol)
        return [r.chunk for r in res]

    def suggest_related(self, file_path: str) -> list[str]:
        try:
            path = Path(file_path)
            return [str(p) for p in path.parent.iterdir() if p.is_file() and p.name != path.name]
        except Exception:
            return []
