#!/usr/bin/env python3
"""Run the bounded local Hybrid RAG performance/quality baseline."""

from __future__ import annotations

import json
from decimal import Decimal

from elmos_repository_orchestrator.contracts import sha256_payload
from elmos_repository_orchestrator.performance import RetrievalCase, benchmark_retrieval
from elmos_repository_orchestrator.retrieval import RetrievalQuery, SearchDocument, SourceAnchor


def main() -> int:
    documents = []
    cases = []
    for index in range(500):
        topic = index % 25
        content = f"ELMOS module topic-{topic} durable checkpoint hybrid retrieval item-{index}"
        vector = tuple(1.0 if position == topic % 8 else 0.0 for position in range(8))
        documents.append(
            SearchDocument(
                document_id=f"doc-{index}",
                tenant_id="benchmark-tenant",
                project_id="benchmark-project",
                revision_id="benchmark-revision",
                content=content,
                anchor=SourceAnchor(
                    uri=f"repo://benchmark/doc-{index}.txt",
                    kind="text-lines",
                    content_sha256=sha256_payload(content),
                    start=1,
                    end=1,
                ),
                allowed_principals=frozenset({"benchmark-runner"}),
                vector=vector,
            )
        )
    for topic in range(25):
        relevant = frozenset(f"doc-{index}" for index in range(topic, 500, 25))
        query_vector = tuple(1.0 if position == topic % 8 else 0.0 for position in range(8))
        cases.append(
            RetrievalCase(
                RetrievalQuery(
                    tenant_id="benchmark-tenant",
                    project_id="benchmark-project",
                    revision_id="benchmark-revision",
                    principal_ids=frozenset({"benchmark-runner"}),
                    text=f"topic-{topic}",
                    vector=query_vector,
                    top_k=10,
                ),
                relevant,
                {identity: 1.0 for identity in relevant},
            )
        )
    report = benchmark_retrieval(
        documents,
        cases,
        repetitions=3,
        workload="500-document-25-query-local-synthetic",
        representative=False,
        measured_token_cost=Decimal("0"),
    )
    print(json.dumps(report.to_payload(), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
