# Implementation Guide — AISourceProjectImporter

## Purpose

Inspect and import existing visual DSLs, agent SDK repositories, RAG systems, harness packages and deployment descriptors into evidence-backed AI-SIR.

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

1. Detect exact source framework and version
2. Import source-native semantic objects
3. Preserve opaque/unsupported material
4. Bind import artifacts to source hashes
5. Support round-trip and differential validation

## Native acceptance corpus

- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-01` — known framework fixture
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-02` — mixed framework fixture
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-03` — opaque dependency
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-04` — AiSourceProjectImporter representative end-to-end fixture
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-07` — undeclared authority is denied
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-08` — resource and wall-clock budget is measured
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-09` — minimal import
- `ELMOS_AI_SOURCE_PROJECT_IMPORTER-10` — representative repository

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
