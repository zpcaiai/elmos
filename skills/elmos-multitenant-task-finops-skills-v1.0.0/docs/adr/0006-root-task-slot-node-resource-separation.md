# ADR-0006 — Separate root-task slots from node resource concurrency

## Status
Accepted.

## Context
One root task may fan out into many nodes, and three heavy tasks can still overload the platform.

## Decision
The account limit counts only root tasks. Internal nodes are constrained by task queues, worker limits, per-task fan-out, tenant resource units, provider budgets, and platform capacity.

## Consequences
- Product concurrency remains simple and predictable.
- Scheduler/capacity controls remain necessary.
- Task and node metrics must be reported separately.
