# Implementation Guide — Model Routing Quality, Cost and Latency Optimizer

## Purpose

Optimize model/provider routing under quality, safety, latency, residency, quota and cost constraints with shadow evidence and bounded fallback.

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

1. fit task-conditioned quality and latency models
2. solve constrained route selection
3. reserve safe fallback and circuit breakers
4. evaluate paired shadow traffic
5. retrain only from governed evidence

## Native acceptance corpus

- `ELMOS_MODEL_ROUTING_QUALITY_COST_LATENCY_OPTIMIZER-01` — native scenario: fit task-conditioned quality and latency models
- `ELMOS_MODEL_ROUTING_QUALITY_COST_LATENCY_OPTIMIZER-02` — native scenario: solve constrained route selection
- `ELMOS_MODEL_ROUTING_QUALITY_COST_LATENCY_OPTIMIZER-03` — native scenario: reserve safe fallback and circuit breakers
- `ELMOS_MODEL_ROUTING_QUALITY_COST_LATENCY_OPTIMIZER-04` — native scenario: evaluate paired shadow traffic
- `ELMOS_MODEL_ROUTING_QUALITY_COST_LATENCY_OPTIMIZER-05` — native scenario: retrain only from governed evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
