# Implementation Guide — Backward-Compatible Regeneration and Merge Controller

## Purpose

Regenerate projects after requirement/template/framework changes using semantic three-way merge, user-region ownership and compatibility gates.

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

1. diff prior IR, target profile and generated tree
2. classify generated, user and shared ownership
3. perform semantic merge with conflict artifacts
4. run compatibility and migration tests
5. retain rollback revision and evidence

## Native acceptance corpus

- `ELMOS_BACKWARD_COMPATIBLE_REGENERATION_MERGE_CONTROLLER-01` — native scenario: diff prior IR, target profile and generated tree
- `ELMOS_BACKWARD_COMPATIBLE_REGENERATION_MERGE_CONTROLLER-02` — native scenario: classify generated, user and shared ownership
- `ELMOS_BACKWARD_COMPATIBLE_REGENERATION_MERGE_CONTROLLER-03` — native scenario: perform semantic merge with conflict artifacts
- `ELMOS_BACKWARD_COMPATIBLE_REGENERATION_MERGE_CONTROLLER-04` — native scenario: run compatibility and migration tests
- `ELMOS_BACKWARD_COMPATIBLE_REGENERATION_MERGE_CONTROLLER-05` — native scenario: retain rollback revision and evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
