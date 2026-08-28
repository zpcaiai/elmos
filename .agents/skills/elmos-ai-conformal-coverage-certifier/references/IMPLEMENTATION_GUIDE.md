# Implementation Guide — Conformal Coverage Certifier

## Purpose

Implement and independently certify conformal coverage certifier, including construct prediction sets or intervals with declared exchangeability assumptions, measure marginal and subgroup conditional coverage and monitor coverage degradation and recalibrate under drift.

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

1. construct prediction sets or intervals with declared exchangeability assumptions
2. measure marginal and subgroup conditional coverage
3. monitor coverage degradation and recalibrate under drift
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_CONFORMAL_COVERAGE_CERTIFIER-01` — native scenario: construct prediction sets or intervals with declared exchangeability assumptions
- `ELMOS_AI_CONFORMAL_COVERAGE_CERTIFIER-02` — native scenario: measure marginal and subgroup conditional coverage
- `ELMOS_AI_CONFORMAL_COVERAGE_CERTIFIER-03` — native scenario: monitor coverage degradation and recalibrate under drift
- `ELMOS_AI_CONFORMAL_COVERAGE_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_CONFORMAL_COVERAGE_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
