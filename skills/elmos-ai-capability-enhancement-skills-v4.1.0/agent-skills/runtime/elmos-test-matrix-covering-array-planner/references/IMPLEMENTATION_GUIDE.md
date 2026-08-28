# Implementation Guide — Test Matrix Covering Array Planner

## Purpose

Select risk-weighted PR, nightly, release and certification matrices across language, framework, database, provider, OS, architecture and deployment dimensions.

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

1. Enumerate exact matrix dimensions and constraints
2. Generate pairwise or higher-strength covering arrays
3. Force critical and historically failing combinations
4. Separate PR/nightly/release/soak profiles
5. Explain every omitted combination

## Native acceptance corpus

- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-01` — pairwise matrix
- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-02` — 3-way critical interaction
- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-03` — constraint-aware combinations
- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-04` — changed-route selection
- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-05` — historical incident inclusion
- `ELMOS_TEST_MATRIX_COVERING_ARRAY_PLANNER-06` — full release matrix

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
