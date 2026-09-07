---
name: rag-knowledge-ingestion-retrieval-citation-and-freshness
description: 管理知识源、解析、Chunk、Embedding、Index、Retriever、Reranker、权限、引用、新鲜度和删除。
---

# RAG Platform

## Knowledge Source

DOCUMENT
DATABASE
WEBSITE
WIKI
TICKET
EMAIL_APPROVED
CODE
API
FILE
CATALOG
STRUCTURED_DATA

## Ingestion

Acquire
→ Verify
→ Parse
→ Normalize
→ Classify
→ Chunk
→ Embed
→ Index
→ Validate
→ Publish

## Document Identity

Source
Native ID
Version
Hash
Effective Time
Owner
Classification
Access Policy
Retention

## Chunk

记录：

Document Version
Position
Section
Text Hash
Metadata
Parent
Token Count
Language

## Embedding

Model
Version
Dimension
Normalization
Distance
Batch
Date

Embedding模型变化通常需要新Index版本。

## Retrieval

Lexical
Dense
Hybrid
Filtered
Graph
SQL
Tool Retrieval

## Reranking

记录：

Model
Candidate Count
Top K
Threshold
Latency
Cost

## Evaluation

Retrieval Recall
Precision
MRR／NDCG候选
Context Precision
Context Recall
Groundedness
Citation Accuracy
Answer Completeness

## Permission

Query Identity
→ Filter Authorized Documents
→ Retrieve
→ Generate
→ Citation Check

禁止先检索全部文档，再依靠Prompt要求模型不泄漏。

## Freshness

Source Update
Ingestion Delay
Index Update
Effective Time
Stale Document
Deleted Document

## Citation

每项Claim候选关联：

Document
Version
Chunk
Span
Retrieval Score
Verification Status

## 验收标准

- Source和Index版本可追踪；
- Chunk可回到原文；
- Embedding版本明确；
- 权限在检索前执行；
- Retrieval和Generation分别评测；
- Citation可验证；
- 删除能够传播到Index和Cache。
