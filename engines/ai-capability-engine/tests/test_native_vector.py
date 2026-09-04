import pytest
from elmos_ai_capability.native_vector_bridge import (
    cosine_similarity,
    top_k_cosine,
    estimate_token_count,
    sliding_window_pack,
)


def test_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(v1, v2)) < 1e-5

    v3 = [3.0, 0.0, 0.0]
    assert abs(cosine_similarity(v1, v3) - 1.0) < 1e-5


def test_top_k_cosine():
    query = [1.0, 1.0, 0.0]
    candidates = [
        {"id": "doc1", "embedding": [1.0, 1.0, 0.0]},  # sim = 1.0
        {"id": "doc2", "embedding": [1.0, 0.0, 0.0]},  # sim ~ 0.707
        {"id": "doc3", "embedding": [0.0, 0.0, 1.0]},  # sim = 0.0
    ]

    top = top_k_cosine(query, candidates, k=2)
    assert len(top) == 2
    assert top[0]["id"] == "doc1"
    assert top[1]["id"] == "doc2"
    assert top[0]["score"] > top[1]["score"]


def test_token_count_and_sliding_window():
    code = "def hello():\n    print('world')\n"
    tokens = estimate_token_count(code)
    assert 5 <= tokens <= 20

    long_code = "\n".join([f"var_{i} = {i} * 2" for i in range(100)])
    packed = sliding_window_pack(long_code, max_tokens=30, header_lines=2, footer_lines=2)
    assert packed["truncated"] is True
    assert "var_0" in packed["text"]
    assert "TRUNCATED" in packed["text"]
