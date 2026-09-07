# Implementation Guide — Proof-to-Validation DAG Compiler

## Purpose

Compile Proof Obligation Graphs into dependency-aware validation DAGs with verifier independence, fixtures, resource budgets, retries and evidence gates.

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

1. Map each claim to accepted evidence classes
2. Select independent verifier portfolios
3. Order prerequisites and shared fixtures
4. Allocate machine wall-clock and cost budgets
5. Represent BLOCKED/UNKNOWN explicitly

## Native acceptance corpus

- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-01` — acyclic DAG generation
- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-02` — critical verifier missing blocks
- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-03` — parallel independent verifiers
- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-04` — fixture dependency ordering
- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-05` — resource budget exhaustion
- `ELMOS_PROOF_TO_VALIDATION_DAG_COMPILER-06` — incremental DAG after change

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
