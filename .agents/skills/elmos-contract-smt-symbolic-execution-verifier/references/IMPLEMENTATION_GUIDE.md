# Implementation Guide — Contract SMT and Symbolic Execution Verifier

## Purpose

Verify data, authorization, transformation and routine contracts with SMT and symbolic execution under explicit path and resource bounds.

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

1. encode pre/postconditions and invariants
2. symbolically execute critical paths and routines
3. solve numeric, null, time and authorization constraints
4. report path coverage and unknowns
5. validate candidate transformation instances

## Native acceptance corpus

- `ELMOS_CONTRACT_SMT_SYMBOLIC_EXECUTION_VERIFIER-01` — native scenario: encode pre/postconditions and invariants
- `ELMOS_CONTRACT_SMT_SYMBOLIC_EXECUTION_VERIFIER-02` — native scenario: symbolically execute critical paths and routines
- `ELMOS_CONTRACT_SMT_SYMBOLIC_EXECUTION_VERIFIER-03` — native scenario: solve numeric, null, time and authorization constraints
- `ELMOS_CONTRACT_SMT_SYMBOLIC_EXECUTION_VERIFIER-04` — native scenario: report path coverage and unknowns
- `ELMOS_CONTRACT_SMT_SYMBOLIC_EXECUTION_VERIFIER-05` — native scenario: validate candidate transformation instances

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
