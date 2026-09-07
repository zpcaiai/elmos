# Implementation Guide — SMT Solver Trust-but-Verify Controller

## Purpose

Implement and independently certify smt solver trust-but-verify controller, including capture SMT-LIB problem, logic, options, proof or unsat core and solver digest, replay critical unsat claims with proof checker or diverse solver and detect unknown, timeout, inconsistent and nonstandard-theory results.

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

1. capture SMT-LIB problem, logic, options, proof or unsat core and solver digest
2. replay critical unsat claims with proof checker or diverse solver
3. detect unknown, timeout, inconsistent and nonstandard-theory results
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_SMT_SOLVER_TRUST_BUT_VERIFY_CONTROLLER-01` — native scenario: capture SMT-LIB problem, logic, options, proof or unsat core and solver digest
- `ELMOS_SMT_SOLVER_TRUST_BUT_VERIFY_CONTROLLER-02` — native scenario: replay critical unsat claims with proof checker or diverse solver
- `ELMOS_SMT_SOLVER_TRUST_BUT_VERIFY_CONTROLLER-03` — native scenario: detect unknown, timeout, inconsistent and nonstandard-theory results
- `ELMOS_SMT_SOLVER_TRUST_BUT_VERIFY_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_SMT_SOLVER_TRUST_BUT_VERIFY_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
