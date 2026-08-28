# Implementation Guide — GPU and Accelerator Capacity Scheduler

## Purpose

Schedule heterogeneous GPUs/NPUs, model replicas, batching and preemption under memory, topology, fairness, SLO and cost constraints.

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

1. model accelerator capabilities and topology
2. bin-pack models with memory/KV constraints
3. reserve critical tenant capacity
4. coordinate preemption and warm pools
5. forecast queue, cost and scale-up delay

## Native acceptance corpus

- `ELMOS_GPU_ACCELERATOR_CAPACITY_SCHEDULER-01` — native scenario: model accelerator capabilities and topology
- `ELMOS_GPU_ACCELERATOR_CAPACITY_SCHEDULER-02` — native scenario: bin-pack models with memory/KV constraints
- `ELMOS_GPU_ACCELERATOR_CAPACITY_SCHEDULER-03` — native scenario: reserve critical tenant capacity
- `ELMOS_GPU_ACCELERATOR_CAPACITY_SCHEDULER-04` — native scenario: coordinate preemption and warm pools
- `ELMOS_GPU_ACCELERATOR_CAPACITY_SCHEDULER-05` — native scenario: forecast queue, cost and scale-up delay

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
