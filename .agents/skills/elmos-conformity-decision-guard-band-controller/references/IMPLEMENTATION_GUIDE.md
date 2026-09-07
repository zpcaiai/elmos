# Implementation Guide — Conformity Decision Rule and Guard-Band Controller

## Purpose

Implement and independently certify conformity decision rule and guard-band controller, including compile acceptance limits, guard bands and consumer/producer risk, apply pass, fail, indeterminate and retest decisions consistently and bind decision rule to contract before measurement is observed.

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

1. compile acceptance limits, guard bands and consumer/producer risk
2. apply pass, fail, indeterminate and retest decisions consistently
3. bind decision rule to contract before measurement is observed
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CONFORMITY_DECISION_GUARD_BAND_CONTROLLER-01` — native scenario: compile acceptance limits, guard bands and consumer/producer risk
- `ELMOS_CONFORMITY_DECISION_GUARD_BAND_CONTROLLER-02` — native scenario: apply pass, fail, indeterminate and retest decisions consistently
- `ELMOS_CONFORMITY_DECISION_GUARD_BAND_CONTROLLER-03` — native scenario: bind decision rule to contract before measurement is observed
- `ELMOS_CONFORMITY_DECISION_GUARD_BAND_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CONFORMITY_DECISION_GUARD_BAND_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
