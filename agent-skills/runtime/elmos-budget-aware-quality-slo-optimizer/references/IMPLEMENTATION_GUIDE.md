# Implementation Guide — Budget-Aware Quality and SLO Optimizer

## Purpose

Select model, test, retrieval, cache and infrastructure plans that maximize verified quality under hard cost, latency, risk and residency constraints.

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

1. compile hard and soft objective envelope
2. solve multi-objective plan with mandatory gates
3. reserve uncertainty and incident budget
4. shadow candidate plan and compare
5. prevent optimization from weakening certification claims

## Native acceptance corpus

- `ELMOS_BUDGET_AWARE_QUALITY_SLO_OPTIMIZER-01` — native scenario: compile hard and soft objective envelope
- `ELMOS_BUDGET_AWARE_QUALITY_SLO_OPTIMIZER-02` — native scenario: solve multi-objective plan with mandatory gates
- `ELMOS_BUDGET_AWARE_QUALITY_SLO_OPTIMIZER-03` — native scenario: reserve uncertainty and incident budget
- `ELMOS_BUDGET_AWARE_QUALITY_SLO_OPTIMIZER-04` — native scenario: shadow candidate plan and compare
- `ELMOS_BUDGET_AWARE_QUALITY_SLO_OPTIMIZER-05` — native scenario: prevent optimization from weakening certification claims

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
