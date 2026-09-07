# Implementation Guide — AI Bill of Materials and Provenance Generator

## Purpose

Generate a signed AI BOM covering models, datasets, prompts, Skills, tools, MCP servers, adapters, libraries, images, policies and evidence lineage.

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

1. AI-specific component inventory
2. Digest and publisher identity binding
3. Dependency and transitive service graph
4. License/residency/risk annotations
5. Signed provenance and drift invalidation

## Native acceptance corpus

- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-01` — complete inventory
- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-02` — missing component block
- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-03` — digest mismatch
- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-04` — transitive service capture
- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-05` — signature verification
- `ELMOS_AI_BOM_PROVENANCE_GENERATOR-06` — drift invalidation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
