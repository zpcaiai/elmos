"""External backend query and record adapters for Elastic, pgvector, and Dify."""

from __future__ import annotations

import json
import math
from typing import Any, Mapping, Sequence

from .contracts import (
    ContractError,
    ScopeDeniedError,
    TrustedScope,
    canonical_digest,
)


def elastic_queries(
    scope: TrustedScope,
    query: str,
    vector: Sequence[float],
    k: int = 20,
) -> dict[str, Any]:
    """Generate scoped Elasticsearch queries with strict tenant and revision isolation."""
    if not scope.revisions:
        raise ScopeDeniedError("Scope has no revisions")
    if not query.strip():
        raise ContractError("Query cannot be empty")
    if not 1 <= k <= 100:
        raise ContractError(f"k must be between 1 and 100, got {k}")
    if not vector or any(not math.isfinite(v) for v in vector):
        raise ContractError("Invalid or non-finite vector")

    revision_filters = [
        {
            "bool": {
                "filter": [
                    {"term": {"repository": r.repository}},
                    {"term": {"snapshot": r.snapshot}},
                    {"term": {"generation": r.generation}},
                ]
            }
        }
        for r in scope.revisions
    ]

    base_filters = [
        {"term": {"tenant": scope.tenant}},
        {"term": {"tombstoned": False}},
        {"bool": {"should": revision_filters, "minimum_should_match": 1}},
    ]

    return {
        "lexical": {
            "size": k,
            "_source": False,
            "query": {
                "bool": {
                    "filter": base_filters,
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["symbol_parts^4", "path_parts^2", "text"],
                            }
                        }
                    ],
                }
            },
        },
        "dense": {
            "size": k,
            "_source": False,
            "knn": {
                "field": "embedding",
                "query_vector": list(vector),
                "k": k,
                "num_candidates": min(k * 5, 1000),
                "filter": {"bool": {"filter": base_filters}},
            },
        },
        "qualification": "not_backend_executed",
    }


def pgvector_query(
    scope: TrustedScope,
    vector: Sequence[float],
    k: int = 20,
) -> tuple[str, dict[str, Any]]:
    """Construct parameterized SQL and parameter dict for pgvector retrieval."""
    if not scope.revisions:
        raise ScopeDeniedError("Scope has no revisions")
    if not 1 <= k <= 100:
        raise ContractError(f"k must be between 1 and 100, got {k}")
    if not vector or any(not math.isfinite(v) for v in vector):
        raise ContractError("Invalid or non-finite vector")

    sql = """WITH requested AS (
    SELECT * FROM jsonb_to_recordset(%(bindings)s::jsonb) AS x(repository text, snapshot text, generation text)
)
SELECT d.chunk_id, d.embedding <=> %(vector)s::vector AS distance
FROM elmos_evidence_chunks d
JOIN requested r ON (d.repository, d.snapshot, d.generation) = (r.repository, r.snapshot, r.generation)
WHERE d.tenant = %(tenant)s AND NOT d.tombstoned
ORDER BY d.embedding <=> %(vector)s::vector, d.chunk_id
LIMIT %(k)s"""

    bindings_json = json.dumps([r.to_dict() for r in scope.revisions])
    vector_str = "[" + ",".join(map(str, vector)) + "]"
    params = {
        "bindings": bindings_json,
        "tenant": scope.tenant,
        "vector": vector_str,
        "k": k,
    }
    return sql, params


def dify_records(
    scope: TrustedScope,
    result: Mapping[str, Any],
    scores: Mapping[str, float],
    binding: Mapping[str, Any],
    threshold: float = 0.0,
) -> dict[str, Any]:
    """Adapt EvidenceContext items to external knowledge records for Dify."""
    if binding.get("tenant") != scope.tenant or binding.get("principal") != scope.principal:
        raise ScopeDeniedError("Dify knowledge binding principal/tenant mismatch")

    if result.get("scope_digest") != scope.digest or result.get("acl_epoch", scope.acl_epoch) != scope.acl_epoch:
        raise ScopeDeniedError("Upstream scope digest or epoch mismatch")

    if not binding.get("scoring_profile"):
        raise ContractError("scoring_profile required in binding")
    if not 0.0 <= threshold <= 1.0:
        raise ContractError(f"Threshold must be in [0, 1], got {threshold}")

    records: list[dict[str, Any]] = []
    items = result.get("items", [])
    for item in items:
        item_id = item.get("id", item.get("evidence_ref"))
        score = scores.get(item_id)
        if score is None or not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ContractError(f"Normalized relevance score in [0, 1] required for item {item_id}")

        if score >= threshold:
            anchor = item.get("anchor", {})
            title = anchor.get("path", item_id)
            records.append({
                "content": item.get("text", ""),
                "score": score,
                "title": title,
                "metadata": {
                    "anchor": anchor,
                    "scoring_profile": binding["scoring_profile"],
                },
            })

    return {"records": records}
