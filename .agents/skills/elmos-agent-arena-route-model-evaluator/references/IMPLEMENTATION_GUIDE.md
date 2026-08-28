# Implementation Guide — Agent Arena Route and Model Evaluator

## Purpose

Run controlled multi-agent/model/route competitions on hidden tasks using independent oracles, cost, safety and reproducibility evidence.

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

1. define blinded competitors and resource budgets
2. execute repeated hidden task trials
3. score correctness, safety, cost and latency
4. estimate uncertainty and task-conditioned fit
5. update route registry without global winner claims

## Native acceptance corpus

- `ELMOS_AGENT_ARENA_ROUTE_MODEL_EVALUATOR-01` — native scenario: define blinded competitors and resource budgets
- `ELMOS_AGENT_ARENA_ROUTE_MODEL_EVALUATOR-02` — native scenario: execute repeated hidden task trials
- `ELMOS_AGENT_ARENA_ROUTE_MODEL_EVALUATOR-03` — native scenario: score correctness, safety, cost and latency
- `ELMOS_AGENT_ARENA_ROUTE_MODEL_EVALUATOR-04` — native scenario: estimate uncertainty and task-conditioned fit
- `ELMOS_AGENT_ARENA_ROUTE_MODEL_EVALUATOR-05` — native scenario: update route registry without global winner claims

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
