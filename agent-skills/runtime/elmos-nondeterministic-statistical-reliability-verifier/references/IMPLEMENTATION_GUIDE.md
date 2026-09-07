# Implementation Guide — Nondeterministic Statistical Reliability Verifier

## Purpose

Estimate success, failure, flake and quality distributions for agents and distributed systems using repeated trials, confidence bounds and sequential tests.

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

1. define trial independence and seed strategy
2. estimate confidence intervals and tail failure rates
3. run sequential stopping with error control
4. separate infrastructure flake from behavior variance
5. block underpowered production claims

## Native acceptance corpus

- `ELMOS_NONDETERMINISTIC_STATISTICAL_RELIABILITY_VERIFIER-01` — native scenario: define trial independence and seed strategy
- `ELMOS_NONDETERMINISTIC_STATISTICAL_RELIABILITY_VERIFIER-02` — native scenario: estimate confidence intervals and tail failure rates
- `ELMOS_NONDETERMINISTIC_STATISTICAL_RELIABILITY_VERIFIER-03` — native scenario: run sequential stopping with error control
- `ELMOS_NONDETERMINISTIC_STATISTICAL_RELIABILITY_VERIFIER-04` — native scenario: separate infrastructure flake from behavior variance
- `ELMOS_NONDETERMINISTIC_STATISTICAL_RELIABILITY_VERIFIER-05` — native scenario: block underpowered production claims

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
