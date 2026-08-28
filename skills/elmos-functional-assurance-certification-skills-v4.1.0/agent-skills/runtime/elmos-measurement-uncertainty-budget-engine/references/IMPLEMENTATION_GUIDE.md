# Implementation Guide — Measurement Uncertainty Budget Engine

## Purpose

Implement and independently certify measurement uncertainty budget engine, including combine Type A and Type B uncertainty components with covariance, support analytic, bootstrap, Bayesian and Monte Carlo propagation and report standard, expanded and interval uncertainty with assumptions.

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

1. combine Type A and Type B uncertainty components with covariance
2. support analytic, bootstrap, Bayesian and Monte Carlo propagation
3. report standard, expanded and interval uncertainty with assumptions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MEASUREMENT_UNCERTAINTY_BUDGET_ENGINE-01` — native scenario: combine Type A and Type B uncertainty components with covariance
- `ELMOS_MEASUREMENT_UNCERTAINTY_BUDGET_ENGINE-02` — native scenario: support analytic, bootstrap, Bayesian and Monte Carlo propagation
- `ELMOS_MEASUREMENT_UNCERTAINTY_BUDGET_ENGINE-03` — native scenario: report standard, expanded and interval uncertainty with assumptions
- `ELMOS_MEASUREMENT_UNCERTAINTY_BUDGET_ENGINE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MEASUREMENT_UNCERTAINTY_BUDGET_ENGINE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
