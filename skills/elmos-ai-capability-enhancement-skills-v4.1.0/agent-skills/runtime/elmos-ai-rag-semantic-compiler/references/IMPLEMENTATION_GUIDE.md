# Implementation Guide — AIRagSemanticCompiler

## Purpose

Model the full ingestion, parsing, chunking, ACL, indexing, retrieval, reranking, context packing, grounding, citation, abstention, synchronization and evaluation lifecycle.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Compile typed semantic objects with provenance
2. Preserve source maps and identities
3. Represent effects, state, protocol and assurance semantics
4. Emit semantic gaps instead of guessing

## Native acceptance corpus

- `ELMOS_AI_RAG_SEMANTIC_COMPILER-01` — round-trip fixture
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-02` — unsupported construct
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-03` — source map integrity
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-04` — AiRagSemanticCompiler representative end-to-end fixture
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-07` — undeclared authority is denied
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-08` — resource and wall-clock budget is measured
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-09` — schema validation
- `ELMOS_AI_RAG_SEMANTIC_COMPILER-10` — source map round trip

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
