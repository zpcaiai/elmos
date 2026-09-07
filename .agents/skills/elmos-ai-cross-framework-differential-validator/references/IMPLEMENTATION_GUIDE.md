# Implementation Guide — AICrossFrameworkDifferentialValidator

## Purpose

Compare source and target or multiple generated targets by typed observations, partial-order trace constraints, state invariants, side effects, grounding and tolerances.

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

1. Negotiate exact target profile
2. Emit complete native project and extension artifacts
3. Run native import/build/start/load tests
4. Generate deployment, operations and evidence hooks
5. Preserve unsupported features in a ledger

## Native acceptance corpus

- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-01` — positive proof
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-02` — counterexample
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-03` — unknown verifier
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-04` — AiCrossFrameworkDifferentialValidator representative end-to-end fixture
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-07` — undeclared authority is denied
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-08` — resource and wall-clock budget is measured
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-09` — minimal native project
- `ELMOS_AI_CROSS_FRAMEWORK_DIFFERENTIAL_VALIDATOR-10` — representative production fixture

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
