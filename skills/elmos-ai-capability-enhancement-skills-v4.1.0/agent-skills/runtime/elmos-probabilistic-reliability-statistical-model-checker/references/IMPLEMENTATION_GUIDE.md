# Implementation Guide — Probabilistic Reliability and Statistical Model Checker

## Purpose

Verify probabilistic availability, retry, queue, provider and agent success claims with stochastic models and simulation evidence.

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

1. construct Markov/queue/reliability model
2. estimate rare-event and tail probabilities
3. calibrate model against observed telemetry
4. run sensitivity and uncertainty analysis
5. bind bounded claims to operating envelope

## Native acceptance corpus

- `ELMOS_PROBABILISTIC_RELIABILITY_STATISTICAL_MODEL_CHECKER-01` — native scenario: construct Markov/queue/reliability model
- `ELMOS_PROBABILISTIC_RELIABILITY_STATISTICAL_MODEL_CHECKER-02` — native scenario: estimate rare-event and tail probabilities
- `ELMOS_PROBABILISTIC_RELIABILITY_STATISTICAL_MODEL_CHECKER-03` — native scenario: calibrate model against observed telemetry
- `ELMOS_PROBABILISTIC_RELIABILITY_STATISTICAL_MODEL_CHECKER-04` — native scenario: run sensitivity and uncertainty analysis
- `ELMOS_PROBABILISTIC_RELIABILITY_STATISTICAL_MODEL_CHECKER-05` — native scenario: bind bounded claims to operating envelope

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
