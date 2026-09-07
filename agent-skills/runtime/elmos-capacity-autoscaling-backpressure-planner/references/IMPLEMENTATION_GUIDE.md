# Implementation Guide — Capacity, Autoscaling and Backpressure Planner

## Purpose

Plan end-to-end queues, concurrency, rate limits, autoscaling, load shedding and admission control across agents, tools, stores and models.

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

1. build queueing and dependency capacity model
2. set per-tenant concurrency and rate limits
3. coordinate scale signals and cooldown
4. propagate backpressure and cancellation
5. verify overload degradation and recovery

## Native acceptance corpus

- `ELMOS_CAPACITY_AUTOSCALING_BACKPRESSURE_PLANNER-01` — native scenario: build queueing and dependency capacity model
- `ELMOS_CAPACITY_AUTOSCALING_BACKPRESSURE_PLANNER-02` — native scenario: set per-tenant concurrency and rate limits
- `ELMOS_CAPACITY_AUTOSCALING_BACKPRESSURE_PLANNER-03` — native scenario: coordinate scale signals and cooldown
- `ELMOS_CAPACITY_AUTOSCALING_BACKPRESSURE_PLANNER-04` — native scenario: propagate backpressure and cancellation
- `ELMOS_CAPACITY_AUTOSCALING_BACKPRESSURE_PLANNER-05` — native scenario: verify overload degradation and recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
