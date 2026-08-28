# Implementation Guide — Peer Assessment and Witness Audit Controller

## Purpose

Implement and independently certify peer assessment and witness audit controller, including plan peer assessments, office reviews and witnessed evaluations, evaluate evaluator consistency, competence and application of scheme rules and record findings, corrective action and recognition decisions.

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

1. plan peer assessments, office reviews and witnessed evaluations
2. evaluate evaluator consistency, competence and application of scheme rules
3. record findings, corrective action and recognition decisions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_PEER_ASSESSMENT_WITNESS_AUDIT_CONTROLLER-01` — native scenario: plan peer assessments, office reviews and witnessed evaluations
- `ELMOS_PEER_ASSESSMENT_WITNESS_AUDIT_CONTROLLER-02` — native scenario: evaluate evaluator consistency, competence and application of scheme rules
- `ELMOS_PEER_ASSESSMENT_WITNESS_AUDIT_CONTROLLER-03` — native scenario: record findings, corrective action and recognition decisions
- `ELMOS_PEER_ASSESSMENT_WITNESS_AUDIT_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_PEER_ASSESSMENT_WITNESS_AUDIT_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
