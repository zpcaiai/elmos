# Implementation Guide — Proof-Carrying Artifact Compiler

## Purpose

Implement and independently certify proof-carrying artifact compiler, including package artifact, specification, proof object, checker, assumptions and environment digest, bind proof to exact executable or generated repository revision and enable small independent checker validation without trusting producer.

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

1. package artifact, specification, proof object, checker, assumptions and environment digest
2. bind proof to exact executable or generated repository revision
3. enable small independent checker validation without trusting producer
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_PROOF_CARRYING_ARTIFACT_COMPILER-01` — native scenario: package artifact, specification, proof object, checker, assumptions and environment digest
- `ELMOS_PROOF_CARRYING_ARTIFACT_COMPILER-02` — native scenario: bind proof to exact executable or generated repository revision
- `ELMOS_PROOF_CARRYING_ARTIFACT_COMPILER-03` — native scenario: enable small independent checker validation without trusting producer
- `ELMOS_PROOF_CARRYING_ARTIFACT_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_PROOF_CARRYING_ARTIFACT_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
