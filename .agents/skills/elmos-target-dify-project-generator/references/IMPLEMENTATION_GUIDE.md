# Implementation Guide — TargetDifyProjectGenerator

## Purpose

Generate and import/export Dify Chatflow, Workflow, Agent, knowledge-pipeline and plugin projects with deterministic layout, dependency manifests and unsupported-node accounting.

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

1. Generate Chatflow, Workflow and Agent DSL
2. Generate model/tool/data-source plugins
3. Preserve deterministic node IDs and visual layout
4. Import/export with unsupported-node ledger
5. Run exact-version Dify import and invocation smoke tests

## Native acceptance corpus

- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-01` — Chatflow import/export round trip
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-02` — Workflow branch/iteration/parallel nodes
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-03` — Agent tool binding
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-04` — knowledge pipeline incremental update
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-05` — model/tool/data-source plugin load
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-06` — secret redaction
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-07` — unsupported node preservation
- `ELMOS_TARGET_DIFY_PROJECT_GENERATOR-08` — upgrade and import rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
