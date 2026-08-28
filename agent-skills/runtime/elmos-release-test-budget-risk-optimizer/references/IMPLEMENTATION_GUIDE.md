# Implementation Guide — Release Test Budget and Risk Optimizer

## Purpose

Select PR, nightly, release and certification suites under wall-clock and cost budgets while preserving mandatory critical obligations.

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

1. score change impact, criticality and evidence freshness
2. reserve mandatory proof and security tests
3. optimize covering array and historical regression set
4. forecast wall-clock and resource cost
5. explain excluded tests and residual risk

## Native acceptance corpus

- `ELMOS_RELEASE_TEST_BUDGET_RISK_OPTIMIZER-01` — native scenario: score change impact, criticality and evidence freshness
- `ELMOS_RELEASE_TEST_BUDGET_RISK_OPTIMIZER-02` — native scenario: reserve mandatory proof and security tests
- `ELMOS_RELEASE_TEST_BUDGET_RISK_OPTIMIZER-03` — native scenario: optimize covering array and historical regression set
- `ELMOS_RELEASE_TEST_BUDGET_RISK_OPTIMIZER-04` — native scenario: forecast wall-clock and resource cost
- `ELMOS_RELEASE_TEST_BUDGET_RISK_OPTIMIZER-05` — native scenario: explain excluded tests and residual risk

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
