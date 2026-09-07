# Implementation Guide — Rare-Event and Tail-Risk Estimator

## Purpose

Implement and independently certify rare-event and tail-risk estimator, including estimate low-frequency severe failures using importance sampling, stress testing and extreme-value methods, bound uncertainty when zero failures are observed and combine scenario likelihood and consequence for certification decisions.

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

1. estimate low-frequency severe failures using importance sampling, stress testing and extreme-value methods
2. bound uncertainty when zero failures are observed
3. combine scenario likelihood and consequence for certification decisions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_RARE_EVENT_TAIL_RISK_ESTIMATOR-01` — native scenario: estimate low-frequency severe failures using importance sampling, stress testing and extreme-value methods
- `ELMOS_AI_RARE_EVENT_TAIL_RISK_ESTIMATOR-02` — native scenario: bound uncertainty when zero failures are observed
- `ELMOS_AI_RARE_EVENT_TAIL_RISK_ESTIMATOR-03` — native scenario: combine scenario likelihood and consequence for certification decisions
- `ELMOS_AI_RARE_EVENT_TAIL_RISK_ESTIMATOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_RARE_EVENT_TAIL_RISK_ESTIMATOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
