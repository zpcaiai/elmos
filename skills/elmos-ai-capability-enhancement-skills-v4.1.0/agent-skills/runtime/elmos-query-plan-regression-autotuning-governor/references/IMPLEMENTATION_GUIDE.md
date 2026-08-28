# Implementation Guide — Query Plan Regression and Autotuning Governor

## Purpose

Detect plan regressions and propose bounded statistics, index, partition or query changes under proof, rollback and workload constraints.

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

1. capture normalized plan fingerprints
2. detect cardinality and statistics sensitivity
3. simulate bounded index/query alternatives
4. shadow candidate plans on representative workload
5. promote only with correctness and rollback evidence

## Native acceptance corpus

- `ELMOS_QUERY_PLAN_REGRESSION_AUTOTUNING_GOVERNOR-01` — native scenario: capture normalized plan fingerprints
- `ELMOS_QUERY_PLAN_REGRESSION_AUTOTUNING_GOVERNOR-02` — native scenario: detect cardinality and statistics sensitivity
- `ELMOS_QUERY_PLAN_REGRESSION_AUTOTUNING_GOVERNOR-03` — native scenario: simulate bounded index/query alternatives
- `ELMOS_QUERY_PLAN_REGRESSION_AUTOTUNING_GOVERNOR-04` — native scenario: shadow candidate plans on representative workload
- `ELMOS_QUERY_PLAN_REGRESSION_AUTOTUNING_GOVERNOR-05` — native scenario: promote only with correctness and rollback evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
