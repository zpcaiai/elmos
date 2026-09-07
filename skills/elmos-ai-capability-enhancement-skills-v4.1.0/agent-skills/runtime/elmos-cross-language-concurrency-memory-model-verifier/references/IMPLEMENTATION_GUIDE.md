# Implementation Guide — Cross-Language Concurrency and Memory-Model Verifier

## Purpose

Verify that generated or migrated code preserves happens-before, atomicity, cancellation, scheduling and shared-state invariants across incompatible language runtimes.

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

1. compare JMM, .NET, ECMAScript, Go and Rust ordering semantics
2. exercise data-race and lost-update litmus tests
3. verify async cancellation and structured-concurrency propagation
4. check lock-free atomic and visibility mappings
5. derive bounded runtime monitors for unprovable schedules

## Native acceptance corpus

- `ELMOS_CROSS_LANGUAGE_CONCURRENCY_MEMORY_MODEL_VERIFIER-01` — native scenario: compare JMM, .NET, ECMAScript, Go and Rust ordering semantics
- `ELMOS_CROSS_LANGUAGE_CONCURRENCY_MEMORY_MODEL_VERIFIER-02` — native scenario: exercise data-race and lost-update litmus tests
- `ELMOS_CROSS_LANGUAGE_CONCURRENCY_MEMORY_MODEL_VERIFIER-03` — native scenario: verify async cancellation and structured-concurrency propagation
- `ELMOS_CROSS_LANGUAGE_CONCURRENCY_MEMORY_MODEL_VERIFIER-04` — native scenario: check lock-free atomic and visibility mappings
- `ELMOS_CROSS_LANGUAGE_CONCURRENCY_MEMORY_MODEL_VERIFIER-05` — native scenario: derive bounded runtime monitors for unprovable schedules

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
