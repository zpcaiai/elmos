# Implementation Guide — AI Data Contract and Quality Governor

## Purpose

Define and enforce contracts for training, evaluation, retrieval, memory and tool data with freshness, completeness, distribution and ownership controls.

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

1. Typed schema and semantic constraints
2. Freshness/completeness/uniqueness checks
3. Distribution and segment monitoring
4. Ownership and stewardship workflow
5. Quarantine and downstream evidence invalidation

## Native acceptance corpus

- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-01` — schema validation
- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-02` — freshness breach
- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-03` — duplicate data
- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-04` — distribution shift
- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-05` — owner approval
- `ELMOS_AI_DATA_CONTRACT_QUALITY_GOVERNOR-06` — quarantine propagation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
