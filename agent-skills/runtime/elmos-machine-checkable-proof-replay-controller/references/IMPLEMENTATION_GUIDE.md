# Implementation Guide — Machine-Checkable Proof Replay Controller

## Purpose

Implement and independently certify machine-checkable proof replay controller, including replay theorem, SMT, model-checking and proof-assistant artifacts in clean room, pin solver, library, logic, resource bounds and proof checker digests and classify proof rot, timeout, unsupported and semantic drift.

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

1. replay theorem, SMT, model-checking and proof-assistant artifacts in clean room
2. pin solver, library, logic, resource bounds and proof checker digests
3. classify proof rot, timeout, unsupported and semantic drift
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MACHINE_CHECKABLE_PROOF_REPLAY_CONTROLLER-01` — native scenario: replay theorem, SMT, model-checking and proof-assistant artifacts in clean room
- `ELMOS_MACHINE_CHECKABLE_PROOF_REPLAY_CONTROLLER-02` — native scenario: pin solver, library, logic, resource bounds and proof checker digests
- `ELMOS_MACHINE_CHECKABLE_PROOF_REPLAY_CONTROLLER-03` — native scenario: classify proof rot, timeout, unsupported and semantic drift
- `ELMOS_MACHINE_CHECKABLE_PROOF_REPLAY_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MACHINE_CHECKABLE_PROOF_REPLAY_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
