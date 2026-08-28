# Implementation Guide — Formal Proof Maintenance and Drift Recertifier

## Purpose

Implement and independently certify formal proof maintenance and drift recertifier, including compute proof dependency graph for code, model, library, solver and assumption changes, reuse only unaffected proof nodes with exact validity evidence and schedule incremental replay and full periodic clean-room verification.

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

1. compute proof dependency graph for code, model, library, solver and assumption changes
2. reuse only unaffected proof nodes with exact validity evidence
3. schedule incremental replay and full periodic clean-room verification
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_FORMAL_PROOF_MAINTENANCE_DRIFT_RECERTIFIER-01` — native scenario: compute proof dependency graph for code, model, library, solver and assumption changes
- `ELMOS_FORMAL_PROOF_MAINTENANCE_DRIFT_RECERTIFIER-02` — native scenario: reuse only unaffected proof nodes with exact validity evidence
- `ELMOS_FORMAL_PROOF_MAINTENANCE_DRIFT_RECERTIFIER-03` — native scenario: schedule incremental replay and full periodic clean-room verification
- `ELMOS_FORMAL_PROOF_MAINTENANCE_DRIFT_RECERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_FORMAL_PROOF_MAINTENANCE_DRIFT_RECERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
