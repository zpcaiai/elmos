# Implementation Guide — TargetLangchainProjectGenerator

## Purpose

Generate typed Python and TypeScript LangChain applications for model, tool, retriever, middleware and short-horizon agent composition with migration hooks to LangGraph.

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

1. Generate Python and TypeScript projects
2. Generate models, tools, retrievers and middleware
3. Generate structured output and streaming API
4. Generate evals and observability
5. Generate migration path to LangGraph for durable flows

## Native acceptance corpus

- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-01` — Python/TypeScript build
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-02` — tool calling
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-03` — retriever
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-04` — middleware
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-05` — structured output
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-06` — streaming
- `ELMOS_TARGET_LANGCHAIN_PROJECT_GENERATOR-07` — LangGraph migration fixture

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
