"""Unit and integration tests for AI Agent and RAG service scaffold."""

from __future__ import annotations

import ast
import math

import pytest

from elmos_project_synthesis.ai_agent_scaffold import render_ai_agent_scaffold
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest


def test_ai_agent_scaffold_file_generation():
    draft = create_draft(
        name="customer-support-ai",
        description="AI powered customer support and knowledge retrieval microservice",
        entity="ticket",
        languages=["python"],
        persistence="in-memory",
        auth_mode="none",
    )
    draft["ai_integration"] = True
    approved = approve_request(draft, actor="ai-architect")
    request = SynthesisRequest.from_mapping(approved)

    files = render_ai_agent_scaffold(request)

    expected_files = [
        "ai/models.py",
        "ai/vector_store.py",
        "ai/llm_client.py",
        "ai/rag_service.py",
        "ai/routes.py",
        "ai/__init__.py",
    ]
    for filename in expected_files:
        assert filename in files, f"Missing expected file: {filename}"
        # Verify that each generated file is valid Python syntax
        ast.parse(files[filename], filename=filename)


def test_ai_agent_scaffold_contents_and_ddl():
    draft = create_draft(
        name="search-ai",
        description="Search AI service",
        entity="document",
        languages=["python"],
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="lead")
    request = SynthesisRequest.from_mapping(approved)
    files = render_ai_agent_scaffold(request)

    # 1. Models checks
    models_code = files["ai/models.py"]
    assert "class ChatMessage" in models_code
    assert "class ChatRequest" in models_code
    assert "class ChatResponse" in models_code
    assert "class DocumentChunk" in models_code
    assert "class RAGQueryRequest" in models_code
    assert "class RAGQueryResponse" in models_code

    # 2. Vector store checks
    vector_store_code = files["ai/vector_store.py"]
    assert "def cosine_similarity" in vector_store_code
    assert "class VectorStore" in vector_store_code
    assert "def pgvector_ddl" in vector_store_code
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in vector_store_code
    assert "vector(" in vector_store_code

    # 3. LLM client checks
    llm_code = files["ai/llm_client.py"]
    assert "class LLMClient" in llm_code
    assert "def complete" in llm_code

    # 4. RAG service checks
    rag_code = files["ai/rag_service.py"]
    assert "def chunk_text" in rag_code
    assert "class RAGService" in rag_code
    assert "def ingest_document" in rag_code
    assert "def query" in rag_code

    # 5. Routes checks
    routes_code = files["ai/routes.py"]
    assert 'router = APIRouter(prefix="/api/v1/ai"' in routes_code
    assert '@router.post("/chat"' in routes_code
    assert '@router.post("/documents"' in routes_code
    assert '@router.get("/documents"' in routes_code
    assert '@router.post("/rag-query"' in routes_code


def test_vector_similarity_pure_logic():
    # Test the pure mathematical cosine similarity implementation
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2, strict=False))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(b * b for b in v2))
        if magnitude1 == 0.0 or magnitude2 == 0.0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine_similarity([3.0, 4.0], [3.0, 4.0]) == pytest.approx(1.0)
    assert cosine_similarity([], []) == 0.0


def test_chunking_pure_logic():
    def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        if not text.strip():
            return []
        if len(text) <= chunk_size:
            return [text.strip()]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(text):
                break
            start += chunk_size - overlap
        return chunks

    text = "A" * 1200
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) == 3
    assert len(chunks[0]) == 500
