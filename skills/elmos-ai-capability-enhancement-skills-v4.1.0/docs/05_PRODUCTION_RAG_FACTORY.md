# Production RAG Factory

## Why RAG is a domain, not a template

A production RAG system is a data product, search system, security boundary and evaluation program. Elmos must generate the entire lifecycle rather than a single `embed → retrieve → prompt` function.

## Generated service topology

```text
connectors ──► ingestion orchestrator ──► parser/OCR workers
                                       └─► normalization/dedup/classification
                                               │
                                               ▼
                              canonical document/version/span store
                                │         │          │
                                ▼         ▼          ▼
                           dense index  sparse index  graph index
                                └─────────┬──────────┘
                                          ▼
query API ─► auth/tenant/ACL ─► rewrite/filter/retrieve/fuse/rerank
                                          ▼
                         context pack + evidence authorization
                                          ▼
                         answer/structured output/citation/abstain
                                          ▼
                          feedback/evals/trace/cost/operations
```

## Required generated modules

1. Source connectors and incremental cursors.
2. Parser and OCR selection with document-type confidence.
3. Canonical document, version, page/section/span and metadata model.
4. Content deduplication and lineage.
5. Data classification and ACL projection.
6. Chunking/linking strategy with parent/child relations.
7. Embedding, sparse and optional graph indexing workers.
8. Query classification, rewrite and decomposition.
9. Metadata/ACL filtering before model context.
10. Retrieval fusion and reranking.
11. Context packing with token and evidence budgets.
12. Answering with structured output, citations and abstention.
13. Evaluation data sets and online/offline metrics.
14. Deletion propagation, reindex and tombstone lifecycle.
15. Admin APIs, operations UI, metrics, backup/restore and runbooks.

## RAG archetypes

| Archetype | Additional semantics |
|---|---|
| Basic RAG | Dense retrieval and citations; suitable only for low-risk, small corpora |
| Enterprise hybrid RAG | Dense+sparse, metadata/ACL, reranking, lifecycle and operations |
| Agentic RAG | Iterative query planning, tool/retriever choice, bounded loops and trace |
| GraphRAG | Entity/relation extraction, graph index, global/local/community retrieval |
| Multimodal RAG | Page images, tables, charts, audio/video spans and modality-aware citation |
| SQL/API/federated RAG | Multiple authoritative sources, query routing and result reconciliation |

## Data and ACL invariants

- Every index record points to canonical document version and authorized span.
- Tenant/project/collection/document ACL is evaluated before context assembly.
- Cache keys include tenant, policy version, document/index version and model/retriever profile.
- Deletion and access revocation invalidate indexes, caches, generated summaries and memory.
- OCR/parsing uncertainty is preserved and can lower confidence or trigger review.
- A citation cannot resolve to a version or span the caller is not authorized to read.

## Retrieval evaluation

Separate retrieval from answer evaluation.

### Retrieval

- Recall@K and hit rate on evidence-labeled queries.
- MRR/nDCG and ranking stability.
- Filter/ACL precision.
- Reranker lift and failure cases.
- Query rewrite contribution.
- Coverage by document type, language, age, tenant and access class.
- Freshness and delete-propagation lag.

### Grounding and answer

- Citation precision and completeness.
- Claim-to-evidence entailment or verified support.
- Faithfulness and unsupported-claim rate.
- Correct abstention.
- Structured-output validity.
- Answer correctness where an authoritative answer exists.
- Adversarial injection resistance.
- Cost, latency and context utilization.

Metrics are contract-specific. The package does not impose one universal pass number; the Assurance Contract declares thresholds and confidence requirements.

## Golden data and holdouts

Maintain:

```text
datasets/
├── development/
├── regression/
├── security/
├── document-edge-cases/
├── access-control/
├── freshness-delete/
├── performance/
└── holdout/
```

A model or agent that helped generate a data set cannot independently certify performance on that same data. Customer Golden Routes require holdouts and repeated runs.

## Prompt and document injection

The factory generates controls at multiple layers:

- trust labels for source/connectors;
- isolation of document text from system/tool instructions;
- retrieval-time malicious-content signals;
- tool arguments derived from typed policy, not copied instructions;
- model output validation;
- no secret/tool authority exposed to untrusted context;
- security trace recording;
- attack corpus and regression suite.

## Store portability

AI-SIR uses a portable `Document/Span/ACL/Index/Query/RetrievalResult/Citation` contract. Target profiles map this to pgvector, Qdrant, Milvus, Weaviate, Neo4j or another approved store. Store-specific features are explicit optimizations, not canonical semantics.

## Production gates

A production RAG target cannot pass E5 without:

- representative ingestion and delete propagation;
- ACL and cross-tenant negative tests;
- retrieval and grounding thresholds;
- injection red team;
- latency/throughput/capacity evidence;
- backup/restore and reindex runbook;
- model/index drift monitoring;
- support ownership and incident response;
- exact data/provider/residency policy.
