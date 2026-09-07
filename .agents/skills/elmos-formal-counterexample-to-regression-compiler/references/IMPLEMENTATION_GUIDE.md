# Implementation Guide — Formal Counterexample-to-Regression Compiler

## Purpose

Translate solver and model-checker traces into deterministic unit, integration, concurrency and fault tests with exact assumptions.

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

1. parse verifier-specific counterexamples
2. map symbolic values and schedules to fixtures
3. preserve minimal causal sequence
4. generate target-language and runtime tests
5. verify the test fails before and passes after repair

## Native acceptance corpus

- `ELMOS_FORMAL_COUNTEREXAMPLE_TO_REGRESSION_COMPILER-01` — native scenario: parse verifier-specific counterexamples
- `ELMOS_FORMAL_COUNTEREXAMPLE_TO_REGRESSION_COMPILER-02` — native scenario: map symbolic values and schedules to fixtures
- `ELMOS_FORMAL_COUNTEREXAMPLE_TO_REGRESSION_COMPILER-03` — native scenario: preserve minimal causal sequence
- `ELMOS_FORMAL_COUNTEREXAMPLE_TO_REGRESSION_COMPILER-04` — native scenario: generate target-language and runtime tests
- `ELMOS_FORMAL_COUNTEREXAMPLE_TO_REGRESSION_COMPILER-05` — native scenario: verify the test fails before and passes after repair

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
