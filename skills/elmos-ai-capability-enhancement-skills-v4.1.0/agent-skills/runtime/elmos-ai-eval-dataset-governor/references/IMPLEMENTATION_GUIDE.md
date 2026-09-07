# Implementation Guide — AI Evaluation Dataset Governor

## Purpose

Govern versioned evaluation datasets from provenance and consent through deduplication, labels, holdout isolation, contamination detection, retention and release.

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

1. Dataset source, consent and PII classification
2. Deduplication and difficulty/coverage annotation
3. Development/regression/hidden/red-team partitioning
4. Contamination and leakage detection
5. Version, retention, expiry and lineage governance

## Native acceptance corpus

- `ELMOS_AI_EVAL_DATASET_GOVERNOR-01` — schema and lineage
- `ELMOS_AI_EVAL_DATASET_GOVERNOR-02` — consent enforcement
- `ELMOS_AI_EVAL_DATASET_GOVERNOR-03` — cross-split duplicate detection
- `ELMOS_AI_EVAL_DATASET_GOVERNOR-04` — holdout access denial
- `ELMOS_AI_EVAL_DATASET_GOVERNOR-05` — PII redaction
- `ELMOS_AI_EVAL_DATASET_GOVERNOR-06` — expired dataset block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
