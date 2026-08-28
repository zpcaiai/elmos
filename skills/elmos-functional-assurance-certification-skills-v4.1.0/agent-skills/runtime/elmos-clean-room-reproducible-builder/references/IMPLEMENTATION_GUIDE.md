# Implementation Guide — Clean-Room Reproducible Builder

## Purpose

Rebuild release candidates in an isolated certification environment from frozen source, lockfiles and declared inputs, producing independent artifact and provenance evidence.

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

1. Use fresh isolated builder identity and workspace
2. Fetch only declared content-addressed inputs
3. Capture complete source/build provenance
4. Compare independently rebuilt artifacts
5. Block unexplained binary differences

## Native acceptance corpus

- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-01` — offline/hermetic rebuild
- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-02` — source provenance verification
- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-03` — dependency lock enforcement
- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-04` — binary reproducibility
- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-05` — builder compromise simulation
- `ELMOS_CLEAN_ROOM_REPRODUCIBLE_BUILDER-06` — unexplained difference blocks

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
