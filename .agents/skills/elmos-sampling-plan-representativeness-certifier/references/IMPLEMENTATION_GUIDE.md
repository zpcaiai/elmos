# Implementation Guide — Sampling Plan and Representativeness Certifier

## Purpose

Implement and independently certify sampling plan and representativeness certifier, including define sampling frame, inclusion probabilities, strata and coverage targets, quantify selection, nonresponse, temporal and survivorship bias and verify sample supports the scope of inference claimed.

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

1. define sampling frame, inclusion probabilities, strata and coverage targets
2. quantify selection, nonresponse, temporal and survivorship bias
3. verify sample supports the scope of inference claimed
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_SAMPLING_PLAN_REPRESENTATIVENESS_CERTIFIER-01` — native scenario: define sampling frame, inclusion probabilities, strata and coverage targets
- `ELMOS_SAMPLING_PLAN_REPRESENTATIVENESS_CERTIFIER-02` — native scenario: quantify selection, nonresponse, temporal and survivorship bias
- `ELMOS_SAMPLING_PLAN_REPRESENTATIVENESS_CERTIFIER-03` — native scenario: verify sample supports the scope of inference claimed
- `ELMOS_SAMPLING_PLAN_REPRESENTATIVENESS_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_SAMPLING_PLAN_REPRESENTATIVENESS_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
